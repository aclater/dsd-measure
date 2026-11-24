"""A deliberately separate, minimal reference analyser (plain numpy).

It shares no code with ``dsd_measure.analyse``, and uses different methods on purpose, so that
agreement between the two means something:

* levels, harmonics and intermodulation products come from a least-squares sine fit in the time
  domain (IEEE 1057 four-parameter fit for the frequency), not from FFT lobes;
* THD+N is the residual of the sine fit, band-limited with a Kaiser window (beta 30) and an
  exact rectangular band, and a second way, AES17-style: a second-order notch at the tone
  followed by the same band limit;
* A-weighting is evaluated from the IEC 61672-1 poles and zeros (exact constants), not from
  the rounded closed-form;
* noise density is a Welch estimate with a Hann window;
* group delay is the negative derivative of the unwrapped phase, not the transform of n*h[n].

Nothing here is fast. It is only for tests and for ``scripts/validate.sh``.
"""

import numpy as np

# IEC 61672-1 constants (Hz), exact to the digits the standard prints.
F1, F2, F3, F4 = 20.598997, 107.65265, 737.86223, 12194.217
SINE_REF_DB = 10 * np.log10(2.0)
_A1000_DB = -2.0  # the A curve (pole-zero form, K=1) is -2.000 dB at 1 kHz


def _a_raw(f):
    s = 1j * 2 * np.pi * np.asarray(f, dtype=np.float64)
    w1, w2, w3, w4 = (2 * np.pi * v for v in (F1, F2, F3, F4))
    return s**4 / ((s + w1) ** 2 * (s + w2) * (s + w3) * (s + w4) ** 2)


_K = 1.0 / abs(_a_raw(1000.0))


def a_weight_db(f):
    """A-weighting gain in dB from the analogue poles and zeros, normalised to 0 dB at 1 kHz."""
    f = np.maximum(np.asarray(f, dtype=np.float64), 1e-6)
    return 20 * np.log10(_K * np.abs(_a_raw(f)))


def a_weight_mag(f):
    return _K * np.abs(_a_raw(np.maximum(np.asarray(f, dtype=np.float64), 1e-6)))


# ----------------------------------------------------------------------- sine fitting

def _wls(m, x):
    """Least squares with a Kaiser (beta 30) weight on every sample.

    An unweighted fit has a rectangular window: the leakage of the wideband noise of a
    delta-sigma decoder (ultrasonic noise at -50 dBFS and above) then lands in every fitted line
    and limits it to about -125 dB. Weighting the samples gives the fit the window's sidelobes.
    """
    w = np.kaiser(len(x), 30.0)
    coef, *_ = np.linalg.lstsq(m * w[:, None], x * w, rcond=None)
    return coef


def fit_sine(x, fs, f_guess, iters=30, fixed=False):
    """IEEE 1057 sine fit: four parameters (frequency refined), or three if ``fixed``.

    Returns dict(freq, amp, phase, offset, residual). With wideband noise in the record (the
    ultrasonic noise of a delta-sigma decoder) the refined frequency is only as good as the
    Cramer-Rao bound allows and a tiny frequency error leaves a tone remnant in the residual,
    so records with a known coherent frequency should use ``fixed=True``.
    """
    x = np.asarray(x, dtype=np.float64)
    n = len(x)
    t = np.arange(n) / fs
    f = float(f_guess)
    for _ in range(0 if fixed else iters):
        w = 2 * np.pi * f
        c, s = np.cos(w * t), np.sin(w * t)
        m = np.stack([c, s, np.ones(n)], axis=1)
        coef, *_ = np.linalg.lstsq(m, x, rcond=None)
        a, b = coef[0], coef[1]
        # derivative of the model with respect to the angular frequency
        dw = t * (-a * s + b * c)
        d = np.stack([c, s, np.ones(n), dw], axis=1)
        r = x - m @ coef
        step, *_ = np.linalg.lstsq(d, r, rcond=None)
        f += step[3] / (2 * np.pi)
        if abs(step[3]) < 1e-14 * w:
            break
    w = 2 * np.pi * f
    c, s = np.cos(w * t), np.sin(w * t)
    m = np.stack([c, s, np.ones(n)], axis=1)
    coef = _wls(m, x)
    res = x - m @ coef
    return {"freq": f, "amp": float(np.hypot(coef[0], coef[1])), "offset": float(coef[2]),
            "phase": float(np.arctan2(coef[0], coef[1])), "residual": res}


