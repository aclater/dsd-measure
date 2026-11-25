[dsd-measure](../README.md) › [Documentation](README.md) › Performance

# Performance

How long a run takes, by release, and what each speed-up contributes. Every time is the wall time of the whole command for the reference chain measured by itself (`dsd-measure init`, then `dsd-measure run suite.toml`: one class A and one class B device), taken on an otherwise idle machine. A converter's own run time comes on top.

## By release

Intel Core i9-13900H (6 P-cores, 8 E-cores, 20 threads), Fedora 44, Python 3.14, NumPy 2.5.5, SciPy 1.18.1.

| Run | 0.1.1 (s) | 0.1.3, first run (s) | 0.1.3, later runs (s) |
|---|---:|---:|---:|
| Quick profile, default jobs (10 here) | 264.6 | 19.7 | 11.6 |
| Quick profile, four P-cores, `--jobs 4` | | 27.8 | 15.4 |
| Quick profile, four E-cores, `--jobs 4` | | 55.7 | 32.5 |
| Quick profile, `--jobs 1` | 264.6 | 75.9 | 36.9 |
| Gate profile, default jobs | 83.7 | 12.0 | 7.1 |
| Gate profile, four P-cores, `--jobs 4` | | 13.6 | 8.3 |
| Gate profile, four E-cores, `--jobs 4` | | 27.5 | 17.4 |
| Gate profile, `--jobs 1` | 83.7 | 26.7 | 13.9 |
| Full profile with DSD128 and DSD256 rows, default jobs | | 80.3 | 28.1 |
| Full profile with DSD128 and DSD256 rows, `--jobs 1` | | 274.1 | 87.1 |

0.1.1 had one process and no cache, so its time does not depend on the number of cores; its gate row is the same four tests chosen with `--only`. The 0.1.1 column was measured on the development tree just before the speed work, whose measuring code is that of 0.1.1. The full-profile rows are `examples/suites/ref.toml`; its first run with one job was taken without the cache, and it was not timed on 0.1.1. "First run" starts with an empty cache of encoded test signals, "later runs" read every signal back. The four-core rows are the budget of a small hosted CI runner (four virtual CPUs); such a runner has not been timed yet.

## What each change gives

The quick profile on the same machine, one change at a time.

| Version of the code | First run (s) | Later runs (s) | Numbers in the report |
|---|---:|---:|---|
| 0.1.1 | 264.6 | 264.6 | |
| with the cache of encoded test signals | 166.4 | 36.9 | the same, number for number |
| and the FFT interpolator | 75.9 | 36.9 | the same within [repeatability](accuracy.md#repeatability) |
| and the FFT interpolator, cache off | 101.9 | 101.9 | the same as with the cache |
| and worker processes (10 jobs) | 19.7 | 11.6 | the same as with one job |
| and worker processes, cache off | 23.6 | 23.6 | the same as with the cache |

The cache helps the first run too, because the two halves of the reference chain and the reference floor use some of the same signals. In 0.1.1, 79 % of a run was the direct-form interpolation filter in front of the reference modulator and 12 % was the modulator itself. Interpolating a 31 s signal from 88.2 kHz to DSD64 takes 12.8 s in the direct form and 2.0 s as FFT convolutions on one P-core; the first stage (2047 taps) alone is 24 times faster.

## Memory and disk

| Run | Peak memory (GiB) | Cache after the run (MiB) |
|---|---:|---:|
| Quick, 1 job | 2.1 | 89 |
| Quick, 4 jobs | 4.2 | 89 |
| Quick, 8 jobs | 5.8 | 89 |
| Gate, 4 jobs | 3.4 | 32 |
| Full, 1 job | 7.5 | 231 |
| Full, 8 jobs | 14.7 | 231 |

Peak memory is that of all processes of the run together, measured on an AMD Ryzen AI Max+ 395. The default number of jobs is lowered when the machine has less memory available than the profile needs. That choice uses a planning figure, not these measurements: a fixed part plus a part for each job, 1.6 GiB and 0.6 GiB per job for the quick and gate profiles (4.0 GiB for four jobs, where the gate run above peaked at 3.4 GiB) and 6.5 GiB and 1.1 GiB per job for the full profile.

The table above was measured before the long records were made in pieces. From 0.1.3 the long records are made, decoded and analysed in pieces, so memory grows with the record by one to two bytes per DSD sample (the bit stream itself, one byte, and a copy of it in some tests) and not by tens of bytes. The figures below are the peak resident memory of one test in one process, measured on the same CPU with the cache off, for the class B reference modulator. Rows marked "run" were measured; the 0.1.2 figure for the 60 s holds is an extrapolation from the shorter holds (about 50 bytes per DSD sample).

| Stability test (three holds) | 0.1.2 | 0.1.3 |
|---|---:|---:|
| DSD64, 10 s holds | 1.45 GB (run) | 0.47 GB (run) |
| DSD256, 2 s holds | 0.93 GB (run) | 0.46 GB (run) |
| DSD256, 6 s holds | not run | 0.55 GB (run) |
| DSD256, 60 s holds (the full profile) | about 34 GB (extrapolated) | 1.4 GB (run) |

The longest records of the full profile at DSD256 in 0.1.3, each run on its own:

| Test | Record | Peak memory |
|---|---|---:|
| Levels, class A | 102 s of signal | 2.1 GB |
| Stability, class B | three holds of 60 s | 1.4 GB |
| Noise, class B | 15 s | 1.2 GB |
| J-Test, class A | 24 s | 0.9 GB |

The whole full profile at DSD256 was not run in one process for these tables.

## What was tried and not adopted

| Idea | Measured | Verdict |
|---|---|---|
| Other compiler flags for the modulator core, state in registers | 18.1 ns per sample as shipped; 16.5 to 18.3 ns for five variants, all byte-identical | Not adopted: the loop already runs at the latency of its feedback sum |
| A C kernel for the decoder's decimating filter | byte-identical to SciPy's and 1.1 times faster | Not adopted |
| Shorter filters in the later interpolation stages | signal differs by 2e-8 (-155 dB) | Not adopted: a different reference signal |
| FFT interpolation in 64-bit float on a GPU (RTX 4070 Ti) | 0.48 s against 2.03 s on one P-core for a 31.5 s signal (the GPU's host was busy with other work); output differs by 5e-15 | Not adopted: less than the worker processes give, nothing on later runs, and a second set of rounding |
| Analysis transforms in 32-bit float on a GPU | error -130 dB re full scale | Not acceptable: above the -147 dB reference floor |

The reasons are in [Design](design.md#decisions).

## Run it yourself

<!-- docs-run: skip="times full runs for the timing table; timings come only from the timing host" -->
```sh
dsd-measure init
dsd-measure cache --clear
time dsd-measure run suite.toml
time dsd-measure run suite.toml
time dsd-measure run suite.toml --profile gate
time dsd-measure run suite.toml --jobs 1 --no-cache
```

## See also

- [User guide: Speed](user-guide.md#speed)
- [Accuracy: Repeatability](accuracy.md#repeatability)
- [Design](design.md)

Part of the [DSD Toolbox](https://github.com/dsd-toolbox/dsd-toolbox).
