"""Known-answer cases for every analyser, shared by the tests and ``scripts/validate.py``.

Each case builds a signal whose answer is known from construction (an exact formula, never a
measurement) and returns rows::

    {"metric": ..., "case": ..., "truth": float, "ours": float, "ref": float or None,
     "tol_truth": dB-or-unit, "tol_ref": ...}

``truth`` is what the signal was built to contain. ``ours`` is ``dsd_measure.analyse``.
``ref`` is the independent implementation in ``refanalyser.py`` (None where it has no
counterpart). ``check(row)`` returns a list of failure strings; an empty list means the row passes.
``quick`` limits the sizes so the whole set runs in about a minute; ``quick=False`` adds the
long records (2^20 points, 15 s of noise) and more rates.
"""

import numpy as np
from scipy import signal

import refanalyser as ra
from dsd_measure import analyse as an
from dsd_measure import signals as sg
from dsd_measure.levels import REF_DBFS

REF_FS = 352800
SR = 10 * np.log10(2.0)  # noise dBFS is re the rms of a full-scale sine: mean square + 3.01 dB
SEED = 20261124


def _row(metric, case, truth, ours, ref=None, tol_truth=0.1, tol_ref=0.1):
    return {"metric": metric, "case": case, "truth": float(truth), "ours": float(ours),
            "ref": None if ref is None else float(ref), "tol_truth": tol_truth, "tol_ref": tol_ref}


def check(r):
    out = []
    if abs(r["ours"] - r["truth"]) > r["tol_truth"]:
        out.append(f"{r['metric']} [{r['case']}]: ours {r['ours']:.4f} vs truth {r['truth']:.4f}"
                   f" (tolerance {r['tol_truth']})")
    if r["ref"] is not None and abs(r["ours"] - r["ref"]) > r["tol_ref"]:
        out.append(f"{r['metric']} [{r['case']}]: ours {r['ours']:.4f} vs reference {r['ref']:.4f}"
                   f" (tolerance {r['tol_ref']})")
    return out


def nfft_at(fs):
    """The analysis length with the same bin spacing as 2^18 points at 352.8 kHz."""
    return max(int(round(2**18 * fs / REF_FS)), 2**12)


def _db(v):
    return 10 * np.log10(v)


def _band_noise_power(sigma, fs, lo=20.0, hi=20000.0):
    """Power of white noise of standard deviation ``sigma`` inside [lo, hi] Hz."""
    return sigma**2 * (hi - lo) / (fs / 2)


def _aw_white(sigma, fs):
    """A-weighted 20 Hz-20 kHz power of white noise of standard deviation ``sigma``."""
    return _aw_integral(lambda f: np.full_like(f, sigma**2 / (fs / 2)))


def _aw_integral(psd_fn, lo=20.0, hi=20000.0):
    f = np.linspace(lo, hi, 400001)
    return float(np.trapezoid(psd_fn(f) * ra.a_weight_mag(f) ** 2, f))


# ---------------------------------------------------------------------------- tone analysis

def tone_rows(quick=True):
    rows = []
    rng = np.random.default_rng(SEED)
    rates = [(352800, 2**18), (96000, 2**16), (44100, 2**15)] if not quick else [(352800, 2**18), (44100, 2**15)]
    levels = [-6.0, -60.0] if quick else [-6.0, -20.0, -60.0, -90.0]
    for fs, n in rates:
        f0 = sg.coherent_freq(1000, fs, n)
        t = np.arange(n) / fs
        for lvl in levels:
            a = 10 ** (lvl / 20)
            p1 = a**2 / 2
            for rel in (-60.0, -100.0, -120.0, -140.0) + (() if quick else (-150.0, -160.0)):
                # 3rd harmonic at ``rel`` dB below the fundamental plus white noise 10 dB below
                # the harmonic (noise as large as the harmonic makes a single record's THD
                # uncertain by about 0.3 dB, for any method), so THD is ``rel`` and THD+N is
                # 10 log10(1.1) more
                hp = p1 * 10 ** (rel / 10)
                sigma = np.sqrt(0.1 * hp / (19980 / (fs / 2)))
                x = (a * np.sin(2 * np.pi * f0 * t) + np.sqrt(2 * hp) * np.sin(2 * np.pi * 3 * f0 * t + 0.7)
                     + sigma * rng.standard_normal(n))
                m = an.tone_metrics(x, fs, f0, n)
                case = f"{fs / 1000:g} kHz, {lvl:g} dBFS, 3rd harmonic at {rel:g} dB, noise 10 dB lower"
                th = ra.thd_harmonics(x, fs, f0)
                sf = ra.thdn_sinefit(x, fs, f0)
                rows.append(_row("fundamental level, dBFS rms", case, _db(p1), m["fundamental_dbfs"],
                                 sf["fund_dbfs"], 0.002, 0.002))
                rows.append(_row("THD, dB", case, rel, m["thd_db"], th["thd_db"], 0.1, 0.1))
                rows.append(_row("THD+N, dB", case, _db(10 ** (rel / 10) * 1.1), m["thdn_db"], sf["thdn_db"], 0.1, 0.1))
                if fs == 352800 and lvl == -6.0:
                    nt = ra.thdn_notch(x, fs, f0)
                    rows.append(_row("THD+N, dB (notch method)", case, _db(10 ** (rel / 10) * 1.1),
                                     m["thdn_db"], nt["thdn_db"], 0.1, 0.1))
                    # A-weighted: the harmonic at 3 kHz and the noise are weighted, the tone is
                    # referred to its own weighted level
                    w3 = ra.a_weight_mag(3 * f0) ** 2
                    wn = _aw_white(sigma, fs)
                    w1 = ra.a_weight_mag(f0) ** 2
                    truth_aw = _db((hp * w3 + wn) / (p1 * w1))
                    rows.append(_row("THD+N A-weighted, dB", case, truth_aw, m["thdn_a_db"],
                                     ra.thdn_sinefit(x, fs, f0, weighted=True)["thdn_db"], 0.1, 0.1))
    return rows


