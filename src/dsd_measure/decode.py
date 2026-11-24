"""Reference DSD -> PCM decoder: a long linear-phase FIR, the "perfect DAC" of docs/footprint.md.

Written from public DSP principles. A chain of Kaiser-windowed FIR decimators (160 dB stopband),
each with the pass edge at ``keep`` Hz and the stop edge at ``fs_out - keep`` Hz, so anything that
aliases lands above ``keep`` and never inside it. ``keep`` is 20 kHz for output rates up to
176.4 kHz (a flat response to 20 kHz, then a transition that ends at the first alias-free edge)
and 0.4 x the output rate above that, so wide outputs (352.8 / 705.6 kHz) are usable for
ultrasonic analysis up to 0.4 x the output rate. All arithmetic is float64.
"""

import numpy as np
from scipy import signal

BASE = 352800
ATTEN_DB = 160.0


def keep_edge(out_rate, passband=20000.0):
    return passband if out_rate <= 176400 else 0.4 * out_rate


def _ntaps(fs, width_hz, atten=ATTEN_DB):
    n = int(np.ceil((atten - 8) / (2.285 * 2 * np.pi * width_hz / fs)))
    return n | 1


def decimator(fs_in, q, keep, atten=ATTEN_DB):
    """FIR taps for one decimate-by-q stage, plus the stage output rate."""
    fs_out = fs_in // q
    stop = fs_out - keep
    if stop <= keep:
        raise ValueError("keep edge is too high for this output rate")
    beta = 0.1102 * (atten - 8.7)
    taps = signal.firwin(_ntaps(fs_in, stop - keep, atten), 0.5 * (keep + stop) / (fs_in / 2),
                         window=("kaiser", beta))
    return taps, fs_out


def stage_plan(dsd_rate, out_rate):
    total = dsd_rate // out_rate
    if total * out_rate != dsd_rate:
        raise ValueError("out_rate must divide the DSD rate")
    plan, r = [], total
    while r > 1:
        q = 8 if r % 8 == 0 else (4 if r % 4 == 0 else (2 if r % 2 == 0 else r))
        plan.append(q)
        r //= q
    return plan


#: Output samples per piece of a decimating stage: a long record is filtered piece by piece, so
#: the working memory stays small whatever its length.
PIECE = 1 << 18


def _decimate_pieces(chunks, n, taps, q):
    """Yield ``resample_poly(x, 1, q, window=taps)`` of a signal of ``n`` samples a piece at a time.

    ``chunks`` is the signal in any number of consecutive arrays; only the input a piece still
    needs is kept. Each piece starts on an input sample that is a multiple of ``q``, so it is
    filtered with the same polyphase phases as the whole signal and every output sample is the
    same sum in the same order (``tests/test_stream.py`` checks the result against the whole-signal call).
    """
    half = (len(taps) - 1) // 2
    reach = -(-half // q) * q  # the input before a piece that its first output still meets, in whole outputs
    nout = -(-n // q)
    chunks = iter(chunks)
    buf, base = np.empty(0), 0
    for m0 in range(0, nout, PIECE):
        m1 = min(nout, m0 + PIECE)
        lo, hi = max(0, m0 * q - reach), min(n, m1 * q + half + 1)
        while base + len(buf) < hi:
            buf = np.concatenate([buf, np.asarray(next(chunks), dtype=np.float64)])
        seg = buf[lo - base : hi - base]
        y = signal.resample_poly(seg, 1, q, window=taps)
        yield y[m0 - lo // q : m1 - lo // q]
        keep = max(0, m1 * q - reach)
        buf, base = buf[keep - base :], keep


def decode(bits, dsd_rate, out_rate=BASE, passband=20000.0):
    """DSD bits (+-1, 1-D) -> PCM float64 at ``out_rate`` with a flat 0..keep response.

    Runs piece by piece (``_decimate_pieces``): the bits are turned into floats a block at a
    time, so a record of any length needs memory for its output and a few blocks, not for a
    float64 copy of every bit.
    """
    bits = np.asarray(bits)
    keep = keep_edge(out_rate, passband)
    fs, n = dsd_rate, len(bits)
    step = 4 * PIECE
    pieces = (bits[i : i + step].astype(np.float64) for i in range(0, n, step))
    for q in stage_plan(dsd_rate, out_rate):
        # intermediate stages keep the same edge; the stop edge is measured against *their* output
        taps, fs_out = decimator(fs, q, keep)
        pieces = _decimate_pieces(pieces, n, taps, q)
        fs, n = fs_out, -(-n // q)
    y = np.empty(n)
    pos = 0
    for piece in pieces:
        y[pos : pos + len(piece)] = piece
        pos += len(piece)
    return y


def to_rate(y, fs, out_rate=44100, passband=21500.0):
    """Low-pass and decimate a PCM record from ``fs`` to ``out_rate`` (160 dB stopband).

    The pass edge is ``passband`` and the stop edge ``out_rate - passband``, so nothing that
    aliases lands below ``passband``. ``fs`` must be a whole multiple of ``out_rate``; with
    ``fs == out_rate`` the record is returned unchanged. Used before a rectangular-window
    transform: the ultrasonic noise of a DSD stream would otherwise leak across the band.
    """
    y = np.asarray(y, dtype=np.float64)
    fs, out_rate = int(round(fs)), int(out_rate)
    if fs == out_rate:
        return y
    if fs % out_rate:
        raise ValueError(f"{fs} Hz is not a whole multiple of {out_rate} Hz")
    q = fs // out_rate
    taps, _ = decimator(fs, q, passband)
    return signal.resample_poly(y, 1, q, window=taps)


def total_taps_report(dsd_rate, out_rate):
    """Human-readable filter description recorded in provenance."""
    keep, fs, parts = keep_edge(out_rate), dsd_rate, []
    for q in stage_plan(dsd_rate, out_rate):
        taps, fs_out = decimator(fs, q, keep)
        parts.append(f"/{q}: {len(taps)} taps at {fs} Hz")
        fs = fs_out
    return f"keep {keep:g} Hz, {atten_str()}; " + "; ".join(parts)


def atten_str():
    return f"{ATTEN_DB:g} dB stopband"
