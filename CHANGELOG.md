# Changelog

All notable changes are listed here, newest first. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## 0.1.1 - unreleased

### Security

- audit-public.sh reads its private-names list from outside the repository and fails closed.
- The compiled core is now built and loaded from a private per-user cache.

### Fixed

- Report figures that reflected the analysis, not the device (found by an independent review of 0.1.0, each now with a regression test): the class B multitone range (read about 30 dB low), the stopband (read -81 dB for a filter that is -156 dB; now an upper bound from tones that start 20 kHz below the output rate), overload recovery (the analysis filter spanned +-46 ms at 44.1 kHz), the ultrasonic "peak" (the band edge), the noise headline (the stimulus dither), the J-Test sideband (noise at the farthest position; each position is now compared with its own neighbours), multitone at 48 kHz-family rates (a nonsense figure with no warning), spectrum plots (tones 7.2 dB low), linearity (stopped at -123 dBFS and hid failures), THD+N against frequency (no harmonics from 10 kHz up) and the peak-level SINAD of class A devices (the reference modulator's fallback design, now named in the row with its own floor).
- A second review of 0.1.1 found that four of these fixes held only at a 44.1 kHz output. Now: the multitone of a class A device is decimated to 44.1 kHz before the rectangular window at every output rate (it read 106 to 138 dB at 88.2, 176.4 and 352.8 kHz for a chain that reads 150.7 dB); the stopband tones start at the output rate minus 20 kHz and the row says "upper bound", "or deeper" and the tones tested (at 88.2 kHz it read the filter's transition band as -9 dB); the impulse, filter and group-delay measurements report "not run" at 48 kHz-family rates; the filter rows print "not measurable" when the DSD stream's noise sets the ringing threshold above -60 dB (every output rate of 88.2 kHz or more on the reference decoder); and the device delay is found and removed before the impulse, step, overload and polarity tests, and the first impulse is not used (a 1000-sample delay made a linear-phase decoder read minimum phase and inverted).
- Limits that remain: the filter rows are "not measurable" for wide-band outputs, so they are shown only for 44.1 kHz outputs in practice; the filter, group-delay, polarity and stability conclusions stay off; the stopband is an upper bound read from at most six tones (two at 176.4 kHz, none from 192 kHz); see [accuracy](docs/accuracy.md#known-limits).
- The dither of silent inputs is about -194.85 dBFS over 20 kHz (the label said -162, which is the A-weighted noise of the reference chain with that dither in).
- Wide-band THD: a 20 Hz sine read -61 dB, and noise could be counted as harmonics; the lobes are cut as for THD and the local noise is a mean with a 10 dB margin. The treble sentence is scoped to the 20 kHz band.
- THD of a tone below about 27 Hz counted the fundamental's skirt as second harmonic (a 20 Hz tone with a -80 dB harmonic read -61 dB).
- The alias image is read at its folded frequency (output rate minus tone), not at the largest bin, which was noise.
- DSF and DFF files are padded with the DSD idle pattern, not zeros (a burst at -100 % modulation at the end of a file read as distortion).
- WAV float files carry the extended fmt and fact chunks, which strict readers (SoX) expect; `write_wav` failed for multi-channel 24-bit files.
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
- Accuracy validation ([docs/accuracy.md](docs/accuracy.md)): an independent second analyser that must agree with the main one on more than 300 known-answer cases, SoX and ffmpeg cross-checks, and `scripts/validate.sh` to re-run it.
- Floors for IMD, multitone, crosstalk, J-Test, alias and peak-level figures, and the "at the reference floor" flag on them.
- SoX-DSD adapter options `input_gain_db` and `trellis`.
- A release test plan ([docs/release-test-plan.md](docs/release-test-plan.md)), a CI workflow (ruff and the tests on Python 3.11 and 3.13), and tests for the class B measurement path, the private cache, command templates, timeouts, cleanup, exit status and every fixed finding.

## 0.1.0

### Added

- The measurement footprint ([docs/footprint.md](docs/footprint.md)): 19 tests of DSD to PCM converters (class A) and PCM to DSD modulators (class B), with the reduced methods listed honestly.
- A reference modulator (single bit, Legendre zeros, order 8 down to 5 behind a stability guard) and a long linear-phase reference decoder, and the reference floor in every report: about -147 dB THD+N at DSD64 and -176 dB at DSD128, with the decoder alone below -280 dB. Figures within 6 dB of the floor are marked.
- Tests: SINAD, THD and THD+N at several levels, THD+N against level and frequency, dynamic range, noise, frequency response, filter, impulse and step, group delay, SMPTE and CCIF IMD and the IMD sweep, 32-tone multitone, J-Test, linearity, 15 kHz tone, crosstalk and channel match, alias tones, overload recovery, polarity, DC, gain, stability at the peak level, and a DSD128 and DSD256 rate table.
- Reports as HTML with inline SVG, Markdown, CSV and JSON; a comparison report with two or more devices side by side.
- Adapters: `reference`, `cli` (DSF or DFF in), `import`, `sox-dsd`, and presets for dsd2pcm and sacd_extract; pinned black-box reference tool containers (SoX-DSD, ffmpeg-free, sacd_extract) through `tools/reftool.sh`.
- Example reports in `examples/`.

### Known issues in 0.1.0 (history)

An independent review found that some report figures in 0.1.0 reflect the analysis rather than the device: the stopband, the class B multitone range, the ultrasonic noise peak, the noise headline, overload recovery, the J-Test sideband, multitone at 48 kHz-family rates, and the peak-level SINAD of class A devices. They are corrected in 0.1.1 (see Fixed above). For 0.1.0 results, the figures the review confirmed are THD, THD+N and SINAD, dynamic range, gain, linearity, frequency response, single-point IMD, crosstalk and the reference floor.

Part of the [DSD Toolbox](https://github.com/aclater/dsd-toolbox).