def tone_edge_rows():
    """Tone frequency at the ends of the band and at non-coherent frequencies."""
    rows = []
    fs, n = REF_FS, 2**18
    rng = np.random.default_rng(SEED + 1)
    t = np.arange(n) / fs
    for f in (20.0, 25.0, 30.0, 40.0, 100.0, 5000.0, 6000.0, 9000.0):
        f0 = sg.coherent_freq(f, fs, n)
        a = 10 ** (-6 / 20)
        rel2, rel3 = -80.0, -100.0
        x = (a * np.sin(2 * np.pi * f0 * t) + a * 10 ** (rel2 / 20) * np.sin(2 * np.pi * 2 * f0 * t)
             + a * 10 ** (rel3 / 20) * np.sin(2 * np.pi * 3 * f0 * t + 1) + 3e-7 * rng.standard_normal(n))
        m = an.tone_metrics(x, fs, f0, n)
        # a harmonic above the 20 kHz band edge is not counted (THD: harmonics inside the band)
        hsum = 10 ** (rel2 / 10) + (10 ** (rel3 / 10) if 3 * f0 <= 20000 else 0.0)
        truth_thd = _db(hsum)
        noise = _band_noise_power(3e-7, fs)
        truth_thdn = _db(hsum + noise / (a**2 / 2))
        rows.append(_row("THD, dB", f"{f:g} Hz tone", truth_thd, m["thd_db"],
                         ra.thd_harmonics(x, fs, f0)["thd_db"], 0.05, 0.05))
        rows.append(_row("THD+N, dB", f"{f:g} Hz tone", truth_thdn, m["thdn_db"],
                         ra.thdn_sinefit(x, fs, f0)["thdn_db"], 0.05, 0.05))
    # Non-coherent tones: the window's leakage sets a floor (see docs/accuracy.md)
    for frac in (0.1, 0.25, 0.5):
        f0 = (743 + frac) * fs / n
        x = sg.sine(f0, -6.0, fs, n)
        m = an.tone_metrics(x, fs, f0, n)
        rows.append(_row("THD+N floor, dB, non-coherent", f"{frac} bin off", -300.0, max(m["thdn_db"], -300.0),
                         None, 140.1, 0.0))  # ours must read -160 dB or lower (|-300 - ours| <= 140.1)
        rows.append(_row("fundamental level, dBFS rms", f"non-coherent, {frac} bin off", _db(10 ** (-6 / 10) / 2),
                         m["fundamental_dbfs"], None, 0.002, 0.0))
    return rows


