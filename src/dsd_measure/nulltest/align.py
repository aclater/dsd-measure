"""Alignment of two tracks at one rate: delay (whole and fractional samples), polarity and gain.

Delay: a whole-sample estimate from the normalised cross-correlation of the first differences of
both signals, band-limited to the alignment band (20 Hz to 20 kHz, or less when the devices' passbands
are narrower), which sharpens the peak of bass-heavy music and keeps level, polarity and ultrasonic noise out
of the search; then a fractional refinement that maximises the cross-spectrum
phase coherence ``Re sum conj(A_k) B_k exp(j w_k tau)`` over the same band. That is the band-limited
(sinc) interpolation of the correlation peak, so the result is not limited to the sample grid.
The fractional shift is applied with a Kaiser-windowed sinc of 512 taps (160 dB stopband), flat to
0.479 x the rate; the analysis band stops at 0.45 x the rate, so the interpolation adds nothing there.
"""

import numpy as np
from scipy import optimize, signal

FRAC_HALF = 256  # half length of the fractional-delay filter, in samples
FRAC_ATTEN = 160.0
EST_BAND_HZ = (20.0, 20000.0)  # default alignment band
DIFF_FLOOR_DB = 70.0  # a band counts as a cut only where the stronger device is within this of its own mid-band level
CUT_DB = 20.0  # a device is cut where it is this far below the other, relative to the level in the mid band
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


def _bandlimit(x, rate, band):
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / rate)
    X[(f < band[0]) | (f > band[1])] = 0
    return np.fft.irfft(X, len(x))


def _coarse(a, track_b, ch, s, max_lag, rate, band):
    """Whole-sample lag, sign and the normalised peak (1 for identical band-limited signals)."""
    n = len(a)
    b = track_b.read(ch, s - max_lag, s + n + max_lag)
    wa, wb = np.diff(_bandlimit(a, rate, band)), np.diff(_bandlimit(b, rate, band))
    # c[j] = sum_n wb[j+n] * wa[n]  for lags m = j - max_lag
    c = signal.fftconvolve(wb, wa[::-1], mode="valid")
    cs = np.concatenate([[0.0], np.cumsum(wb * wb)])
    eb = cs[len(wa):] - cs[:len(cs) - len(wa)]  # energy of B under each lag
    norm = np.sqrt(np.maximum(eb, 1e-12 * float(np.max(eb))) * float(np.dot(wa, wa)))
    r = c / norm
    j = int(np.argmax(np.abs(r)))
    return j - max_lag, float(np.sign(c[j]) or 1.0), float(abs(r[j]))


def _fine(a, track_b, ch, s, d0, rate, band):
    n = len(a)
    b = track_b.read(ch, s + d0, s + d0 + n)
    w = np.hanning(n)
    fa, fb = np.fft.rfft(a * w), np.fft.rfft(b * w)
    k = np.arange(len(fa))
    om = 2 * np.pi * k / n
    hz = k * rate / n
    keep = (hz >= band[0]) & (hz <= min(band[1], 0.45 * rate))
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


def estimate_passbands(track_a, track_b, ch, n0, n1, rate, span=1 << 17, spans=4):
    """Each device's bandwidth, from its own spectrum against the other's: (bandwidth of A, of B) in Hz, None if not cut.

    Both devices decode the same source, so the ratio of their spectra is flat where both pass and departs where one is
    cut, whatever the music does (quiet music gives a small level in both, not a small ratio). Levels are summed in
    twelfth-octave bands from 200 Hz to 0.45 x the rate. The reference ratio is the median from 200 Hz to 8 kHz. A device is
    cut from the lowest band above 2 kHz from which at least two consecutive bands (a sixth of an octave) are ``CUT_DB`` or more below the other
    device (relative to the reference ratio); the cut is that band's lower edge. The departure lasts until the other
    device's own cut, where both are noise and the ratio returns to the reference, or until the top. When it ends below the
    top, the end is the other device's bandwidth. A departed band counts only where the stronger device holds energy
    above ``DIFF_FLOOR_DB`` below its own mid-band level (per Hz): two noise floors that differ are not a cut.
    """
    span = min(span, (n1 - n0) // spans)
    pa = pb = 0.0
    for i in range(spans):
        s = n0 + (n1 - n0 - span) * i // max(spans - 1, 1)
        f, p = signal.welch(track_a.read(ch, s, s + span), rate, nperseg=8192)
        pa = pa + p
        pb = pb + signal.welch(track_b.read(ch, s, s + span), rate, nperseg=8192)[1]
    edges = 200.0 * 2 ** (np.arange(0, 128) / 12)
    edges = edges[edges <= 0.45 * rate]
    lo, hi = edges[:-1], edges[1:]
    la = np.array([pa[(f >= l) & (f < h)].sum() for l, h in zip(lo, hi, strict=True)])
    lb = np.array([pb[(f >= l) & (f < h)].sum() for l, h in zip(lo, hi, strict=True)])
    ok = (la > 0) & (lb > 0)
    d = np.where(ok, 10 * np.log10(np.where(ok, lb, 1) / np.where(ok, la, 1)), 0.0)
    mid = (lo >= 200) & (hi <= 8000) & ok
    if not mid.any():
        return None, None
    rel = d - np.median(d[mid])
    width = hi - lo  # power per Hz: a wide band at the top is compared with a narrow one in the mid band
    floor = np.median(la[mid] / width[mid]) * width * 10 ** (-DIFF_FLOOR_DB / 10), np.median(lb[mid] / width[mid]) * width * 10 ** (-DIFF_FLOOR_DB / 10)

    def departure(sign):
        """The first run of two or more departed bands from 2 kHz: (first band, band after the last), or None."""
        strong = lb >= floor[1] if sign > 0 else la >= floor[0]  # the floors are per band
        gone = (sign * rel >= CUT_DB) & strong & (lo >= 2000)
        i = 0
        while i < len(lo):
            if gone[i]:
                k = i
                while k < len(lo) and gone[k]:
                    k += 1
                if k - i >= 2:
                    return i, k
                i = k
            else:
                i += 1
        return None

    ra, rb = departure(1), departure(-1)  # A is cut where B is far above A; B is cut where B is far below A

    def bandwidth(own, other):
        if own:
            return float(lo[own[0]])
        return float(hi[other[1] - 1]) if other and other[1] < len(lo) else None  # the other device's departure ends where this one's cut is

    return bandwidth(ra, rb), bandwidth(rb, ra)


def estimate_delay(track_a, track_b, ch, n0, n1, rate, max_delay_s=0.5, segments=4, seg_len=SEG_LEN, band=EST_BAND_HZ):
    """Delay of B behind A in samples (positive: B is late), polarity of B (+1 or -1) and the spread.

    Segments are taken from the loudest of eight evenly spaced candidates in ``n0..n1``. A segment
    that cannot be placed because the range is short is shortened. ``band`` is the alignment band in Hz. ``peak_correlation``
    is the median over segments of the normalised in-band correlation at the best lag (1 for the same signal).
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
    ds, pols, peaks = [], [], []
    for s, a in picks:
        if not np.any(a):
            continue
        d0, p0, pk = _coarse(a, track_b, ch, s, max_lag, rate, band)
        tau, p1 = _fine(a, track_b, ch, s, d0, rate, band)
        peaks.append(pk)
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
            "polarity": pol, "segments": len(ds), "peak_correlation": float(np.median(peaks)), "estimates": [float(x) for x in ds]}