def fit_harmonics(x, fs, f0, orders):
    """Least-squares amplitudes of f0 and the listed harmonic orders (list of ints incl. 1)."""
    n = len(x)
    t = np.arange(n) / fs
    cols = []
    for h in orders:
        cols += [np.cos(2 * np.pi * f0 * h * t), np.sin(2 * np.pi * f0 * h * t)]
    cols.append(np.ones(n))
    m = np.stack(cols, axis=1)
    coef = _wls(m, np.asarray(x, dtype=np.float64))
    return {h: float(np.hypot(coef[2 * i], coef[2 * i + 1])) for i, h in enumerate(orders)}


def fit_freqs(x, fs, freqs):
    """Least-squares rms amplitudes of sines at known frequencies (works off-bin too)."""
    n = len(x)
    t = np.arange(n) / fs
    cols = []
    for f in freqs:
        cols += [np.cos(2 * np.pi * f * t), np.sin(2 * np.pi * f * t)]
    cols.append(np.ones(n))
    m = np.stack(cols, axis=1)
    coef = _wls(m, np.asarray(x, dtype=np.float64))
    return [float(np.hypot(coef[2 * i], coef[2 * i + 1]) / np.sqrt(2)) for i in range(len(freqs))]


# ----------------------------------------------------------------------- band power

def _kaiser(n, beta=30.0):
    return np.kaiser(n, beta)


def band_power(r, fs, lo, hi, weight=None, exclude=None):
    """Mean-square of ``r`` inside [lo, hi] Hz by Kaiser-windowed Parseval; optional weight(f).

    ``exclude=(f_lo, f_hi)`` leaves that range out (the notch around the tone).
    """
    n = len(r)
    w = _kaiser(n)
    spec = np.fft.rfft(np.asarray(r, dtype=np.float64) * w)
    p = 2 * np.abs(spec) ** 2 / (n * np.sum(w**2))
    p[0] /= 2
    if n % 2 == 0:
        p[-1] /= 2
    f = np.fft.rfftfreq(n, 1 / fs)
    m = (f >= lo) & (f <= hi)
    if exclude is not None:
        m &= ~((f >= exclude[0]) & (f <= exclude[1]))
    if weight is not None:
        p = p * weight(f) ** 2
    return float(np.sum(p[m]))


def _db(v):
    return 10 * np.log10(max(v, 1e-300))


def thdn_sinefit(x, fs, f0, band=(20.0, 20000.0), weighted=False, refine=True, notch_hz=13.5):
    """THD+N in dB relative to the fitted fundamental, by sine-fit residual.

    ``refine=False`` takes ``f0`` as exact (a coherent tone), see ``fit_sine``. ``notch_hz`` is the
    half-width of the range around the tone left out of the residual, the equivalent of the notch
    of an analyser (the main analyser leaves out +-10 bins = 13.46 Hz): any real converter has
    some energy next to the carrier, and what a notch hides is part of the definition of THD+N.
    """
    fit = fit_sine(x, fs, f0, fixed=not refine)
    res = fit["residual"]
    p_sig = fit["amp"] ** 2 / 2
    wt = a_weight_mag if weighted else None
    p_res = band_power(res, fs, band[0], band[1], wt, exclude=(fit["freq"] - notch_hz, fit["freq"] + notch_hz))
    # the A-weighted figure is referred to the weighted fundamental (gain at f0)
    p_ref = p_sig * (a_weight_mag(fit["freq"]) ** 2 if weighted else 1.0)
    return {"thdn_db": _db(p_res / p_ref), "fund_dbfs": _db(p_sig), "freq": fit["freq"],
            "noise_dbfs": _db(p_res)}


def thdn_notch(x, fs, f0, band=(20.0, 20000.0), q=20.0, cascade=3, trim=8192):
    """AES17-style: notch out the tone in the time domain, then take the band-limited rms.

    The notch is ``cascade`` second-order IIR notches (scipy ``iirnotch``, pre-warped, quality
    factor ``q``) run forwards and backwards (zero phase), so the tone is rejected by far more
    than 150 dB. ``trim`` samples are dropped at both ends, where the filters have not settled.
    The notch also removes a little noise around the tone (about pi/2 x f0/q wide, 0.02 dB
    for white noise at q = 20). The reference level is the least-squares tone amplitude.
    """
    from scipy import signal  # filter design only: the analysis itself is plain numpy

    x = np.asarray(x, dtype=np.float64)
    sos = np.vstack([np.array(signal.tf2sos(*signal.iirnotch(f0, q, fs))) for _ in range(cascade)])
    y = signal.sosfiltfilt(sos, x)[trim:-trim]
    fit = fit_sine(x[trim:-trim], fs, f0, fixed=True)
    p_res = band_power(y, fs, band[0], band[1])
    p_sig = fit["amp"] ** 2 / 2
    return {"thdn_db": _db(p_res / p_sig), "fund_dbfs": _db(p_sig)}