def quantisation_rows():
    """Signals stored the way files store them: 16 and 24 bit with TPDF dither, float32."""
    rows = []
    rng = np.random.default_rng(SEED + 2)
    fs, n = REF_FS, 2**18
    f0 = sg.coherent_freq(1000, fs, n)
    x = sg.sine(f0, -6.0, fs, n)
    p1 = 10 ** (-6 / 10) / 2
    for bits in (16, 24):
        q = 2.0 ** (bits - 1)
        d = (rng.random(n) - rng.random(n))  # TPDF, +-1 LSB
        y = np.round(x * q + d) / q
        # TPDF dither (variance 1/6 LSB^2) + rounding (1/12 LSB^2), spread over 0..fs/2
        noise = (1 / q) ** 2 * (1 / 6 + 1 / 12)
        truth = _db(noise * 19980 / (fs / 2) / p1)
        m = an.tone_metrics(y, fs, f0, n)
        rows.append(_row("THD+N, dB", f"{bits}-bit TPDF-dithered -6 dBFS tone",
                         truth, m["thdn_db"], ra.thdn_sinefit(y, fs, f0)["thdn_db"], 0.1, 0.1))
        z = np.zeros(n)  # silence, dithered: A-weighted noise floor
        z = np.round(z * q + d) / q
        o, _, _ = an.noise_floor(np.tile(z, 4), fs, nfft=2**16, nseg=8)
        rows.append(_row("noise 20 Hz-20 kHz, dBFS", f"{bits}-bit TPDF-dithered silence",
                         _db(noise * 19980 / (fs / 2)) + SR, o["unweighted_dbfs"],
                         ra.noise_dbfs(np.tile(z, 4), fs), 0.1, 0.1))
    # float32 storage: relative rounding error 2^-24 per sample, uniform within one binade
    y = x.astype(np.float32).astype(np.float64)
    m = an.tone_metrics(y, fs, f0, n)
    err = y - x
    rows.append(_row("THD+N, dB", "float32-stored -6 dBFS tone (storage floor)",
                     _db(np.sum(err**2) / n * 19980 / (fs / 2) / p1), m["thdn_db"],
                     ra.thdn_sinefit(y, fs, f0)["thdn_db"], 0.3, 0.3))
    return rows


# ---------------------------------------------------------------------------- noise

def noise_rows(quick=True):
    rows = []
    rng = np.random.default_rng(SEED + 3)
    cases = [(352800, 2**16), (352800, 2**18), (44100, 2**15)]
    if not quick:
        cases += [(352800, 2**20), (705600, 2**19), (96000, 2**16)]
    for fs, nf in cases:
        sigma = 3e-6
        secs = 14 if nf < 2**20 else 24
        x = sigma * rng.standard_normal(int(fs * secs))
        o, _, _ = an.noise_floor(x, fs, nfft=nf, nseg=8)
        case = f"white, {fs / 1000:g} kHz, {nf} points x 8"
        rows.append(_row("noise 20 Hz-20 kHz, dBFS", case, _db(_band_noise_power(sigma, fs)) + SR,
                         o["unweighted_dbfs"], ra.noise_dbfs(x, fs), 0.15, 0.15))
        wn = _aw_white(sigma, fs)
        rows.append(_row("noise A-weighted, dBFS", case, _db(wn) + SR, o["a_weighted_dbfs"],
                         ra.noise_dbfs(x, fs, weighted=True), 0.15, 0.15))
        rows.append(_row("noise density at 1 kHz, dBFS/Hz", case, _db(sigma**2 / (fs / 2)) + SR,
                         o["density_1k_dbfs_hz"], None, 0.7, 0.0))  # single-realisation scatter, see docs
    # shaped noise built in the frequency domain, so the truth is the integral of a known PSD
    fs, n = REF_FS, 2**20
    f = np.fft.rfftfreq(n, 1 / fs)
    for name, shape in (("pink (1/f)", lambda f: 1e-14 * 1000.0 / np.maximum(f, 1.0)),
                        ("rising 6 dB/octave", lambda f: 1e-15 * (np.maximum(f, 1.0) / 1000.0) ** 2),
                        ("rising 12 dB/octave", lambda f: 1e-16 * (np.maximum(f, 1.0) / 1000.0) ** 4)):
        psd = shape(f)  # power per Hz, one-sided
        mag = np.sqrt(psd * fs * n / 2 / 2)  # |X_k| so that the one-sided power per Hz is psd
        spec = mag * (rng.standard_normal(len(f)) + 1j * rng.standard_normal(len(f)))
        spec[0] = 0
        x = np.fft.irfft(spec, n)
        truth_u = _db(float(np.trapezoid(psd[(f >= 20) & (f <= 20000)], f[(f >= 20) & (f <= 20000)]))) + SR
        truth_a = _db(_aw_integral(shape)) + SR
        o, _, _ = an.noise_floor(x, fs, nfft=2**18, nseg=8)
        case = f"{name}, 352.8 kHz"
        rows.append(_row("noise 20 Hz-20 kHz, dBFS", case, truth_u, o["unweighted_dbfs"],
                         ra.noise_dbfs(x, fs, nseg=2**17), 0.25, 0.25))
        rows.append(_row("noise A-weighted, dBFS", case, truth_a, o["a_weighted_dbfs"],
                         ra.noise_dbfs(x, fs, weighted=True, nseg=2**17), 0.25, 0.25))
        # band 20-40 kHz
        b2 = _db(float(np.trapezoid(psd[(f >= 20000) & (f < 40000)], f[(f >= 20000) & (f < 40000)]))) + SR
        rows.append(_row("noise 20-40 kHz, dBFS", case, b2, o["bands"]["20000-40000"],
                         ra.noise_dbfs(x, fs, 20000, 39999.99, nseg=2**17), 0.3, 0.3))
    return rows


