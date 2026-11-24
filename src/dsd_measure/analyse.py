"""Analysers: one function per metric of docs/footprint.md.

Conventions: signals are 1-D float arrays; levels are dBFS (a full-scale sine peaks at 1.0);
spectra are one-sided power spectra normalised so that the sum over all bins equals the
mean square of the signal (so a coherent sine of amplitude A sums to A^2 / 2 over its lobe).
"""

from functools import lru_cache

import numpy as np
from scipy import signal

from .levels import REF_DBFS

# 7-term Blackman-Harris window (Albrecht), main lobe +-7 bins, sidelobes below -180 dB
_BH7 = (0.27105140069342, 0.43329793923448, 0.21812299954311, 0.06592544638803,
        0.01081174209837, 0.00077658482522, 0.00001388721735)
LOBE = 10  # the 7-term window main lobe is +-7 bins; the margin keeps leakage below -180 dB


@lru_cache(maxsize=8)
def bh7(n):
    """The 7-term Blackman-Harris window of ``n`` points (kept between calls; read-only)."""
    k = np.arange(n)
    w = np.zeros(n)
    for i, a in enumerate(_BH7):
        w += (-1) ** i * a * np.cos(2 * np.pi * i * k / n)
    w.setflags(write=False)
    return w


def db(p):
    return 10 * np.log10(np.maximum(p, 1e-300))


#: Noise levels are quoted in dBFS re the rms of a full-scale sine (AES17, ASR, RMAA), which is
#: 3.01 dB above the mean square re a peak of 1.0. A white-noise power ``p`` therefore reads
#: ``db(p) + SINE_REF_DB``. Tone levels already use this reference (a -6.02 dBFS sine reads -6.02).
SINE_REF_DB = 10 * np.log10(2.0)


def a_weight_db(f):
    """IEC 61672 A-weighting in dB (0 dB at 1 kHz)."""
    f = np.asarray(f, dtype=np.float64)
    f2 = f**2
    ra = (12194.0**2 * f2**2) / (
        (f2 + 20.6**2) * np.sqrt((f2 + 107.7**2) * (f2 + 737.9**2)) * (f2 + 12194.0**2))
    with np.errstate(divide="ignore"):
        return 20 * np.log10(np.maximum(ra, 1e-30)) + 2.0


def power_spectrum(x, nfft, window="bh7"):
    """Single-segment one-sided power spectrum of the first ``nfft`` samples."""
    seg = np.asarray(x[:nfft], dtype=np.float64)
    if len(seg) < nfft:
        raise ValueError(f"need {nfft} samples, got {len(seg)}")
    w = bh7(nfft) if window == "bh7" else np.ones(nfft)
    X = np.fft.rfft(seg * w)
    p = 2 * np.abs(X) ** 2 / (nfft * np.sum(w**2))
    p[0] /= 2
    if nfft % 2 == 0:
        p[-1] /= 2
    return p


