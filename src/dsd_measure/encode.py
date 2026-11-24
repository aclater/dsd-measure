"""Reference DSD modulator (PCM -> DSD), a documented open design.

Design (all public DSP): the PCM signal is interpolated to the DSD rate with a Kaiser-windowed
linear-phase FIR chain (>150 dB stopband), then passed through a single-bit error-feedback
delta-sigma loop whose noise transfer function (NTF) has Legendre zeros in the audio band and a
Butterworth pole set scaled to a chosen out-of-band gain (Lee's criterion). A stability guard
picks the best design from a ladder (order 8 down to order 5) that does not overload. The loop runs in double precision in a small C
core (``csrc/dsm.c``, built on first use with the system C compiler into a private per-user cache), with a slow pure-Python
fallback. Bits are returned as int8 values +1 / -1.

This is a *reference*, not a product: it is meant to be stable and reproducible.
"""

import ctypes
import hashlib
import os
import stat
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


@lru_cache(maxsize=64)
def design_ntf(order=5, hinf=1.3, fs=DSD_BASE, band=20000.0):
    """Return (b, a), the monic NTF polynomials in z^-1 with max out-of-band gain ``hinf``.

    The pair is kept between calls (the bisection costs 60 filter evaluations) and is read-only.

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
    b, a = make(lo)
    b.setflags(write=False)
    a.setflags(write=False)
    return b, a


#: Stability guard: noise transfer functions to try, best first, per DSD rate (as a multiple of
#: 44.1 kHz x 64). A high-order single-bit loop is only stable up to a certain input level, so
#: the encoder runs the first design and moves down the list when the loop overloads (|w| above
#: ``OVERLOAD_LIMIT`` at the quantiser input). The design actually used is returned in ``info``.
#: Measured limits (1 kHz, single sine): order 8 at 1.45 is stable to 0 dB SACD (-6 dBFS) at DSD64
#: but not at the +3.1 dB SACD peak level; order 8 at 1.3 is stable at the peak level (|w| about
#: 0.9, 1 kHz, 100 Hz and 19 kHz) and reads about 129 dB SINAD there at DSD64. Order 8 at 1.5 is
#: stable at 0 dB SACD too but with |w| above 2, too close to the edge to be a reference. The
#: designs further down are for stretches that overload the ones above. A report names the design
#: each peak-level row used and carries a floor measured with that design.
LADDERS = {
    1: [(8, 1.45), (8, 1.4), (7, 1.4), (8, 1.3), (7, 1.3), (5, 1.3)],
    2: [(7, 1.4), (8, 1.3), (7, 1.3), (5, 1.3)],
    4: [(7, 1.4), (8, 1.3), (7, 1.3), (5, 1.3)],
}
OVERLOAD_LIMIT = 2.0  # stable loops keep |w| near 1 (largest seen about 1.2 at 0 dB SACD)


CFLAGS = ["-O2", "-shared", "-fPIC", "-ffp-contract=off"]


class UnsafeCacheError(RuntimeError):
    """The compiled-core cache is not private to the current user."""


def _cache_dir():
    """The per-user cache directory for the compiled core."""
    own = os.environ.get("DSD_MEASURE_CACHE_DIR")
    if own:
        if not os.path.isabs(own):
            raise ValueError(f"DSD_MEASURE_CACHE_DIR must be an absolute path (it is {own!r}); "
                             "a relative one would silently put the cache somewhere else")
        return Path(own)
    base = os.environ.get("XDG_CACHE_HOME")
    root = Path(base) if base and os.path.isabs(base) else Path.home() / ".cache"
    return root / "dsd-measure"


def _check_private(path, what):
    """Refuse anything that is not ours or that others could write."""
    st = os.lstat(path)
    if stat.S_ISLNK(st.st_mode):
        raise UnsafeCacheError(f"{what} {path} is a symbolic link")
    if st.st_uid != os.geteuid():
        raise UnsafeCacheError(f"{what} {path} is owned by another user")
    if st.st_mode & 0o022:
        raise UnsafeCacheError(f"{what} {path} is writable by group or others (mode {st.st_mode & 0o7777:o})")
    return st


def _private_dir(d):
    d.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.mkdir(d, 0o700)
    except FileExistsError:
        pass
    st = _check_private(d, "cache directory")
    if not stat.S_ISDIR(st.st_mode):
        raise UnsafeCacheError(f"{d} is not a directory")
    if st.st_mode & 0o077:
        raise UnsafeCacheError(f"cache directory {d} is accessible to others (mode {st.st_mode & 0o7777:o})")
    return d


def _build_lib(cache=None):
    """Compile ``csrc/dsm.c`` into the private cache (atomic rename) and return the library path."""
    src = Path(__file__).with_name("csrc") / "dsm.c"
    tag = hashlib.sha256(src.read_bytes() + " ".join(CFLAGS).encode()).hexdigest()[:16]
    d = _private_dir(Path(cache) if cache else _cache_dir())
    out = d / f"dsm_{tag}.so"
    if out.exists() or out.is_symlink():
        _check_private(out, "compiled core")
        return out
    fd, tmp = tempfile.mkstemp(prefix=".build-", suffix=".so", dir=d)  # 0600, same directory
    os.close(fd)
    try:
        subprocess.run(["cc", *CFLAGS, str(src), "-o", tmp], check=True, stdout=subprocess.DEVNULL,
                       stderr=subprocess.PIPE)
        os.chmod(tmp, 0o700)
        os.replace(tmp, out)  # atomic: a reader sees the whole file or none
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    _check_private(out, "compiled core")
    return out


@lru_cache(maxsize=1)
def _lib():
    lib = ctypes.CDLL(str(_build_lib()))
    lib.dsm_run.restype = ctypes.c_int
    return lib


def _modulate(u, b, a, limit=OVERLOAD_LIMIT, use_c=True, state=None, wmax0=0.0, v=None):
    """Returns (bits, overload_count, max |w|).

    ``state`` is the pair of history buffers (``ebuf``, ``sbuf``, updated in place) and ``wmax0``
    the largest |w| so far: a long signal passed in pieces, with the same ``state``, gives the same
    bits as the whole signal in one call. ``v`` is an int8 array of ``len(u)`` to write into.
    """
    order = len(a) - 1
    n = len(u)
    if v is None:
        v = np.empty(n, dtype=np.int8)
    ebuf, sbuf = state if state is not None else (np.zeros(order), np.zeros(order))
    if use_c:
        u = np.ascontiguousarray(u, dtype=np.float64)
        bb = np.ascontiguousarray(b)
        aa = np.ascontiguousarray(a)
        dp = ctypes.POINTER(ctypes.c_double)
        wmax = ctypes.c_double(wmax0)
        over = _lib().dsm_run(
            u.ctypes.data_as(dp), v.ctypes.data_as(ctypes.POINTER(ctypes.c_byte)),
            ctypes.c_size_t(n), bb.ctypes.data_as(dp), aa.ctypes.data_as(dp),
            order, ebuf.ctypes.data_as(dp), sbuf.ctypes.data_as(dp), ctypes.c_double(limit),
            ctypes.byref(wmax))
        return v, over, wmax.value
    over, wmax = 0, wmax0
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


#: Input samples per piece of a stage: long signals are filtered piece by piece so the working
#: memory stays small (the result does not depend on where the pieces are cut, except by rounding).
PIECE = 1 << 20


def _upsample_pieces(chunks, n, L, h):
    """Yield ``_upsample`` of a signal of ``n`` samples, one piece (``PIECE`` input samples) at a time.

    ``chunks`` is the signal in any number of consecutive arrays. Only the input a piece still
    needs is kept, so a stage's memory is a few pieces however long the signal is. The pieces are
    cut at the same input positions whatever the chunks are, so the output is the same bits of
    arithmetic as the whole signal in one call.
    """
    half = (len(h) - 1) // 2
    hs = h * L
    branches = []
    for p in range(L):
        r = (p + half) % L
        branches.append(((p + half - r) // L, hs[r::L]))
    ahead = max(off for off, _ in branches)
    chunks = iter(chunks)
    buf, base = np.empty(0), 0  # the input held: samples base .. base + len(buf) - 1
    for s in range(0, n, PIECE):
        e = min(n, s + PIECE)
        while base + len(buf) < min(n, e + ahead):
            buf = np.concatenate([buf, np.asarray(next(chunks), dtype=np.float64)])
        y = np.empty((e - s) * L)
        for p, (off, hp) in enumerate(branches):
            lo = max(0, s + off - (len(hp) - 1))  # the first input sample that outputs s..e-1 meet
            c = signal.oaconvolve(buf[lo - base : min(n, e + off) - base], hp)
            seg = c[s + off - lo : e + off - lo]
            y[p : p + len(seg) * L : L] = seg
            if len(seg) < e - s:  # past the end of the signal the input is zero
                y[len(seg) * L + p :: L] = 0.0
        yield y
        keep = min(max(0, e + off - (len(hp) - 1)) for off, hp in branches)
        buf, base = buf[keep - base :], keep


def _upsample(x, L, h):
    """Zero-stuff ``x`` by ``L`` and filter with ``L * h`` (odd length), keeping ``len(x) * L`` centred samples.

    The same sum as ``scipy.signal.resample_poly(x, L, 1, window=h)``, computed one polyphase
    branch at a time with SciPy's FFT overlap-add convolution instead of the direct form: output
    ``q * L + p`` only meets the taps ``h[r::L]`` with ``r = (p + half) % L``. The two differ by
    rounding only (about 4e-15 of full scale, -287 dB; ``tests/test_perf.py`` holds the bound).
    """
    n = len(x)
    y = np.empty(n * L)
    pos = 0
    for piece in _upsample_pieces([x], n, L, h):
        y[pos : pos + len(piece)] = piece
        pos += len(piece)
    return y


def _stages(ratio):
    """The factors of an integer interpolation ratio: x2 first, then 3, 5 and 7."""
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
    return stages


def _stage_filters(stages, atten_db):
    beta = 0.1102 * (atten_db - 8.7)
    out = []
    for i, L in enumerate(stages):
        ntaps = 2047 if i == 0 else 255
        # stage 0 keeps the audio band (cutoff 93 % of the input Nyquist frequency); later
        # stages only reject images, so the cutoff sits at the input Nyquist frequency.
        frac = 0.93 if i == 0 else 1.0
        out.append((L, signal.firwin(ntaps, frac / L, window=("kaiser", beta))))
    return out


def _interpolate_pieces(x, ratio, atten_db=160.0):
    """``interpolate(x, ratio)`` (the FFT method) as a stream of arrays, one stage feeding the next piece by piece."""
    n = len(x)
    pieces = [np.asarray(x, dtype=np.float64)]
    for L, h in _stage_filters(_stages(ratio), atten_db):
        pieces = _upsample_pieces(pieces, n, L, h)
        n *= L
    return pieces


def interpolate(x, ratio, atten_db=160.0, method="fft"):
    """Integer-ratio interpolation by a chain of x2 (then odd) Kaiser-windowed FIR stages.

    ``method="fft"`` (the default) runs each stage as FFT convolutions; ``method="direct"`` is the
    direct-form polyphase filter of 0.1.1 (``scipy.signal.resample_poly``), kept as the reference
    the fast path is tested against. Same filters, same output to rounding.
    """
    if method not in ("fft", "direct"):
        raise ValueError(f"method must be 'fft' or 'direct', not {method!r}")
    y = np.asarray(x, dtype=np.float64)
    if method == "direct":
        for L, h in _stage_filters(_stages(ratio), atten_db):
            y = signal.resample_poly(y, L, 1, window=h)
        return y
    out = np.empty(len(y) * int(ratio))
    pos = 0
    for piece in _interpolate_pieces(y, ratio, atten_db):
        out[pos : pos + len(piece)] = piece
        pos += len(piece)
    return out


#: Interpolator used by ``encode``: "fft" or "direct" (see ``interpolate``). Part of the cache key.
INTERPOLATOR = "fft"


def encode(x, fs, dsd_rate=DSD_BASE, order=None, hinf=None, headroom=1.0):
    """PCM (1-D float) at ``fs`` -> DSD bits (int8 +-1) at ``dsd_rate``. Returns (bits, info).

    With ``order`` and ``hinf`` unset the stability guard picks the best design in ``LADDERS``
    for this rate and signal; ``info["ntf"]`` names it and ``info["fallbacks"]`` counts the
    designs skipped because the loop overloaded. With both set that one design is used.

    The result is deterministic, so it is kept in the per-user stimulus cache (``stimcache``) and
    read back, checked by hash, when the same call comes again.
    """
    ratio = dsd_rate // fs
    if ratio * fs != dsd_rate:
        raise ValueError("dsd_rate must be an integer multiple of fs")
    from . import stimcache
    k = None
    if stimcache.enabled():
        k = stimcache.key(np.asarray(x, dtype=np.float64), fs, dsd_rate, order, hinf, headroom, INTERPOLATOR)
        hit = stimcache.load(k)
        if hit is not None:
            return hit
    mult = max(1, dsd_rate // DSD_BASE)
    ladder = [(order, hinf)] if order and hinf else LADDERS.get(mult, LADDERS[4])
    tries = 0
    c_core = True
    for i, (o, h) in enumerate(ladder):
        b, a = design_ntf(o, h, fs=dsd_rate)
        last = i == len(ladder) - 1
        try:
            bits, over, wmax, peak = _encode_design(x, ratio, b, a, headroom, True, last)
        except (OSError, subprocess.CalledProcessError, FileNotFoundError):
            sys.stderr.write("dsd-measure: C core unavailable, using slow Python modulator\n")
            c_core = False
            bits, over, wmax, peak = _encode_design(x, ratio, b, a, headroom, False, last)
        if over == 0:
            break
        tries += 1
    info = {"order": o, "hinf": h, "ntf": f"order {o}, max gain {h}", "overload_samples": int(over),
            "fallbacks": tries, "max_w": round(float(wmax), 3), "dsd_rate": dsd_rate,
            "peak_input": float(peak)}
    if k is not None and c_core:  # only what the compiled core made is kept
        stimcache.store(k, bits, info)
    return bits, info


def _encode_design(x, ratio, b, a, headroom, use_c, run_on):
    """Interpolate and modulate with one design, piece by piece: the working memory is the bits plus a few pieces.

    The loop state is carried from piece to piece, so the bits are those of the whole signal in
    one call. Returns (bits, overload count, max |w|, peak input). A design that overloads is
    given up at the first overloaded piece unless ``run_on``: its bits are not used.
    """
    n = len(x) * ratio
    if INTERPOLATOR == "direct":
        pieces = [interpolate(x, ratio, method="direct")]
    else:
        pieces = _interpolate_pieces(np.asarray(x, dtype=np.float64), ratio)
    bits = np.empty(n, dtype=np.int8)
    state = (np.zeros(len(a) - 1), np.zeros(len(a) - 1))
    pos, over, wmax, peak = 0, 0, 0.0, 0.0
    for up in pieces:
        up = up * headroom
        peak = max(peak, float(np.max(np.abs(up))))
        m = len(up)
        _, o, wmax = _modulate(up, b, a, use_c=use_c, state=state, wmax0=wmax, v=bits[pos : pos + m])
        over += o
        pos += m
        if over and not run_on:
            break
    return bits, over, wmax, peak
