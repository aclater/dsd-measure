"""One member of the repeatability ensemble: the quick suite with a rounding-level perturbation.

usage: member.py METHOD SEED OUTDIR      (METHOD: fft or direct; SEED: a whole number, or "none")

White noise of 1e-14 rms (-280 dBFS, far below anything measured) is added to the reference
modulator's input. The modulator is chaotic, so it then writes a different bitstream with the same
statistics: the spread of a figure over the seeds is its repeatability. METHOD picks the
interpolator in front of the modulator ("direct" is the 0.1.1 direct-form filter), so the two
ensembles show whether the FFT interpolator moves any figure. See docs/accuracy.md, Repeatability.
"""

import sys

import numpy as np

import dsd_measure.encode as enc


def perturb(method, seed):
    """Choose the interpolator and, unless ``seed`` is "none", add the noise to its output.

    The same noise for both methods on the same signal: it is seeded by the seed and the signal, and
    drawn in the order of the samples, so the pieces of the FFT method get what the whole record of
    the direct method gets.
    """
    enc.INTERPOLATOR = method
    if seed == "none":
        return

    def rng_for(x, n):
        return np.random.default_rng([int(seed), n, int(abs(float(np.sum(x))) * 1e6) % 2**31])

    if method == "direct":
        plain = enc.interpolate

        def perturbed(x, ratio, atten_db=160.0, method="fft"):
            y = plain(x, ratio, atten_db, method)
            return y + rng_for(x, len(y)).standard_normal(len(y)) * 1e-14

        enc.interpolate = perturbed
    else:
        plain_pieces = enc._interpolate_pieces

        def perturbed_pieces(x, ratio, atten_db=160.0):
            rng = rng_for(x, len(x) * int(ratio))
            for piece in plain_pieces(x, ratio, atten_db):
                yield piece + rng.standard_normal(len(piece)) * 1e-14

        enc._interpolate_pieces = perturbed_pieces


if __name__ == "__main__":
    from dsd_measure.cli import main

    perturb(sys.argv[1], sys.argv[2])
    sys.exit(main(["run", "suite.toml", "-o", sys.argv[3], "-j", "1"]))