def band_edge_rows():
    """Noise blocks just inside and just outside the 20 Hz and 20 kHz edges (built bin by bin)."""
    rows = []
    fs, n = REF_FS, 2**20
    f = np.fft.rfftfreq(n, 1 / fs)
    rng = np.random.default_rng(SEED + 8)

    def block(lo, hi, power):
        """Time signal with ``power`` (mean square) spread evenly over the bins in [lo, hi]."""
        sel = (f >= lo) & (f <= hi)
        spec = np.zeros(len(f), dtype=complex)
        spec[sel] = np.exp(2j * np.pi * rng.random(sel.sum()))
        x = np.fft.irfft(spec, n)
        return x * np.sqrt(power / np.mean(x**2))

    p = 10 ** (-120 / 10)
    for name, inside, outside in (("upper edge", (19000.0, 19900.0), (20100.0, 21000.0)),
                                  ("lower edge", (30.0, 3000.0), (4.0, 10.0))):
        x = block(*inside, p) + block(*outside, 100 * p)  # the outside block is 20 dB louder
        o, _, _ = an.noise_floor(x, fs, nfft=2**18, nseg=8)
        rows.append(_row("noise 20 Hz-20 kHz, dBFS", f"{name}: block inside, 20 dB louder block outside",
                         _db(p) + SR, o["unweighted_dbfs"], ra.noise_dbfs(x, fs, nseg=2**17), 0.1, 0.1))
        # a tone with the same two blocks: THD+N must also exclude the outside block
        f0 = sg.coherent_freq(1000, fs, 2**18)
        tone = sg.sine(f0, -6.0, fs, 2**18)
        m = an.tone_metrics(tone + (block(*inside, p) + block(*outside, 100 * p))[: 2**18], fs, f0, 2**18)
        rows.append(_row("THD+N, dB", f"{name}: block inside, 20 dB louder block outside", _db(p / (10 ** (-6 / 10) / 2)),
                         m["thdn_db"], None, 0.5, 0.0))
    return rows


def dynamic_range_rows():
    rows = []
    rng = np.random.default_rng(SEED + 4)
    fs, n = REF_FS, 2**18
    f0 = sg.coherent_freq(1000, fs, n)
    for noise_db in (-100.0, -120.0, -140.0):
        # noise sigma such that 20 Hz-20 kHz power is noise_db dBFS
        sigma = np.sqrt(10 ** (noise_db / 10) / (19980 / (fs / 2)))
        x = sg.sine(f0, REF_DBFS - 60, fs, n) + sigma * rng.standard_normal(n)
        r = an.dynamic_range(x, fs, f0, n)
        rows.append(_row("dynamic range -60 dB method, dB", f"noise {noise_db:g} dBFS",
                         REF_DBFS - 3.0103 - noise_db, r["dr_db"], REF_DBFS - ra.noise_dbfs(
                             x - sg.sine(f0, REF_DBFS - 60, fs, n), fs), 0.1, 0.15))
        wn = _aw_white(sigma, fs)
        rows.append(_row("dynamic range A-weighted, dB", f"noise {noise_db:g} dBFS",
                         REF_DBFS - 3.0103 - _db(wn), r["dr_a_db"], None, 0.1, 0.0))
    return rows


# ---------------------------------------------------------------------------- intermodulation

