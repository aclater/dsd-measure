"""Deterministic test-signal generators (see docs/footprint.md).

All generators return float64 arrays of shape (samples,) and are bit-for-bit repeatable.
Levels are given in dBFS. ``coherent_freq`` moves a requested frequency to the nearest
bin centre of an FFT of ``nfft`` points, so tones need no window correction.
"""

import numpy as np

from .levels import PEAK_DBFS, REF_DBFS, db_to_amp

#: Multitone definition (footprint test 11).
MT_TONES = 32
MT_F_LO = 17.6
MT_F_HI = 21400.0
MT_CREST_DB = 13.3


def coherent_freq(f, fs, nfft):
    """Nearest frequency with an integer number of cycles in ``nfft`` samples (odd cycle count)."""
    k = max(1, int(round(f * nfft / fs)))
    if k % 2 == 0:
        k += 1 if (f * nfft / fs) >= k else -1
    return k * fs / nfft


def silence(n):
    return np.zeros(n)


def sine(f, level_dbfs, fs, n, phase=0.0):
    t = np.arange(n) / fs
    return db_to_amp(level_dbfs) * np.sin(2 * np.pi * f * t + phase)


def with_lead(x, fs, lead=0.5, tail=0.1, ramp=0.05):
    """Silence + raised-cosine ramp in, ramp out and tail silence (footprint: settling)."""
    x = np.asarray(x, dtype=np.float64).copy()
    r = int(ramp * fs)
    if r > 0:
        w = 0.5 - 0.5 * np.cos(np.pi * np.arange(r) / r)
        x[:r] *= w
        x[-r:] *= w[::-1]
    return np.concatenate([np.zeros(int(lead * fs)), x, np.zeros(int(tail * fs))])


def trim(x, fs, lead=0.5, tail=0.1):
    """Inverse of the settling margins: drop the first ``lead`` and last ``tail`` seconds."""
    return x[..., int(lead * fs) : x.shape[-1] - int(tail * fs)]


def sweep(f0, f1, level_dbfs, fs, dur):
    """Exponential (log) sine sweep and its inverse filter (Farina). Returns (x, inverse)."""
    n = int(dur * fs)
    t = np.arange(n) / fs
    r = np.log(f1 / f0)
    x = np.sin(2 * np.pi * f0 * dur / r * (np.exp(t / dur * r) - 1))
    # fade ends to limit spectral splatter
    m = int(0.01 * fs)
    w = 0.5 - 0.5 * np.cos(np.pi * np.arange(m) / m)
    x[:m] *= w
    x[-m:] *= w[::-1]
    x *= db_to_amp(level_dbfs)
    inv = x[::-1] / np.exp(t / dur * r)  # amplitude compensation: -6 dB/octave
    return x, inv