def welch_segments(n, nfft, nseg=8, overlap=0.5):
    """How many segments ``welch`` really averages over a record of ``n`` points (fewer than asked when it is short)."""
    step = int(nfft * (1 - overlap))
    return nseg if n >= nfft + step * (nseg - 1) else max(1, (n - nfft) // step + 1)


def welch(x, nfft, nseg=8, overlap=0.5, window="bh7"):
    """Power-averaged spectrum over ``nseg`` segments (Welch). Returns the averaged spectrum.

    A record too short for ``nseg`` segments gets fewer; ``welch_segments`` says how many, and the
    noise results carry that number as ``averages``.
    """
    step = int(nfft * (1 - overlap))
    nseg = welch_segments(len(x), nfft, nseg, overlap)
    acc = np.zeros(nfft // 2 + 1)
    for i in range(nseg):
        acc += power_spectrum(x[i * step :], nfft, window)
    return acc / nseg


def freqs(nfft, fs):
    return np.fft.rfftfreq(nfft, 1 / fs)


def tone_bin(f, nfft, fs):
    return int(round(f * nfft / fs))


def lobe_power(p, k, half=LOBE):
    lo, hi = max(0, k - half), min(len(p), k + half + 1)
    return float(np.sum(p[lo:hi]))


def band_mask(nfft, fs, f_lo, f_hi):
    f = freqs(nfft, fs)
    return (f >= f_lo) & (f <= f_hi)


def notch_noise(p, k, mask, half=LOBE):
    """Power in the masked band excluding the lobe around bin k."""
    m = mask.copy()
    m[max(0, k - half) : k + half + 1] = False
    return float(np.sum(p[m]))


def tone_metrics(x, fs, f0, nfft=2**18, band=(20.0, 20000.0), nharm=9, fund_level_ref=None, thd_wide_hz=None):
    """THD, THD+N, SINAD, noise and harmonics for a coherent tone (footprint tests 7, 8, 9)."""
    p = power_spectrum(x, nfft)
    k0 = tone_bin(f0, nfft, fs)
    fund = lobe_power(p, k0)
    mask = band_mask(nfft, fs, *band)
    # Harmonic lobes must not overlap the fundamental's lobe or each other: below about 27 Hz
    # (at 2^18 points, 352.8 kHz) the lobes are wider than the harmonic spacing, and the
    # fundamental's skirt would be counted as 2nd-harmonic distortion. Each bin is counted once,
    # and the half-width shrinks to the half-spacing where the harmonics are closer than that.
    half = max(1, min(LOBE, (k0 - 1) // 2))
    claimed = np.zeros(len(p), dtype=bool)
    claimed[max(0, k0 - LOBE) : k0 + LOBE + 1] = True
    harm = {}
    for h in range(2, nharm + 1):
        fh = f0 * h
        if fh > band[1]:
            break
        kh = tone_bin(fh, nfft, fs)
        sel = np.zeros(len(p), dtype=bool)
        sel[max(0, kh - half) : kh + half + 1] = True
        sel &= ~claimed
        harm[h] = float(np.sum(p[sel]))
        claimed |= sel
    hp = sum(harm.values())
    noise_total = notch_noise(p, k0, mask)  # harmonics + noise
    f = freqs(nfft, fs)
    aw = 10 ** (a_weight_db(np.maximum(f, 1e-3)) / 10)
    pw = p * aw
    fund_w = lobe_power(pw, k0)
    noise_w = notch_noise(pw, k0, mask)
    top = max(harm, key=harm.get) if harm else None
    res = {
        "fundamental_dbfs": float(db(fund) ),
        "thd_db": float(db(hp / fund)) if harm else float("-inf"),
        "thdn_db": float(db(noise_total / fund)),
        "thdn_a_db": float(db(noise_w / fund_w)),
        "sinad_db": float(-db(noise_total / fund)),
        "noise_dbfs": float(db(noise_total - hp) + SINE_REF_DB) if noise_total > hp else float("-inf"),
        "largest_harmonic": None if top is None else {"order": int(top), "db": float(db(harm[top] / fund))},
    }
    if thd_wide_hz:
        # All harmonics (2 to 9) up to ``thd_wide_hz``: the 10, 15 and 20 kHz tones have their
        # harmonics above the 20 kHz band, which the band-limited THD cannot see. Above the band a
        # modulator's shaped noise is much louder than any harmonic, so a harmonic counts only when
        # its lobe is 10 dB above the local noise (mean of the bins 30 to 60 away that are in no lobe); with none,
        # ``thd_wide_db`` is None and ``thd_wide_bound_db`` is the total of the lobes (an upper
        # bound: "no worse than").
        # The lobes are cut the way ``thd_db`` cuts them: each bin belongs to one lobe, and the half
        # width shrinks where the harmonics are closer than a lobe (a 20 Hz tone). The local noise is
        # the mean power of the bins 30 to 60 away that belong to no lobe (the mean, not the median,
        # which sits 1.6 dB low for noise), and a harmonic counts only when 10 dB above it: with a
        # single spectrum a lobe of pure noise varies by about 2 dB.
        wclaimed = np.zeros(len(p), dtype=bool)
        wclaimed[max(0, k0 - LOBE) : k0 + LOBE + 1] = True
        lobes = []
        for h in range(2, nharm + 1):
            if f0 * h < min(thd_wide_hz, 0.45 * fs):
                kh = tone_bin(f0 * h, nfft, fs)
                sel = np.zeros(len(p), dtype=bool)
                sel[max(0, kh - half) : kh + half + 1] = True
                sel &= ~wclaimed
                wclaimed |= sel
                lobes.append((kh, sel))
        wp = tot = 0.0
        for kh, sel in lobes:
            lp = float(np.sum(p[sel]))
            ref = np.zeros(len(p), dtype=bool)
            ref[max(0, kh - 60) : max(0, kh - 30)] = True
            ref[kh + 30 : kh + 60] = True
            ref &= ~wclaimed
            nl = float(np.mean(p[ref])) * int(sel.sum()) if ref.any() else 0.0
            tot += lp
            if lp > 10 * nl:
                wp += lp - nl
        res["thd_wide_db"] = float(db(wp / fund)) if wp > 0 else None
        res["thd_wide_bound_db"] = float(db(tot / fund)) if tot > 0 else None
        res["thd_wide_hz"] = float(min(thd_wide_hz, 0.45 * fs))
    res["thd_percent"] = float(100 * np.sqrt(hp / fund))
    res["thdn_percent"] = float(100 * np.sqrt(noise_total / fund))
    return res


def dynamic_range(x, fs, f0, nfft=2**18, band=(20.0, 20000.0)):
    """-60 dB method: tone at -60 dB SACD; DR = 60 + (-noise relative to 0 dB SACD level)."""
    p = power_spectrum(x, nfft)
    k0 = tone_bin(f0, nfft, fs)
    mask = band_mask(nfft, fs, *band)
    f = freqs(nfft, fs)
    n_un = notch_noise(p, k0, mask)
    aw = 10 ** (a_weight_db(np.maximum(f, 1e-3)) / 10)
    n_a = notch_noise(p * aw, k0, mask)
    ref = REF_DBFS
    # noise level in dB relative to the 0 dB SACD tone level (rms of a -6.02 dBFS sine)
    ref_rms_dbfs = ref - 3.0103
    return {
        "dr_db": float(ref_rms_dbfs - db(n_un) ),
        "dr_a_db": float(ref_rms_dbfs - db(n_a)),
        "noise_dbfs": float(db(n_un) + SINE_REF_DB),
        "noise_a_dbfs": float(db(n_a) + SINE_REF_DB),
    }


def noise_floor(x, fs, nfft=2**18, nseg=8, bands=((20, 20000), (20000, 40000), (40000, 96000))):
    """Noise in dBFS (rms, re a full-scale sine) over bands, A-weighted 20 Hz..20 kHz, and density.

    ``density_*`` are dBFS per Hz at 1 and 20 kHz, averaged over +-100 Hz and +-1 kHz.
    """
    p = welch(x, nfft, nseg)
    f = freqs(nfft, fs)
    out = {"bands": {}}
    for lo, hi in bands:
        if hi > fs / 2:
            hi = fs / 2
        if lo >= hi:
            continue
        m = (f >= lo) & (f < hi)
        out["bands"][f"{lo}-{hi}"] = float(db(np.sum(p[m])) + SINE_REF_DB)
    m = (f >= 20) & (f <= 20000)
    aw = 10 ** (a_weight_db(np.maximum(f, 1e-3)) / 10)
    out["a_weighted_dbfs"] = float(db(np.sum((p * aw)[m])) + SINE_REF_DB)
    out["unweighted_dbfs"] = float(db(np.sum(p[m])) + SINE_REF_DB)
    df = fs / nfft  # per-bin bandwidth in Hz (power per bin -> per Hz)
    out["density_1k_dbfs_hz"] = float(db(np.mean(p[(f > 900) & (f < 1100)]) / df) + SINE_REF_DB)
    out["density_20k_dbfs_hz"] = float(db(np.mean(p[(f > 19000) & (f < 21000)]) / df) + SINE_REF_DB)
    out["bin_hz"] = float(df)
    out["averages"] = welch_segments(len(x), nfft, nseg)
    return out, f, p


def ultrasonic_peak(x, fs, nfft=2**20, nseg=8, f_lo=20000.0, f_hi=None, bands=None):
    """Ultrasonic noise: density at fixed frequencies, band levels and the 1/3-octave peak.

    Levels are dBFS re a full-scale sine rms (see ``SINE_REF_DB``). ``density_dbfs_hz`` is the
    power per Hz averaged over 1/3 octave around 50, 100 and 200 kHz (when the record reaches
    them), ``integrated_dbfs`` is the power in each band, and ``peak_*`` is the highest 1/3-octave
    density between ``f_lo`` and ``f_hi`` (default 0.4 x fs, inside the decoder's passband). A
    single noisy bin is never reported: the maximum of 10^5 bins reads several dB above the
    noise. When the peak sits within a third of an octave of the upper limit it is the edge of
    the analysis band, not a feature of the noise: ``peak_at_band_edge`` says so.
    """
    p = welch(x, nfft, nseg)
    f = freqs(nfft, fs)
    df = fs / nfft
    hi = f_hi or 0.4 * fs
    third = 2 ** (1 / 6)
    dens = {}
    for fc in (50e3, 100e3, 200e3):
        if fc * third < hi:
            m = (f >= fc / third) & (f < fc * third)
            dens[str(int(fc))] = float(db(np.mean(p[m]) / df) + SINE_REF_DB)
    centres = []
    c = f_lo * third
    while c * third <= hi:
        centres.append(c)
        c *= 2 ** (1 / 3)
    best, bd = None, -1e9
    for c in centres:
        m = (f >= c / third) & (f < c * third)
        d = float(db(np.mean(p[m]) / df) + SINE_REF_DB)
        if d > bd:
            best, bd = c, d
    edge = best is not None and best * 2 ** (1 / 3) * third > hi
    bands = bands or ((20000, 40000), (40000, 96000), (96000, 192000))
    return {"peak_hz": None if best is None else float(best), "peak_density_dbfs_hz": bd,
            "peak_at_band_edge": bool(edge), "density_dbfs_hz": dens, "bin_hz": float(df),
            "averages": welch_segments(len(x), nfft, nseg),
            "integrated_dbfs": {
                f"{lo}-{hi_}": float(db(np.sum(p[(f >= lo) & (f < min(hi_, fs / 2))])) + SINE_REF_DB)
                for lo, hi_ in bands if lo < fs / 2}}


def imd_smpte(x, fs, nfft, f1, f2, orders=4):
    """SMPTE IMD: sidebands at f2 +- n*f1 relative to f2 (f1 low, f2 high tone)."""
    p = power_spectrum(x, nfft)
    ref = lobe_power(p, tone_bin(f2, nfft, fs))
    sb = 0.0
    for n in range(1, orders + 1):
        for s in (-1, 1):
            sb += lobe_power(p, tone_bin(f2 + s * n * f1, nfft, fs))
    # Alternative convention: the sideband amplitudes added arithmetically (as in the SMPTE
    # recommendation) instead of root-sum-square; never lower than ``imd_db``.
    amp = sum(np.sqrt(lobe_power(p, tone_bin(f2 + s * n * f1, nfft, fs)))
              for n in range(1, orders + 1) for s in (-1, 1))
    return {"imd_db": float(db(sb / ref)), "imd_percent": float(100 * np.sqrt(sb / ref)),
            "imd_db_amplitude_sum": float(db(amp**2 / ref))}


def imd_ccif(x, fs, nfft, f1, f2):
    """CCIF IMD: difference products (f2-f1, 2f1-f2, 2f2-f1, 3f1-... up to 3rd order)."""
    p = power_spectrum(x, nfft)
    p1, p2 = lobe_power(p, tone_bin(f1, nfft, fs)), lobe_power(p, tone_bin(f2, nfft, fs))
    ref = p1 + p2
    prods = [f2 - f1, 2 * f1 - f2, 2 * f2 - f1, 3 * f1 - 2 * f2, 3 * f2 - 2 * f1, 2 * (f2 - f1),
             3 * (f2 - f1)]
    lv = 0.0
    nyq = fs / 2
    for fp in prods:
        if 20 < fp < nyq:
            lv += lobe_power(p, tone_bin(fp, nfft, fs))
    # ``imd_db`` is referred to the power sum of the two tones. The IEC 60268-3 convention refers
    # to the sum of their amplitudes, which reads 3.01 dB lower for equal tones.
    return {"imd_db": float(db(lv / ref)), "imd_percent": float(100 * np.sqrt(lv / ref)),
            "imd_db_iec": float(db(lv / (np.sqrt(p1) + np.sqrt(p2)) ** 2))}


def multitone_metrics(x, fs, nfft, tone_bins, nseg=8, step=None, f_max=20000.0):
    """Distortion-free range: tone level minus the highest in-between residual bin.

    Returns the 8-average headline and the 1-average extra. ``step`` is the segment hop
    (default nfft, i.e. no overlap, so periodic coherent tones stay exactly on their bins).
    Tones and residual bins above ``f_max`` (20 kHz, the audio band) are left out of the range:
    the 21.4 kHz tone sits on a decoder's roll-off and would set the figure by itself.

    The window is rectangular because every tone sits on a bin; that is only valid for a record
    that holds whole periods and has nothing outside the analysis band that is not periodic.
    A modulator's ultrasonic noise leaks through a rectangular window at 1/f, so decode it to an
    output rate whose Nyquist frequency is just above the band (see ``measure.multitone``).
    """
    step = step or nfft
    res = {}
    for label, n in (("averaged", nseg), ("avg1", 1)):
        acc = np.zeros(nfft // 2 + 1)
        cnt = 0
        for i in range(n):
            if (i + 1) * step > len(x) and i > 0:
                break
            acc += power_spectrum(x[i * step :], nfft, "rect")
            cnt += 1
        p = acc / cnt
        bins = np.asarray(tone_bins)
        bins = bins[bins * fs / nfft <= f_max]
        tone_p = p[bins]
        mask = np.ones_like(p, dtype=bool)
        mask[:2] = False
        for b in bins:
            mask[b] = False  # coherent tones sit exactly on their bin with a rectangular window
        f = freqs(nfft, fs)
        mask &= f <= f_max
        resid = p[mask]
        res[label] = {
            "tone_min_dbfs": float(db(tone_p.min())),
            "tone_mean_dbfs": float(db(tone_p.mean())),
            "residual_max_dbfs": float(db(resid.max())),
            "residual_mean_dbfs": float(db(resid.mean())),
            "distortion_free_range_db": float(db(tone_p.min()) - db(resid.max())),
            "per_tone_snr_db": [float(v) for v in db(tone_p) - db(resid.mean())],
        }
    res["headline"] = res["averaged"]
    return res


def jtest_metrics(x, fs, nfft=2**20, nseg=8, bits=24, fs_nominal=None, margin_db=6.0, level_dbfs=-3.0):
    """Jitter-like sidebands around fs/4: the largest one above both the noise and the stimulus.

    ``fs_nominal`` is the sample rate the J-Test was generated at (default ``fs``); the tone
    sits at fs_nominal/4 and the sidebands at odd multiples of fs_nominal/192 around it.

    Two things look like sidebands and are not. (1) Noise: each odd position is compared with the
    mean of the two even positions next to it (its own neighbours, where a J-Test has no sideband),
    because the noise of a noise-shaped chain changes by 20 dB or more across 2 to 20 kHz. (2) The stimulus itself:
    fs/4 is 48 x fs/192, so every sideband position is also an odd harmonic (number 48 +- n) of
    the +-1 LSB square wave, which the signal carries at baseband with amplitude (4/pi)/m LSB and
    which a linear device passes unchanged. Each position is compared with that expected level
    too (scaled by the measured carrier). A position counts only when it is ``margin_db`` above
    both. With none, ``largest_sideband_db`` is None and ``noise_floor_db`` (median lobe power of
    the even positions re the carrier) is the result. Levels are lobe powers (+-10 bins), so the
    bin width matters: it is reported.
    """
    fn = fs_nominal or fs
    p = welch(x, nfft, nseg)
    k0 = tone_bin(fn / 4, nfft, fs)
    carrier = lobe_power(p, k0)
    nominal = (10 ** (level_dbfs / 20)) ** 2 / 2  # carrier power as generated
    lsb = 2.0 ** (1 - bits)  # peak of the square wave, 2^-(bits-1)
    spacing = fn / 192
    side, noise, expect, even = {}, [], {}, {}
    for n in range(1, 41):
        for s_ in (-1, 1):
            k = tone_bin(fn / 4 + s_ * n * spacing, nfft, fs)
            if 0 < k < len(p):
                if n % 2:
                    side[s_ * n] = lobe_power(p, k)
                    m = 48 + s_ * n  # harmonic number of the baseband square wave
                    expect[s_ * n] = ((4 / np.pi) * lsb / m) ** 2 / 2 * (carrier / nominal)
                else:
                    even[s_ * n] = lobe_power(p, k)
                    noise.append(even[s_ * n])
    floor = float(np.median(noise)) if noise else 0.0
    gain = 10 ** (margin_db / 10)

    def local_noise(o):
        """Noise at a sideband position: the mean of the even positions on either side of it (the carrier is not one)."""
        nb = [even[q] for q in (o - 1, o + 1) if q in even and q != 0]
        return float(np.mean(nb)) if nb else floor

    found = {o: v for o, v in side.items() if v > local_noise(o) * gain and v > expect[o] * gain}
    count = sum(1 for v in side.values() if db(v) > -130)
    res = {"carrier_dbfs": float(db(carrier)), "noise_floor_db": float(db(floor / carrier)),
           "bin_hz": float(fs / nfft), "sidebands_detected": len(found), "sidebands_above_minus130": int(count),
           "note": "file-level jitter test (arithmetic only)"}
    if found:
        top = max(found, key=found.get)
        res.update({"largest_sideband_db": float(db(found[top] / carrier)), "largest_sideband_order": int(top)})
    else:
        res.update({"largest_sideband_db": None, "largest_sideband_order": None})
    return res


def tone_level_db(x, fs, f0, nfft):
    """RMS level of a coherent tone in dBFS (lobe power -> rms)."""
    return float(db(lobe_power(power_spectrum(x, nfft), tone_bin(f0, nfft, fs))))


def linearity(x, marks, fs, f0, nfft, lead=0.0):
    """Level error per step: measured tone level minus its nominal level (both dBFS rms).

    Each step uses the largest power-of-two segment (at most ``nfft``) after ``lead`` seconds.
    ``f0`` must be coherent for that length (a power-of-two segment of a coherent tone is).
    """
    out = []
    for lv, a, b in marks:
        seg = x[a + int(lead * fs) : b]
        n = min(nfft, 1 << int(np.floor(np.log2(len(seg)))))
        p = power_spectrum(seg, n)
        meas = db(lobe_power(p, tone_bin(f0, n, fs)))
        nominal = lv - 3.0103
        out.append({"level_dbfs": lv, "measured_dbfs": float(meas), "error_db": float(meas - nominal)})
    return out


def crosstalk(driven, silent, fs, f0, nfft=2**18):
    pd = power_spectrum(driven, nfft)
    ps = power_spectrum(silent, nfft)
    k = tone_bin(f0, nfft, fs)
    return float(db(lobe_power(ps, k) / lobe_power(pd, k)))


def channel_match(a, b, fs, f0, nfft=2**18):
    """Gain difference (dB, b - a) and phase difference (degrees, b - a) at f0."""
    w = bh7(nfft)
    A = np.fft.rfft(a[:nfft] * w)
    B = np.fft.rfft(b[:nfft] * w)
    k = tone_bin(f0, nfft, fs)
    sa = A[k - LOBE : k + LOBE + 1].sum() if False else A[k]
    sb = B[k]
    return {"gain_diff_db": float(20 * np.log10(abs(sb) / abs(sa))),
            "phase_diff_deg": float(np.degrees(np.angle(sb / sa)))}


def dc_offset(x):
    m = float(np.mean(x))
    return {"dc": m, "dc_dbfs": float(20 * np.log10(max(abs(m), 1e-300)))}


def polarity(out_pulse, in_pulse):
    """+1 if the output pulse has the same sign as the input pulse, else -1."""
    i = np.argmax(np.abs(in_pulse))
    j = np.argmax(np.abs(out_pulse))
    return "normal" if np.sign(in_pulse[i]) == np.sign(out_pulse[j]) else "inverted"


def gain_error_db(x, fs, expected_dbfs, trim_s=0.5):
    seg = x[int(trim_s * fs) : len(x) - int(0.1 * fs)]
    rms = np.sqrt(np.mean(seg**2))
    return float(20 * np.log10(rms) - (expected_dbfs - 3.0103))


# --- impulse, step, response -------------------------------------------------------------

def impulse_metrics(h, fs, floor_db=-60.0):
    """Ringing before/after the peak, peak position and filter type.

    Ringing counts samples above ``floor_db`` of the peak, raised to 12 dB above the measured
    noise (the rms of the outer eighths of the record) so that a noisy measurement does not
    report noise as ringing. ``floor_used_db`` says which was applied.
    """
    h = np.asarray(h, dtype=np.float64)
    ip = int(np.argmax(np.abs(h)))
    k = max(8, len(h) // 8)
    noise = float(np.sqrt(np.mean(np.concatenate([h[:k], h[-k:]]) ** 2)))
    floor_db = max(floor_db, 20 * np.log10(max(4 * noise, 1e-300) / abs(h[ip])))
    rel = 20 * np.log10(np.maximum(np.abs(h) / abs(h[ip]), 1e-300))
    above = np.where(rel > floor_db)[0]
    pre = int(ip - above.min()) if len(above) else 0
    post = int(above.max() - ip) if len(above) else 0
    e = h**2
    m = min(ip, len(h) - 1 - ip)
    # symmetry about the peak: 1 for a linear-phase filter (pairs h[ip-k], h[ip+k] match)
    pair = float(np.dot(h[ip - m : ip][::-1], h[ip + 1 : ip + 1 + m]))
    sym = abs(2 * pair) / max(e.sum() - e[ip], 1e-300)
    sym = min(sym, 1.0)
    if sym > 0.9:
        kind = "linear phase"
    elif pre <= 0.1 * max(post, 1):
        kind = "minimum phase"
    else:
        kind = "intermediate"
    return {"peak_index": ip, "pre_ringing_samples": pre, "post_ringing_samples": post,
            "pre_ringing_ms": 1000 * pre / fs, "post_ringing_ms": 1000 * post / fs,
            "pre_energy_fraction": float(e[:ip].sum() / e.sum()), "symmetry": sym,
            "floor_used_db": float(floor_db),
            "filter_type": kind}


def step_metrics(s, fs):
    """Overshoot (percent of final value) and 1 percent settling time of a step response."""
    s = np.asarray(s, dtype=np.float64)
    n = len(s)
    if np.mean(s[int(0.9 * n) :]) < 0:
        s = -s  # an inverting device: read the step in its own direction
    final = float(np.mean(s[int(0.9 * n) :]))
    over = 100 * (float(s.max()) - final) / abs(final) if final else float("nan")
    err = np.abs(s - final) > 0.01 * abs(final)
    last = np.where(err)[0]
    start = int(np.argmax(np.abs(s) > 0.01 * abs(final))) if final else 0
    settle = (int(last.max()) - start) / fs * 1000 if len(last) else 0.0
    return {"overshoot_percent": over, "settle_1pct_ms": settle, "final": final}


def response_from_impulse(h, fs, nfft=2**20):
    """Magnitude (dB) and unwrapped phase of an impulse response, frequency axis in Hz."""
    n = max(nfft, len(h))
    H = np.fft.rfft(h, n)
    return np.fft.rfftfreq(n, 1 / fs), 20 * np.log10(np.maximum(np.abs(H), 1e-300)), np.unwrap(np.angle(H))


def group_delay_us(h, fs, nfft=2**20):
    """Group delay in microseconds, constant latency (the peak position) removed."""
    n = max(nfft, len(h))
    ip = int(np.argmax(np.abs(h)))
    k = np.arange(len(h))
    f = np.fft.rfftfreq(n, 1 / fs)
    H = np.fft.rfft(h, n)
    Hk = np.fft.rfft(h * k, n)
    with np.errstate(divide="ignore", invalid="ignore"):
        gd = np.real(Hk / H) / fs  # seconds, from the derivative of the transform
    return f, (gd - ip / fs) * 1e6


def response_metrics(f, mag_db, ref_f=1000.0, passband=(20.0, 20000.0)):
    """Ripple, -0.1/-1/-3 dB frequencies and level at key frequencies relative to 1 kHz."""
    ref = float(np.interp(ref_f, f, mag_db))
    rel = mag_db - ref
    m = (f >= passband[0]) & (f <= passband[1])
    out = {"ripple_pp_db": float(rel[m].max() - rel[m].min())}
    above = f > passband[0]
    for th in (0.1, 1.0, 3.0):
        idx = np.where(above & (rel < -th))[0]
        out[f"minus_{str(th).replace('.', 'p')}_db_hz"] = float(f[idx[0]]) if len(idx) else None
    out["at_hz"] = {str(h): float(np.interp(h, f, rel)) for h in (20, 1000, 10000, 15000, 20000)}
    return out


def alias_images(x, fs, f0, nfft=2**18):
    """Largest non-harmonic component below Nyquist relative to the tone (dB) and its frequency."""
    p = power_spectrum(x, nfft)
    k0 = tone_bin(f0, nfft, fs)
    ref = lobe_power(p, k0)
    skip = np.zeros_like(p, dtype=bool)
    for h in range(1, int(fs / 2 / f0) + 1):
        kk = tone_bin(h * f0, nfft, fs)
        skip[max(0, kk - LOBE) : kk + LOBE + 1] = True
    skip[:5] = True
    q = np.where(skip, 0, p)
    i = int(np.argmax(q))
    return {"image_db": float(db(q[i] / ref)), "image_hz": float(freqs(nfft, fs)[i])}


def spur_report(x, fs, f0, nfft=2**18, floor_db=-100.0):
    """Test 17: largest spur in the audio band and above it, and the count above ``floor_db``."""
    p = power_spectrum(x, nfft)
    k0 = tone_bin(f0, nfft, fs)
    ref = lobe_power(p, k0)
    f = freqs(nfft, fs)
    q = p.copy()
    q[max(0, k0 - LOBE) : k0 + LOBE + 1] = 0
    q[f < 20] = 0
    def top(mask):
        qq = np.where(mask, q, 0)
        i = int(np.argmax(qq))
        return {"db": float(db(lobe_power(qq, i) / ref)), "hz": float(f[i])}
    # count peaks (local maxima above floor)
    pk, _ = signal.find_peaks(db(q / ref), height=floor_db)
    return {"audio_band": top(f <= 20000), "above_audio": top(f > 20000), "count_above": int(len(pk))}


# --- class B: bitstream health -----------------------------------------------------------

def bit_density(bits, window=28):
    """Sliding-window density of +1 bits (fraction), via a cumulative sum."""
    b = (np.asarray(bits) > 0).astype(np.int32)
    c = np.concatenate([[0], np.cumsum(b, dtype=np.int64)])
    return (c[window:] - c[:-window]) / window


def longest_run(bits):
    b = np.asarray(bits) > 0
    d = np.flatnonzero(np.diff(b.astype(np.int8)) != 0)
    edges = np.concatenate([[-1], d, [len(b) - 1]])
    return int(np.max(np.diff(edges)))


class StabilityScan:
    """The density and run figures of ``stability_report``, taken from a record fed in pieces.

    The bit density is the share of +1 bits in a sliding window of ``window`` bits; the scan keeps
    the last ``window - 1`` bits and the open run between pieces, so the result does not depend
    on where the pieces are cut. With ``row`` set, the largest, smallest and mean density of
    every complete block of ``row`` window positions is kept too (the per-second plot).
    Memory is the running results and one piece, not a copy of the record.
    """

    PIECE = 1 << 22

    def __init__(self, window=28, row=None):
        self.w, self.row = window, row
        self.n = self.windows = self.ones = 0
        self.max_c = self.min_c = None
        self._tail = np.zeros(0, dtype=np.int8)
        self._last, self._run, self.longest = None, 0, 0
        self._rows = []  # per row: [largest count, smallest count, sum of counts]

    def feed(self, bits):
        bits = np.asarray(bits)
        for i in range(0, len(bits), self.PIECE):
            self._piece(bits[i : i + self.PIECE] > 0)

    def _piece(self, b):
        self.n += len(b)
        self.ones += int(np.count_nonzero(b))
        d = np.flatnonzero(b[1:] != b[:-1])
        lens = np.diff(np.concatenate([[-1], d, [len(b) - 1]]))
        if self._last is not None and b[0] == self._last:
            lens[0] += self._run
        self.longest = max(self.longest, int(lens.max()))
        self._run, self._last = int(lens[-1]), b[-1]
        ext = np.concatenate([self._tail, b.astype(np.int8)])
        self._tail = ext[len(ext) - (self.w - 1) :] if self.w > 1 else ext[:0]
        if len(ext) < self.w:
            return
        c = np.concatenate([[0], np.cumsum(ext, dtype=np.int32)])
        c = c[self.w :] - c[: -self.w]
        hi, lo = int(c.max()), int(c.min())
        self.max_c = hi if self.max_c is None else max(self.max_c, hi)
        self.min_c = lo if self.min_c is None else min(self.min_c, lo)
        if self.row:
            start = 0
            while start < len(c):
                r = (self.windows + start) // self.row
                end = min(len(c), (r + 1) * self.row - self.windows)
                seg = c[start:end]
                if r == len(self._rows):
                    self._rows.append([int(seg.max()), int(seg.min()), 0])
                row = self._rows[r]
                row[0], row[1] = max(row[0], int(seg.max())), min(row[1], int(seg.min()))
                row[2] += int(seg.sum(dtype=np.int64))
                start = end
        self.windows += len(c)

    def report(self):
        if self.max_c is None:
            raise ValueError("the record is shorter than the density window")
        hi, lo = self.max_c / self.w, self.min_c / self.w
        return {"max_density": float(hi), "min_density": float(lo),
                "max_modulation_pct": float(100 * (2 * hi - 1)), "min_modulation_pct": float(100 * (2 * lo - 1)),
                "saturated": bool(hi >= 1.0 or lo <= 0.0),
                "longest_run": self.longest, "mean_density": float(self.ones / self.n)}

    def rows(self):
        """Largest, smallest and mean modulation (percent) of each complete row of window positions."""
        done = self.windows // self.row
        out = [(100 * (2 * (r[0] / self.w) - 1), 100 * (2 * (r[1] / self.w) - 1),
                100 * (2 * (r[2] / self.w / self.row) - 1)) for r in self._rows[:done]]
        return np.array(out).reshape(-1, 3).T


def stability_report(bits, fs_dsd, window=28):
    scan = StabilityScan(window)
    scan.feed(bits)
    return scan.report()
