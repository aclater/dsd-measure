"""The null test: align two decoders' outputs, subtract, and measure what is left.

Everything runs in blocks of about two million samples, so memory use does not depend on the
length of the track. Two passes per pair: the first aligns and measures the gain and correlation,
the second subtracts and accumulates levels, per-second levels, band spectra and the peak.
"""

import struct
from dataclasses import dataclass
from math import ceil, log2

import numpy as np
from scipy import signal

from ..dsdstream import DsdFile
from .align import FRAC_HALF, estimate_delay, shifted
from .tracks import ResampledTrack

BLOCK = 1 << 21
FLOOR_DB = -400.0  # reported when a level is exactly zero
IDENTICAL_DEPTH_DB = 300.0  # beyond this the difference is floating-point rounding


@dataclass
class Options:
    trim_start: float = 0.5  # seconds cut at the start (decoder start-up transients)
    trim_end: float = 0.5
    start: float = 0.0  # analyse from this time in the file
    duration: float | None = None
    rate: int | None = None  # common rate; default the lower of the two
    max_delay: float = 0.5  # seconds searched either way
    polarity: str = "auto"  # auto | keep
    gain: str = "match"  # match | none
    channels: tuple | None = None
    diff_wav: bool = False
    diff_gain_db: float = 0.0  # gain applied to the difference WAV only
    band_hz: float = 20000.0  # top of the in-band depth; bands above are ultrasonic


def db(x):
    return FLOOR_DB if x <= 0 else max(FLOOR_DB, 10 * np.log10(x))


def third_octave_bands(fmax, fmin=17.0):
    """(centre, low, high) of third-octave bands from about 20 Hz whose upper edge is below ``fmax``."""
    out, n = [], -17
    while True:
        c = 1000.0 * 2 ** (n / 3)
        lo, hi = c * 2 ** (-1 / 6), c * 2 ** (1 / 6)
        if hi > fmax:
            break
        if lo >= fmin:
            out.append((c, lo, hi))
        n += 1
    return out