def impulse(n, level_dbfs=REF_DBFS, pos=None):
    x = np.zeros(n)
    x[n // 2 if pos is None else pos] = db_to_amp(level_dbfs)
    return x


def step(n, level_dbfs=REF_DBFS, pos=None):
    x = np.zeros(n)
    x[n // 2 if pos is None else pos :] = db_to_amp(level_dbfs)
    return x


def two_tone(f1, f2, a1_db, a2_db, fs, n):
    return sine(f1, a1_db, fs, n) + sine(f2, a2_db, fs, n)


def smpte(fs, n, nfft, level_dbfs=REF_DBFS):
    """60 Hz + 7 kHz, 4:1 amplitude, summed peak = ``level_dbfs``."""
    f1, f2 = coherent_freq(60, fs, nfft), coherent_freq(7000, fs, nfft)
    x = 4 * np.sin(2 * np.pi * f1 * np.arange(n) / fs) + np.sin(2 * np.pi * f2 * np.arange(n) / fs)
    return x / 5 * db_to_amp(level_dbfs), (f1, f2)


def ccif(fs, n, nfft, f1=19000.0, f2=20000.0, level_dbfs=REF_DBFS):
    """Two equal tones; the sum peaks at ``level_dbfs``."""
    g1, g2 = coherent_freq(f1, fs, nfft), coherent_freq(f2, fs, nfft)
    t = np.arange(n) / fs
    x = (np.sin(2 * np.pi * g1 * t) + np.sin(2 * np.pi * g2 * t)) / 2
    return x * db_to_amp(level_dbfs), (g1, g2)


def tone_15k(fs, n, nfft, level_dbfs=-12.0):
    """Single coherent 15 kHz tone at -12 dBFS (footprint test 17)."""
    f = coherent_freq(15000, fs, nfft)
    return sine(f, level_dbfs, fs, n), f


def multitone_freqs(fs, nfft):
    """32 log-spaced tones from 17.6 Hz to 21.4 kHz, each snapped to a distinct bin."""
    f = np.geomspace(MT_F_LO, MT_F_HI, MT_TONES)
    k = np.unique(np.round(f * nfft / fs).astype(int))
    k = np.maximum(k, 1)
    # make bins distinct and keep at least two bins between tones (room for the residual)
    out = [int(k[0])]
    for v in k[1:]:
        out.append(max(int(v), out[-1] + 2))
    return np.array(out) * fs / nfft, np.array(out)


def multitone_standard(level_dbfs=REF_DBFS, n=None, fs=None):
    """The shared 32-tone multitone (1/10 decade, 17.6 Hz to 21.4 kHz, crest 13.3 dB).

    Bins, phases and amplitude come from ``data/multitone32.json`` (designed for a 2^20-point
    FFT at 352.8 kHz, seed 886) and are shared with the modulator measurement tools. Returns
    (x[n], freqs, bins) with one period of 2^20 samples at 352.8 kHz unless ``n`` is given.
    """
    import json
    from importlib import resources

    d = json.loads(resources.files("dsd_measure").joinpath("data/multitone32.json").read_text())
    nfft = d["fft_points"]
    fs_ref = d["analysis_fs"]
    fs = fs or fs_ref
    n = n or nfft * fs // fs_ref
    t = np.arange(n) / fs
    f = np.array(d["freqs_hz"])
    ph = np.array(d["phases_rad"])
    x = (d["unit_peak_amplitude"] * np.sin(2 * np.pi * f[:, None] * t[None, :] + ph[:, None])).sum(0)
    return x * db_to_amp(level_dbfs) / np.max(np.abs(x)), f, np.array(d["bins"])


def multitone(fs, nfft, level_dbfs=REF_DBFS, seed=20261123, iters=200):
    """Multitone with crest factor ~13.3 dB; the peak is set to ``level_dbfs``.

    Phases start from a Schroeder sweep and are refined by a seeded random search so the crest
    factor lands on MT_CREST_DB (+/- 0.05 dB). Returns (x[nfft], freqs, phases).
    """
    freqs, bins = multitone_freqs(fs, nfft)
    t = np.arange(nfft) / fs
    n = len(freqs)

    def build(ph):
        return np.sin(2 * np.pi * freqs[:, None] * t[None, :] + ph[:, None]).sum(0)

    def crest(x):
        return 20 * np.log10(np.max(np.abs(x)) / np.sqrt(np.mean(x**2)))

    rng = np.random.default_rng(seed)
    k = np.arange(n)
    ph = -np.pi * k * (k + 1) / n  # Schroeder phases: low crest, we then raise it to the target
    best = abs(crest(build(ph)) - MT_CREST_DB)
    x = build(ph)
    for _ in range(iters):
        if best < 0.05:
            break
        trial = ph.copy()
        i = rng.integers(0, n)
        trial[i] = rng.uniform(0, 2 * np.pi)
        xt = build(trial)
        err = abs(crest(xt) - MT_CREST_DB)
        if err < best:
            ph, best, x = trial, err, xt
    x = x / np.max(np.abs(x)) * db_to_amp(level_dbfs)
    return x, freqs, ph


def jtest(fs, n, bits=24, level_dbfs=-3.0):
    """J-Test: fs/4 tone plus a +/-1 LSB square wave at fs/192 (24-bit default)."""
    t = np.arange(n)
    tone = db_to_amp(level_dbfs) * np.sin(2 * np.pi * 0.25 * t)  # exactly fs/4
    # fs/192 square: 96 samples high, 96 low
    sq = np.where((t // 96) % 2 == 0, 1.0, -1.0) / 2 ** (bits - 1)
    q = 2 ** (bits - 1)
    return np.round((tone + sq) * q) / q


def level_steps(f, fs, nfft, start_dbfs=-6.0, stop_dbfs=-126.0, step_db=3.0, seg_s=10.0):
    """Stepped coherent sine for linearity (footprint test 13). Returns (x, [(level, start, stop)])."""
    f = coherent_freq(f, fs, nfft)
    levels = np.arange(start_dbfs, stop_dbfs - 1e-9, -step_db)
    seg = int(seg_s * fs)
    out, marks = [], []
    pos = 0
    for lv in levels:
        out.append(sine(f, lv, fs, seg))
        marks.append((float(lv), pos, pos + seg))
        pos += seg
    return np.concatenate(out), marks


def polarity_pulse(n=4096, level_dbfs=REF_DBFS):
    x = np.zeros(n)
    m = 10
    x[n // 2 : n // 2 + m] = db_to_amp(level_dbfs) * np.sin(np.pi * (np.arange(m) + 0.5) / m)
    return x


def peak_sine(f, fs, n):
    """Sine at the 71.43 % peak level (-2.9 dBFS)."""
    return sine(f, PEAK_DBFS, fs, n)