def imd_rows():
    rows = []
    fs, n = REF_FS, 2**18
    # SMPTE: 60 Hz + 7 kHz, 4:1; y = x + a2 x^2 + a3 x^3
    x, (f1, f2) = sg.smpte(fs, n, n)
    a1 = 4 / 5 * 10 ** (REF_DBFS / 20)
    a2 = 1 / 5 * 10 ** (REF_DBFS / 20)
    for k2, k3 in ((1e-3, 0.0), (0.0, 1e-3), (1e-4, 1e-4), (1e-5, 1e-5)):
        y = x + k2 * x**2 + k3 * x**3
        # Sideband amplitudes from the polynomial: k2 x^2 puts k2 a1 a2 at f2 +- f1; k3 x^3 puts
        # 3/4 k3 a1^2 a2 at f2 +- 2 f1. (x^3 also adds 3/2 k3 a2 (a1^2 + a2^2/... ) to f2 itself,
        # a gain change of at most 1e-3 x a2^2, which moves the reference by < 0.01 dB.)
        amp1 = k2 * a1 * a2  # at f2 +- f1
        amp2 = 0.75 * k3 * a1**2 * a2  # at f2 +- 2 f1
        pwr = 2 * (amp1**2 / 2) + 2 * (amp2**2 / 2)
        truth = _db(pwr / (a2**2 / 2))
        r = an.imd_smpte(y, fs, n, f1, f2)
        rows.append(_row("IMD SMPTE, dB", f"a2={k2:g}, a3={k3:g}", truth, r["imd_db"],
                         ra.imd_smpte(y, fs, f1, f2)["imd_db"], 0.1, 0.1))
        amp_sum = 2 * amp1 + 2 * amp2
        rows.append(_row("IMD SMPTE, dB (amplitude-sum convention)", f"a2={k2:g}, a3={k3:g}",
                         _db(amp_sum**2 / a2**2), r["imd_db_amplitude_sum"], None, 0.1, 0.0))
    # CCIF: 19 kHz + 20 kHz, equal tones
    x, (g1, g2) = sg.ccif(fs, n, n)
    a = 10 ** (REF_DBFS / 20) / 2
    for k2, k3 in ((1e-3, 0.0), (0.0, 1e-3), (1e-4, 1e-4)):
        y = x + k2 * x**2 + k3 * x**3
        d2 = k2 * a * a * 1  # amplitude at f2 - f1: k2 * 2 * a*a * (1/2) = k2 a^2
        d3 = 0.75 * k3 * a**3  # at 2 f1 - f2 and 2 f2 - f1 (21 kHz is below Nyquist here)
        pwr = d2**2 / 2 + 2 * d3**2 / 2
        # products counted by the analyser also include 3rd-order terms at 2(f2-f1)=2 kHz from
        # k2 x^2 (none: x^2 has f2-f1 and 2 f1, 2 f2, f1+f2) and 3(f2-f1)=3 kHz from x^3 (none)
        truth = _db(pwr / (2 * a**2 / 2))
        r = an.imd_ccif(y, fs, n, g1, g2)
        rows.append(_row("IMD CCIF, dB", f"a2={k2:g}, a3={k3:g}", truth, r["imd_db"],
                         ra.imd_ccif(y, fs, g1, g2)["imd_db"], 0.1, 0.1))
        rows.append(_row("IMD CCIF, dB (IEC 60268-3 convention)", f"a2={k2:g}, a3={k3:g}",
                         _db(pwr / (2 * a) ** 2 * 2), r["imd_db_iec"], None, 0.1, 0.0))
    return rows


# ---------------------------------------------------------------------------- stereo

def stereo_rows():
    rows = []
    fs, n = REF_FS, 2**18
    f0 = sg.coherent_freq(1000, fs, n)
    x = sg.sine(f0, REF_DBFS, fs, n)
    rng = np.random.default_rng(SEED + 5)
    for xt in (-60.0, -100.0, -130.0, -150.0):
        leak = 10 ** (xt / 20) * np.roll(x, 3) + 1e-9 * rng.standard_normal(n)  # phase-shifted leak
        rows.append(_row("crosstalk, dB", f"{xt:g} dB", xt, an.crosstalk(x, leak, fs, f0, n),
                         _db(ra.fit_freqs(leak, fs, [f0])[0] ** 2 / ra.fit_freqs(x, fs, [f0])[0] ** 2),
                         0.05, 0.05))
    for g, ph in ((0.5, 0.0), (-0.1, 5.0), (0.01, -30.0)):
        y = 10 ** (g / 20) * sg.sine(f0, REF_DBFS, fs, n, phase=np.radians(ph))
        m = an.channel_match(x, y, fs, f0, n)
        rows.append(_row("channel gain difference, dB", f"{g:g} dB, {ph:g} deg", g, m["gain_diff_db"], None, 0.002, 0.0))
        rows.append(_row("channel phase difference, deg", f"{g:g} dB, {ph:g} deg", ph, m["phase_diff_deg"], None, 0.01, 0.0))
    return rows


# ---------------------------------------------------------------------------- response, delay

