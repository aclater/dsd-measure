"""Reference DSD modulator (PCM -> DSD), a documented open design.

Design (all public DSP): the PCM signal is interpolated to the DSD rate with a Kaiser-windowed
linear-phase FIR chain (>150 dB stopband), then passed through a single-bit error-feedback
delta-sigma loop whose noise transfer function (NTF) has Legendre zeros in the audio band and a
Butterworth pole set scaled to a chosen out-of-band gain (Lee's criterion). A stability guard
picks the best design from a ladder (order 8 down to order 5) that does not overload. The loop runs in double precision in a small C
core (``csrc/dsm.c``, built on first use with the system C compiler), with a slow pure-Python
fallback. Bits are returned as int8 values +1 / -1.

This is a *reference*, not a product: it is meant to be stable, transparent and reproducible.
"""

import ctypes
import hashlib
import subprocess
import sys
import tempfile
from functools import lru_cache
from pathlib import Path

import numpy as np
from scipy import signal

DSD_BASE = 44100 * 64  # DSD64


def _legendre_zeros(order, fs, band):
    """In-band NTF zeros at the roots of the Legendre polynomial of degree ``order``.

    These minimise the integrated in-band noise power (Schreier and Temes, *Understanding
    Delta-Sigma Data Converters*, sec. 4.3); an odd order puts one zero at DC.
    """
    roots = np.sort(np.polynomial.legendre.leggauss(order)[0])
    zeros = []
    for r in roots[roots > 1e-9]:
        w = 2 * np.pi * r * band / fs
        zeros += [np.exp(1j * w), np.exp(-1j * w)]
    if order % 2:
        zeros.append(1.0 + 0j)
    return np.array(zeros)


def design_ntf(order=5, hinf=1.3, fs=DSD_BASE, band=20000.0):
    """Return (b, a), the monic NTF polynomials in z^-1 with max out-of-band gain ``hinf``.

    Zeros: Legendre positions inside the audio band; poles: a Butterworth high-pass whose corner
    is bisected until the largest NTF gain is ``hinf`` (Lee's rule, sec. 4.4.1 of the same book).
    """
    zeros = _legendre_zeros(order, fs, band)
    b = np.real(np.poly(zeros))

    def make(wn):
        _, poles, _ = signal.butter(order, wn, "high", output="zpk")
        return b, np.real(np.poly(poles))

    def gain(wn):
        bb, aa = make(wn)
        _, h = signal.freqz(bb, aa, worN=1 << 14)
        return np.max(np.abs(h))

    lo, hi = 1e-4, 0.9
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if gain(mid) > hinf:
            hi = mid
        else:
            lo = mid
    return make(lo)


#: Stability guard: noise transfer functions to try, best first, per DSD rate (as a multiple of
#: 44.1 kHz x 64). A high-order single-bit loop is only stable up to a certain input level, so
#: the encoder runs the first design and moves down the list when the loop overloads (|w| above
#: ``OVERLOAD_LIMIT`` at the quantiser input). The design actually used is returned in ``info``.
#: Measured limits (1 kHz, single sine): order 8 at 1.45 is stable to 0 dB SACD (-6 dBFS) at DSD64
#: but not at the +3.1 dB SACD peak level; order 5 at 1.3 is stable at the peak level. Order 8 at
#: 1.5 is stable at 0 dB SACD too but with |w| above 2, too close to the edge to be a reference.
LADDERS = {
    1: [(8, 1.45), (8, 1.4), (7, 1.4), (7, 1.3), (5, 1.3)],
    2: [(7, 1.4), (7, 1.3), (5, 1.3)],
    4: [(7, 1.4), (7, 1.3), (5, 1.3)],
}
OVERLOAD_LIMIT = 2.0  # stable loops keep |w| near 1 (largest seen about 1.2 at 0 dB SACD)


@lru_cache(maxsize=1)
def _lib():
    src = Path(__file__).with_name("csrc") / "dsm.c"
    tag = hashlib.sha256(src.read_bytes()).hexdigest()[:12]
    out = Path(tempfile.gettempdir()) / f"dsd_measure_dsm_{tag}.so"
    if not out.exists():
        subprocess.run(
            ["cc", "-O2", "-shared", "-fPIC", str(src), "-o", str(out)],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )
    lib = ctypes.CDLL(str(out))
    lib.dsm_run.restype = ctypes.c_int
    return lib


