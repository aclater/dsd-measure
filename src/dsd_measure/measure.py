"""The measurements of docs/footprint.md, run against one adapter.

``measure_device(adapter, profile)`` returns a result dict:
``{"metrics": {...}, "plots": {...}, "not_run": {...}, "notes": [...]}``. ``plots`` holds the
arrays that ``report`` draws; ``metrics`` is what goes into JSON and CSV.
"""

import time

import numpy as np
from scipy import signal

from . import analyse as an
from . import decode as dec
from . import signals as sg
from .levels import PEAK_DBFS, REF_DBFS

REF_FS = 352800
REF_NFFT = 2**18
DSD64 = 2822400


def rate_name(r):
    return f"DSD{int(r) // 44100 // 64 * 64}"

#: Duration profiles. ``quick`` is for a first look (minutes); ``full`` follows the footprint.
PROFILES = {
    "quick": dict(seg_s=1.5, step_db=6.0, fr_every=2, noise_s=6.0, mt_periods=3, imd_s=2.0,
                  hold_s=5.0, jtest_s=12.0, tone_s=2.0),
    "full": dict(seg_s=2.5, step_db=3.0, fr_every=1, noise_s=15.0, mt_periods=8, imd_s=4.0,
                 hold_s=60.0, jtest_s=24.0, tone_s=4.0),
}

THIRD_OCTAVE = [20, 25, 31.5, 40, 50, 63, 80, 100, 125, 160, 200, 250, 315, 400, 500, 630, 800, 1000,
                1250, 1600, 2000, 2500, 3150, 4000, 5000, 6300, 8000, 10000, 12500, 16000, 20000]
EXTRA_HF = [20500, 21000, 21500, 22000, 23000, 24000, 26000, 28000, 30000, 35000, 40000]


def nfft_for(fs, base=REF_NFFT):
    """FFT length with the same bin spacing as ``base`` points at 352.8 kHz."""
    n = base * fs / REF_FS
    return max(int(round(n)), 2**12)


class Chain:
    """Feeds a PCM signal through the device and returns analysable PCM."""

    def __init__(self, adapter, in_rate=88200):
        self.a = adapter
        self.in_rate = in_rate
        self.tag = None
        self.ntf = {}  # reference modulator design used per call (class A), for provenance

    @property
    def dsd_rate(self):
        return self.a.dsd_rate

    def run(self, x, tag, in_rate=None, decode_rate=REF_FS):
        """Class A: PCM -> reference modulator -> device. Class B: PCM -> device -> reference decoder.

        ``x`` is mono (1-D) or stereo (2 x n); the result has the same shape.
        """
        from . import encode as enc
        r = in_rate or self.in_rate
        if hasattr(self.a, "current"):
            self.a.current = tag
        x = np.asarray(x)
        chans = x if x.ndim == 2 else x[None]
        if self.a.klass == "A":
            bl = []
            for c in chans:
                b, info = enc.encode(c, r, self.dsd_rate)
                bl.append(b)
                self.ntf[tag] = {"ntf": info["ntf"], "fallbacks": info["fallbacks"], "overload": info["overload_samples"]}
            bits = np.array(bl) if x.ndim == 2 else bl[0]
            y, fs = self.a.dsd_to_pcm(bits, self.dsd_rate)
            return y, fs, bits
        bits, rate = self.a.pcm_to_dsd(x, r)
        g = 10 ** (self.a.gain_db / 20)
        if x.ndim == 2:
            y = np.array([dec.decode(b, rate, decode_rate) for b in bits]) * g
        else:
            y = dec.decode(bits, rate, decode_rate) * g
        return y, decode_rate, bits


def _tail(y, n):
    return y[-n:] if len(y) >= n else y


def _thin(f, p_db, per_octave=48, f_min=10.0):
    """Reduce a spectrum to <= ~2000 points: keep low bins, power-average in log buckets above."""
    f = np.asarray(f)
    keep = f > 0
    f, p_db = f[keep], np.asarray(p_db)[keep]
    edges = np.geomspace(max(f_min, f[0]), f[-1], int(np.log2(f[-1] / max(f_min, f[0])) * per_octave) + 2)
    idx = np.searchsorted(edges, f)
    out_f, out_p = [], []
    p = 10 ** (p_db / 10)
    for i in np.unique(idx):
        m = idx == i
        out_f.append(float(np.exp(np.mean(np.log(f[m])))))
        out_p.append(float(10 * np.log10(np.mean(p[m]))))
    return out_f, out_p