def response_rows():
    rows = []
    fs = REF_FS
    # (a) a Butterworth low-pass has an analytic magnitude and group delay
    for order, fc in ((4, 22000.0), (6, 30000.0)):
        b, a = signal.butter(order, fc, fs=fs)
        h = signal.lfilter(b, a, np.r_[1.0, np.zeros(80000)])
        f, mag, _ = an.response_from_impulse(h, fs, nfft=2**20)
        rm = an.response_metrics(f, mag)
        fgrid = np.linspace(1.0, fs / 2 * 0.99, 2_000_001)
        _, hg = signal.freqz(b, a, worN=fgrid, fs=fs)
        rel_g = 20 * np.log10(np.abs(hg) / np.abs(hg[np.searchsorted(fgrid, 1000.0)]))
        for th, key in ((0.1, "minus_0p1_db_hz"), (1.0, "minus_1p0_db_hz"), (3.0, "minus_3p0_db_hz")):
            # exact digital response from the coefficients (not the FFT of the impulse response)
            truth = float(fgrid[np.argmax(rel_g < -th)])
            rows.append(_row(f"-{th:g} dB frequency, Hz", f"Butterworth {order}, fc {fc:g}", truth, rm[key], None, 1.0, 0.0))
        w = np.array([100.0, 1000.0, 5000.0, 15000.0, 20000.0])
        _, gd_t = signal.group_delay((b, a), w=w, fs=fs)
        f2, gd = an.group_delay_us(h, fs, nfft=2**20)
        ip = int(np.argmax(np.abs(h)))
        g = np.interp(w, f2, gd) + ip / fs * 1e6
        refgd = ra.group_delay_s(h, fs, w) * 1e6
        for i, fw in enumerate(w):
            rows.append(_row("group delay, us", f"Butterworth {order}, fc {fc:g}, {fw:g} Hz",
                             gd_t[i] / fs * 1e6, g[i], refgd[i], 0.01, 0.01))
        # in-band magnitude against scipy's analytic response
        _, hh = signal.freqz(b, a, worN=w, fs=fs)
        rows.append(_row("magnitude at 15 kHz, dB", f"Butterworth {order}, fc {fc:g}", 20 * np.log10(abs(hh[3])),
                         float(np.interp(15000, f, mag)), ra.response(h, fs, [15000.0])[0][0], 0.001, 0.001))
    # (b) a known ripple: three-tap echo filter H = 1 + e cos(2 pi f m / fs)
    for e, m in ((0.01, 9), (0.002, 9), (0.0005, 11)):
        h = np.zeros(2 * m + 1)
        h[m] = 1.0
        h[0] = h[-1] = e / 2
        f, mag, _ = an.response_from_impulse(h, fs, nfft=2**20)
        rm = an.response_metrics(f, mag)
        fg = np.linspace(20, 20000, 400001)
        hh = 1 + e * np.cos(2 * np.pi * fg * m / fs)
        truth = ref_ripple = 20 * np.log10(hh.max() / hh.min())
        # response is relative to 1 kHz, so the ripple (max minus min) is unaffected by it
        rows.append(_row("passband ripple p-p, dB", f"echo e={e:g}, m={m}", truth, rm["ripple_pp_db"],
                         ref_ripple, 0.0005, 0.0005))
    # (c) linear-phase FIR: group delay is exactly (N-1)/2 samples
    h = signal.firwin(1001, 30000, fs=fs, window=("kaiser", 14))
    w = np.array([100.0, 5000.0, 15000.0])
    f2, gd = an.group_delay_us(h, fs, nfft=2**20)
    for fw in w:
        rows.append(_row("group delay (linear phase, constant removed), us", f"FIR 1001 taps, {fw:g} Hz", 0.0,
                         float(np.interp(fw, f2, gd)), None, 0.001, 0.0))
    return rows


def impulse_step_rows():
    rows = []
    fs = REF_FS
    h = np.zeros(4096)
    c = 2048
    h[c] = 1.0
    h[c - 37] = 0.01      # -40 dB, 37 samples before
    h[c - 100] = 0.0005   # -66 dB, below the -60 dB ringing floor
    h[c + 55] = 0.002     # -54 dB
    r = an.impulse_metrics(h, fs)
    rows.append(_row("pre-ringing, samples", "known echoes", 37, r["pre_ringing_samples"], None, 0.0, 0.0))
    rows.append(_row("post-ringing, samples", "known echoes", 55, r["post_ringing_samples"], None, 0.0, 0.0))
    # step response of a 2nd-order system: overshoot exp(-pi z / sqrt(1 - z^2))
    for zeta in (0.3, 0.5, 0.7):
        wn = 2 * np.pi * 20000
        tt = np.arange(0, 0.002, 1 / fs)
        _, y = signal.step(signal.lti([wn**2], [1, 2 * zeta * wn, wn**2]), T=tt)
        s = an.step_metrics(y, fs)
        truth = 100 * np.exp(-np.pi * zeta / np.sqrt(1 - zeta**2))
        rows.append(_row("step overshoot, percent", f"2nd order, zeta {zeta}", truth, s["overshoot_percent"], None, 0.2, 0.0))
        # 1 % settling time: last sample outside +-1 % of the final value, brute force
        fin = y[-1]
        last = np.where(np.abs(y - fin) > 0.01 * fin)[0].max()
        first = np.where(np.abs(y) > 0.01 * fin)[0][0]
        rows.append(_row("step settling 1 %, ms", f"2nd order, zeta {zeta}", (last - first) / fs * 1000,
                         s["settle_1pct_ms"], None, 0.01, 0.0))
    return rows