def _modulate(u, b, a, limit=OVERLOAD_LIMIT, use_c=True):
    """Returns (bits, overload_count, max |w|)."""
    order = len(a) - 1
    n = len(u)
    v = np.empty(n, dtype=np.int8)
    ebuf = np.zeros(order)
    sbuf = np.zeros(order)
    if use_c:
        u = np.ascontiguousarray(u, dtype=np.float64)
        bb = np.ascontiguousarray(b)
        aa = np.ascontiguousarray(a)
        dp = ctypes.POINTER(ctypes.c_double)
        wmax = ctypes.c_double(0.0)
        over = _lib().dsm_run(
            u.ctypes.data_as(dp), v.ctypes.data_as(ctypes.POINTER(ctypes.c_byte)),
            ctypes.c_size_t(n), bb.ctypes.data_as(dp), aa.ctypes.data_as(dp),
            order, ebuf.ctypes.data_as(dp), sbuf.ctypes.data_as(dp), ctypes.c_double(limit),
            ctypes.byref(wmax))
        return v, over, wmax.value
    over, wmax = 0, 0.0
    for i in range(n):
        acc = 0.0
        for k in range(1, order + 1):
            acc += (b[k] - a[k]) * ebuf[k - 1] - a[k] * sbuf[k - 1]
        w = u[i] + acc
        q = 1.0 if w >= 0 else -1.0
        over += abs(w) > limit
        wmax = max(wmax, abs(w))
        ebuf[1:] = ebuf[:-1].copy()
        sbuf[1:] = sbuf[:-1].copy()
        ebuf[0] = q - w
        sbuf[0] = acc
        v[i] = int(q)
    return v, over, wmax


def interpolate(x, ratio, atten_db=160.0):
    """Integer-ratio interpolation by a chain of x2 (then odd) Kaiser-windowed FIR stages."""
    ratio = int(ratio)
    stages, r = [], ratio
    while r % 2 == 0:
        stages.append(2)
        r //= 2
    for p in (3, 5, 7):
        while r % p == 0:
            stages.append(p)
            r //= p
    if r != 1:
        raise ValueError(f"unsupported ratio {ratio}")
    y = np.asarray(x, dtype=np.float64)
    beta = 0.1102 * (atten_db - 8.7)
    for i, L in enumerate(stages):
        ntaps = 2047 if i == 0 else 255
        # stage 0 keeps the audio band (cutoff 93 % of the input Nyquist frequency); later
        # stages only reject images, so the cutoff sits at the input Nyquist frequency.
        frac = 0.93 if i == 0 else 1.0
        h = signal.firwin(ntaps, frac / L, window=("kaiser", beta))
        y = signal.resample_poly(y, L, 1, window=h)
    return y


def encode(x, fs, dsd_rate=DSD_BASE, order=None, hinf=None, headroom=1.0):
    """PCM (1-D float) at ``fs`` -> DSD bits (int8 +-1) at ``dsd_rate``. Returns (bits, info).

    With ``order`` and ``hinf`` unset the stability guard picks the best design in ``LADDERS``
    for this rate and signal; ``info["ntf"]`` names it and ``info["fallbacks"]`` counts the
    designs skipped because the loop overloaded. With both set that one design is used.
    """
    ratio = dsd_rate // fs
    if ratio * fs != dsd_rate:
        raise ValueError("dsd_rate must be an integer multiple of fs")
    up = interpolate(x, ratio) * headroom
    mult = max(1, dsd_rate // DSD_BASE)
    ladder = [(order, hinf)] if order and hinf else LADDERS.get(mult, LADDERS[4])
    tries = 0
    for o, h in ladder:
        b, a = design_ntf(o, h, fs=dsd_rate)
        try:
            bits, over, wmax = _modulate(up, b, a)
        except (OSError, subprocess.CalledProcessError, FileNotFoundError):
            sys.stderr.write("dsd-measure: C core unavailable, using slow Python modulator\n")
            bits, over, wmax = _modulate(up, b, a, use_c=False)
        if over == 0:
            break
        tries += 1
    info = {"order": o, "hinf": h, "ntf": f"order {o}, max gain {h}", "overload_samples": int(over),
            "fallbacks": tries, "max_w": round(float(wmax), 3), "dsd_rate": dsd_rate,
            "peak_input": float(np.max(np.abs(up)))}
    return bits, info
