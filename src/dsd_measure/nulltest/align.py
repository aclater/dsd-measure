"""Alignment of two tracks at one rate: delay (whole and fractional samples), polarity and gain.

Delay: a whole-sample estimate from the cross-correlation of first differences (which sharpens
the peak of bass-heavy music), then a fractional refinement that maximises the cross-spectrum
phase coherence ``Re sum conj(A_k) B_k exp(j w_k tau)`` over the band up to 20 kHz. That is the band-limited
(sinc) interpolation of the correlation peak, so the result is not limited to the sample grid.
The fractional shift is applied with a Kaiser-windowed sinc of 512 taps (160 dB stopband), flat to
0.479 x the rate; the analysis band stops at 0.45 x the rate, so the interpolation adds nothing there.
"""

import numpy as np
from scipy import optimize, signal

FRAC_HALF = 256  # half length of the fractional-delay filter, in samples
FRAC_ATTEN = 160.0
EST_BAND_HZ = 20000.0
SEG_LEN = 1 << 19  # samples per estimation segment (1.5 s at 352.8 kHz, 12 s at 44.1 kHz)


def frac_filter(f, half=FRAC_HALF, atten=FRAC_ATTEN):
    """Taps ``h[k]``, k = -half+1..half, for evaluating a signal at ``n + f`` (0 <= f < 1) from its samples."""
    k = np.arange(-half + 1, half + 1)
    t = f - k
    beta = 0.1102 * (atten - 8.7)
    w = np.i0(beta * np.sqrt(np.clip(1 - (t / half) ** 2, 0, None))) / np.i0(beta)
    h = np.sinc(t) * w
    return h / h.sum()


def shifted(track, ch, start, stop, delay):
    """``track`` at positions ``start+delay .. stop+delay`` (delay in samples, may be fractional)."""
    di = int(np.floor(delay))
    f = delay - di
    if abs(f) < 1e-12:
        return track.read(ch, start + di, stop + di)
    x = track.read(ch, start + di - FRAC_HALF + 1, stop + di + FRAC_HALF)
    h = frac_filter(f)
    return signal.fftconvolve(x, h[::-1], mode="valid")


def _coarse(a, track_b, ch, s, max_lag):
    n = len(a)
    b = track_b.read(ch, s - max_lag, s + n + max_lag)
    wa, wb = np.diff(a), np.diff(b)
    # c[j] = sum_n wb[j+n] * wa[n]  for lags m = j - max_lag
    c = signal.fftconvolve(wb, wa[::-1], mode="valid")
    j = int(np.argmax(np.abs(c)))
    return j - max_lag, float(np.sign(c[j]) or 1.0)


def _fine(a, track_b, ch, s, d0, rate):
    n = len(a)
    b = track_b.read(ch, s + d0, s + d0 + n)
    w = np.hanning(n)
    fa, fb = np.fft.rfft(a * w), np.fft.rfft(b * w)
    k = np.arange(len(fa))
    om = 2 * np.pi * k / n
    keep = k * rate / n <= min(EST_BAND_HZ, 0.45 * rate)
    cross = (np.conj(fa) * fb)[keep]
    om = om[keep]

    def j(tau):
        return float(np.real(np.sum(cross * np.exp(1j * om * tau))))

    grid = np.linspace(-1.0, 1.0, 81)
    vals = np.array([abs(j(t)) for t in grid])
    t0 = grid[int(np.argmax(vals))]
    res = optimize.minimize_scalar(lambda t: -abs(j(t)), bounds=(t0 - 0.05, t0 + 0.05), method="bounded",
                                   options={"xatol": 1e-9})
    return float(res.x), float(np.sign(j(res.x)) or 1.0)


def estimate_delay(track_a, track_b, ch, n0, n1, rate, max_delay_s=0.5, segments=4, seg_len=SEG_LEN):
    """Delay of B behind A in samples (positive: B is late), polarity of B (+1 or -1) and the spread.

    Segments are taken from the loudest of eight evenly spaced candidates in ``n0..n1``. A segment
    that cannot be placed because the range is short is shortened.
    """
    max_lag = int(round(max_delay_s * rate))
    n = min(seg_len, n1 - n0 - 2 * max_lag - 2 * FRAC_HALF)
    if n < 4096:
        raise ValueError("the analysed range is too short to estimate a delay; lower --max-delay or trim less")
    span = n1 - n0 - n - 2 * max_lag
    starts = [n0 + max_lag + int(span * (i + 0.5) / 8) for i in range(8)]
    reads = [(s, track_a.read(ch, s, s + n)) for s in starts]
    reads.sort(key=lambda r: -float(np.sum(r[1] ** 2)))
    picks = sorted(reads[:segments], key=lambda r: r[0])
    ds, pols = [], []
    for s, a in picks:
        if not np.any(a):
            continue
        d0, p0 = _coarse(a, track_b, ch, s, max_lag)
        tau, p1 = _fine(a, track_b, ch, s, d0, rate)
        ds.append(d0 + tau)
        pols.append(p1)
    if not ds:
        raise ValueError("the music is silent in every segment tried; nothing to align")
    pol = 1.0 if sum(pols) >= 0 else -1.0
    delay = float(np.median(ds))
    if abs(delay - round(delay)) < 1e-3:  # a whole-sample delay: use it exactly if it nulls at least as well
        s, a = picks[0]
        n = min(len(a), 1 << 16)
        a = a[:n]

        def resid(dl):
            b = pol * shifted(track_b, ch, s, s + n, dl)
            g = np.dot(a, b) / max(np.dot(b, b), 1e-300)
            return float(np.sum((a - g * b) ** 2))

        if resid(float(round(delay))) <= resid(delay) * 1.0001:
            delay = float(round(delay))
    return {"delay_samples": delay, "spread_samples": float(np.max(ds) - np.min(ds)),
            "polarity": pol, "segments": len(ds), "estimates": [float(x) for x in ds]}