def dc_polarity_rows():
    rows = []
    fs, n = 44100, 2**15
    f0 = sg.coherent_freq(1000, fs, n)
    for dc in (1e-3, 1e-5, 1e-7):
        x = sg.sine(f0, -6.0, fs, n) + dc
        rows.append(_row("DC offset, dBFS", f"{dc:g} with a -6 dBFS tone", 20 * np.log10(dc),
                         an.dc_offset(x)["dc_dbfs"], 20 * np.log10(abs(np.mean(x - sg.sine(f0, -6.0, fs, n)))), 0.01, 0.01))
    p = sg.polarity_pulse()
    lp = signal.lfilter(*signal.butter(2, 0.2), p)
    rows.append(_row("polarity (1 = normal)", "low-pass filtered pulse", 1, 1 if an.polarity(lp, p) == "normal" else -1, None, 0, 0))
    rows.append(_row("polarity (1 = normal)", "inverted filtered pulse", -1, 1 if an.polarity(-lp, p) == "normal" else -1, None, 0, 0))
    for g in (-0.5, 0.0, 0.3):
        x = sg.sine(f0, REF_DBFS + g, fs, fs * 3)
        rows.append(_row("gain error, dB", f"{g:+g} dB", g, an.gain_error_db(x, fs, REF_DBFS), None, 0.005, 0.0))
    return rows


# ---------------------------------------------------------------------------- spectral tests

def multitone_rows():
    rows = []
    fs, nf = REF_FS, 2**20
    x, f, bins = sg.multitone_standard()
    rng = np.random.default_rng(SEED + 6)
    ref = np.tile(x, 8)
    spur_db = -110.0
    k = int(bins[10]) + 1
    spur = 10 ** (spur_db / 20) * np.sqrt(2) * np.sin(2 * np.pi * k * np.arange(len(ref)) / nf)
    y = ref + spur
    r2 = an.multitone_metrics(y, fs, nf, bins)
    rows.append(_row("multitone residual peak, dBFS", "spur at -110 dBFS (rms) between tones", spur_db,
                     r2["headline"]["residual_max_dbfs"], None, 0.1, 0.0))
    # white noise at a known level: mean residual bin power
    sigma = 1e-6
    y = ref + sigma * rng.standard_normal(len(ref))
    r3 = an.multitone_metrics(y, fs, nf, bins)
    # rect window, power per bin = sigma^2 / (nf/2) for a one-sided spectrum of nf points
    rows.append(_row("multitone residual mean, dBFS per bin", "white noise 1e-6", _db(sigma**2 / (nf / 2)),
                     r3["averaged"]["residual_mean_dbfs"], None, 0.15, 0.0))
    return rows


def spur_rows():
    rows = []
    fs, n = REF_FS, 2**18
    x, f0 = sg.tone_15k(fs, n, n)
    t = np.arange(n) / fs
    a = 10 ** (-12 / 20)
    for fsp, rel in ((7000.0, -80.0), (12000.0, -110.0), (35000.0, -120.0)):
        g = sg.coherent_freq(fsp, fs, n)
        y = x + a * 10 ** (rel / 20) * np.sin(2 * np.pi * g * t)
        r = an.spur_report(y, fs, f0, n)
        key = "audio_band" if g <= 20000 else "above_audio"
        rows.append(_row("spur level, dB re tone", f"{g:.0f} Hz at {rel:g} dB", rel, r[key]["db"], None, 0.05, 0.0))
        rows.append(_row("spur frequency, Hz", f"{g:.0f} Hz", g, r[key]["hz"], None, fs / n, 0.0))
    # ultrasonic noise: a tone at 61 kHz and white noise with a known density
    rng = np.random.default_rng(SEED + 7)
    sigma = 1e-6
    tt = np.arange(fs * 12) / fs
    y = sigma * rng.standard_normal(fs * 12) + 10 ** (-70 / 20) * np.sqrt(2) * np.sin(2 * np.pi * 61000.0 * tt)
    u = an.ultrasonic_peak(y, fs, nfft=2**18, nseg=8)
    rows.append(_row("ultrasonic peak 1/3-octave centre, Hz", "tone at 61 kHz", 61000.0, u["peak_hz"], None,
                     61000 * (2 ** (1 / 6) - 1), 0.0))
    rows.append(_row("ultrasonic integrated 40-96 kHz, dBFS", "tone at -70 dBFS rms", -70.0 + SR,
                     u["integrated_dbfs"]["40000-96000"], None, 0.1, 0.0))
    w = sigma * rng.standard_normal(fs * 12)
    uw = an.ultrasonic_peak(w, fs, nfft=2**18, nseg=8)
    for k in ("50000", "100000"):
        rows.append(_row("ultrasonic density, dBFS/Hz", f"white noise at {int(k) // 1000} kHz", _db(sigma**2 / (fs / 2)) + SR,
                         uw["density_dbfs_hz"][k], None, 0.1, 0.0))
    return rows


