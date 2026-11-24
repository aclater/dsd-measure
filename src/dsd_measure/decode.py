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


def decode(bits, dsd_rate, out_rate=BASE, passband=20000.0):
    """DSD bits (+-1, 1-D) -> PCM float64 at ``out_rate`` with a flat 0..keep response."""
    x = np.asarray(bits, dtype=np.float64)
    keep = keep_edge(out_rate, passband)
    fs = dsd_rate
    for q in stage_plan(dsd_rate, out_rate):
        # intermediate stages keep the same edge; the stop edge is measured against *their* output
        taps, fs_out = decimator(fs, q, keep)
        x = signal.resample_poly(x, 1, q, window=taps)
        fs = fs_out
    return x


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
