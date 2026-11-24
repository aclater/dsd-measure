[dsd-measure](../README.md) › [Documentation](README.md) › Methodology limits

# Methodology limits

What dsd-measure can and cannot claim today, in plain words. A hostile methodology review of 0.1.2 found the analysers sound against known answers and the claims too strong; this page is the list of claims that are not yet supported, and what stands behind each one.

## What a report supports today

- This tool reads this file, at this level, rate and format, on these synthetic signals. The figures are checked against known answers and cross-checked with SoX and ffmpeg by the authors (see [accuracy](accuracy.md)).
- Release-to-release tracking of the authors' own tools on a fixed suite, on the same host with the same settings, reported as raw figures with the reference floor and the output format stated. This is self-measurement. No repeatability interval has been measured yet, so a change of less than 1 dB is not interpreted.

## Not claimed yet

1. That any converter is higher quality than, or wins against, any other. The reference chain is ours, one device is not independent of it, and no repeatability interval exists (items 2, 3 and 8).
2. Any ranking of decoders that depends on one output rate, one modulator or one output format. In particular nothing is claimed against a tool that writes 24-bit integer: its file format sets a floor of its own (see [the output format](#output-format)).
3. Any ranking of PCM to DSD modulators against SoX-DSD from one setting. SoX-DSD is run at `sdm-8` by default and a report names its level mapping; its other documented settings and a matched modulation depth are separate runs.
4. Audibility of anything. The reports give measured levels and, where a threshold from the literature is cited, name the source and say whether the authors have read it. They make no statement that a difference is or is not heard. The null test gives a depth, not a verdict on hearing.
5. AES17 measurements or conformance. Only the 20 kHz band edge and the dBFS-re-sine convention follow AES17-2020; see [what follows AES17](#what-follows-aes17).
6. Independent validation. Every check so far was made by the authors with their own tools. There is no outside analyser, no Audio Precision, REW, Multitone Analyzer or DeltaWave reading, and no outside reviewer yet.
7. That anyone gets the same numbers on any machine. A run is deterministic on the same package versions; equality across platforms, compilers and SciPy versions is not verified.
8. That a difference smaller than a measured repeatability interval is an improvement or a regression. No such interval exists, so no table marks a better figure.
9. Anything about idle tones, limit cycles, modulator stability, polarity, filter type or ultrasonic safety. These are measured or listed, and not concluded.
10. Anything about hardware DACs, native DSD playback or music. The signals are synthetic; the null test reads one recording and says how far apart two decoders are on it, not which is right.

## What is not covered by the figures

- **One stimulus family.** Class A devices are fed DSD made by the built-in modulator only. A decoder tuned to that modulator's spectrum, or one that reads differently on another modulator's noise, is not found. Class B devices are judged through the built-in decoder only.
- **One level and one tone.** The headline is 1 kHz at 0 dB SACD (-6.02 dBFS). Nothing is tested above +3.1 dB SACD for class A. A converter that distorts only at other tones or levels can read well in the headline.
- **Ultrasonic content** is not scored by SINAD, which integrates 20 Hz to 20 kHz with a brick wall. A decoder that passes all the shaped noise reads well in band.
- **Repeatability.** Every figure is one deterministic run: one dither seed, tone phase and record. Estimator scatter is documented in [accuracy](accuracy.md); the variance of the stimulus is not measured.
- **Near the tone.** Energy within 13.5 Hz of the tone is not counted (the notch), which hides skirt noise close to the carrier.

## Output format

A converter that writes integer PCM adds rounding noise whatever its decoder does. The report records every output's word length, kind and rate, and states the SINAD that its word length allows both for plain rounding and for TPDF dither (24-bit at 44.1 kHz: 140.7 and 135.9 dB, against a reference floor of 147 dB). A figure between 6 dB under the dithered bound and 6 dB over the plain bound is marked "not judged: output format" and is not ranked. Whether a file was dithered is not detected, which is why both bounds are given. A FLAC output is converted to 32-bit float through ffmpeg before analysis: exact for 24-bit and below, lossy for 32-bit integer FLAC.

## Fairness of a comparison

- Every device's version (what its `--version` prints, or the version declared in the suite) and the SHA-256 of its executable are recorded in `provenance.json`. A tool that prints no version is recorded as such.
- A comparison of devices measured at different output rates or formats is marked "not like-for-like", and distortion and noise are not compared. The run prints a warning.
- The SoX-DSD adapter defaults to `sdm-8`, not `clans-8`, and records which level mapping it used: SoX-DSD maps PCM full scale to 50 % modulation, so the 0 dB SACD test tone enters at 25 % unless `input_gain_db = 6.0206` is set. Both mappings are legitimate; a report must name the one used, and a published comparison should show both.
- Settings are taken from each tool's documentation, not agreed with its maintainers. No maintainer has reviewed a result.

## What follows AES17

The AES17-2020 clauses below were checked against the standard itself.

| Item | AES17-2020 | dsd-measure |
|---|---|---|
| Band edge and the dBFS reference (a sine whose peak is full scale) | 20 kHz; 0 dBFS is a full-scale sine | the same |
| Test tone | 997 Hz | 1 kHz, adjusted to a whole number of cycles in the record |
| Weighting | CCIR-RMS (ITU-R BS.468 shifted by -5.63 dB), clause 5.2.7 | A-weighting where a weighted figure is shown; unweighted for SINAD |
| THD+N notch | Q between 1.2 and 3, clause 5.2.8 | the window's main lobe is cut out of the spectrum, about 13.5 Hz either side of the tone (Q of about 37 at 1 kHz) |
| Dynamic range | 997 Hz at -60 dB re maximum input level, CCIR-RMS, clause 6.4.1 | -66 dBFS (-60 dB SACD), A-weighted |
| THD+N levels | -1 dB and -20 dB re maximum level, clause 6.3.2 | 0 dB SACD (-6.02 dBFS) |
| Stimulus dither | at the input word length, clause 5.1.3 | 32-bit-level dither on the stimuli |

So a figure here is not an AES17 figure and cannot be laid beside an Audio Precision reading without these differences in mind. A profile that follows the standard is on the roadmap.

## What would close each gap

Repeatability intervals over at least eight realisations; a matrix of third-party modulators and decoders; a pinned container with the competitor builds and kept device outputs; readings from outside analysers; a pre-registered protocol with a maintainer review window of at least 14 days; an outside reader of the method. None is done in 0.1.2.

## See also

- [Accuracy](accuracy.md)
- [Conclusions](conclusions.md)
- [Roadmap](roadmap.md)

Part of the [DSD Toolbox](https://github.com/dsd-toolbox/dsd-toolbox).