def jtest_rows():
    fs = 44100
    x = sg.jtest(fs, 2**20)
    r = an.jtest_metrics(x, fs, 2**18, nseg=2)
    rng = np.random.default_rng(SEED + 12)
    clean = sg.sine(fs / 4, -3.0, fs, 2**20) + 3e-8 * rng.standard_normal(2**20)  # tone and noise, no sideband
    c = an.jtest_metrics(clean, fs, 2**18, nseg=2)
    # a real sideband: 5 x fs/192 above the carrier at -120 dB re the carrier (power), on top of the J-Test
    t = np.arange(2**20) / fs
    inj = x + 10 ** (-3 / 20) * 10 ** (-120 / 20) * np.sin(2 * np.pi * (fs / 4 + 5 * fs / 192) * t)
    j = an.jtest_metrics(inj, fs, 2**18, nseg=2)
    return [_row("J-Test carrier, dBFS rms", "24-bit", -3 - 3.0103, r["carrier_dbfs"], None, 0.01, 0.0),
            # the stimulus carries the square wave's own harmonics at the sideband positions: not sidebands
            _row("J-Test sidebands found (1 = yes)", "the J-Test signal as generated", 0.0, float(r["sidebands_detected"] > 0), None, 0.0, 0.0),
            _row("J-Test sidebands found (1 = yes)", "tone and noise only", 0.0, float(c["sidebands_detected"] > 0), None, 0.0, 0.0),
            _row("J-Test sideband level, dB re carrier", "injected at -120 dB, order +5", -120.0,
                 j["largest_sideband_db"] if j["largest_sideband_db"] is not None else 0.0, None, 0.5, 0.0),
            _row("J-Test sideband order", "injected at order +5", 5.0, float(j["largest_sideband_order"] or 0), None, 0.0, 0.0)]


def all_rows(quick=True):
    rows = []
    rows += tone_rows(quick)
    rows += tone_edge_rows()
    rows += quantisation_rows()
    rows += noise_rows(quick)
    rows += band_edge_rows()
    rows += dynamic_range_rows()
    rows += imd_rows()
    rows += stereo_rows()
    rows += response_rows()
    rows += impulse_step_rows()
    rows += dc_polarity_rows()
    rows += multitone_rows()
    rows += spur_rows()
    rows += jtest_rows()
    rows += a_weighting_rows()
    return rows


# IEC 61672-1:2013 Table 3 (A weighting at the exact one-third-octave frequencies 10^(n/10), dB).
IEC_A = {
    10.0: -70.4, 12.5893: -63.4, 15.8489: -56.7, 19.9526: -50.5, 25.1189: -44.7, 31.6228: -39.4,
    39.8107: -34.6, 50.1187: -30.2, 63.0957: -26.2, 79.4328: -22.5, 100.0: -19.1, 125.893: -16.1,
    158.489: -13.4, 199.526: -10.9, 251.189: -8.6, 316.228: -6.6, 398.107: -4.8, 501.187: -3.2,
    630.957: -1.9, 794.328: -0.8, 1000.0: 0.0, 1258.93: 0.6, 1584.89: 1.0, 1995.26: 1.2, 2511.89: 1.3,
    3162.28: 1.2, 3981.07: 1.0, 5011.87: 0.5, 6309.57: -0.1, 7943.28: -1.1, 10000.0: -2.5,
    12589.3: -4.3, 15848.9: -6.6, 19952.6: -9.3,
}


def a_weighting_rows():
    rows = []
    for f, v in IEC_A.items():
        rows.append(_row("A-weighting, dB", f"{f:g} Hz (IEC 61672-1 table)", v, float(an.a_weight_db(f)),
                         float(ra.a_weight_db(f)), 0.1, 0.01))
    return rows
