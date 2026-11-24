"""A stand-in decoder for the tests (run as a script): DSF in, WAV out, in the word length asked for.

It decodes with the reference decoder, so its figures are the reference chain's, whatever the
file format it writes. ``--fail-after N`` makes every call after the N-th exit with an error
(state kept in ``--state``); ``--no-dsf`` makes it refuse DSF files as a distribution ffmpeg
does; ``--noise-dbfs`` adds seeded white noise (a decoder that got worse); ``--tone`` writes a 0.5 s tone and ignores the input (for tests that need no analysis).
"""

import argparse
import sys
from pathlib import Path

import numpy as np

from dsd_measure import decode
from dsd_measure.dsf import read_dsf
from dsd_measure.wavio import write_wav

ap = argparse.ArgumentParser()
ap.add_argument("input")
ap.add_argument("output")
ap.add_argument("--format", default="float32", choices=["pcm16", "pcm24", "pcm32", "float32"])
ap.add_argument("--fail-after", type=int)
ap.add_argument("--state")
ap.add_argument("--no-dsf", action="store_true")
ap.add_argument("--tone", action="store_true")
ap.add_argument("--silent", action="store_true")
ap.add_argument("--noise-dbfs", type=float, help="add white noise of this rms level (seeded, the same every call)")
a = ap.parse_args()

if a.fail_after is not None:
    st = Path(a.state)
    n = int(st.read_text()) if st.exists() else 0
    st.write_text(str(n + 1))
    if n >= a.fail_after:
        print("stubtool: simulated failure on a later call", file=sys.stderr)
        sys.exit(1)
if a.no_dsf and a.input.endswith(".dsf"):
    print("stubtool: Invalid data found when processing input", file=sys.stderr)
    sys.exit(1)
if a.tone:
    t = np.arange(176400) / 352800
    write_wav(a.output, 0.5 * np.sin(2 * np.pi * 1000 * t), 352800, a.format)
    sys.exit(0)
bits, rate = read_dsf(a.input)
y = np.array([decode.decode(b, rate, 352800) for b in bits])
y = y * (0.0 if a.silent else 1.0)
if a.noise_dbfs is not None:
    y = y + 10 ** (a.noise_dbfs / 20) * np.random.default_rng(1).standard_normal(y.shape)
write_wav(a.output, y, 352800, a.format)
