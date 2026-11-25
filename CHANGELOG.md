# Changelog

All notable changes are listed here, newest first. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## Unreleased

## 0.1.3 - 2026-11-25

A faster run, the release gate as a step for GitHub Actions, and fixes to the null test, the long records of the full profile and class B devices fed at 48 kHz-family rates. The faster interpolator changes the reference modulator's bitstream, so every figure read at the noise floor is a new draw from the same distribution (see Changed).

### Added

- A cache of encoded test signals. The reference modulator's output for a signal is kept per user (`~/.cache/dsd-measure/stimuli`, private, 4096 MiB limit, oldest read deleted first) and read back by later runs and by every further device of a suite. An entry is named by a hash of the signal, the rates, the design, the dsd-measure version, the encoder's source, the NumPy and SciPy versions and the machine type, and is checked by hash on every read. `--no-cache` and `DSD_MEASURE_NO_CACHE=1` switch it off; `dsd-measure cache` shows it, `--clear` empties it and `--key` prints the name to save it under in CI. `DSD_MEASURE_CACHE_DIR` moves the folder and must be an absolute path: a relative one is an error (exit status 2), not ignored. No number changes.
- Parallel runs: the tests of all devices run in worker processes (`-j N`, `jobs = N` in the suite, `DSD_MEASURE_JOBS`; default all cores up to four, then half, at most 16). The report is the one a single job writes, number for number.
- A `gate` profile: the reference floor, the level steps, the noise and the alias tones of the quick profile, with the quick profile's signals and therefore its numbers.
- `dsd-measure gate OLD NEW`: compares two device results figure by figure and exits 1 when one is worse beyond the measurement's repeatability. It judges figures, not output bytes. A NaN or infinite figure counts as not measured, so it fails when it appears in the new result. It exits 2 and prints no PASS when it cannot compare: nothing was measured in both results, a result does not record its analysis version, device class or DSD rate, or two report folders with a `provenance.json` differ in input rate, output rate or profile (the `gate` and `quick` profiles are comparable).
- The repeatability of every figure, measured over 24 runs of the reference chain with different noise realisations (docs/accuracy.md, "Repeatability"; `scripts/repeatability/run.sh` repeats it).
- docs/performance.md: run times by release.
- A reusable GitHub Actions step for the release gate (`.github/actions/gate`): it installs dsd-measure from its own pinned checkout, measures the previous release and the candidate with the gate profile, and fails the job when a figure is worse beyond repeatability. It writes the table into the job summary and keeps the report as an artifact. A workflow in this repository (`gate-selftest`) runs it on every pull request and push, on Ubuntu and macOS.
- Documentation page [Use dsd-measure in your project's CI](docs/ci-gate.md), with a copy-paste workflow, how to choose the previous release, how to read a failure and example suites for ffmpeg and SoX (the SoX suite has not been run).
- `null` estimates each device's passband and flags a pair that is not like-for-like in band (`trust.not_like_for_like`, with both bandwidths). It sees two devices that are both cut, at different frequencies, and ignores two noise floors that differ far below the music; a cut at or above 20 kHz is recorded and worded as information, with `trust.null_band_affected` false, because the null band is not affected. The estimate and its limits are in [methodology limits](docs/methodology-limits.md#null-test-passbands). An alignment whose in-band correlation is below 0.5 is marked untrustworthy (`trust.untrustworthy`): the report gives no depth band for it and `dsd-measure null` exits with status 1, as does `dsd-measure run` for a suite's `[null]` table (its last lines name the pair).
- Every report (device, comparison and null test, HTML and Markdown) ends with "Measured with dsd-measure X.Y.Z" and the project address, and every plot carries the same line in small grey text under the figure. The version is the one recorded in the results when there is one.
- `NOTICE` and `LICENSES/CC-BY-4.0.txt`. The documentation and the example measurement data are CC BY 4.0, the code stays MIT OR Apache-2.0, and reports you generate are your own (README, "Licence and credits"). The licence files ship in the sdist and the wheel.

### Changed

- The SoX-DSD adapter's default `trellis` is SoX's own settings (`"default"`), no longer `"32x32"` (`-t 32 -n 32`), which understated the tool: `sdm-8` at +6.0206 dB input on the built-in stimulus (DSD64, 0 dB SACD) reads SINAD 140.8 dB and A-weighted noise -156.5 dBFS with SoX's own settings, against 138.6 dB and -147.5 dBFS with 32x32. `trellis = "32x32"` still selects the old setting. No figure in these docs was made with the old default: the rows of the SoX-DSD tables in `docs/accuracy.md` name their trellis.
- The interpolator in front of the reference modulator runs each filter stage as FFT convolutions (`scipy.signal.oaconvolve`, one per polyphase branch) instead of the direct form. Same filters; the interpolated signal differs by rounding only (below 1e-14 of full scale, -280 dB). The modulator is chaotic, so its bitstream for signals above the dither level is a different one with the same statistics. Proof that no figure moved: 12 perturbed runs of the quick suite with each interpolator; of 323 figures that vary with the noise, 18 differ between the two at p < 0.05 (16 expected by chance), 4 at p < 0.01 (3 expected), none at p < 0.001. The reference floor reads -146.91 dB THD+N (standard deviation 0.08 dB) against -146.95 dB (0.11 dB) before; SINAD 146.88 dB (0.11) against 146.90 dB (0.14). One report is one draw: SINAD of the reference chain prints 146.9 dB where 0.1.1 printed 147.0 dB, and its multitone floor 152.7 dB where 0.1.1 printed 150.7 dB (that figure's standard deviation is 0.7 dB; the 0.1.1 chain reads 151.0 to 153.7 dB over 12 noise realisations).
- The slow test of the multitone range at every output rate expects 152.4 dB within 2.2 dB (the mean and three standard deviations over noise realisations) instead of 150.7 dB within 1 dB, which was one realisation and narrower than the figure repeats.
- The example report in `examples/reference-chain` is regenerated.
- The headline `null_depth_db` of the null test is the depth in the null band (20 Hz to 20 kHz, or the band both devices pass when that is narrower). The full-band figure, which this key held before, is `null_depth_fullband_db`.
- The default number of jobs also counts the memory and CPU limit of a container or a systemd scope (`memory.max`, `cpu.max` of the control group), not only the machine's free memory and cores. Under a 4 GiB limit the default was up to 16 jobs and the kernel stopped the workers; it is now 2.
- `dsd-measure gate` separates the figures in its FAIL line with semicolons (the figure names hold commas).
- The build needs setuptools 77 or newer (licence files in the package metadata, PEP 639).
- **Measurement changes.** Compare figures only between runs of the same dsd-measure version; 0.1.2 and 0.1.3 measure the same things but not with the same bits. Cause: the faster interpolator (see Changed) gives the reference modulator a different bitstream for the same signal. The null-test source of pysacd's quality suite (seed 20261124, 20 s) hashes to `5defb027...` on 0.1.3 and `128f6ecb...` on 0.1.2; 0.1.3 with the direct-form interpolator (`encode.INTERPOLATOR = "direct"`) reproduces `128f6ecb...`, and the hash is the same with NumPy 2.5.2 and 2.5.5 (SciPy 1.18.1), so it follows the code, not the library versions tried. Figures that read the modulator's noise move as a new draw. The alias image of a filter that rejects more than the modulator's noise at the image frequency (about -150 dB or deeper) has a spread of 1.3 to 2.3 dB (standard deviation of the worst of six images over 12 draws); two draws commonly differ by 2.6 to 3.0 dB, and by up to 6 dB among twelve draws (the 12-draw ranges were 3.6 and 6.0 dB for a decoder with a deep, about 200 dB, stopband). The same test with a filter that leaks (about -127 dB) has a spread of 0.07 to 0.09 dB, so its figure moves by 0.0 to 0.25 dB (the 12-draw ranges were 0.20 and 0.25 dB). Both interpolators give a similar distribution (means within 0.5 dB); neither reads systematically higher or lower. What to compare: a 0.1.2 alias figure with a 0.1.3 one only to the spreads above. For a release comparison run both releases of the device under test with the same dsd-measure version.

### Fixed

- `null` aligned over the full band, so uncorrelated ultrasonic noise (two DSD outputs, or PCM that still holds DSD noise) or a level difference could give a wrong delay, inverted polarity and a depth near 0 dB ([#4](https://github.com/dsd-toolbox/dsd-measure/issues/4)). Delay, polarity and gain are now found in the null band with a normalised, band-limited correlation.
- The full profile no longer keeps its long records in memory: the reference modulator and decoder, the stability figures and the DSF reader and writer work in pieces, with the same bits and the same figures. A 60 s stability hold at DSD256 peaks at 1.4 GB where it needed tens of GB ([#3](https://github.com/dsd-toolbox/dsd-measure/issues/3)).
- The class B impulse and step tests work with a 48 kHz-family input: they are read at the smallest 44.1 kHz-family rate at or above the input rate, with the stimulus placed on decoder samples ([#7](https://github.com/dsd-toolbox/dsd-measure/issues/7)).

## 0.1.2 - 2026-11-24

Usability fixes from a first-run study of 0.1.1, and the fixes a hostile methodology review of this release asked for before it was tagged: measurement language in place of audibility language, no AES17 claim, fairness inputs recorded, every output word length handled, and a page of limits. No analysis number of the reference chain changes; the regenerated example reports differ in text only.

### Added

- `CITATION.cff` and a README "How to cite" line, for GitHub's cite button and the Zenodo archive of each release.
- [Methodology limits](docs/methodology-limits.md): what the tool can and cannot claim today, what follows AES17-2020 and what does not, and what would close each gap. Linked from the README.
- Every device's version (what its `--version` prints, a `version_command`, or a `version` declared in the suite) and the SHA-256 of its executable are recorded in `provenance.json`, `results.json` and the "What was measured" details (`tool_versions()` is now implemented for every adapter; a program that prints no version is recorded as such). The run prints a note when a version could not be read.
- A comparison of devices measured at different output rates, DSD rates or integer word lengths is marked "Not like-for-like": the run prints a warning, `comparison/results.json` records `like_for_like` and each device's conditions, and distortion and noise are not compared.
- The SoX-DSD adapter records its level mapping (the 0 dB SACD tone enters at 25 % or 50 % modulation) in the report, and `examples/suites/sox.toml` measures `sdm-8` at both mappings beside `clans-8`.
- The output word length handling covers every integer width: the report states the SINAD that plain rounding and TPDF dither allow at the output rate (24-bit at 44.1 kHz: 140.7 and 135.9 dB), marks a figure inside those bounds "Not judged: output format" and does not rank it, in the device report, the comparison and the null test. The row is now "Output format" and shows the kind, width and rate of every output.
- The output word length of every file a converter writes is read from its header and recorded in the provenance. When an integer output may limit SINAD (see the word length item above), the verdict is "Not judged: output format" instead of a verdict on the decoder, the comparison does not rank distortion and noise for that device, and the null test says its depth is limited by the output format and gives the ceiling.
- An `ffmpeg` preset, so `dsd-measure quick ffmpeg`, `adapter = "ffmpeg"` and `dsd-measure null track.dsf ffmpeg` work. It asks for 32-bit float output and, if the ffmpeg build cannot read DSF files, gives it DFF files.
- A pre-flight check: each device converts a 0.5 s test signal before anything is measured. A missing program, a failing command or an empty, silent or short output stops the run in about a second with the tool's own error printed once, no report and status 2. A suite is checked in full before its first device is measured.
- `dsd-measure null FILE [DEVICE ...]`: a positional file and preset names, with the built-in reference decoder as the baseline when one decoder is named. A missing tool is reported before the file is read.
- A one-sentence "Result:" at the top of every device, comparison and null report (HTML, Markdown and `results.json`) and as the last line of terminal output.
- A numbered progress line for every test (`[3/17]`) with the time left.
- Bare `dsd-measure` prints three lines saying what to type; a DSD file given to `quick` or on its own is answered with the `null` command for it; an unknown converter name lists the presets and the `--command` line to type.
- Presets take extra arguments: `quick dsd2pcm --args '--filter pysacd'`, `args = "..."` in a suite file, `dsd2pcm:--filter pysacd` for the null test.
- A stopband row that says "not measurable at this output rate", with the reason, when the output rate leaves no test tone above its Nyquist frequency (352.8 kHz and up).

### Fixed

- The `dsd2pcm` preset ran `dsd2pcm {input} -o {output}`, but dsd2pcm takes `IN OUT` and rejects `-o`, so `quick dsd2pcm` failed (the user guide had the same command).
- `signals.json` recorded the hash of the sample array as `sha256`; it is now the file's SHA-256, and the array hash is `samples_sha256`.
- The end-of-run line named "the reference floor" for a whole device when any row was at its own floor, in practice the peak-level SINAD row (floor 129.2 dB against 147 dB for the 0 dB SACD rows). It now lists the rows at their own floor.
- SINAD and THD+N were two rows with the same number; they are one row, and THD (harmonics only) has its own.
- The reference floor's dynamic range is shown to 0.1 dB everywhere (it read 151.8 dB in one place and 152 dB in another).
- The null report's per-channel table labels its two null depths (20 Hz to 20 kHz, and the full analysed band).

### Changed

- Verdicts, Result sentences, reports and docs state measurements and make no statement about hearing. "Transparent", "Inaudible in normal listening" and "Audible risk" are now "At least 120 dB down", "At least 87 dB down" and "Under 87 dB down"; "technical, not audible", "a difference in sound is not expected", "too little to change the tone" and "kinder to amplifiers" are gone; the null test's tiers are depth bands ("depth band 100 dB or more") with no audibility words. Verdict ids changed in `results.json` (`transparent` to `margin-120`, `inaudible` to `margin-87`, `audible-risk` to `margin-low`, `may-matter` to `notable`, `technical` to `difference-low`, `indistinguishable` to `same`, `unsettled` to `no-threshold`) and so did two threshold names (`hearing_range_db` to `range_120_db`, `cd_floor_db` to `dither16_db`).
- The 87 dB reference (the noise of dithered 16-bit on the reference scale) is no longer called settled: Meyer and Moran 2007 report no detection at normal volume but detection of the loop's noise floor in a brief two-subject test at 14 dB of extra gain, and easily above it, and Reiss 2016 finds a small but statistically significant effect. Thresholds whose source the authors have not read (Fielder, Jesteadt et al., Blauert and Laws) say "cited, not checked against the paper".
- A comparison states "X measures N dB less than Y in this metric under these conditions" and "no repeatability interval has been measured yet"; it marks no better cell (there is no bold), because no repeatability interval exists to say a difference is more than noise.
- The AES17 attributions are corrected: only the 20 kHz band edge and the dBFS-re-sine convention follow AES17-2020. The test tone (1 kHz, not 997 Hz), the weighting (A, not CCIR-RMS), the notch, the levels and the dither differ, and the report legend says so.
- The SoX-DSD adapter's default modulator is `sdm-8` (it was `clans-8`, which read 21 dB worse in the accuracy checks).
- The word-length limit follows the tone level the tool actually wrote (measured gain error and any `gain_db`), and the null test compares the rounding noise after the applied gain. The "Not judged" text says the figures cannot be told from the file format.
- The comparison table does not mark a better figure, and tags the cell "format", when a device is format-limited. The pre-flight is capped at 120 s, converters no longer read the terminal (stdin), and WAV headers are read chunk by chunk (a `fmt ` chunk after a large chunk, a short one, or a zero rate no longer fail), including the valid bits of extensible files.
- The README Quick start measures ffmpeg (`dsd-measure quick ffmpeg`). The reference chain's self-test (`dsd-measure init`, `dsd-measure run suite.toml`) is described as such.
- The comparison headline says "in the audio band".
- Messages for mistakes the user can fix no longer carry a Python exception name.
- Links in the README and in reports point at the dsd-toolbox organisation. The report's "Run as" line shows the command template, not an example path that never existed.

## 0.1.1 - 2026-11-24

### Security

- audit-public.sh reads its private-names list from outside the repository and fails closed.
- The compiled core is now built and loaded from a private per-user cache.

### Fixed

- Report figures that reflected the analysis, not the device (found by a separate internal review of 0.1.0, each now with a regression test): the class B multitone range (read about 30 dB low), the stopband (read -81 dB for a filter that is -156 dB; now an upper bound from tones that start 20 kHz below the output rate), overload recovery (the analysis filter spanned +-46 ms at 44.1 kHz), the ultrasonic "peak" (the band edge), the noise headline (the stimulus dither), the J-Test sideband (noise at the farthest position; each position is now compared with its own neighbours), multitone at 48 kHz-family rates (a nonsense figure with no warning), spectrum plots (tones 7.2 dB low), linearity (stopped at -123 dBFS and hid failures), THD+N against frequency (no harmonics from 10 kHz up) and the peak-level SINAD of class A devices (the reference modulator's fallback design, now named in the row with its own floor).
- A second review of 0.1.1 found that four of these fixes held only at a 44.1 kHz output. Now: the multitone of a class A device is decimated to 44.1 kHz before the rectangular window at every output rate (it read 106 to 138 dB at 88.2, 176.4 and 352.8 kHz for a chain that reads 150.7 dB); the stopband tones start at the output rate minus 20 kHz and the row says "upper bound", "or deeper" and the tones tested (at 88.2 kHz it read the filter's transition band as -9 dB); the impulse, filter and group-delay measurements report "not run" at 48 kHz-family rates; the filter rows print "not measurable" when the DSD stream's noise sets the ringing threshold above -60 dB (every output rate of 88.2 kHz or more on the reference decoder); and the device delay is found and removed before the impulse, step, overload and polarity tests, and the first impulse is not used (a 1000-sample delay made a linear-phase decoder read minimum phase and inverted).
- Limits that remain: the filter rows are "not measurable" for wide-band outputs, so they are shown only for 44.1 kHz outputs in practice; the filter, group-delay, polarity and stability conclusions stay off; the stopband is an upper bound read from at most six tones (two at 176.4 kHz, none from 192 kHz); see [accuracy](docs/accuracy.md#known-limits).
- The dither of silent inputs is about -194.85 dBFS over 20 kHz (the label said -162, which is the A-weighted noise of the reference chain with that dither in).
- Wide-band THD: a 20 Hz sine read -61 dB, and noise could be counted as harmonics; the lobes are cut as for THD and the local noise is a mean with a 10 dB margin. The treble sentence is scoped to the 20 kHz band.
- THD of a tone below about 27 Hz counted the fundamental's skirt as second harmonic (a 20 Hz tone with a -80 dB harmonic read -61 dB).
- The alias image is read at its folded frequency (output rate minus tone), not at the largest bin, which was noise.
- DSF and DFF files are padded with the DSD idle pattern, not zeros (a burst at -100 % modulation at the end of a file read as distortion).
- WAV float files carry the extended fmt and fact chunks, which strict readers (SoX) expect; `write_wav` failed for multichannel 24-bit files.
- Temporary work folders are removed when a run ends, including after an error or Ctrl-C.
- A brace in a command template (`awk '{print}'`) no longer crashes the run; only `{input}` and `{output}` are replaced.
- A timed-out device command is killed together with its child processes; the FLAC conversion and the container wrapper have timeouts too.
- The `quick` command no longer breaks on quotes in a name or path; two devices whose names give the same report folder are refused instead of overwriting each other.
- Install instructions: `pipx install git+...` needs git, which a minimal system lacks; the install lines now include it.

### Changed

- Results differ from 0.1.0 (`metrics["analysis_version"]` is 2, reference chain version 2). Noise in dBFS is referred to the rms of a full-scale sine (AES17, ASR), 3.01 dB higher than the 0.1.0 mean-square figures; the silent-input dither is 32-bit level; the ultrasonic peak is replaced by densities at 50, 100 and 200 kHz, band-integrated levels and the highest third-octave band; the stopband comes from the alias tones; multitone tones and residual run to 20 kHz.
- At the +3.1 dB SACD peak level the reference modulator uses order 8 at gain 1.3 (about 129 dB SINAD at DSD64, was order 7 at 122.5 dB); rows made at that level name the design and carry its own floor.
- Class B reports no longer show the filter type, ringing, cut-off or group delay: for a modulator those figures describe the reference decoder. They stay in `results.json` as `reference_decoder_only`.
- A `cli` device's command is split into words and run without a shell by default. To migrate, add `shell = true` to any device whose command uses `|`, `>`, `&&`, `;` or globs. A suite file is a program: run only suites you trust.
- `dsd-measure` exits 1 when any test raised an error (the report is still written), 2 on a fatal error and 130 on Ctrl-C; user mistakes print a one-line error instead of a traceback.
- `dsd-measure signals DIR` writes every signal a run feeds a device (a DSF per test for class A, a WAV per test for class B) with `signals.json`, so the `import` adapter workflow can complete a report; it wrote five WAV files before.
- Class B reports show their notes in HTML and Markdown, and the comparison report lists every device's notes. `-v` on `run` and `quick` shows device details.
- The compiled core is built with `-ffp-contract=off`, so the bitstream does not depend on the CPU's fused multiply-add. The unused `pyyaml` dependency is removed.
- The measurement footprint now states what the code does (durations, settling, noise averages, multitone, stability holds, mono channels) and lists every reduced method; IMD conventions are stated in the labels.

### Added

- Conclusions: "Transparent" now counts image rejection; the overload sentence states the 10 ms resolution and calls the class A burst a loud burst, not an overload.
- Null test: the verdict no longer says a shallow null is "potentially" or "likely audible" (a null cannot say that: an all-pass difference reads 27 dB); the 17.96 to 22.6 kHz band is cut at 20 kHz so 18 to 20 kHz is in the verdict; a copy that is 0.1 dB louder is not plain "identical".
- Signal sets include a `latency` signal (an impulse in silence) that the time-domain tests use to find the device delay.
- Conclusions at the top of every report: a few plain sentences made by fixed rules from the figures, with the evidence and the published thresholds behind each ([docs/conclusions.md](docs/conclusions.md)).
- `dsd-measure null`: a real-music difference (null) test of two or more decoders on your own DSF or DFF file, with a verdict and an optional difference WAV.
- `--plan` for `run` and `quick`, a clear run log, a "What was measured" block in every report, `dsd-measure signals --list`, and a README "How it works" with a worked example.
- Accuracy validation ([docs/accuracy.md](docs/accuracy.md)): a separately written second analyser that must agree with the main one on more than 300 known-answer cases, SoX and ffmpeg cross-checks, and `scripts/validate.sh` to re-run it.
- Floors for IMD, multitone, crosstalk, J-Test, alias and peak-level figures, and the "at the reference floor" flag on them.
- SoX-DSD adapter options `input_gain_db` and `trellis`.
- A release test plan ([docs/release-test-plan.md](docs/release-test-plan.md)), a CI workflow (ruff and the tests on Python 3.11 and 3.13), and tests for the class B measurement path, the private cache, command templates, timeouts, cleanup, exit status and every fixed finding.

## 0.1.0 - 2026-11-23

### Added

- The measurement footprint ([docs/footprint.md](docs/footprint.md)): 19 tests of DSD to PCM converters (class A) and PCM to DSD modulators (class B), with the reduced methods listed honestly.
- A reference modulator (single bit, Legendre zeros, order 8 down to 5 behind a stability guard) and a long linear-phase reference decoder, and the reference floor in every report: about -147 dB THD+N at DSD64 and -176 dB at DSD128, with the decoder alone below -280 dB. Figures within 6 dB of the floor are marked.
- Tests: SINAD, THD and THD+N at several levels, THD+N against level and frequency, dynamic range, noise, frequency response, filter, impulse and step, group delay, SMPTE and CCIF IMD and the IMD sweep, 32-tone multitone, J-Test, linearity, 15 kHz tone, crosstalk and channel match, alias tones, overload recovery, polarity, DC, gain, stability at the peak level, and a DSD128 and DSD256 rate table.
- Reports as HTML with inline SVG, Markdown, CSV and JSON; a comparison report with two or more devices side by side.
- Adapters: `reference`, `cli` (DSF or DFF in), `import`, `sox-dsd`, and presets for dsd2pcm and sacd_extract; pinned black-box reference tool containers (SoX-DSD, ffmpeg-free, sacd_extract) through `tools/reftool.sh`.
- Example reports in `examples/`.

**Known issues in 0.1.0 (history).** A separate internal review found that some report figures in 0.1.0 reflect the analysis rather than the device: the stopband, the class B multitone range, the ultrasonic noise peak, the noise headline, overload recovery, the J-Test sideband, multitone at 48 kHz-family rates, and the peak-level SINAD of class A devices. They are corrected in 0.1.1 (see Fixed above). For 0.1.0 results, the figures the review confirmed are THD, THD+N and SINAD, dynamic range, gain, linearity, frequency response, single-point IMD, crosstalk and the reference floor.

Part of the [DSD Toolbox](https://github.com/dsd-toolbox/dsd-toolbox).