def thd_harmonics(x, fs, f0, nharm=9, band=(20.0, 20000.0), fixed=False):
    """THD in dB (harmonics 2..nharm that fit under the band edge) and the harmonic levels."""
    fit = fit_sine(x, fs, f0, fixed=fixed)
    fx = fit["freq"]
    orders = [h for h in range(1, nharm + 1) if h == 1 or h * fx <= band[1]]
    amp = fit_harmonics(x, fs, fx, orders)
    a1 = amp[1]
    hp = sum(amp[h] ** 2 for h in orders if h >= 2)
    return {"thd_db": _db(hp / a1**2), "amps": amp, "fund_dbfs": _db(a1**2 / 2)}


# ----------------------------------------------------------------------- noise

def welch_psd(x, fs, nseg=2**16, overlap=0.5):
    """One-sided Hann Welch PSD in power per Hz."""
    x = np.asarray(x, dtype=np.float64)
    w = np.hanning(nseg)
    hop = int(nseg * (1 - overlap))
    acc, cnt = 0.0, 0
    for s in range(0, len(x) - nseg + 1, hop):
        acc = acc + np.abs(np.fft.rfft(x[s : s + nseg] * w)) ** 2
        cnt += 1
    psd = 2 * acc / cnt / (fs * np.sum(w**2))
    psd[0] /= 2
    if nseg % 2 == 0:
        psd[-1] /= 2
    return np.fft.rfftfreq(nseg, 1 / fs), psd


def noise_dbfs(x, fs, lo=20.0, hi=20000.0, weighted=False, nseg=2**16):
    """Noise in dBFS re the rms of a full-scale sine (AES17): 10 log10(mean square) + 3.01 dB."""
    f, psd = welch_psd(x, fs, nseg)
    if weighted:
        psd = psd * a_weight_mag(f) ** 2
    df = f[1] - f[0]
    m = (f >= lo) & (f <= hi)
    return _db(float(np.sum(psd[m]) * df)) + SINE_REF_DB


# ----------------------------------------------------------------------- IMD

def imd_smpte(x, fs, f1, f2, orders=4):
    """Rms sum of sidebands f2 +- n f1 (n=1..orders) relative to f2, by least squares."""
    sb = [f2 + s * n * f1 for n in range(1, orders + 1) for s in (-1, 1)]
    a = fit_freqs(x, fs, [f2] + sb)
    return {"imd_db": _db(sum(v**2 for v in a[1:]) / a[0] ** 2)}


def imd_ccif(x, fs, f1, f2):
    prods = [f2 - f1, 2 * f1 - f2, 2 * f2 - f1, 3 * f1 - 2 * f2, 3 * f2 - 2 * f1, 2 * (f2 - f1), 3 * (f2 - f1)]
    prods = [p for p in prods if 20 < p < fs / 2]
    a = fit_freqs(x, fs, [f1, f2] + prods)
    return {"imd_db": _db(sum(v**2 for v in a[2:]) / (a[0] ** 2 + a[1] ** 2))}


# ----------------------------------------------------------------------- transfer functions

def response(h, fs, freqs):
    """Magnitude (dB) and unwrapped phase of an FIR at given frequencies, by direct summation."""
    n = np.arange(len(h))
    e = np.exp(-2j * np.pi * np.outer(freqs, n) / fs)
    hf = e @ h
    return 20 * np.log10(np.abs(hf)), np.unwrap(np.angle(hf)), hf


def group_delay_s(h, fs, freqs, df=1.0):
    """Group delay in seconds as minus the phase slope, by central difference of the phase."""
    fl, fh = np.asarray(freqs) - df, np.asarray(freqs) + df
    _, _, a = response(h, fs, fl)
    _, _, b = response(h, fs, fh)
    dphi = np.angle(b / a)
    return -dphi / (2 * np.pi * 2 * df)