class _Psd:
    """Averaged one-sided power per bin; band sums add up to the signal's mean square."""

    def __init__(self, nfft):
        self.nfft, self.hop = nfft, nfft // 2
        self.win = signal.windows.hann(nfft, sym=False)
        self.acc, self.frames = np.zeros(nfft // 2 + 1), 0

    def add(self, x):
        nf = (len(x) - self.nfft) // self.hop + 1
        if nf <= 0:
            return
        fr = np.lib.stride_tricks.sliding_window_view(x, self.nfft)[:: self.hop][:nf]
        p = np.abs(np.fft.rfft(fr * self.win, axis=1)) ** 2
        self.acc += p.sum(axis=0)
        self.frames += nf

    def power(self):
        p = self.acc / max(self.frames, 1) / (self.nfft * np.sum(self.win ** 2))
        p[1:-1] *= 2
        return p


class _Channel:
    def __init__(self, ch, al, nfft):
        self.ch, self.al = ch, al
        self.aa = self.ab = self.bb = 0.0
        self.dd = self.peak_d = self.peak_a = self.energy_a = 0.0
        self.n = 0
        self.sec_a, self.sec_d, self.sec_n = {}, {}, {}
        self.pa, self.pd = _Psd(nfft), _Psd(nfft)


def _add_seconds(store, idx0, rate, x2):
    sec = (idx0 + np.arange(len(x2))) // rate
    base = int(sec[0])
    sums = np.bincount(sec - base, weights=x2)
    cnts = np.bincount(sec - base)
    for i, (s, c) in enumerate(zip(sums, cnts, strict=True)):
        if c:
            store.setdefault(base + i, [0.0, 0])
            store[base + i][0] += float(s)
            store[base + i][1] += int(c)


def _write_wav_header(f, channels, rate, frames):
    raw = frames * channels * 4
    f.write(b"RIFF" + struct.pack("<I", 36 + raw) + b"WAVE")
    f.write(b"fmt " + struct.pack("<IHHIIHH", 16, 3, channels, rate, rate * channels * 4, channels * 4, 32))
    f.write(b"data" + struct.pack("<I", raw))


def common_rate(ra, rb, requested=None):
    fc = int(requested) if requested else min(ra, rb)
    if fc > min(ra, rb):
        raise ValueError(f"common rate {fc} Hz is above a device's rate ({ra} and {rb} Hz); resampling up adds no "
                         f"information and is refused. Use {min(ra, rb)} Hz or lower")
    return fc


def compare(track_a, track_b, opts, diff_wav_path=None, log=lambda *_: None):
    """Compare two tracks (any rates). Returns a dict of results; see ``docs/user-guide.md``."""
    if track_a.channels != track_b.channels:
        raise ValueError(f"the devices gave {track_a.channels} and {track_b.channels} channels; "
                         "the null test needs the same layout")
    fc = common_rate(track_a.rate, track_b.rate, opts.rate)
    resampled = {}
    if track_a.rate != fc:
        track_a, resampled["A"] = ResampledTrack(track_a, fc), (track_a.rate, fc)
    if track_b.rate != fc:
        track_b, resampled["B"] = ResampledTrack(track_b, fc), (track_b.rate, fc)
    chans = list(opts.channels) if opts.channels else list(range(track_a.channels))
    length = min(track_a.length, track_b.length)
    n0 = int(round(max(opts.start, opts.trim_start) * fc))
    n1 = length - int(round(opts.trim_end * fc))
    if opts.duration is not None:
        n1 = min(n1, int(round((opts.start + opts.duration) * fc)))
    fmax = 0.45 * fc
    bands = []
    for c, lo, hi in third_octave_bands(fmax):
        if lo < opts.band_hz < hi:
            # the band that holds the top of the verdict is cut at exactly 20 kHz: the part below counts
            # towards the verdict, the part above is ultrasonic
            bands += [(float(np.sqrt(lo * opts.band_hz)), lo, opts.band_hz), (float(np.sqrt(opts.band_hz * hi)), opts.band_hz, hi)]
        else:
            bands.append((c, lo, hi))
    nfft = max(1 << 15, 1 << int(round(log2(0.75 * fc))))
    hop = nfft // 2
    block = ceil(BLOCK / hop) * hop

    # 1. delay and polarity per channel
    states = []
    for c in chans:
        log(f"  channel {c}: estimating delay")
        est = estimate_delay(track_a, track_b, c, n0, n1, fc, opts.max_delay)
        states.append(_Channel(c, est, nfft))
    d_max, d_min = max(s.al["delay_samples"] for s in states), min(s.al["delay_samples"] for s in states)
    # keep every read inside both tracks
    n0 = max(n0, FRAC_HALF + 1 - int(np.floor(d_min)))
    n1 = min(n1, track_a.length, track_b.length - int(np.ceil(d_max)) - FRAC_HALF - 1)
    if n1 - n0 < 4 * nfft:
        raise ValueError("too little audio is left after trimming and alignment; reduce --trim-start/--trim-end")
    total = n1 - n0

    def blocks():
        s = n0
        while s < n1:
            e = min(s + block, n1)
            yield s, e
            s = e

    # 2. pass one: gain and correlation, in the audio band only (devices may differ above it)
    log(f"  pass 1 of 2: gain and correlation ({total / fc:.1f} s at {fc} Hz)")
    gain_hi = min(opts.band_hz, fmax)
    win = signal.windows.hann(nfft, sym=False)
    sel = np.arange(nfft // 2 + 1) * fc / nfft <= gain_hi
    for s, e in blocks():
        for st in states:
            ext = min(e + hop, n1)
            a = track_a.read(st.ch, s, ext)
            b = shifted(track_b, st.ch, s, ext, st.al["delay_samples"])
            nf = (len(a) - nfft) // hop + 1
            if nf <= 0:
                continue
            fa = np.fft.rfft(np.lib.stride_tricks.sliding_window_view(a, nfft)[::hop][:nf] * win, axis=1)[:, sel]
            fb = np.fft.rfft(np.lib.stride_tricks.sliding_window_view(b, nfft)[::hop][:nf] * win, axis=1)[:, sel]
            st.aa += float(np.sum(np.abs(fa) ** 2))
            st.bb += float(np.sum(np.abs(fb) ** 2))
            st.ab += float(np.sum(np.real(fa * np.conj(fb))))
    for st in states:
        raw_sign = 1.0 if st.ab >= 0 else -1.0
        st.pol = raw_sign if opts.polarity == "auto" else 1.0
        st.corr_raw = st.ab / np.sqrt(st.aa * st.bb) if st.aa > 0 and st.bb > 0 else 0.0
        st.gain = (abs(st.ab) / st.bb) if opts.gain == "match" and st.bb > 0 else 1.0

    # 3. pass two: difference
    log("  pass 2 of 2: difference, levels and spectra")
    wavf = None
    if diff_wav_path:
        wavf = open(diff_wav_path, "wb")
        _write_wav_header(wavf, len(states), fc, total)
    wgain = 10 ** (opts.diff_gain_db / 20)
    try:
        for s, e in blocks():
            ds = []
            for st in states:
                ext = min(e + hop, n1)  # a little beyond the block so every hop gets a full frame
                a = track_a.read(st.ch, s, ext)
                b = shifted(track_b, st.ch, s, ext, st.al["delay_samples"])
                d = a - st.gain * st.pol * b
                m = e - s
                st.n += m
                st.dd += float(np.dot(d[:m], d[:m]))
                st.energy_a += float(np.dot(a[:m], a[:m]))
                st.peak_d = max(st.peak_d, float(np.max(np.abs(d[:m]))))
                st.peak_a = max(st.peak_a, float(np.max(np.abs(a[:m]))))
                _add_seconds(st.sec_a, s - n0, fc, a[:m] ** 2)
                _add_seconds(st.sec_d, s - n0, fc, d[:m] ** 2)
                st.pa.add(a)
                st.pd.add(d)
                ds.append(d[:m])
            if wavf:
                wavf.write((np.stack(ds, axis=1) * wgain).astype("<f4").tobytes())
    finally:
        if wavf:
            wavf.close()

    freqs = np.arange(nfft // 2 + 1) * fc / nfft
    out_ch = []
    for st in states:
        pa, pd = st.pa.power(), st.pd.power()
        brows = []
        for c, lo, hi in bands:
            sel = (freqs >= lo) & (freqs < hi)
            la, ld = db(float(pa[sel].sum())), db(float(pd[sel].sum()))
            brows.append({"centre_hz": round(c, 1), "low_hz": round(lo, 1), "high_hz": round(hi, 1),
                          "music_dbfs": la, "diff_dbfs": ld, "depth_db": la - ld,
                          "ultrasonic": bool(lo >= opts.band_hz)})
        secs = []
        for k in sorted(st.sec_a):
            sa, na = st.sec_a[k]
            sd, nd = st.sec_d[k]
            if na < 0.25 * fc:
                continue
            ra, rd = db(sa / na), db(sd / nd)
            secs.append({"t_s": k, "music_dbfs": ra, "diff_dbfs": rd, "depth_db": ra - rd})
        music, diff = db(st.energy_a / st.n), db(st.dd / st.n)
        out_ch.append({
            "channel": st.ch,
            "delay_samples": st.al["delay_samples"], "delay_us": st.al["delay_samples"] / fc * 1e6,
            "delay_spread_samples": st.al["spread_samples"], "delay_segments": st.al["segments"],
            "polarity_inverted": bool(st.pol < 0),
            "raw_correlation": st.corr_raw,
            "gain": st.gain, "gain_db": 20 * np.log10(abs(st.gain)) if st.gain else FLOOR_DB,
            "correlation": abs(st.corr_raw),
            "one_minus_correlation": float(1 - abs(st.corr_raw)),
            "music_rms_audio_dbfs": db(sum(10 ** (b["music_dbfs"] / 10) for b in brows if not b["ultrasonic"])),
            "diff_rms_audio_dbfs": db(sum(10 ** (b["diff_dbfs"] / 10) for b in brows if not b["ultrasonic"])),
            "music_rms_dbfs": music, "music_peak_dbfs": db(st.peak_a ** 2),
            "diff_rms_dbfs": diff, "diff_peak_dbfs": db(st.peak_d ** 2),
            "null_depth_db": music - diff,
            "identical": bool(st.dd <= 1e-30 * st.energy_a),
            "bands": brows, "seconds": secs,
        })
    return {"common_rate": fc, "resampled": resampled, "samples": total, "seconds": total / fc,
            "range_s": [n0 / fc, n1 / fc], "analysis_band_hz": fmax, "nfft": nfft,
            "bin_hz": fc / nfft, "channels": out_ch}


def source_info(path):
    f = DsdFile(path)
    return {"name": f.path.name, "format": f.kind.upper(), "dsd_rate": f.rate, "channels": f.channels,
            "seconds": f.samples / f.rate, "sha256": f.sha256()}
