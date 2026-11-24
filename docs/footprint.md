[dsd-measure](../README.md) › [Documentation](README.md) › Measurement footprint

# Measurement footprint

This page is the shared standard for what dsd-measure measures, how each result is computed and how it is shown. It covers DSD to PCM converters and PCM to DSD modulators, and it is written so that anyone can repeat a measurement and get the same numbers.

## Contents

- [What is measured and why](#what-is-measured-and-why)
- [Principles](#principles)
- [Sources and credit](#sources-and-credit)
- [Device classes](#device-classes)
- [Level conventions](#level-conventions)
- [Common analysis settings](#common-analysis-settings)
- [The measurements](#the-measurements)
- [Modulator-only measurements](#modulator-only-measurements)
- [Real-music null test](#real-music-null-test)
- [Report layout](#report-layout)
- [Adapters](#adapters)
- [Reference tools](reference-tools.md)
- [Determinism and provenance](#determinism-and-provenance)

## What is measured and why

Class A is a DSD to PCM converter, class B a PCM to DSD modulator. "Run" says what version 0.1.1 does; the method for each is in [The measurements](#the-measurements).

| # | Measurement | What it tells you | Plain-language reason | Run in 0.1.1 |
|---|---|---|---|---|
| 1 | Summary dashboard | SINAD, THD, noise, DR, IMD, ripple, gain, polarity | One screen to compare devices | yes |
| 2 | Frequency response, ripple | Gain across 20 Hz to 20 kHz | Dull or bright treble | yes (stepped tones, reduced) |
| 3 | Filter magnitude, stopband, aliasing | Roll-off above the audio band | Ultrasonic leakage and fold-back | magnitude yes (class A only); alias tones yes (class A) |
| 4 | Impulse and step response | Ringing before and after, overshoot | Pre-echo, the filter fingerprint | yes (class A only: for a modulator they describe the reference decoder and are not shown) |
| 5 | Group delay and phase | Arrival time against frequency | Timing of treble against bass | yes (delay, class A only) |
| 6 | Noise floor, in-band and ultrasonic | Hiss and shaped noise | Low-level detail, amplifier safety | yes |
| 7 | Dynamic range, -60 dB method | How quiet it is | The headline "DR" figure | yes |
| 8 | THD and THD+N at several levels | Distortion at 1 kHz | The classic review numbers | yes |
| 9 | THD+N against level and frequency | Quiet and loud, bass and treble | Where it behaves best | yes |
| 10 | IMD SMPTE and CCIF | Distortion between tones | Harsh, non-harmonic distortion | yes: single points and the sweep |
| 11 | 32-tone multitone | Distortion-free range with music-like load | Real-world stress | yes |
| 12 | J-Test | Jitter-like sidebands (arithmetic only here) | Truncation and dither problems | yes |
| 13 | Linearity to -120 dB | Level accuracy for quiet signals | Low-level detail | yes |
| 14 | Crosstalk and channel match | Stereo separation and balance | Imaging | yes (stereo path) |
| 15 | Polarity and DC | Inversion, offset | Speaker safety, absolute polarity | yes |
| 16 | Gain accuracy | Level error | Fair A/B comparisons | yes |
| 17 | 15 kHz tone at -12 dBFS | Spurs and images at high frequency | Filter and noise-shaper behaviour | yes |
| 18 | Stability and overload (class B) | 60 s tones to the peak level | Never saturates at loud peaks | yes, with overload recovery |
| 19 | Ultrasonic peak per rate (class B) | Where the shaped noise peaks | DSD64 against higher rates | yes: DSD64 plus the rate table (DSD128, DSD256) |

## Principles

1. **Measure what readers look at.** The set follows what audiophile reviewers publish, so a result can be compared with a review.
2. **One definition per metric.** Signal, level, FFT size, window, bandwidth and weighting are fixed here. A device may only differ where a test says so.
3. **Raw samples, never interpolated.** Impulse and step plots show the actual output samples as stems or steps.
4. **A plain-language line under every plot.** Non-engineers get a "what this means" sentence. Engineers get the numbers in CSV and JSON.
5. **Same chain for every device.** The reference decoder and the analysers are shared, so differences come from the device under test and not from the analysis.
6. **Be honest about the limits.** The measurement floor of the reference chain is reported next to every result, and a result within 6 dB of that floor is flagged as "at the floor".
7. **Every comparison states each device's output rate and level convention.** A decoder's in-band floor depends on the rate it writes (a filter that is deep at 352.8 kHz can fold more of the ultrasonic noise into the audio band at 88.2 kHz: one widely used decoder reads about 147 dB SINAD at 352.8 kHz and about 126 dB at 88.2 kHz on the same bits), and tools map PCM full scale to different DSD modulation depths (SoX-DSD maps 0 dBFS to 50 percent, so a -6 dBFS tone reaches its modulator at 25 percent). A table that compares devices must therefore list, per device, the output rate, the input and output gains applied and the modulator settings, and must not compare rows made at different rates or levels without saying so. The report's device header and `provenance.json` carry these fields.

## Sources and credit

The set is a synthesis of public practice; it copies no private test and no text of a standard.

| Source | What we took from it |
|---|---|
| [Archimago, "Measurements: DSD to PCM conversion in foobar" (2015-04)](https://archimago.blogspot.com/2015/04/analysis-dsd-to-pcm-2015-foobar-sacd.html) | DSD to PCM comparison across decoders: RMAA-style noise and THD, a 1 kHz tone, filter shape, ultrasonic content |
| [Archimago, "DSD with SoX" (2021-10)](https://archimago.blogspot.com/2021/10/measurements-look-at-dsd-and-using-sox.html) | Using SoX as a DSD to PCM and PCM to DSD reference; checking filter and gain through a 32-bit float chain |
| [Archimago, DAC DSD and PDM notes (2022-06)](https://archimago.blogspot.com/2022/06/notes-on-dac-dsd-1-bit-pdm-measurements.html) | DSD playback behaviour: noise shaping, ultrasonic noise, level headroom, DSD64 against DSD128 |
| [Audio Science Review (ASR)](https://www.audiosciencereview.com/) | The SINAD dashboard, the 32-tone multitone, the filter and impulse plots, THD+N against level, the J-Test |
| [Stereophile (John Atkinson)](https://www.stereophile.com/content/measurements-maps-precision) | Impulse and step response, frequency response, spectra at 16 and 24 bit, the J-Test, linearity error, the 15 kHz composite |
| [RMAA](http://audio.rightmark.org/) | Noise level dB(A), dynamic range, THD, IMD (SMPTE), crosstalk, frequency response |
| AES17 | The 20 kHz measurement bandwidth, A-weighting, the notch method for THD+N, the -60 dB dynamic range method |

The [dsd2pcm quality tools](https://github.com/aclater/dsd2pcm-rs) (tools/quality, MIT OR Apache-2.0) are a sister project that measures DSD to PCM decoders in the same spirit. From them we took the SoX-DSD filter per DSD rate (CLANS-8, 7 and 6, from Archimago's 2022 tests), the Legendre-zero modulator design that our reference modulator extends to higher order, and the observation that a wide decoder filter folds 300 to 400 kHz DSD noise into the audio band. Not yet taken: their separate low-pass step for comparing a 30 kHz decoder filter with a wide decode.

The SACD level convention is taken from public reviewer practice and is restated below in our own words.

## Device classes

| Class | Device under test (DUT) | Input | Output that is analysed |
|---|---|---|---|
| A | DSD to PCM converter (a decoder, a filter, a player's DSD path in software) | DSD stream made by the reference modulator | PCM file from the DUT |
| B | PCM to DSD modulator (a DSD encoder) | PCM test signal | DSD stream from the DUT, decoded by the reference decoder to 32-bit float PCM |

For class B the reference decoder is a long linear-phase FIR low-pass with a very deep stopband, run in 64-bit maths and written out as 32-bit float. This is the "perfect DAC" method: the DAC is taken to be ideal, so what is left is the modulator. The reference decoder's own residual is measured once (a class A run of the reference decoder on the reference modulator's output) and published as the floor.

Hardware DACs are out of scope for the first release. A recording of a DAC's analogue output can still be imported as a WAV and analysed as class A.

## Level conventions

dBFS is the level of a PCM sample relative to full scale (a full-scale sine peaks at 1.0). DSD levels are quoted as a percentage of the DSD modulation and in dB relative to the 0 dB SACD reference.

| Name | Modulation | PCM level |
|---|---|---|
| 0 dB SACD (reference level) | 50% | -6.0 dBFS |
| Peak level (+3.1 dB SACD) | 71.43% | -2.9 dBFS |
| 100% modulation (not reachable by a stable modulator) | 100% | 0 dBFS |

So a PCM level in dBFS equals the SACD level minus 6.0 dB, and 71.43% is 20 log10(0.7143 / 0.5) = +3.1 dB above reference. Tests that say "full scale" mean 0 dB SACD (-6 dBFS) unless stated; tests that stress a modulator go up to the 71.43% peak level (-2.9 dBFS).

Every plot labels the level in both units where it matters, for example "-6 dBFS (0 dB SACD)".

## Common analysis settings

These apply to every FFT-based result unless a row says otherwise.

| Setting | Value |
|---|---|
| Analysis format | 64-bit float internally. In-band analysis runs at 352.8 kHz for every DSD rate (class B decodes to 352.8 kHz; class A uses the DUT's own output rate), so coherent bins are the same for all rates (1 kHz is bin 743 of 2^18 at 352.8 kHz) |
| Ultrasonic analysis | The reference decoder runs again at 705.6 kHz (DSD64 and DSD128) or 1411.2 kHz (DSD256 and up), which reaches 192 kHz and beyond; an output rate of 352.8 kHz only reaches 176.4 kHz |
| DUT input (class B) | 32-bit integer WAV at 88.2 kHz by default, because 24-bit TPDF dither (about -146.7 dBFS over 20 kHz) would mask the floors of DSD128 and DSD256; the J-Test stays 24-bit at 44.1 kHz. A PCM reference line (the same signal at 24-bit and 88.2 kHz, equal bin width) is drawn in noise plots |
| Test files | Mono files, one channel per file, so channels stay independent; test 14 (crosstalk) uses a stereo pair |
| Test tones | Coherent: an integer number of cycles in the FFT length, so no window leakage for the stimulus |
| Window | 7-term Blackman-Harris (main lobe 7 bins each side, sidelobes below -180 dB) for spectra; rectangular only for the multitone, where every tone is on a bin |
| FFT length | 2^18 points (262144) at 352.8 kHz for tone spectra; the same bin width (1.3458 Hz) at every other output rate. Noise: 2^20 points when the record is long enough (full profile), otherwise 2^18; J-Test 2^18; ultrasonic noise 2^18 at 705.6 kHz or 1411.2 kHz; stated per test |
| Averages | Noise: up to 8 half-overlapped segments (power-averaged); a record too short for 8 gets fewer and the result carries the number used (`averages`). J-Test: 3. Coherent tones: 1. Multitone: one per whole period (3 in the quick profile, 8 in the full profile) |
| Measurement bandwidth | 20 Hz to 20 kHz (AES17), with 22.05 kHz and 40 kHz variants for wide-band noise |
| Weighting | Unweighted and A-weighted (IEC 61672 curve) both reported where the metric is a noise figure |
| Spectrum plots | dBFS. No smoothing is applied to metrics. To keep SVG files small, a plot may reduce the raw bins to about 2000 points: power-averaged in 1/48-octave buckets for noise plots, peak-held for tone spectra |
| Channels | Mono. Every test feeds and analyses one channel, except crosstalk and channel match, which use a stereo pair. A device's second channel is not measured separately; use the stereo tests to see a difference between channels |
| Settling | A record is analysed over its last N points (N is the FFT length, about 0.74 s at 352.8 kHz); whatever comes earlier is settling and is not analysed. Noise and J-Test also drop the first 0.5 s. There are no ramps: every stimulus starts at once. The padding of the last block of a DSF or DFF file is the DSD idle pattern, not zeros, so a decoder that converts whole blocks sees no burst at the end |
| Duration | By profile. Quick: 1.5 s per level or frequency step, 2 s for the IMD and 15 kHz tones, 6 s noise, 12 s J-Test, 5 s stability holds. Full: 2.5 s per step, 4 s for the IMD and 15 kHz tones, 15 s noise, 24 s J-Test, 60 s stability holds. Each record holds at least one analysis window after settling. A full run takes minutes |

## The measurements

Each entry gives the signal, the analysis, the metric, the plot and why a listener cares. Class applies to A and B unless noted. "Coherent 1 kHz" means the tone frequency is moved to the nearest bin-centred frequency of the FFT, which rounds to within 1 Hz of 1 kHz.

### 1. Summary dashboard

- **Signal:** none of its own; it is assembled from the results below.
- **Metric table:** SINAD (THD+N at 1 kHz, 0 dB SACD, 20 Hz to 20 kHz, dB), THD (dB), noise floor dB(A) and unweighted (dBFS), dynamic range (dB, -60 dB method), IMD SMPTE and CCIF (dB), crosstalk (dB at 1 kHz), passband ripple (dB peak to peak, 20 Hz to 20 kHz), -3 dB frequency, stopband attenuation (dB), gain error (dB), DC offset, polarity, ultrasonic noise (dBFS per Hz at 50, 100 and 200 kHz, and integrated 20 to 40 and 40 to 96 kHz).
- **Plot:** a single table in the report, plus a coloured bar per metric against the group (comparison report).
- **Why:** it is the first thing readers look at (the ASR dashboard).

### 2. Frequency response and passband ripple

- **Signal:** a log sine sweep from 5 Hz to the Nyquist frequency at 0 dB SACD (-6 dBFS), 20 s, plus, as a cross-check, 31 stepped coherent tones at 1/3-octave centres.
- **Analysis:** deconvolve the sweep (inverse-filter method) to get the impulse response, then FFT with a 2^20 window. The stepped tones give an independent magnitude at each point; the two agree within 0.01 dB for a linear device.
- **Metric:** gain relative to 1 kHz, dB, at 20 Hz, 1, 10, 15, 20, 20.5 kHz; peak-to-peak passband ripple 20 Hz to 20 kHz; -0.1 dB, -1 dB and -3 dB frequencies.
- **Plot:** magnitude in dB, x log 5 Hz to Nyquist, y +1 to -6 dB (zoomed) and a full view y +3 to -120 dB.
- **Why:** it shows treble roll-off or lift in the audible band, which listeners hear as dull or bright.

### 3. Filter magnitude, transition band, stopband and aliasing

- **Signal:** the same sweep as the frequency response, extended to the DUT's own Nyquist, plus single tones at 0 dB SACD placed from the output rate minus 20 kHz upward in 2 kHz steps (24.1 to 34.1 kHz at a 44.1 kHz output, 68.2 to 78.2 kHz at 88.2 kHz, two tones at 176.4 kHz, not run from 192 kHz) so every image lands at or below 20 kHz, to catch alias products.
- **Analysis:** magnitude from the deconvolved response; alias level from the spectrum of each tone (the image of each tone is read at its folded frequency, output rate minus tone, in dB below the tone).
- **Metric:** transition band edges (-3 dB and -60 dB), stopband attenuation (the worst image of the alias tones, re the tone: an impulse measurement cannot see below its own noise, about -80 dB, and so is not used for the stopband), worst alias image (dB) and its frequency. The image level includes the device's noise, so it is an upper bound on the stopband.
- **Plot:** magnitude in dB, x linear 0 to 30 kHz (class A at 44.1 kHz: 0 to 22.05 kHz) with the transition band shaded, y 0 to -140 dB; a second plot shows alias image levels against the input tone frequency.
- **Why:** filter steepness decides how much ultrasonic noise leaks in and how much aliasing folds back into the audible band; it is the main difference between decoders.

### 4. Impulse and step response

- **Signal:** a single-sample impulse at -6 dBFS (0 dB SACD) in a silent file, and a step from 0 to -6 dBFS held for 1 ms-scale lengths (at least 2048 samples), both with 0.5 s of silence before. For class A the DSD input is the modulated impulse or step.
- **Analysis:** none beyond alignment to the main peak. Samples are plotted exactly as delivered. For class A the sample grid is the DUT's output grid.
- **Metric:** pre-ringing and post-ringing length (samples above -60 dB of the peak), peak overshoot of the step (percent), time to settle within 1 percent, and filter type from the shape (linear phase, minimum phase, intermediate).
- **Plot:** stem plot of samples, x in milliseconds, y in percent of peak; a zoom of +/-0.5 ms and a wide view of +/-5 ms. No interpolation, no smoothing and no "sinc reconstruction".
- **Why:** pre-ringing and overshoot are the most visible fingerprints of a filter and the subject of most filter debates.

### 5. Group delay and phase

- **Signal:** the deconvolved sweep impulse response from test 2.
- **Analysis:** unwrap the phase of the 2^20 FFT of the impulse response, differentiate against angular frequency, report in microseconds after removing the constant latency.
- **Metric:** group delay at 20 Hz, 1, 10 and 20 kHz and its maximum deviation in the passband.
- **Plot:** group delay in microseconds against log frequency, y +/-100 microseconds (zoomed) with a full view; the phase in degrees against log frequency, y +/-180 degrees.
- **Why:** a flat group delay means all frequencies arrive together; steep delay near 20 kHz is the audible cost of some minimum-phase filters.

### 6. Noise floor, in-band and ultrasonic

- **Signal:** two kinds of silence, because an exact-zero input makes a delta-sigma modulator fall into a limit cycle that is far quieter than real music would leave it (about -218 dB). (1) The DSD idle pattern, the repeating byte 0x69, for class A. (2) TPDF-dithered silence at 32-bit level (about -194.85 dBFS over 20 kHz, dBFS re a full-scale sine, fixed seed; the reference chain's A-weighted noise with it in is about -162 dBFS) for class B and for the modulator feeding class A. The dither is 32-bit because a 24-bit dither (about -146.7 dBFS) would be the floor of the result: with it the reference chain read -151.6 dBFS(A) when its own noise is below -160. Exact-zero PCM is also run for class B and reported separately as zero input. 6 s (quick) or 15 s (full) long, the first 0.5 s dropped, analysed as Welch averages: 50 percent overlap, 8 segments of 2^20 samples at 352.8 kHz when the record is long enough (the full profile) and of 2^18 otherwise; the report states the number of averages used.
- **Analysis:** FFT 2^20, Blackman-Harris, 8 averages, bin power divided by the effective noise bandwidth to give dBFS per Hz. Integrated noise over 20 Hz to 20 kHz (unweighted and A-weighted), 20 kHz to 40 kHz, and 40 kHz up to the larger of 96 kHz and the output Nyquist, in steps of 48 kHz, to at least 192 kHz, which needs the 705.6 kHz or 1411.2 kHz decode (a 352.8 kHz output only reaches 176.4 kHz); class A is limited by its own output rate and the report says so.
- **Metric:** in-band noise dBFS and dB(A), referred to the rms of a full-scale sine (the AES17 and ASR convention: a noise power of 1e-10 reads -97.0 dBFS, 3.01 dB above its mean square re a peak of 1.0); noise density at 1 kHz and 20 kHz (dBFS/Hz); ultrasonic noise integrated in bands, as density at 50, 100 and 200 kHz (power per Hz over a third of an octave) and the highest third-octave band, flagged when it is the edge of the analysis band. A single bin is never reported as a peak: the largest of 10^5 noisy bins reads several dB above the noise, and its bin width changes with the FFT size.
- **Plot:** spectrum in dBFS per Hz, x log 20 Hz to 192 kHz (or the output Nyquist), y -180 to -60 dB; a second linear-x view to 192 kHz so noise-shaper humps are visible.
- **Why:** audiophiles look for ultrasonic noise (the shaped quantisation noise of DSD) that can upset amplifiers and tweeters, and for the in-band floor that sets low-level detail.

### 7. Dynamic range (-60 dB method)

- **Signal:** a coherent 1 kHz sine at -60 dB below 0 dB SACD (-66 dBFS).
- **Analysis:** FFT 2^18, A-weighted and unweighted. The tone is removed with a notch (AES17 method: a notch at 1 kHz, width as narrow as the window allows), the rest of the 20 Hz to 20 kHz band is integrated.
- **Metric:** dynamic range = 60 + (the level of the tone, in dB relative to 0 dB SACD, minus the level of the residual noise, in dB), reported unweighted and A-weighted; this is the DR value reviewers quote.
- **Plot:** spectrum of the -66 dBFS tone, y -160 to -60 dB, x log 20 Hz to 20 kHz.
- **Why:** it is the plain "how quiet is it?" number; it is the RMAA dynamic range figure.

### 8. THD and THD+N at 1 kHz, several levels

- **Signal:** coherent 1 kHz sines at 0 dB SACD (-6 dBFS), -20, -40 and -60 dB SACD, plus the peak level (-2.9 dBFS). For class A the peak-level tone is made by the reference modulator's design for that level (order 8, largest NTF gain 1.3, about 129 dB SINAD at DSD64), and its row names the design and carries that design's own floor.
- **Analysis:** FFT 2^18, Blackman-Harris, 1 average. THD is the power sum of harmonics 2 to 9 (up to 20 kHz) divided by the fundamental. THD+N is the notch method over 20 Hz to 20 kHz: everything except the fundamental, unweighted, plus the A-weighted figure.
- **Metric:** THD (dB and percent), THD+N (dB and percent), the largest single harmonic (order and level), SINAD (the negative of THD+N in dB).
- **Plot:** spectrum 0 to 24 kHz linear, y -160 to 0 dB, harmonics labelled; one panel per level.
- **Why:** these are the numbers in every review; the spectrum shows whether distortion is mostly low-order (benign) or high-order (harsher).

### 9. THD+N against level and against frequency

- **Signal:** against level: the steps of test 13 (1 kHz coherent sines from -6 dBFS down to -126 dBFS, 3 dB steps in the full profile and 6 dB in the quick one) and the peak level; against frequency: sines at 20 Hz, 100 Hz, 1, 5, 10, 15 and 20 kHz at 0 dB SACD.
- **Analysis:** as test 8, with a measurement bandwidth of 20 Hz to 20 kHz; at 15 kHz and 20 kHz the harmonic products fall above 20 kHz, so the harmonics are also counted up to 80 kHz (or 0.45 x the output rate) wherever they stand 6 dB above the local noise, and the report shows that figure beside the 20 kHz one. Counted harmonics are only those above the noise: a missing figure reads "none found" with a bound.
- **Metric:** THD+N in dB at each point; the level at which THD+N is lowest.
- **Plot:** THD+N in dB against level (x -100 to 0 dBFS, y -140 to -60 dB), and against frequency (x log 20 Hz to 20 kHz).
- **Why:** it shows how the device behaves for quiet and for loud passages, and whether the treble is as clean as the midrange (the ASR chart).

### 10. IMD, SMPTE and CCIF, and the IMD sweep

- **SMPTE signal:** 60 Hz and 7 kHz summed 4:1 in amplitude (the standard ratio), total level 0 dB SACD for the peak.
- **CCIF signal:** two equal tones at 19 kHz and 20 kHz, each at -6 dB below 0 dB SACD (so the sum peaks at 0 dB SACD).
- **Analysis:** SMPTE: the amplitude of the sidebands at 7 kHz +/- n x 60 Hz (n = 1 to 4) relative to the 7 kHz tone, as a percentage and in dB. CCIF: the difference tone at 1 kHz and the products at 18 and 21 kHz (and 2 and 3 kHz), relative to the sum of the tones. Window: Blackman-Harris, FFT 2^18, coherent tones. **Conventions:** every product is summed as power over a 21-bin lobe, so noise inside the lobes counts and a clean device reads its own noise (the sweep's lowest SMPTE levels are noise). CCIF is referenced to the power sum of the two tones, which reads 3.01 dB higher than the amplitude-sum reference of IEC 60268-3; SMPTE sums the sideband power against the 7 kHz tone. The labels say so. Compare only figures made the same way.
- **IMD sweep:** the CCIF pair centred on 10, 12, 14, 16, 18 and 19.5 kHz with a fixed 1 kHz spacing, and the SMPTE pair swept in level from -60 dB to 0 dB SACD.
- **Metric:** IMD in dB and percent per condition; the worst of the sweep.
- **Plot:** spectrum of each pair (zoomed on the products), and IMD against centre frequency or level.
- **Why:** intermodulation makes distortion that is not harmonically related to the music, which listeners find harsher than harmonic distortion at the same level.

### 11. 32-tone multitone with distortion-free range

- **Signal:** 32 sine tones spaced logarithmically from 17.6 Hz to 21.4 kHz, each on an FFT bin centre, phases optimised so the crest factor is 13.3 dB. Total level: the peak is set to 0 dB SACD (-6 dBFS), so the RMS is -19.3 dBFS and each tone has a peak amplitude of about -31.4 dBFS (-34.4 dBFS RMS). A fixed per-tone level must never be used, because 32 tones at equal levels can sum past 100 percent modulation. Only the 0 dB SACD multitone is run; a second one at the 71.43 percent level is not. The file has 1 s of silence, then whole periods of the signal with no ramp; one period at each end is left out of the analysis, which uses only the whole periods in between. The tone list is stored in the repository and in every report, so the signal is reproducible bit for bit.
- **Analysis:** FFT 2^20 points at 352.8 kHz (2^17 at 44.1 kHz, 2^18 at 88.2 kHz: one period of the signal) with a rectangular window, because every tone sits exactly on an FFT bin. That is only valid for a record that holds whole periods and has nothing outside the band that is not periodic: the ultrasonic noise of a modulator leaks through a rectangular window at 1/f, so class B is decoded to 44.1 kHz (pass edge 21.5 kHz) before the transform, and a device that outputs 48, 96 or 192 kHz is reported as "not run" because its period is not a whole number of samples. Tones and residual are taken up to 20 kHz: the 21.4 kHz tone sits on a decoder's roll-off and would set the figure alone.
- **Averages:** the headline value is the power spectrum averaged over the whole periods (8 in the full profile, to match published REW figures; 3 in the quick profile; the number is in the report); the 1-average value is reported next to it as an extra, because a single average reads about 10 dB more pessimistic. The multitone is peak-normalised per sample rate, so its crest factor differs by 0.03 dB between 88.2 kHz and 352.8 kHz.
- **Metric:** the distortion-free range: the level difference between the lowest-level tone and the highest of the in-between bins (the "multitone dynamic range"), the tone-to-residual ratio at each tone, and the average of the 31 residual bins in dB.
- **Plot:** spectrum 20 Hz to 22 kHz on a log axis; tones as markers and the residual as a line; y -140 to 0 dB.
- **Why:** it stresses a device with music-like signals; a clean residual at -100 dB or better is what a good converter shows, and the ASR multitone is a standard way to compare.

### 12. J-Test

- **Signal:** a tone at one quarter of the sample rate (11.025 kHz at 44.1 kHz) at -3 dBFS (the same for both classes), plus a square wave at fs/192 (229.7 Hz at 44.1 kHz) with an amplitude of plus and minus one least-significant bit at 24 bit (2 LSB peak to peak; Dunn's original toggles one LSB, so absolute sideband levels are not comparable with published J-Test figures). The 24-bit variant is the default; a 16-bit variant is optional.
- **Analysis:** FFT 2^18 points at the 1.3458 Hz grid (bin width the same at every output rate), Blackman-Harris, averages 3 or more. The jitter sidebands appear at odd multiples of fs/192 around the main tone. Each position is compared with the noise measured at the even positions between them, and with the stimulus itself: fs/4 is 48 x fs/192, so every sideband position is also an odd harmonic (number 48 +- n) of the +-1 LSB square wave, which the signal carries at baseband with amplitude (4/pi)/m LSB. A position counts as a sideband only when it is 6 dB above both.
- **Metric:** the level of the largest sideband that stands out, relative to the carrier (dB), or "none above the noise" with the noise floor and the bin width; the count of positions above -130 dBFS.
- **Plot:** spectrum 9 to 13 kHz (class A at 44.1 kHz), y -160 to -60 dB, with the expected sideband positions marked.
- **Why:** it is the standard jitter test; for file-level class A and B it measures the arithmetic of the chain and not the clock, so the report states "file-level jitter test (arithmetic only)". It is still useful because a poorly dithered or truncating chain shows up as sidebands.

### 13. Linearity down to -120 dB

- **Signal:** a coherent 1 kHz sine, stepped from -6 dBFS down to -126 dBFS in 3 dB steps, 1.5 s each (quick) or 2.5 s each (full), one file.
- **Analysis:** FFT 2^18 with Blackman-Harris. The tone level is read with a narrow window and compared with the stepped input; the residual is the energy outside +/- 4 bins around the tone.
- **Metric:** level error in dB at each step; the lowest level where the error stays within 0.5 dB (walking down from the top and stopping at the first level that fails); linearity error (deviation from a straight line) at -90, -100, -110 and -120 dB.
- **Plot:** level error in dB against input level (x -126 to -6 dB, y +/-3 dB), and measured against expected level on a 1:1 axis.
- **Why:** it shows how well low-level detail is preserved, the Stereophile linearity plot.

### 14. Crosstalk and channel matching

- **Signal:** stereo; a coherent 1 kHz sine at 0 dB SACD on one channel and silence on the other, repeated at 100 Hz, 1 kHz, 10 kHz and 20 kHz, and with the channels swapped.
- **Analysis:** FFT 2^18; the level at the tone frequency in the silent channel relative to the driven channel.
- **Metric:** crosstalk (dB) per frequency and direction; channel gain difference (dB) at 1 kHz; channel phase difference (degrees) at 1 kHz and 20 kHz.
- **Plot:** crosstalk against frequency, left to right and right to left, y -160 to -60 dB; a table for the matching figures.
- **Why:** it gives the sense of stereo separation and shows channel imbalance.

### 15. Polarity and DC

- **Signal:** an asymmetric pulse (a 10-sample rising half-sine of positive polarity) and silence for the DC test.
- **Analysis:** polarity from the sign of the output peak against the input peak; the DC figure is the mean of the dithered-silence record of the noise test, in dBFS. It is a noise statistic of that record (about -170 dBFS for the reference chain), not a measurement of a device's offset, and no verdict uses it.
- **Metric:** polarity (normal or inverted); DC offset (dBFS, absolute).
- **Plot:** none for polarity (a single field); DC is a number in the dashboard.
- **Why:** inverted polarity is audible to some on asymmetric material, and a DC offset can damage speakers and consume headroom.

### 16. Gain accuracy

- **Signal:** the 0 dB SACD step of test 13 (coherent 1 kHz sine at -6 dBFS).
- **Analysis:** the power in the tone's lobe (the Blackman-Harris main lobe, so the tone only, not the noise), relative to the expected level; one channel, and the channel difference from test 14.
- **Metric:** gain error in dB (positive means the output is louder than expected). For class A the expected level is -6 dBFS for a 50% DSD tone. For class B the expected output is the input level.
- **Plot:** a number in the dashboard, plus gain against level on the linearity plot.
- **Why:** an offset of 1 dB changes any A/B comparison; mismatched gain is the most common cause of a fake "better sound".

### 17. The 15 kHz -12 dBFS tone

- **Signal:** a single coherent 15 kHz sine at -12 dBFS (about -6 dB SACD), the tone Archimago uses for high-frequency distortion and noise-shaper checks. (An earlier draft combined it with a 1 kHz tone, which cannot both peak at 0 dB SACD and sit -12 dB below it; this definition replaces that one.)
- **Analysis:** FFT 2^18 and Blackman-Harris; the spectrum is examined for harmonics (30 kHz and above fall outside the audio band but are still shown), images and aliases, and for any component that is not the tone.
- **Metric:** the largest spurious component in 20 Hz to 20 kHz, dB relative to the tone, and its frequency; the largest component above 20 kHz and its frequency; the count of components above -100 dB.
- **Plot:** spectrum 0 to the output Nyquist frequency, y -160 to -20 dB, the tone and the largest spurs labelled.
- **Why:** high-frequency tones expose filter images, aliasing and noise-shaper behaviour that a 1 kHz tone hides.

## Modulator-only measurements

These tests apply to class B only.

### 18. Stability and overload

- **Signal:** three holds: 1 kHz at 0 dB SACD (-6 dBFS), 1 kHz at the peak level +3.1 dB SACD (-2.9 dBFS) and 20 kHz at the peak level, each 5 s (quick) or 60 s (full). The over-range levels and the silence after them are not run; the overload test below stands in for them.
- **Analysis:** the DSD stream is checked for: (a) the longest run of identical bits, (b) density of 1 bits over a sliding window of 28 bits, expressed as modulation (2 x density - 1), against the expected 71.43 percent at the peak level, (c) THD+N at the end of the hold against the start. Time to recover after an overload is the separate overload test (a 50 ms burst: digital full scale for class B, the peak level for class A), resolution about 10 ms.
- **Metric:** pass or fail per hold: the density in the 28-bit window never reaches 100 percent or 0 percent (so the modulator never saturates); the maximum modulation seen against 71.43 percent; the THD+N drift between the start and the end of the hold (dB); the overload recovery time (milliseconds).
- **Plot:** the 28-bit window density against time (min, mean and max per second) with the 71.43 percent line marked, plus the THD+N drift as a small table.
- **Why:** it tests that the modulator is stable at the loudest levels a player must still accept; an unstable loop makes loud bursts of noise or silence.

### 19. Ultrasonic peak level and frequency per rate

- **Signal:** 1 kHz sine at 0 dB SACD, and silence, for each DSD rate the modulator supports (DSD64, DSD128, DSD256 and up).
- **Analysis:** decode with the reference decoder at 705.6 kHz (DSD64 and DSD128) or 1411.2 kHz (DSD256 and up). Spectrum with FFT 2^20 and Blackman-Harris, 8 averages, over 20 kHz to the Nyquist of the decoded stream, in dBFS per Hz and integrated over each 20 kHz band.
- **Metric:** the noise density at 50, 100 and 200 kHz (dBFS/Hz, third-octave averages), the integrated 20 to 40, 40 to 96 and 96 to 192 kHz noise, and the highest third-octave band with its frequency (flagged "band edge" when the noise still rises at the limit of the analysis, as DSD64 noise does at 0.4 x the decode rate).
- **Plot:** spectrum 20 kHz to the Nyquist (linear x), y -160 to -40 dB; one line per DSD rate on one plot.
- **Why:** this is where the quality difference between DSD64 and higher rates is visible, and it is what the Archimago PDM notes show.

## Reduced methods

Some tests have a full method (the target) and a reduced method that version 0.1.1 uses because it costs less compute. This table lists every place where what the code does differs from the test text above. A report says which method was used.

| Test | Full method (target) | Reduced method (first round) |
|---|---|---|
| 2 Frequency response | log sweep with deconvolution | stepped coherent tones (31 at the full profile), plus the filter magnitude from the interleaved impulse response |
| 3 Filter magnitude | deconvolved sweep | the same stepped tones and the impulse-response magnitude |
| 5 Group delay | the deconvolved sweep's impulse response, 2^20 FFT | the interleaved impulse response of test 3 (352.8 kHz resolution), 2^17 FFT |
| 3 Alias tones | five tones at 2, 4, 6, 8 and 10 kHz above the output Nyquist frequency | the same; class A only; not run when the output rate is 352.8 kHz or more |
| 9 THD+N vs level, 13 Linearity | 3 dB steps, 10 s per step, all DSD rates | 3 dB steps from -6 dBFS to -126 dBFS, 2.5 s per step (full profile; 6 dB and 1.5 s in the quick profile), one record, DSD64; the peak level is a separate record |
| 10 IMD sweep | CCIF pairs at 1 kHz spacing from 10 to 19.5 kHz, SMPTE from -60 to 0 dB SACD | six CCIF pairs and five SMPTE levels, as listed |
| Durations | 10 s per tone, 60 s stability holds | 1.5 to 4 s per tone, 5 to 60 s holds (profile table above) |
| Channels | both channels, worst reported | one channel; the stereo pair only in test 14 |
| Settling and ramps | first 0.5 s and last 0.1 s discarded, raised-cosine ramps | the last FFT-length window of each record; no ramps (the table row above) |
| 11 Multitone | 3 s silence and a 2 s ramp; a second multitone at the peak level for class B | 1 s silence, whole periods, no ramp; 0 dB SACD only |
| 7 Dynamic range, 16 Gain | the measured tone level; the output rms | the nominal tone level (a gain error shifts DR by the same amount); the tone's lobe power |
| 15 DC offset | 60 s of silence | the mean of the noise record (a noise statistic) |
| 14 Crosstalk | 20 Hz to 20 kHz, both directions, one-third octaves | 1 kHz and 10 kHz, both directions, plus the channel gain and phase difference at both |
| 18 Overload recovery | several burst lengths and levels | one 50 ms burst: digital full scale (class B) or the +3.1 dB SACD peak (class A, because the reference modulator cannot be driven higher); resolution about 10 ms |
| Class A input rates | DSD64, DSD128, DSD256 | one rate per run (`dsd_rate`), DSD64 by default; a rate table adds DSD128 and DSD256 (`rates`) |
| 19 Ultrasonic peak per rate | all DSD rates | DSD64 in the main run; DSD128 and DSD256 in the rate table |

## The reference floor

A measurement cannot see below its own noise and distortion, so every report carries the floor of the reference chain and marks any device figure within 6 dB of it.

- **Class A** (the device is fed DSD from the reference modulator): the floor is the reference modulator and decoder together, measured with the same signals as the device (1 kHz at 0 dB SACD, -60 dB SACD, 32-bit-level dithered silence).
- **Class B** (the device's DSD is read by the reference decoder): the floor is the decoder alone, measured with an ideal 64-bit sine at the DSD rate, plus the rejection of loud tones just above multiples of the output rate (which would fold into the audio band if the stopband were weak).
- **What the reference achieves.** A single-bit modulator cannot be driven to full scale, so the floor is stated at 0 dB SACD (-6.02 dBFS), where 8th-order loops are stable. At DSD64 the reference modulator (order 8, largest NTF gain 1.45) reads THD+N of about -147 dB and an A-weighted dynamic range of about 152 dB; at DSD128 and DSD256 (order 7, gain 1.4) about -176 dB. The decoder alone reads below -280 dB, and its rejection of tones that would alias is better than 170 dB, so the decoder is not the limit.
- **Stability guard.** The modulator tries a ladder of designs from order 8 down to order 5 and uses the first that does not overload (the quantiser input stays within 2). The design used for each signal is written to the provenance file. At the +3.1 dB SACD peak level the guard picks order 8 at gain 1.3 (stable, about 129 dB SINAD at DSD64), or lower if that overloads. Every row made at the peak level or at -3 dBFS (the peak-level SINAD, the J-Test, the overload test) names the design that was used and carries a floor measured with that design; the peak-level SINAD is flagged "at the reference floor" within 6 dB of it.
- **Class A at DSD128.** Set `dsd_rate = 5644800`: the floor then moves to about -176 dB.
- A device that is limited by the floor is not shown as better than the floor; its row carries "at the reference floor".
- The floor is also what makes decoder side effects measurable. For example, a wide-band decoder filter lets DSD noise from 300 to 400 kHz fold back into the audio band (about +3 dB of in-band noise was seen with one decoder), which a floor of -122 dB would hide.

The test modulator in the dsd2pcm quality tools is a plain 5th-order design with a floor near -122.5 dBFS; the reference modulator here is the same family taken to higher order with the stability guard.

## Real-music null test

This is a separate test from everything above, and it is not synthetic. It decodes a DSD file you supply, with two or more decoders, aligns the outputs and reports how far below the music the difference is. Because it needs your file, it cannot be repeated by someone without it and it is not part of the reference floor comparison; it shows that decoders differ on that recording, not which is right.

| Item | Method |
|---|---|
| Common rate | The lower of the two output rates; Kaiser polyphase resampler, 160 dB stopband, flat to 0.45 x the rate. Upsampling is refused |
| Delay | Cross-correlation of first differences on four loud segments for the whole-sample lag, then the maximum of the band-limited cross-spectrum coherence for the fraction; applied with a 512-tap Kaiser sinc |
| Gain and polarity | Least squares in 20 Hz to 20 kHz; negative correlation flips the polarity |
| Difference | Subtracted in 64-bit float, in blocks, after trimming 0.5 s at each end |
| Results | RMS and peak of the difference, null depth (music RMS minus difference RMS), correlation, per second and per third-octave band from 20 Hz to 0.45 x the common rate |
| Verdict | Tiers of null depth over 20 Hz to 20 kHz, with sources, in the report |

## Report layout

One report per device under test, plus a comparison report across devices.

### Per-device report

```
report/<device>/
  index.html       the report: conclusions first, then the dashboard and the plots in the order above
  index.md         the same content in Markdown, for forges and diffs
  plots/*.svg      one SVG per plot, vector, no raster
  results.json     the conclusions (ids, verdicts, evidence) and every metric
  results.csv      the same, one row per metric and channel
  provenance.json  tool versions, input hashes, seeds, suite file hash
```

The report opens with a "Conclusions" block: a few plain sentences made by fixed rules from the figures, each with its evidence and thresholds. The rules, thresholds and sources are in [Conclusions](conclusions.md).

Each plot has:

1. a title in plain words ("Frequency response"),
2. the plot, with units on both axes,
3. a one-line "what this means" in plain English, filled from a fixed template with the real numbers ("The treble is flat to within 0.02 dB up to 20 kHz."),
4. a "details" line for engineers: signal id, FFT size, window, averages and the metric values.

### Comparison report

```
report/comparison/
  index.html       conclusions, then a dashboard table with one column per device, the best value in each row marked
  index.md
  results.json     the conclusions of the comparison
  plots/*.svg      overlays: frequency response, filter, impulse, noise, THD+N against level, linearity
  results.csv      one row per device and metric
```

Overlays use one colour and one line style per device, the same in every plot of a report. A comparison report is made from one suite run, so every device in it shares the suite file hash, the profile and the signals; results from separate runs are not merged.

### Visual style

One typeface family, a light page with a dark variant, a colour-blind-safe palette for the lines, axis ranges fixed per plot type as given above where a range is stated (so two reports can be laid side by side), a fixed figure size of 7.5 by 3.9 inches, and the plain-language line in a larger size than the detail line.

## Adapters

An adapter turns a device or a tool into "give me a PCM file for this DSD file" (class A) or "give me a DSD file for this PCM file" (class B).

| Adapter | Class | How it runs | Notes |
|---|---|---|---|
| `dsd2pcm` | A | CLI or Rust crate; a DSD file in, a WAV or FLAC out | The DSD to PCM library under test or a reference run |
| `scarletbook-pcm` 0.7.0 | A | its PCM output, run as a black box | Run only; its source is never read |
| `pysacd` | A | Python library or CLI | |
| `sacd_extract` | A | black box: run it and take the output | Run only |
| `foobar2000-sacd` | A | import only: WAVs made elsewhere with the foobar2000 SACD plug-in are read with their provenance recorded | A manual step; the report says "imported" |
| `sox-dsd` | A and B | black box: the pinned container through `tools/reftool.sh`, or SoX on the path | Optional; the modulator is `sdm-8`, `clans-8` or `auto` (CLANS-8, 7 and 6 for DSD64, 128 and 256, as in Archimago's 2022 tests) |
| `cli` | A or B | a generic command template with `{input}` and `{output}` placeholders | The universal fallback |
| `import` | A or B | read a WAV, FLAC or DSF produced elsewhere, with the device name and a note | No tool is run |

Rules for adapters:

- **Gain convention.** Some encoders map WAV full scale to 50 percent modulation (0 dB SACD). The pinned SoX-DSD does this: its DSD sits 6.02 dB below what Archimago's level rule (0 dB SACD = 50 % = -6 dBFS) assumes, so a tone that is 0 dBFS in the WAV comes out at 0 dB SACD rather than +6 dB SACD. Class B outputs are decoded and then corrected, and class A outputs are corrected, by the +6.0206 dB that the adapter applies and the provenance file records. The adapter applies the gain that makes the output level equal the input level (for example +6.02 dB) and reports the gain in the provenance file; test 16 (gain accuracy) is measured after that, and the raw gain is a separate field.
- An adapter never modifies the signal; it passes the file unchanged and records the command and the output hash.
- If the output length or sample rate differs from what the test expects, the adapter reports it and the analysis uses the output's own rate.
- Decoder source code of SACD or DST decoders is never read to write an adapter; those tools are run as black boxes only.
- A device that cannot run a test (for example a decoder that clips at the peak level) records "not run" with a reason; it never records a silent zero.

## Determinism and provenance

- All signal generators are deterministic. Where noise or dither is needed, a fixed seed is used and recorded.
- Each report records the name and version of every tool used, the Python, NumPy and SciPy versions, the SHA-256 of every input and output file, the suite file's hash, and the command line.
- The reference decoder and modulator are versioned. A change in either bumps the report's "reference chain" version, so old and new results are not silently mixed.
- The measurement floor of the reference chain is computed at the start of each run (it is deterministic, and cached within a process), stored in every report's `results.json` and shown in every report. It is not a file in the repository: to compare, read `reference_floor` in two reports.

## See also

- [Documentation index](README.md)
- [Archimago's Musings](https://archimago.blogspot.com/) for the DSD measurement series that shaped this set
- [Audio Science Review](https://www.audiosciencereview.com/) for the dashboard and multitone conventions
- [Stereophile](https://www.stereophile.com/content/measurements-maps-precision) (John Atkinson) for the digital measurement set
- [AES17](https://www.aes.org/publications/standards/) for the measurement method for digital audio equipment

Part of the [DSD Toolbox](https://github.com/dsd-toolbox/dsd-toolbox).