def measure_device(adapter, profile="quick", in_rate=88200, log=print, only=None):
    prof = PROFILES[profile]
    ch = Chain(adapter, in_rate)
    res = {"metrics": {}, "plots": {}, "not_run": {}, "notes": [], "timing_s": {}}
    M, P = res["metrics"], res["plots"]
    A = adapter.klass == "A"
    M["device_class"] = adapter.klass
    M["dsd_rate"] = adapter.dsd_rate

    def step(name, fn):
        if only and name not in only:
            return
        t0 = time.time()
        try:
            fn()
        except FileNotFoundError as e:
            res["not_run"][name] = f"missing input: {e}"
        except Exception as e:  # a failing test must not lose the others
            res["not_run"][name] = f"failed: {type(e).__name__}: {e}"
        res["timing_s"][name] = round(time.time() - t0, 1)
        log(f"  {adapter.name}: {name} ({res['timing_s'][name]} s)")

    f_tone = sg.coherent_freq(1000, REF_FS, REF_NFFT)

    # ---------------------------------------------------------------- levels (tests 7, 8, 9, 13, 16)
    def levels():
        # The peak level runs on its own: a high-order reference modulator is stable to 0 dB SACD
        # but not to +3.1 dB SACD, and one overloaded stretch must not push the other levels
        # onto a lower-order design (the stability guard works per call).
        lv = list(np.arange(REF_DBFS, -126.0, -prof["step_db"]))
        seg = int(prof["seg_s"] * in_rate)
        parts, marks, pos = [], [], 0
        for L in lv:
            parts.append(sg.sine(f_tone, L, in_rate, seg))
            marks.append((float(L), pos, pos + seg))
            pos += seg
        x = np.concatenate(parts)
        y, fs, _ = ch.run(x, "levels")
        scale = fs / in_rate
        n = nfft_for(fs)
        rows = []
        for L, a, b in marks:
            sy = y[int(a * scale) : int(b * scale)]
            sy = _tail(sy, n)
            m = an.tone_metrics(sy, fs, f_tone, n)
            m["level_dbfs"] = L
            m["error_db"] = m["fundamental_dbfs"] - (L - 3.0103)
            rows.append(m)
        ypk, fspk, _ = ch.run(sg.sine(f_tone, PEAK_DBFS, in_rate, seg), "levels_peak")
        pk = an.tone_metrics(_tail(ypk, nfft_for(fspk)), fspk, f_tone, nfft_for(fspk))
        pk["level_dbfs"] = PEAK_DBFS
        pk["error_db"] = pk["fundamental_dbfs"] - (PEAK_DBFS - 3.0103)
        rows_all = [pk] + rows
        P["levels"] = {"level": [r["level_dbfs"] for r in rows_all], "thdn_db": [r["thdn_db"] for r in rows_all],
                       "thd_db": [r["thd_db"] for r in rows_all], "error_db": [r["error_db"] for r in rows_all],
                       "thdn_a_db": [r["thdn_a_db"] for r in rows_all]}
        ref = min(rows, key=lambda r: abs(r["level_dbfs"] - REF_DBFS))
        M["tone_0dbsacd"] = {k: ref[k] for k in ("thd_db", "thdn_db", "thdn_a_db", "sinad_db", "thd_percent",
                                                    "thdn_percent", "largest_harmonic")}
        M["tone_peak"] = {k: pk[k] for k in ("thd_db", "thdn_db", "sinad_db")}
        M["gain_error_db"] = ref["error_db"]
        low = min(rows, key=lambda r: abs(r["level_dbfs"] - (REF_DBFS - 60)))
        seg60 = _tail(y[int(marks[rows.index(low)][1] * scale) : int(marks[rows.index(low)][2] * scale)], n)
        M["dynamic_range"] = an.dynamic_range(seg60, fs, f_tone, n)
        ok = [r["level_dbfs"] for r in rows_all if abs(r["error_db"]) <= 0.5]
        M["linearity"] = {"lowest_level_within_0p5_db": min(ok) if ok else None,
                          "error_at": {str(int(r["level_dbfs"])): r["error_db"] for r in rows_all
                                       if int(r["level_dbfs"]) in (-6, -66, -90, -102, -114, -126)}}
        P["spectrum_1k"] = _spectrum_for_plot(_tail(y[int(marks[0][1] * scale) : int(marks[0][2] * scale)], n), fs, n)

    # ---------------------------------------------------------------- THD+N against frequency (test 9)
    def thdn_freq():
        fl = [20, 100, 1000, 5000, 10000, 15000, 20000]
        seg = int(prof["seg_s"] * in_rate)
        x = np.concatenate([sg.sine(sg.coherent_freq(f, REF_FS, REF_NFFT), REF_DBFS, in_rate, seg) for f in fl])
        y, fs, _ = ch.run(x, "thdn_freq")
        n = nfft_for(fs)
        sc = fs / in_rate
        rows = []
        for i, f in enumerate(fl):
            sy = _tail(y[int(i * seg * sc) : int((i + 1) * seg * sc)], n)
            m = an.tone_metrics(sy, fs, sg.coherent_freq(f, REF_FS, REF_NFFT), n)
            rows.append({"f": f, "thdn_db": m["thdn_db"], "thd_db": m["thd_db"]})
        P["thdn_freq"] = {"f": fl, "thdn_db": [r["thdn_db"] for r in rows]}
        M["thdn_vs_frequency"] = {str(r["f"]): r["thdn_db"] for r in rows}
        M["thdn_vs_frequency"]["bandwidth"] = "20 Hz to 20 kHz"

    # ---------------------------------------------------------------- frequency response (test 2)
    def fr():
        freqs = THIRD_OCTAVE[:: prof["fr_every"]] + [f for f in EXTRA_HF if f < in_rate / 2]
        if A:
            freqs = [f for f in freqs if f < 22050 * 0.99]  # class A outputs may be 44.1 kHz
        freqs = sorted(set(freqs + [1000]))
        seg = 2 * nfft_for(in_rate, REF_NFFT)
        parts = [sg.sine(sg.coherent_freq(f, REF_FS, REF_NFFT), REF_DBFS, in_rate, seg) for f in freqs]
        y, fs, _ = ch.run(np.concatenate(parts), "fr")
        n = nfft_for(fs)
        sc = fs / in_rate
        lv = []
        for i, f in enumerate(freqs):
            sy = y[int(i * seg * sc) : int((i + 1) * seg * sc)]
            sy = _tail(sy, n)
            fc = sg.coherent_freq(f, REF_FS, REF_NFFT)
            p = an.power_spectrum(sy, n)
            lv.append(an.db(an.lobe_power(p, an.tone_bin(fc, n, fs), half=min(an.LOBE, max(1, an.tone_bin(fc, n, fs) - 1)))))
        lv = np.array(lv)
        mag = lv - lv[freqs.index(1000)]
        fa = np.array(freqs, dtype=float)
        P["fr"] = {"f": fa.tolist(), "mag_db": mag.tolist()}
        M["frequency_response"] = an.response_metrics(fa, mag + 0.0)
        M["frequency_response"]["method"] = "stepped coherent tones (reduced)" if profile == "quick" else "stepped coherent tones"
        M["frequency_response"]["tones"] = len(freqs)

    # ---------------------------------------------------------------- impulse, step, filter (tests 3, 4, 5)
    def impulse():
        # Class A: impulses at 352.8 kHz with eight sub-sample offsets, so the output samples of
        # all alignments interleave into one response at 352.8 kHz resolution (no interpolation:
        # every point is a real output sample). Class B: impulses at the input rate.
        # (Class B is decoded at the input rate: the modulator's ultrasonic noise would otherwise
        # bury the response; the in-band response is what the impulse shows.)
        rin = REF_FS if A else in_rate
        unit_rate = REF_FS if A else in_rate
        u = unit_rate // rin  # input sample length in response-grid units
        sp, nj = 8192, 64
        x = np.zeros(sp * (nj + 1))
        ts = []
        for j in range(nj):
            o = j % 8 if A else 0
            pos = sp // 2 + j * sp + (o if A else 0)
            x[pos] = 10 ** (REF_DBFS / 20)
            ts.append((pos * u, o))
        y, fs, _ = ch.run(x, "impulse", in_rate=rin, decode_rate=unit_rate)
        r = unit_rate // fs if unit_rate % fs == 0 else 1
        span = max(256, 4096 // r)
        size = 2 * span * r
        acc, cnt = np.zeros(size), np.zeros(size)
        for T, o in ts:
            m0 = (T - o * u) // r
            for m in range(m0 - span, m0 + span):
                if 0 <= m < len(y):
                    t = (m - m0) * r - o * u
                    k = t + span * r
                    if 0 <= k < size:
                        acc[k] += y[m]
                        cnt[k] += 1
        h = np.divide(acc, cnt, out=np.zeros(size), where=cnt > 0) / 10 ** (REF_DBFS / 20)
        h = h[16:-16]  # edge samples are not covered by every alignment
        fs_eff = unit_rate
        P["impulse"] = {"fs": fs_eff, "h": h.tolist(), "center": int(np.argmax(np.abs(h))), "output_rate": fs}
        M["impulse"] = an.impulse_metrics(h, fs_eff)
        M["impulse"]["output_rate"] = fs
        if not A:
            res["notes"].append("Class B impulse and step include the reference decoder's own filter.")
        M["impulse"]["method"] = ("samples of eight alignments interleaved at 352.8 kHz" if A and r > 1 else "output samples")
        hh = np.zeros(2**17)
        hh[: len(h)] = h
        f, mag, _ = an.response_from_impulse(hh, fs_eff, nfft=2**17)
        rel = mag - float(np.interp(1000, f, mag))

        def first_below(th, f_from):
            idx = np.where((f > f_from) & (rel < -th))[0]
            return float(f[idx[0]]) if len(idx) else None

        fsum = {"minus_0p1_db_hz": first_below(0.1, 15000), "minus_3_db_hz": first_below(3, 15000),
                "minus_60_db_hz": first_below(60, 15000), "output_nyquist_hz": fs / 2 if A else None}
        # the stopband starts at the lowest frequency that folds back into 0 to 20 kHz
        edge = fs - 20000.0
        if A and 22050 <= edge < fs_eff / 2 * 0.97:
            fsum["stopband_edge_hz"] = edge
            fsum["stopband_worst_db"] = float(rel[f >= edge].max())
        M["filter_summary"] = fsum
        fl, ml = _thin(f[1:], mag[1:], per_octave=24)
        P["filter"] = {"f": fl, "mag_db": ml}
        f2, gd = an.group_delay_us(h, fs_eff, nfft=2**17)
        m = (f2 > 20) & (f2 < 20000)
        fg, gg = f2[m][:: max(1, m.sum() // 800)], gd[m][:: max(1, m.sum() // 800)]
        P["group_delay"] = {"f": fg.tolist(), "gd_us": gg.tolist()}
        M["group_delay_us"] = {"at_1k": float(np.interp(1000, f2, gd)), "at_10k": float(np.interp(10000, f2, gd)),
                              "at_20k": float(np.interp(20000, f2, gd))}
        # step: 9 periods of a square wave, the 8 rising edges averaged
        per = 16384
        sx = np.tile(np.concatenate([np.zeros(per // 2), np.full(per // 2, 10 ** (REF_DBFS / 20))]), 9)
        ys, fs2, _ = ch.run(sx, "step", decode_rate=REF_FS if A else in_rate)
        sc2 = fs2 / in_rate
        pre, post = 400, int(0.01 * fs2)
        edges = [int((per // 2 + i * per) * sc2) for i in range(1, 9)]
        sy = np.mean([ys[c - pre : c + post] for c in edges], axis=0) / 10 ** (REF_DBFS / 20)
        P["step"] = {"fs": fs2, "s": sy.tolist(), "center": pre}
        M["step"] = an.step_metrics(sy[pre - 20 :], fs2)
        M["step"]["note"] = "average of 8 rising edges"

    # ---------------------------------------------------------------- noise (test 6)
    def noise():
        n_in = int(prof["noise_s"] * in_rate)
        rng = np.random.default_rng(7)
        x = (rng.random(n_in) - rng.random(n_in)) * 2.0**-23  # TPDF dither at 24-bit
        y, fs, _ = ch.run(x, "noise")
        M["noise_input"] = "24-bit TPDF-dithered silence" + (" through the reference modulator" if A else "")
        if A:
            # The DSD idle pattern (repeating 0x69) decodes to near-exact zero in a linear decoder,
            # so it is reported as an extra: only the device's own idle behaviour shows in it.
            pat = np.unpackbits(np.frombuffer(bytes([0x69]) * (int(prof["noise_s"] * adapter.dsd_rate) // 8), np.uint8))
            if hasattr(adapter, "current"):
                adapter.current = "noise_idle"
            yi, fi = adapter.dsd_to_pcm(pat.astype(np.int8) * 2 - 1, adapter.dsd_rate)
            oi, _, _ = an.noise_floor(yi[int(0.5 * fi) :], fi, nfft=max(2**12, int(2**18 * fi / REF_FS)), nseg=4)
            M["noise_idle_pattern_a_weighted_dbfs"] = oi["a_weighted_dbfs"]
        y = y[int(0.5 * fs) :]
        # 8 half-overlapped segments of 2^20 points at 352.8 kHz when the record is long enough
        n = 2**20 if len(y) > 2**20 * 4.5 * fs / REF_FS else 2**18
        n = max(int(n * fs / REF_FS), 2**12)
        out, f, p = an.noise_floor(y, fs, nfft=n, nseg=8)
        M["noise"] = out
        M["dc"] = an.dc_offset(y)
        pd = p / (fs / n)
        fl, pl = _thin(f[1:], an.db(pd[1:]))
        P["noise"] = {"f": fl, "dbfs_hz": pl, "fs": fs, "ref_24bit_tpdf": float(an.db(2.0**-46 / 6 / (in_rate / 2)))}
        if not A:
            bits, rate = adapter.pcm_to_dsd(x, in_rate)
            ur = 705600 if rate <= 2822400 else 1411200
            yu = dec.decode(bits, rate, ur)[int(0.5 * ur) :]
            nu = 2**18
            M["ultrasonic"] = an.ultrasonic_peak(yu, ur, nfft=nu, nseg=8)
            ou, fu, pu = an.noise_floor(yu, ur, nfft=nu, nseg=8, bands=((20, 20000), (20000, 40000), (40000, 96000), (96000, 192000)))
            M["noise_wide"] = ou["bands"]
            fl, pl = _thin(fu[1:], an.db(pu[1:] / (ur / nu)))
            P["noise_wide"] = {"f": fl, "dbfs_hz": pl}
            z = np.zeros(n_in)
            yz, fz, _ = ch.run(z, "noise_zero")
            oz, _, _ = an.noise_floor(yz[int(0.5 * fz) :], fz, nfft=n, nseg=4)
            M["noise_zero_input"] = oz["a_weighted_dbfs"]
        else:
            res["notes"].append("Ultrasonic noise is limited by the device output rate.")

    # ---------------------------------------------------------------- IMD (test 10)
    def imd():
        n_in = int(prof["imd_s"] * in_rate)
        x, (f1, f2) = sg.smpte(in_rate, n_in, REF_NFFT * 0 + REF_NFFT)
        # recompute coherent tones on the reference grid
        f1, f2 = sg.coherent_freq(60, REF_FS, REF_NFFT), sg.coherent_freq(7000, REF_FS, REF_NFFT)
        t = np.arange(n_in) / in_rate
        x = (4 * np.sin(2 * np.pi * f1 * t) + np.sin(2 * np.pi * f2 * t)) / 5 * 10 ** (REF_DBFS / 20)
        y, fs, _ = ch.run(x, "imd_smpte")
        n = nfft_for(fs)
        M["imd_smpte"] = an.imd_smpte(_tail(y, n), fs, n, f1, f2)
        P["imd_smpte"] = _spectrum_for_plot(_tail(y, n), fs, n, fmax=20000)
        g1, g2 = sg.coherent_freq(19000, REF_FS, REF_NFFT), sg.coherent_freq(20000, REF_FS, REF_NFFT)
        x = (np.sin(2 * np.pi * g1 * t) + np.sin(2 * np.pi * g2 * t)) / 2 * 10 ** (REF_DBFS / 20)
        y, fs, _ = ch.run(x, "imd_ccif")
        M["imd_ccif"] = an.imd_ccif(_tail(y, n), fs, n, g1, g2)
        P["imd_ccif"] = _spectrum_for_plot(_tail(y, n), fs, n, fmax=fs / 2 if fs < 100000 else 40000)

    # ---------------------------------------------------------------- multitone (test 11)
    def multitone():
        periods = prof["mt_periods"]
        x1, freqs, bins = sg.multitone_standard(REF_DBFS, fs=in_rate)
        lead = np.zeros(int(1.0 * in_rate))
        # one extra period at each end: the onset and the end of a signal leak into a non-periodic
        # window, and with a rectangular window that would read as distortion
        x = np.concatenate([lead, np.tile(x1, periods + 2)])
        y, fs, _ = ch.run(x, "multitone")
        n = int(2**20 * fs / REF_FS)
        y = y[int(1.0 * fs) + n :]
        r = an.multitone_metrics(y, fs, n, bins, nseg=periods)
        M["multitone"] = {"headline": r["avg8" if periods >= 8 else "avg8"],
                          "avg1": r["avg1"], "averages": periods}
        for k in ("per_tone_snr_db",):
            M["multitone"]["headline"] = {a: b for a, b in M["multitone"]["headline"].items() if a != k}
            M["multitone"]["avg1"] = {a: b for a, b in M["multitone"]["avg1"].items() if a != k}
        acc = np.zeros(n // 2 + 1)
        for i in range(min(periods, max(1, len(y) // n))):
            acc += an.power_spectrum(y[i * n :], n, "rect")
        acc /= min(periods, max(1, len(y) // n))
        P["multitone"] = {**_spectrum_arrays(acc, fs, n, fmax=22050), "tone_f": [float(b) * fs / n for b in bins],
                          "tone_db": [float(an.db(acc[b])) for b in bins]}

    # ---------------------------------------------------------------- 15 kHz tone (test 17)
    def tone15():
        n_in = int(prof["tone_s"] * in_rate)
        x, f15 = sg.tone_15k(in_rate, n_in, REF_NFFT)
        f15 = sg.coherent_freq(15000, REF_FS, REF_NFFT)
        x = sg.sine(f15, -12.0, in_rate, n_in)
        y, fs, _ = ch.run(x, "tone15")
        n = nfft_for(fs)
        M["tone_15k"] = an.spur_report(_tail(y, n), fs, f15, n)
        P["tone_15k"] = _spectrum_for_plot(_tail(y, n), fs, n)

    # ---------------------------------------------------------------- J-test (test 12)
    def jtest():
        n_in = int(prof["jtest_s"] * 44100)
        x = sg.jtest(44100, n_in)
        y, fs, _ = ch.run(x, "jtest", in_rate=44100)
        y = y[int(0.5 * fs) :]
        n = 2**18
        M["jtest"] = an.jtest_metrics(y, fs, nfft=n, nseg=3, fs_nominal=44100)
        P["jtest"] = _spectrum_for_plot(y[:n], fs, n, fmin=9000, fmax=13000, linear=True)

    # ---------------------------------------------------------------- polarity (test 15)
    def polarity():
        p = sg.polarity_pulse(8192)
        y, fs, _ = ch.run(p, "polarity")
        sc = fs / in_rate
        c = int(len(p) // 2 * sc)
        M["polarity"] = an.polarity(y[c - 200 : c + 200 + int(20 * sc)], p[len(p) // 2 - 4 : len(p) // 2 + 14])

    # ---------------------------------------------------------------- stability (test 18, class B)
    def stability():
        if A:
            res["not_run"]["stability"] = "class B only"
            return
        out = {}
        hold = int(prof["hold_s"] * in_rate)
        for f0, lv, label in ((1000, REF_DBFS, "0 dB SACD"), (1000, PEAK_DBFS, "+3.1 dB SACD (peak)"),
                              (20000, PEAK_DBFS, "20 kHz at peak")):
            fc = sg.coherent_freq(f0, REF_FS, REF_NFFT)
            x = sg.sine(fc, lv, in_rate, hold)
            bits, rate = adapter.pcm_to_dsd(x, in_rate)
            s = an.stability_report(bits[int(0.5 * rate):], rate)
            d = int(2**18 / REF_FS * rate)
            y0 = dec.decode(bits[int(0.5 * rate) : int(0.5 * rate) + d + 2**22], rate, REF_FS)
            y1 = dec.decode(bits[-(d + 2**22) :], rate, REF_FS)
            n = REF_NFFT
            m0 = an.tone_metrics(y0[5000 : 5000 + n], REF_FS, fc, n)
            m1 = an.tone_metrics(y1[-n - 5000 : -5000], REF_FS, fc, n)
            s["thdn_start_db"], s["thdn_end_db"] = m0["thdn_db"], m1["thdn_db"]
            s["thdn_drift_db"] = m1["thdn_db"] - m0["thdn_db"]
            out[label] = s
            if f0 == 1000 and lv == PEAK_DBFS:
                dens = an.bit_density(bits[int(0.5 * rate):], 28)
                sec = rate
                k = len(dens) // sec
                if k:
                    mod = (2 * dens[: k * sec].reshape(k, sec) - 1) * 100
                    P["density"] = {"t": list(range(k)), "max": mod.max(1).tolist(), "min": mod.min(1).tolist(),
                                    "mean": mod.mean(1).tolist()}
        M["stability"] = {"hold_s": prof["hold_s"], "levels": out}


    # ---------------------------------------------------------------- reference floor (principle 6)
    def floor():
        from .floor import reference_floor
        M["reference_floor"] = reference_floor(adapter.dsd_rate)

    # ---------------------------------------------------------------- crosstalk, channel match (test 14)
    def crosstalk():
        seg = int(prof["seg_s"] * in_rate) + int(0.8 * in_rate)
        rng = np.random.default_rng(11)
        out = {}
        for fq in (1000, 10000):
            f0 = sg.coherent_freq(fq, REF_FS, REF_NFFT)
            tone = sg.sine(f0, REF_DBFS, in_rate, seg)
            quiet = (rng.random(seg) - rng.random(seg)) * 2.0**-23  # 24-bit dithered silence
            y, fs, _ = ch.run(np.array([tone, quiet]), f"crosstalk_{fq}_l")
            n = nfft_for(fs)
            ld, rs = _tail(y[0], n), _tail(y[1], n)
            y2, fs2, _ = ch.run(np.array([quiet, tone]), f"crosstalk_{fq}_r")
            rd, ls = _tail(y2[1], n), _tail(y2[0], n)
            both, fs3, _ = ch.run(np.array([tone, tone]), f"match_{fq}")
            bm = an.channel_match(_tail(both[0], n), _tail(both[1], n), fs3, f0, n)
            out[str(fq)] = {"left_to_right_db": an.crosstalk(ld, rs, fs, f0, n),
                            "right_to_left_db": an.crosstalk(rd, ls, fs2, f0, n),
                            "gain_diff_db": bm["gain_diff_db"], "phase_diff_deg": bm["phase_diff_deg"]}
        M["crosstalk"] = out

    # ---------------------------------------------------------------- IMD sweep (test 10)
    def imd_sweep():
        n_in = int(prof["imd_s"] * in_rate) + int(0.8 * in_rate)
        t = np.arange(n_in) / in_rate
        centres = [10000, 12000, 14000, 16000, 18000, 19500]
        parts, pairs = [], []
        for c in centres:
            g1, g2 = (sg.coherent_freq(c - 500, REF_FS, REF_NFFT), sg.coherent_freq(c + 500, REF_FS, REF_NFFT))
            parts.append((np.sin(2 * np.pi * g1 * t) + np.sin(2 * np.pi * g2 * t)) / 2 * 10 ** (REF_DBFS / 20))
            pairs.append((g1, g2))
        ccif = []
        for c, x, (g1, g2) in zip(centres, parts, pairs, strict=True):
            y, fs, _ = ch.run(x, f"imd_ccif_{c}")
            n = nfft_for(fs)
            ccif.append(an.imd_ccif(_tail(y, n), fs, n, g1, g2)["imd_db"])
        f1, f2 = sg.coherent_freq(60, REF_FS, REF_NFFT), sg.coherent_freq(7000, REF_FS, REF_NFFT)
        levels_db = [-60, -40, -20, -10, 0]
        smpte = []
        for L in levels_db:
            x = (4 * np.sin(2 * np.pi * f1 * t) + np.sin(2 * np.pi * f2 * t)) / 5 * 10 ** ((REF_DBFS + L) / 20)
            y, fs, _ = ch.run(x, f"imd_smpte_{L}")
            n = nfft_for(fs)
            smpte.append(an.imd_smpte(_tail(y, n), fs, n, f1, f2)["imd_db"])
        P["imd_sweep"] = {"ccif_centre": centres, "ccif_db": ccif, "smpte_level": levels_db, "smpte_db": smpte}
        M["imd_sweep"] = {"ccif_worst_db": max(ccif), "ccif_worst_centre_hz": centres[int(np.argmax(ccif))],
                          "ccif_by_centre": {str(c): v for c, v in zip(centres, ccif, strict=True)},
                          "smpte_worst_db": max(smpte), "smpte_by_level_db_sacd": {str(L): v for L, v in zip(levels_db, smpte, strict=True)}}

    # ---------------------------------------------------------------- alias tones (test 3)
    def alias_tones():
        out_rate = getattr(adapter, "out_rate", None)
        # class A only: the output rate decides what lies above the device's own Nyquist frequency
        if not A:
            res["not_run"]["alias_tones"] = "class A only (a modulator has no output Nyquist frequency inside the analysis band)"
            return
        probe, pfs, _ = ch.run(sg.sine(f_tone, REF_DBFS, in_rate, int(2.2 * in_rate)), "alias_probe")
        out_rate = pfs
        if out_rate >= 352800:
            res["not_run"]["alias_tones"] = "output rate of 352.8 kHz or more: no test tone above its Nyquist frequency can be made"
            return
        fin = 88200 if out_rate <= 44100 else 352800
        nyq = out_rate / 2
        tones = [nyq + d for d in (2000, 4000, 6000, 8000, 10000)]
        tones = [f for f in tones if f < fin / 2 * 0.9]
        rows = []
        ref_rms = REF_DBFS - 3.0103
        for ft in tones:
            fc = sg.coherent_freq(ft, REF_FS, REF_NFFT)
            y, fs, _ = ch.run(sg.sine(fc, REF_DBFS, fin, int(2.2 * fin)), f"alias_{int(ft)}", in_rate=fin)
            n = nfft_for(fs)
            p = an.power_spectrum(_tail(y, n), n)
            f = an.freqs(n, fs)
            q = np.where(f < 20, 0, p)
            i = int(np.argmax(q))
            lv = float(an.db(an.lobe_power(q, i)) - ref_rms)
            rows.append({"tone_hz": float(fc), "alias_hz": float(f[i]), "image_db": lv})
        P["alias"] = {"tone": [r["tone_hz"] for r in rows], "image_db": [r["image_db"] for r in rows], "nyquist": nyq}
        worst = max(rows, key=lambda r: r["image_db"])
        M["alias_tones"] = {"output_rate": out_rate, "worst_image_db": worst["image_db"], "worst_tone_hz": worst["tone_hz"],
                            "worst_image_hz": worst["alias_hz"], "rows": rows,
                            "note": "image level relative to the input tone; includes the device noise floor"}

    # ---------------------------------------------------------------- overload recovery (test 18)
    def overload():
        f0 = sg.coherent_freq(1000, REF_FS, REF_NFFT)
        quiet_db = REF_DBFS - 60
        burst_db = 0.0 if not A else PEAK_DBFS  # class B: digital full scale; class A: the reference's peak level
        pre, burst_s, post = 1.0, 0.05, 0.6
        n1, nb, n2 = int(pre * in_rate), int(burst_s * in_rate), int(post * in_rate)
        t = np.arange(n1 + nb + n2) / in_rate
        amp = np.full(len(t), 10 ** (quiet_db / 20))
        amp[n1 : n1 + nb] = 10 ** (burst_db / 20)
        x = amp * np.sin(2 * np.pi * f0 * t)
        y, fs, _ = ch.run(x, "overload")
        # Band-pass 300 Hz to 20 kHz (linear phase, 4097 taps: +-6 ms of smearing around the burst),
        # then in 5 ms windows (five cycles) fit and remove the 1 kHz tone and take the residual rms.
        bp = signal.firwin(4097, [300.0, 20000.0], pass_zero=False, fs=fs, window=("kaiser", 8.0))
        yb = signal.fftconvolve(y, bp, mode="same")
        win = int(round(0.005 * fs))
        nwin = len(yb) // win
        rms = np.zeros(nwin)
        for i in range(nwin):
            seg_ = yb[i * win : (i + 1) * win]
            tt = (np.arange(i * win, (i + 1) * win)) / fs
            basis = np.column_stack([np.sin(2 * np.pi * f0 * tt), np.cos(2 * np.pi * f0 * tt), np.ones(win)])
            coef, *_ = np.linalg.lstsq(basis, seg_, rcond=None)
            rms[i] = np.sqrt(np.mean((seg_ - basis @ coef) ** 2))
        t_w = (np.arange(nwin) + 0.5) * win / fs
        t_b0, t_b1 = n1 / in_rate, (n1 + nb) / in_rate
        base = rms[(t_w > 0.3) & (t_w < t_b0 - 0.03)]
        base_rms = float(np.median(base))
        after = np.where((t_w > t_b1) & (t_w < t_w[-1] - 0.03))[0]  # the last 30 ms is filter edge
        bad = [i for i in after if rms[i] > base_rms * 10 ** (3 / 20)]
        rec_ms = float((t_w[bad[-1]] + 0.5 * win / fs - t_b1) * 1000) if bad else 0.0
        peak_excess = float(20 * np.log10(max(rms[after].max(), 1e-300) / base_rms)) if len(after) else 0.0
        P["overload"] = {"t_ms": ((t_w - t_b1) * 1000).tolist(), "rms_db": (20 * np.log10(np.maximum(rms, 1e-300))).tolist(),
                         "base_db": float(20 * np.log10(base_rms)), "burst_start_ms": float((t_b0 - t_b1) * 1000)}
        M["overload_recovery"] = {"burst_level_dbfs": burst_db, "burst_ms": burst_s * 1000, "recovery_ms": rec_ms,
                                  "residual_peak_over_baseline_db": peak_excess,
                                  "method": "1 kHz at -60 dB SACD, 50 ms burst; residual (300 Hz-20 kHz, 1 kHz fitted out) in 5 ms windows back within 3 dB of its pre-burst level; resolution about 10 ms"}

    # ---------------------------------------------------------------- DSD rate table (tests 8, 19 at other rates)
    def rate_table():
        rates = list(adapter.rates)
        if not rates:
            res["not_run"]["rate_table"] = "no extra DSD rates requested (suite key rates = [5644800, 11289600])"
            return
        base_rate = adapter.dsd_rate
        out = {}
        try:
            for r in rates:
                adapter.dsd_rate = r
                row = {}
                x = np.concatenate([sg.sine(f_tone, REF_DBFS, in_rate, int(2.2 * in_rate)),
                                    sg.sine(f_tone, REF_DBFS - 60, in_rate, int(2.2 * in_rate))])
                y, fs, _ = ch.run(x, f"rate_{r}_tone")
                n = nfft_for(fs)
                h = len(y) // 2
                m = an.tone_metrics(_tail(y[:h], n), fs, f_tone, n)
                dr = an.dynamic_range(_tail(y[h:], n), fs, f_tone, n)
                row.update({"thdn_db": m["thdn_db"], "thd_db": m["thd_db"], "sinad_db": m["sinad_db"],
                            "thdn_a_db": m["thdn_a_db"], "dr_a_db": dr["dr_a_db"]})
                if not A:
                    pk, rate = adapter.pcm_to_dsd(sg.sine(f_tone, PEAK_DBFS, in_rate, int(4 * in_rate)), in_rate)
                    row["stability_peak"] = {"saturated": an.stability_report(pk[int(0.5 * rate):], rate)["saturated"]}
                    rng = np.random.default_rng(7)
                    xs = (rng.random(int(5 * in_rate)) - rng.random(int(5 * in_rate))) * 2.0**-23
                    bits, rate = adapter.pcm_to_dsd(xs, in_rate)
                    ur = 705600 if rate <= 2822400 else 1411200
                    yu = dec.decode(bits, rate, ur)[int(0.5 * ur) :]
                    row["ultrasonic"] = an.ultrasonic_peak(yu, ur, nfft=2**18, nseg=4)
                    on, _, _ = an.noise_floor(dec.decode(bits, rate, REF_FS)[int(0.5 * REF_FS) :], REF_FS, nfft=REF_NFFT, nseg=4)
                    row["noise_a_dbfs"] = on["a_weighted_dbfs"]
                from .floor import reference_floor
                row["reference_floor"] = reference_floor(r)
                out[rate_name(r)] = row
        finally:
            adapter.dsd_rate = base_rate
        M["rates"] = out

    for name, fn in (("reference_floor", floor), ("levels", levels), ("thdn_freq", thdn_freq), ("frequency_response", fr), ("impulse", impulse), ("noise", noise),
                     ("imd", imd), ("multitone", multitone), ("tone_15k", tone15), ("jtest", jtest),
                     ("polarity", polarity), ("stability", stability), ("crosstalk", crosstalk),
                     ("imd_sweep", imd_sweep), ("alias_tones", alias_tones), ("overload", overload),
                     ("rate_table", rate_table)):
        step(name, fn)
    res["reference_chain_ntf"] = ch.ntf
    return res


def _spectrum_arrays(p, fs, n, fmin=10.0, fmax=None):
    f = np.fft.rfftfreq(n, 1 / fs)
    m = (f >= fmin) & (f <= (fmax or fs / 2))
    fl, pl = f[m], an.db(p[m])
    if len(fl) > 2000:  # keep the peaks when thinning
        k = int(np.ceil(len(fl) / 2000))
        cut = len(fl) // k * k
        pl2 = pl[:cut].reshape(-1, k).max(1)
        fl2 = fl[:cut].reshape(-1, k).mean(1)
        return {"f": fl2.tolist(), "db": pl2.tolist()}
    return {"f": fl.tolist(), "db": pl.tolist()}


def _spectrum_for_plot(y, fs, n, fmin=10.0, fmax=None, linear=False):
    return _spectrum_arrays(an.power_spectrum(y, n), fs, n, fmin, fmax)
