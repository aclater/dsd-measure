[dsd-measure](../README.md) › [Documentation](README.md) › Accuracy

# Accuracy

How the numbers of dsd-measure are checked, how well they agree with signals whose answer is known, with a second analyser written separately and with other tools, and where they are known to stop being exact. Everything here can be re-run: `scripts/validate.sh` makes every table on this page.

## Contents

- [The claim in one table](#the-claim-in-one-table)
- [Method](#method)
- [Known answers, metric by metric](#known-answers-metric-by-metric)
- [The reference chain, read by three methods](#the-reference-chain-read-by-three-methods)
- [Other tools](#other-tools)
- [The published SoX-DSD tests](#the-published-sox-dsd-tests)
- [Conventions that change a number](#conventions-that-change-a-number)
- [Repeatability](#repeatability)
- [Known limits](#known-limits)
- [What the validation found](#what-the-validation-found)
- [Re-run it](#re-run-it)

## The claim in one table

| Metric | Validated to | Against |
|---|---|---|
| Tone level, gain error, channel gain and phase difference | 0.002 dB, 0.01 deg | known tones; sine fit; SoX; ffmpeg |
| THD, THD+N, SINAD, A-weighted THD+N (-60 to -160 dB, 20 Hz to 9 kHz tones, 16-bit to float64) | 0.15 dB | known harmonics and noise; sine fit; notch method; SoX (0.02 dB) |
| Noise 20 Hz-20 kHz, A-weighted, 20-40 kHz, density | 0.25 dB for one record of coloured noise, 0.1 dB for white noise | exact noise spectra; Welch with a Hann window; SoX |
| Dynamic range (-60 dB method) | 0.1 dB | known noise, referred to 0 dB SACD |
| A-weighting | 0.005 dB against the exact IEC 61672-1 curve, 0.05 dB against its rounded table | pole-zero evaluation |
| IMD SMPTE and CCIF | 0.01 dB | polynomial nonlinearities with analytic products; least-squares fit |
| Frequency response, -0.1/-1/-3 dB frequencies, ripple, group delay | 1 Hz, 0.0005 dB, 0.01 microsecond | Butterworth and echo filters with analytic responses; phase slope |
| Impulse ringing, step overshoot and settling | exact count, 0.2 percent points, 0.01 ms | built-in echoes; a 2nd-order system |
| Crosstalk | 0.05 dB | known leakage down to -150 dB |
| Multitone residual and range | 0.15 dB | injected spur and noise on the standard tones; the reference decoder read at 44.1, 88.2, 176.4 and 352.8 kHz (every record decimated to 44.1 kHz first) and the modulator column agree to 3 dB |
| J-Test carrier and sideband detection | 0.01 dB; a -120 dB sideband found to 0.03 dB; none reported in white noise or in noise that tilts by 25 dB and ripples by 24 dB across the band (each position is compared with its two neighbours) | built signals |
| Ultrasonic density and band levels | 0.1 dB | white noise and tones with known level |
| Spur level and frequency | 0.05 dB, one bin | injected spurs |
| Reference floor (DSD64, 0 dB SACD, -146.73 dB THD+N) | 0.05 dB | sine fit (-146.70) and notch (-146.73) on the same record of the real output; SoX reads -146.95 over a longer stretch of the same file |

Not covered by this validation: the peak-level (+3.1 dB SACD) SINAD of a class A device is measured with the reference modulator's design for that level (order 8, gain 1.3), whose own floor (about 129 dB at DSD64) is shown beside the figure and limits it; the class B filter rows are not shown, because they describe the reference decoder; the alias-tone stopband figure (an upper bound that includes the device's noise, read from tones that start 20 kHz below the output rate; its accuracy is tested on the reference decoder at 44.1, 88.2 and 176.4 kHz only), the device-delay probe (peak of one impulse, whole samples), the filter, group-delay, polarity and stability rows (not used by any conclusion), and the DC offset (a statistic of the dither record). The [limits](#known-limits) below say where the other figures stop being exact.

## Method

Four separate checks, all made by the authors, from the strictest to the broadest.

1. **Known answers.** Each analyser is run on a signal built so that its answer is a formula, not a measurement: a sine with a 3rd harmonic at exactly -100 dB and white noise of known power, noise shaped as 1/f or 6 and 12 dB per octave built bin by bin, a polynomial nonlinearity with analytic IMD products, a Butterworth filter with analytic magnitude and group delay, a three-tap echo with an analytic ripple, a 2nd-order system with an analytic overshoot, blocks of noise just inside and just outside the band edges, 16 and 24-bit TPDF-dithered silence, and float32 storage. The tolerance is stated per row (the tightest is 0.002 dB for levels, 0.1 dB for distortion and noise down to -160 dB; noise that is a random sample is checked to the scatter of one record, see [limits](#known-limits)).
2. **A second analyser.** `tests/refanalyser.py` is a deliberately separate implementation in plain numpy. It shares no code with `dsd_measure.analyse` and uses different methods: a least-squares sine fit in the time domain (IEEE 1057) for levels, harmonics and intermodulation products; the fit residual, band-limited with a Kaiser window and an exact rectangular band, for THD+N; a second THD+N from a time-domain IIR notch cascade run forwards and backwards (a notch that is not the AES17 one: the standard's notch has a Q of 1.2 to 3, see [methodology limits](methodology-limits.md#what-follows-aes17)); A-weighting from the IEC 61672-1 poles and zeros with the standard's own constants; Welch noise with a Hann window; group delay as the slope of the phase. The two must agree within the stated tolerance on every synthetic signal and on the reference chain's real output.
3. **Other tools** run on the same files: SoX 14.4.2 (resampling, FIR band-limit and band-reject, `stats`) and ffmpeg 7.1 (`astats`, and its DSD decoder), each from a pinned container. REW cannot be used, see [other tools](#other-tools).
4. **Published results.** The SoX-DSD test conditions of Archimago's 2021-10 and 2022-06 posts are run with the pinned SoX-DSD, and the figures he states in text are compared with ours.

## Known answers, metric by metric

Worst error is the largest absolute difference between the analyser and the known answer over all cases of that metric; the second analyser column is the largest difference between the two analysers. Both are in the unit of the metric (dB unless stated). A row passes when both are inside the tolerance.

| Metric | Cases | Worst error vs truth | Tolerance | Cases vs 2nd analyser | Worst difference | Tolerance |
|---|---:|---:|---:|---:|---:|---:|
| -0.1 dB frequency, Hz | 2 | 0.0301 | 1.0 |  |  |  |
| -1 dB frequency, Hz | 2 | 0.2043 | 1.0 |  |  |  |
| -3 dB frequency, Hz | 2 | 0.3118 | 1.0 |  |  |  |
| A-weighting, dB | 34 | 0.0489 | 0.1 | 34 | 0.0046 | 0.01 |
| DC offset, dBFS | 3 | 0.0000 | 0.01 | 3 | 0.0000 | 0.01 |
| IMD CCIF, dB | 3 | 0.0012 | 0.1 | 3 | 0.0000 | 0.1 |
| IMD CCIF, dB (IEC 60268-3 convention) | 3 | 0.0012 | 0.1 |  |  |  |
| IMD SMPTE, dB | 4 | 0.0021 | 0.1 | 4 | 0.0000 | 0.1 |
| IMD SMPTE, dB (amplitude-sum convention) | 4 | 0.0021 | 0.1 |  |  |  |
| J-Test carrier, dBFS rms | 1 | 0.0000 | 0.01 |  |  |  |
| J-Test sideband level, dB re carrier | 1 | 0.0259 | 0.5 |  |  |  |
| J-Test sideband order | 1 | 0.0000 | 0.0 |  |  |  |
| J-Test sidebands found (1 = yes) | 2 | 0.0000 | 0.0 |  |  |  |
| THD+N A-weighted, dB | 6 | 0.0832 | 0.1 | 6 | 0.0128 | 0.1 |
| THD+N floor, non-coherent tone (must read -160 dB or lower) | 3 | reads -161.6 to -171.8 | limit |  |  |  |
| THD+N, dB | 85 | 0.1366 | 0.5 | 83 | 0.0242 | 0.3 |
| THD+N, dB (notch method) | 6 | 0.0831 | 0.1 | 6 | 0.0175 | 0.1 |
| THD, dB | 80 | 0.0883 | 0.1 | 80 | 0.0146 | 0.1 |
| channel gain difference, dB | 3 | 0.0000 | 0.002 |  |  |  |
| channel phase difference, deg | 3 | 0.0000 | 0.01 |  |  |  |
| crosstalk, dB | 4 | 0.0008 | 0.05 | 4 | 0.0001 | 0.05 |
| dynamic range -60 dB method, dB | 3 | 0.0535 | 0.1 | 3 | 0.0722 | 0.15 |
| dynamic range A-weighted, dB | 3 | 0.0421 | 0.1 |  |  |  |
| fundamental level, dBFS rms | 75 | 0.0001 | 0.002 | 72 | 0.0000 | 0.002 |
| gain error, dB | 3 | 0.0001 | 0.005 |  |  |  |
| group delay (linear phase, constant removed), us | 3 | 0.0000 | 0.001 |  |  |  |
| group delay, us | 10 | 0.0000 | 0.01 | 10 | 0.0000 | 0.01 |
| magnitude at 15 kHz, dB | 2 | 0.0000 | 0.001 | 2 | 0.0000 | 0.001 |
| multitone residual mean, dBFS per bin | 1 | 0.0078 | 0.15 |  |  |  |
| multitone residual peak, dBFS | 1 | 0.0000 | 0.1 |  |  |  |
| noise 20 Hz-20 kHz, dBFS | 13 | 0.0790 | 0.25 | 13 | 0.0838 | 0.25 |
| noise 20-40 kHz, dBFS | 3 | 0.0663 | 0.3 | 3 | 0.0241 | 0.3 |
| noise A-weighted, dBFS | 9 | 0.0433 | 0.25 | 9 | 0.0456 | 0.25 |
| noise density at 1 kHz, dBFS/Hz | 6 | 0.5547 | 0.7 |  |  |  |
| passband ripple p-p, dB | 3 | 0.0000 | 0.0005 | 3 | 0.0000 | 0.0005 |
| polarity (1 = normal) | 2 | 0.0000 | 0.0 |  |  |  |
| post-ringing, samples | 1 | 0.0000 | 0.0 |  |  |  |
| pre-ringing, samples | 1 | 0.0000 | 0.0 |  |  |  |
| spur frequency, Hz | 3 | 0.0000 | 1.3458251953125 |  |  |  |
| spur level, dB re tone | 3 | 0.0000 | 0.05 |  |  |  |
| step overshoot, percent | 3 | 0.1452 | 0.2 |  |  |  |
| step settling 1 %, ms | 3 | 0.0000 | 0.01 |  |  |  |
| ultrasonic density, dBFS/Hz | 2 | 0.0200 | 0.1 |  |  |  |
| ultrasonic integrated 40-96 kHz, dBFS | 1 | 0.0000 | 0.1 |  |  |  |
| ultrasonic peak 1/3-octave centre, Hz | 1 | 4431 | 4431 (1/3 octave) |  |  |  |


Things this table does not say in one line:

- **Levels** (tone level, gain, channel match) are exact to 0.002 dB for coherent and non-coherent tones alike, because a tone's level is the sum of its window lobe.
- **THD, THD+N and SINAD** agree to 0.15 dB with the truth and 0.1 dB with both second methods from -60 dB down to -160 dB, at 44.1, 96 and 352.8 kHz, for tones from 20 Hz to 9 kHz, for the A-weighted figure, and for 16 and 24-bit dithered signals.
- **The 20 kHz edge.** A noise block 20 dB louder than the signal just above 20 kHz does not enter the figure (0.02 dB); the same at the 20 Hz end (0.01 dB). Tones whose harmonics fall past 20 kHz have those harmonics left out of THD and THD+N, by definition.
- **A-weighting** differs from the IEC 61672-1 table by at most 0.05 dB (the table is rounded to 0.1 dB) and from the exact pole-zero curve by 0.005 dB, over 10 Hz to 20 kHz.

## The reference chain, read by three methods

The reference chain's floor (DSD64, 1 kHz at 0 dB SACD) is the number everything else is judged against, so it was read by three methods, on the real output of the reference modulator and decoder (352.8 kHz float64, with the delta-sigma noise up to 141 kHz in the record):

| Case | THD+N main | THD+N sine fit | THD+N notch | THD+N SoX | THD main | THD harmonic fit | A-weighted main | A-weighted fit |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| DSD64, 0 dB SACD | -146.73 | -146.70 | -146.73 | -146.95 | -164.34 | -165.78 | -150.31 | -150.29 |
| DSD64, -20 dB SACD | -127.71 | -127.77 | -127.83 | -127.63 | -147.60 | -151.11 | -131.20 | -131.24 |
| DSD64, -60 dB SACD | -88.19 | -88.20 | -88.24 | -88.30 | -104.00 | -105.11 | -91.55 | -91.56 |
| DSD128, 0 dB SACD | -175.85 | -175.85 | -175.88 | -174.95 | -184.32 | -184.59 | -177.17 | -177.17 |

### Same bits decoded by ffmpeg

| ffmpeg output rate (Hz) | SINAD main (dB) | SINAD sine fit (dB) |
|---|---:|---:|
| 352800 | 146.52 | 146.49 |
| 176400 | 138.98 | 138.99 |
| 88200 | 126.31 | 126.30 |
| 44100 | 138.24 | 138.24 |

The same bits decoded by ffmpeg's own DSD decoder at four output rates, read by both analysers: 146.52 dB at 352.8 kHz, 138.98 dB at 176.4 kHz, 126.31 dB at 88.2 kHz and 138.24 dB at 44.1 kHz. One decoder, one stream, 20 dB apart: the output rate decides the floor, which is why the [footprint](footprint.md#principles) requires every comparison to state it.

The sine-fit and notch methods use the exact stimulus frequency and a Kaiser-weighted fit. A fit without a window reads -124 dB on the same record: the ultrasonic noise (about -50 dBFS) leaks through a rectangular window into every fitted line. This is a warning for anyone who re-analyses these files by hand, and it is the same mechanism that made the class B multitone read 104 dB before 0.1.1 (see [findings](#what-the-validation-found)).

## Other tools

Error against the known answer (dB) on the same synthetic files, from each analyser and tool:

| Metric | Case | Truth | dsd-measure | Sine-fit analyser | SoX | ffmpeg |
|---|---:|---:|---:|---:|---:|---:|
| THD+N, dB | -6 dBFS tone, harmonic -100 dB | -99.586 | -0.017 | 0.003 | 0.006 | n/a |
| tone level, dBFS rms | -6 dBFS tone | -9.010 | -0.000 | -0.000 | 0.000 | -0.000 |
| THD+N, dB | -6 dBFS tone, harmonic -120 dB | -119.586 | 0.050 | 0.001 | 0.006 | n/a |
| tone level, dBFS rms | -6 dBFS tone | -9.010 | 0.000 | -0.000 | 0.000 | -0.000 |
| THD+N, dB | -60 dBFS tone, harmonic -90 dB | -89.586 | 0.044 | 0.004 | -0.014 | n/a |
| tone level, dBFS rms | -60 dBFS tone | -63.010 | 0.000 | 0.000 | 0.000 | -0.000 |
| THD+N, dB | -6 dBFS tone, harmonic -140 dB | -139.586 | 0.005 | 0.017 | -0.014 | n/a |
| tone level, dBFS rms | -6 dBFS tone | -9.010 | -0.000 | 0.000 | 0.000 | -0.000 |
| noise 20 Hz-20 kHz, dBFS | white, sigma 0.0001 | -86.449 | -0.025 | -0.007 | -0.011 | n/a |
| noise full band, dBFS rms (no filter) | white, sigma 0.0001 | -80.000 | -0.009 | n/a | n/a | -0.009 |
| noise 20 Hz-20 kHz, dBFS | white, sigma 3e-06 | -116.906 | 0.009 | -0.009 | -0.013 | n/a |
| noise full band, dBFS rms (no filter) | white, sigma 3e-06 | -110.458 | -0.002 | n/a | n/a | -0.002 |
| noise 20 Hz-20 kHz, dBFS | white, sigma 1e-07 | -146.449 | 0.037 | -0.022 | -0.001 | n/a |
| noise full band, dBFS rms (no filter) | white, sigma 1e-07 | -140.000 | 0.003 | n/a | n/a | 0.003 |
| DC offset (linear) | 1e-3 on a 0.3 sine | 0.001 | 0.000 | -0.000 | n/a | 0.000 |

- **SoX** agrees with the known answers to 0.02 dB at every level from -60 to -160 dB, using only `rate`, `sinc` (band-limit and band-reject) and `stats`. A SoX recipe: resample to 96 kHz, `sinc -a 140 -t 25 20 sinc -a 160 -t 150 -20000`, band-reject 80 Hz round the tone with two `sinc` stages, and read `stats` RMS over a steady stretch away from the start and the end (the end of a file rings). Two traps: SoX's `bandreject` filter is not pre-warped, so a narrow notch misses the tone by 60 dB, and a narrow `sinc` at 352.8 kHz silently runs out of taps (32767) and rejects only 40 dB.
- **ffmpeg** agrees on tone level, full-band noise and DC to 0.01 dB (`astats`). Its own DSD decoder is a useful second decoder; see the table above.
- **REW** (Room EQ Wizard 5.31.3) could not be used headless on Linux. It installs silently and starts under a virtual display, but its API (the only scriptable interface) does not start: it reports "API not supported in this build" with the bundled Java and with Java 21, and the program has no command-line analysis mode. Driving its GUI would be fragile and was not attempted. REW's own agreement with these figures is therefore not claimed.

## The published SoX-DSD tests

Archimago's 2021-10 and 2022-06 posts use SoX-DSD as the modulator and measure DAC outputs; only the trends and the file-level parts carry over. The conditions are run with the pinned container and decoded with the reference decoder (the "perfect DAC" of his foobar tests), 1 kHz at the level he states, 12 s files:

| Run | Modulator | DSD rate | Input (dBFS) | Trellis | SINAD (dB) | THD+N A-weighted (dB) | THD (dB) |
|---|---:|---:|---:|---:|---:|---:|---:|
| a21-clans-4 | clans-4 | DSD64 | -0.1 | default | 104.6 | -106.7 | -115.0 |
| a21-clans-6 | clans-6 | DSD64 | -0.1 | default | 121.1 | -123.6 | -133.3 |
| a21-clans-8 | clans-8 | DSD64 | -0.1 | default | 119.5 | -120.3 | -130.0 |
| a21-sdm-4 | sdm-4 | DSD64 | -0.1 | default | 106.2 | -108.3 | -115.7 |
| a21-sdm-6 | sdm-6 | DSD64 | -0.1 | default | 128.0 | -130.8 | -140.0 |
| a21-sdm-8 | sdm-8 | DSD64 | -0.1 | default | 140.8 | -143.7 | -154.7 |
| a21-sdm-8-dsd128 | sdm-8 | DSD128 | -0.1 | default | 179.6 | -180.5 | -196.0 |
| a22-clans-8 | clans-8 | DSD64 | -2.9 | 32x32 | 115.1 | -116.0 | -131.7 |
| a22-clans-7 | clans-7 | DSD128 | -2.9 | 32x32 | 155.1 | -157.3 | -175.7 |
| a22-clans-6 | clans-6 | DSD256 | -2.9 | 32x32 | 174.8 | -176.9 | -193.1 |
| dr-sdm-8 | sdm-8 | DSD64 | -60.0 | default | 82.2 | -85.1 | -97.8 |
| dr-clans-8 | clans-8 | DSD64 | -60.0 | default | 62.9 | -63.6 | -77.3 |

| Run | 50 kHz (dBFS/Hz) | 100 kHz (dBFS/Hz) | Highest 1/3 octave (kHz) | 20-40 kHz (dBFS) | 40-96 kHz (dBFS) |
|---|---:|---:|---:|---:|---:|
| a21-clans-4 | -104.3 | -82.9 | 226 | -77.4 | -43.5 |
| a21-clans-6 | -100.7 | -77.7 | 226 | -78.2 | -38.0 |
| a21-clans-8 | -101.0 | -78.1 | 226 | -79.3 | -38.4 |
| a21-sdm-4 | -104.5 | -80.0 | 226 | -78.4 | -41.6 |
| a21-sdm-6 | -100.3 | -70.3 | 226 | -81.1 | -29.5 |
| a21-sdm-8 | -86.7 | -71.2 | 226 | -74.3 | -24.1 |
| a21-sdm-8-dsd128 | -137.6 | -87.3 | 143 | -125.2 | -55.3 |
| a22-clans-8 | -98.5 | -76.1 | 226 | -77.5 | -35.4 |
| a22-clans-7 | -123.6 | -92.3 | 226 | -104.6 | -55.1 |
| a22-clans-6 | -154.9 | -121.9 | 226 | -135.0 | -85.4 |
| dr-sdm-8 | -87.7 | -74.8 | 71 | -75.8 | -25.3 |
| dr-clans-8 | -104.1 | -80.6 | 226 | -82.6 | -41.0 |

| PCM source rate | Tone (Hz) | Level re 1 kHz (dB) |
|---|---:|---:|
| 44100 | 1000 | 0.00 |
| 44100 | 20000 | -0.00 |
| 44100 | 21400 | -23.12 |
| 96000 | 1000 | 0.00 |
| 96000 | 20000 | -0.00 |
| 96000 | 21400 | 0.00 |

Against his stated figures:

| Statement in the posts | Here |
|---|---|
| CLANS-8 at DSD64 reads about -116 dB THD+N through an ideal decode (2022-06) | 115.1 dB SINAD at -2.9 dBFS in with `-t 32 -n 32`, 119.5 dB at -0.1 dBFS with SoX's own trellis settings |
| SDM-8 has lower noise than CLANS-8 (2022-06; "above 5th order SDM is sometimes better", 2021-10) | SDM-8 140.8 dB against CLANS-8 119.5 dB at the same input: 21 dB higher, at every level run; at -60 dBFS 82.2 against 62.9 dB |
| Higher orders give better noise and distortion below 20 kHz (2021-10) | SDM 4, 6, 8: 106.2, 128.0, 140.8 dB. CLANS 4, 6, 8: 104.6, 121.1, 119.5 dB: CLANS-8 does not read higher than CLANS-6 here |
| Order 8 gives about 140 dB and order 5 about 120 dB in band (2022-06) | SDM-8 140.8 dB; the 5th order lies between the measured 4th and 6th (106 to 128 dB) |
| DSD64 ultrasonic noise is highest, then DSD128, then DSD256 (2021-10) | 40-96 kHz integrated, CLANS at -2.9 dBFS: -35.4, -55.1, -85.4 dBFS for DSD64, 128, 256 |
| DSD128 pushes the noise an octave higher, peaking around 120 kHz (2021-10) | SDM-8 DSD128: highest third octave at 143 kHz (his figure is through a DAC's filter) |
| The 32nd multitone tone at 21.4 kHz drops by about 24 dB through SoX-DSD's steep filter (2021-10) | -23.1 dB from a 44.1 kHz source, 0.0 dB from a 96 kHz source |
| Test signals peak at +3.1 dB SACD (-2.9 dBFS) (2022-06) | SoX-DSD maps PCM full scale to 50 percent modulation, so -2.9 dBFS in is 36 percent (-2.9 dB SACD): the label and the modulation depth differ by 6.02 dB (the adapter's `input_gain_db` fixes the mapping) |

His DAC figures (THD+N around -110 dB, multitone range 112 to 120 dB, a 6 dB level step at DSD) are analogue measurements and are not reproduced here.

## Conventions that change a number

Anyone comparing with other published figures needs these.

- **SINAD** here is the 1 kHz tone over everything else in 20 Hz to 20 kHz, unweighted, 20 Hz to 20 kHz (not comparable with an analogue full-scale reading), at the level in the label (0 dB SACD, -6.02 dBFS, unless it says otherwise). It is THD+N with the sign flipped. When the floor is noise, SINAD falls one dB for each dB the tone is lower, so the same device reads 6.02 dB higher at 0 dBFS than at -6.02 dBFS and 54 dB lower at -60 dBFS; a figure without its level is not comparable. When the floor is distortion that scales with the level the figure changes less.
- **Noise dBFS** is referred to the rms of a full-scale sine (the AES17 convention, also used by ASR and RMAA), so a noise whose mean square is 1e-10 reads -97.0 dBFS. Before 0.1.1 the toolkit quoted the mean square (3.01 dB lower).
- **Dynamic range** is the -60 dB method referred to 0 dB SACD (-6.02 dBFS): a device reads 6.02 dB higher against digital full scale, which is what some published tables use.
- **THD** covers harmonics 2 to 9 below 20 kHz (the 20 kHz band edge decides how many). **THD+N bandwidth** is 20 Hz to 20 kHz; the notch leaves out +-13.5 Hz round the tone.
- **IMD CCIF** is referred to the power sum of the two tones; the IEC 60268-3 convention refers to the sum of the amplitudes and reads 3.01 dB lower (`imd_db_iec`). **IMD SMPTE** is the root-sum-square of the sidebands re the 7 kHz tone; the arithmetic-sum convention reads up to 6 dB higher with four sidebands (`imd_db_amplitude_sum`). Both include the noise in the 21-bin lobes.
- **A-weighting** is the IEC 61672-1 curve, 0 dB at 1 kHz; the figure is the noise power through it.
- **Output rate and level mapping.** A decoder's in-band floor depends on the rate it writes, and tools map PCM full scale to different DSD depths; see the rule in the [footprint](footprint.md#principles).

## Repeatability

How far a figure moves when nothing changes but the noise. The reference modulator is a chaotic system: a change of one part in 10^14 at its input gives a different bitstream with the same statistics, so every figure read near the noise floor has a spread from one noise realisation to the next. That spread is the repeatability, and it is what a comparison between two versions of a converter has to allow for.

It was measured on the quick suite of the reference chain (DSD64, class A at 44.1 kHz and class B). White noise of 1e-14 rms (-280 dBFS) was added to the modulator's input, with 12 different seeds, and the whole suite was run for each. The table gives the mean and the standard deviation of the class A column; the class B column agrees within 0.1 dB in every row but the CCIF IMD (1.2 dB).

| Figure | Mean | Standard deviation (dB) | Allowed between two runs (dB) |
|---|---:|---:|---:|
| SINAD, 1 kHz at 0 dB SACD | 146.9 dB | 0.14 | 0.6 |
| THD, 1 kHz at 0 dB SACD | -163.6 dB | 0.32 | 1.5 |
| THD+N A-weighted | -150.3 dB | 0.12 | 0.6 |
| SINAD at the peak level | 129.2 dB | 0.13 | 0.6 |
| Dynamic range, A-weighted | 150.5 dB | 0.10 | 0.5 |
| Noise 20 Hz to 20 kHz, A-weighted | -162.4 dBFS | 0.03 | 0.2 |
| Noise 20 Hz to 20 kHz | -159.0 dBFS | 0.04 | 0.2 |
| IMD SMPTE | -144.9 dB | 0.41 | 1.8 |
| IMD CCIF | -135.4 dB | 0.64 | 2.8 |
| Multitone distortion-free range | 152.4 dB | 0.72 | 3.1 |
| Worst alias image | -156.5 dB | 1.38 | 6.0 |
| J-Test noise floor | -159.7 dB | 0.40 | 1.7 |
| Reference floor, THD+N of the chain | -146.9 dB | 0.11 | 0.5 |
| Reference floor, decoder alone | -280.9 dB | 0 | 0 |

"Allowed between two runs" is three standard deviations of a difference (3 x 1.414 x the larger standard deviation of the two interpolators below), rounded up; the [release gate](options.md#release-gate) uses these values. The figures of the reference chain are the worst case, because they are all noise: a converter that is clear of the floor repeats better. A decoder (class A) that is deterministic gets the identical bitstream in both runs, so its own figures repeat exactly; the spread then matters only between versions of dsd-measure. The multitone range and the alias image are read from single bins, which is why they spread most. The decoder alone has no modulator in front of it and reads the same in every run.

The multitone range of the 0.1.1 reference chain was published as 150.7 dB. With 12 seeds the same 0.1.1 chain reads 151.0 to 153.7 dB (mean 152.4 dB): 150.7 dB was one draw from the low end, and a tolerance of 1 dB around it was narrower than the figure repeats.

### The FFT interpolator of 0.1.3

Since 0.1.3 the interpolator in front of the reference modulator runs each filter stage as FFT convolutions instead of the direct form. The filters are the same. Two things show that no figure moved:

- **The signal.** The interpolated signal differs from the direct form's by rounding only: less than 1e-14 of full scale (-280 dB) in every case of `tests/test_perf.py` (4e-15 on a 31 s signal), more than 130 dB below the reference floor. For signals at the level of the dither the modulator writes the identical bitstream.
- **The figures.** For larger signals the bitstream is a different one with the same statistics, so the proof is statistical. The ensemble above was run with both interpolators (12 seeds each, 24 runs). Of the 429 numbers in the two `results.json` files, 106 are the same in all 24 runs and 323 vary with the seed. Welch's t-test between the two ensembles gives p below 0.05 for 18 of the 323 (16 are expected by chance), below 0.01 for 4 (3 expected) and below 0.001 for none. No figure separates the two interpolators.

| Figure (class A) | Direct form, mean | sd | FFT, mean | sd | p |
|---|---:|---:|---:|---:|---:|
| SINAD, 1 kHz at 0 dB SACD (dB) | 146.901 | 0.136 | 146.879 | 0.107 | 0.66 |
| THD (dB) | -163.626 | 0.324 | -163.922 | 0.321 | 0.035 |
| SINAD at the peak level (dB) | 129.191 | 0.097 | 129.183 | 0.127 | 0.86 |
| Dynamic range, A-weighted (dB) | 150.509 | 0.047 | 150.476 | 0.100 | 0.32 |
| Noise, A-weighted (dBFS) | -162.440 | 0.030 | -162.440 | 0.030 | 1 |
| IMD SMPTE (dB) | -144.854 | 0.407 | -144.625 | 0.403 | 0.18 |
| IMD CCIF (dB) | -135.382 | 0.643 | -135.780 | 0.381 | 0.08 |
| Multitone distortion-free range (dB) | 152.448 | 0.718 | 152.408 | 0.495 | 0.88 |
| Worst alias image (dB) | -156.465 | 1.380 | -156.616 | 0.984 | 0.76 |
| Reference floor, THD+N of the chain (dB) | -146.948 | 0.114 | -146.907 | 0.076 | 0.32 |

A single 0.1.3 report is one draw from this distribution, as a 0.1.1 report was: its SINAD reads 146.9 dB where the 0.1.1 report read 147.0 dB, and its multitone floor 152.7 dB where 0.1.1 read 150.7 dB. The stimulus cache and the parallel runner change nothing at all: a cached run, a run with any number of jobs and a serial run without the cache write the same `results.json`, number for number (`tests/test_perf.py`).

To run the ensemble again (12 seeds, four runs at a time; about four minutes of one core per seed, and up to 2.5 GB of memory per run):

<!-- docs-run: skip="ensemble of repeated runs for the release gate, many CPU-hours" -->
```sh
sh scripts/repeatability/run.sh ensemble 12 4
```

## Known limits

- **Non-coherent tones.** The window's far sidelobes spread a tone's energy over the whole spectrum at about -160 dB (-161.6 dB at half a bin off, -171.8 dB at 0.1 bin) of the tone. A figure within 3 dB of that is limited by the window; the measurements use coherent tones wherever the output rate allows (44.1 kHz family), and a device that writes 48 kHz family rates is off the coherent grid.
- **Near the carrier.** Energy within +-13.5 Hz of the tone is not counted (the notch). A converter with a skirt there reads a higher SINAD than under a method that counts it: the reference chain has -133 dBFS in that range, 24 dB above its THD+N floor.
- **THD below the noise.** THD counts the noise inside each harmonic's 21-bin lobe; a THD figure more than about 15 dB below THD+N is the noise in those lobes, not a harmonic. With noise equal to the harmonic a single record's THD is uncertain by about 0.3 dB for any method.
- **Statistics.** One 2^18-point record gives THD+N to +-0.07 dB (1 sigma) for noise-only floors; noise over 20 Hz to 20 kHz with 8 averages to +-0.02 dB (2^18) or +-0.013 dB (2^20); noise density at 1 kHz only to +-0.3 dB (a few hundred bins). Multitone residuals are single-bin statistics.
- **Band edges.** The 20 Hz edge is smeared by the window by about +-5 Hz: a noise block closer than 5 Hz to the edge is partly counted.
- **Output rate.** The impulse, filter and group-delay measurements need an output rate on the 44.1 kHz grid (44.1, 88.2, 176.4, 352.8 kHz): at 48 kHz-family rates they report "not run" with the reason, as the multitone does. A class B device may take a 48 kHz-family input: the reference decoder's output rates divide the DSD rate, so its impulse and step records are decoded at the smallest 44.1 kHz-family rate at or above the input rate (88.2 kHz for 48 kHz, 176.4 kHz for 96 kHz, 352.8 kHz for 192 kHz). The impulses and step edges are placed on input samples that fall on decoder samples exactly (every 80 input samples), so nothing is resampled. Through the reference modulator behind a resampler the in-band response read this way agrees with the 88.2 kHz input within 0.01 dB from 20 Hz to 20 kHz (checked in the test suite). At 96 and 192 kHz inputs the decoded record carries the DSD stream's ultrasonic noise, so the filter rows are marked not measurable by the rule in the next item, as they are at 176.4 and 352.8 kHz.
- **Wide-band outputs.** A record at 88.2 kHz or more carries the DSD stream's own ultrasonic noise. When that noise is above the -60 dB ringing threshold of the impulse record (the reference decoder at 88.2 kHz and more), the filter type, ringing, cut-off and group delay print "not measurable" instead of a number read from noise. The stopband figure does not depend on the impulse record.
- **Stopband.** The tones start 20 kHz below the output rate and rise in 2 kHz steps while they fit under the 352.8 kHz test signal (up to about 158 kHz), so every image lands at or below 20 kHz: six tones up to 88.2 kHz, two at 176.4 kHz, none at 192 kHz or more ("not run"). The figure is the worst image, "or deeper": it contains the device's noise.
- **Device delay.** Every time-domain test (impulse, step, overload, polarity) first finds the device's delay from one impulse and shifts its windows by it, so a late device reads like an aligned one (tested with 300, 1000 and 3000 samples, inverted and not). The delay is the peak of the probe, in whole output samples; a device whose first output is not the impulse peak (a start-up click larger than the impulse after 0.1 s) is not handled. An imported signal set made before the probe existed runs with a delay of zero and says so.
- **Rectangular-window figures** (the multitone) need whole periods and nothing non-periodic outside the band; the measurement decodes to a rate where that holds and reports "not run" otherwise.
- **Third-party tools** have their own floors: SoX's integer pipeline limits it near -175 dB (the DSD128 chain reads 1 dB worse in SoX).
- **Stored float32** has its own floor: a -6 dBFS tone stored as float32 reads -162.5 dB THD+N, and a 24-bit TPDF-dithered one -144.9 dB (16-bit: -96.8 dB): a 24-bit stimulus would sit above the -147 dB reference floor, which is why the stimulus files are 32-bit.

## What the validation found

Analyser faults found and fixed (each with a regression test):

- **THD below about 27 Hz.** The second-harmonic lobe overlapped the fundamental's, so the fundamental's skirt was counted as distortion: a 20 Hz tone with a -80 dB harmonic read -61 dB THD. THD+N was not affected, and the 20 Hz figure is not in a published report; fixed in `analyse.tone_metrics`.
- **WAV float files** lacked the extended fmt chunk strict readers expect (SoX warned); fixed.

Measurement faults from the separate internal review of 0.1.0, fixed in 0.1.1 (each with a regression test in `tests/test_review_regressions.py` and `tests/test_batch_011.py`; the example reference-chain report is regenerated):

| Finding | Before | After |
|---|---|---|
| Class B multitone used a rectangular window on a record full of ultrasonic noise (B1) | every modulator read 104 dB; the decoder column of the same chain 136 dB | class B decoded to 44.1 kHz first, and every class A record decimated to 44.1 kHz before the window: the reference decoder reads the same range (150.7 dB in 0.1.1, see [Repeatability](#repeatability)) at 44.1, 88.2, 176.4 and 352.8 kHz (it read 138, 109 and 106 dB at the last three, N1) |
| Stopband taken from the noise of the impulse measurement (B2) | -81 dB for a filter that is -156 dB deep | from the alias tones, at most the stated level, with the tones named: tones start at the output rate minus 20 kHz (they started 2 kHz above Nyquist, so at 88.2 kHz the row read -9 dB from the filter's transition band and at 44.1 kHz -133 dB for a stopband of -155 dB or deeper, N2); the row says "upper bound", "or deeper" and the range |
| Overload recovery's analysis filter had a fixed tap count (B4) | +-46 ms at 44.1 kHz: 47.5 ms against 10 ms for the same chain | sized in seconds: 7.6 ms and 10.0 ms |
| The noise headline was the stimulus dither, 3.01 dB off the dBFS-re-sine convention of AES17 (B5) | -151.6 dBFS(A) for a chain below -160 | 32-bit dither and the sine-rms reference |
| "Ultrasonic peak" was the largest single bin at the band edge (B6) | -61 dBFS at 280 kHz, a bin power of unstated width | densities at 50, 100 and 200 kHz, band levels, the highest third octave, edge flagged |
| Multitone at 48 kHz-family rates was not a whole period (B7) | 13 dB "range" for an ideal signal, silently | "not run: output rate is not on the 44.1 kHz grid" |
| Spectrum plots showed a tone 7.2 dB low (S1) | -13.2 dBFS for a -6.02 dBFS tone | the tone at its level, bin width in the caption |
| J-Test "largest sideband" was noise or the stimulus (S2) | -150 dB at the farthest position | none reported unless 6 dB above the mean of its two neighbouring positions and the square wave's own harmonics (one median of all positions reported the noise at the far end of the spectrum, N5) |
| THD+N against frequency cannot see harmonics above 20 kHz (S3) | 10, 15 and 20 kHz read noise only | wide-band THD against the noise, with a bound when no harmonic stands out |
| Linearity stopped at -123 dBFS and counted passes below a failure (S4) | | includes -126 dBFS, stops at the first failure |
| Only five figures were checked against the floor (S6) | | IMD, multitone, crosstalk, J-Test and alias figures too |
| DSF padded with zero bits (S7) | a burst at the end of every file | the idle pattern |
| Peak-level SINAD of a class A device ran on the fallback modulator and said nothing (B3) | 122.7 dB for every decoder, 24 dB above the stated floor | the peak design is order 8 at gain 1.3, the row names it and carries its own floor, and a figure within 6 dB of it is flagged |
| Impulse, filter and group delay at 48 kHz-family rates read 48 kHz samples as 352.8 kHz samples (N3) | ringing 22 ms, group delay -13.5 ms, no warning | "not run" with the reason |
| Filter rows read from the DSD stream's noise at output rates of 88.2 kHz and more (N4) | the linear-phase reference decoder was "intermediate" with 4 ms of ringing | "not measurable" when the noise sets the ringing threshold above -60 dB |
| A late device was read as minimum phase, inverted, with 824 percent overshoot (N7) | 1000 samples of delay | the delay is found and removed; the first impulse is not used |
| The dither level in the label was wrong by 33 dB (N8) | "about -162 dBFS" | about -194.85 dBFS (-162 is the chain's A-weighted noise with it) |
| Wide-band THD of a 20 Hz tone, and noise counted as harmonics (N6) | -61 dB for an ideal sine; -60.9 and -44.1 dB on two runs | lobes cut as in `thd_db`; local noise is a mean and the margin 10 dB |
| Class B filter rows described the reference decoder (S5) | filter type, ringing and cut-off of the reference decoder under a modulator's name | not shown; kept in `results.json` as `reference_decoder_only` |

Instrument properties found and now documented: the window's far-sidelobe floor for non-coherent tones, the +-13.5 Hz notch around the tone (the reference chain has -133 dBFS there), the rectangular-window leak that also fooled the unwindowed sine fit, the CCIF and SMPTE reference conventions, and the dynamic range being referred to 0 dB SACD.

Not fixed in 0.1.1, listed in the [roadmap](roadmap.md): the stability flag misses a bounded but broken loop, the "density at 50 kHz" row is a third-octave mean, and the nits of the second review.

No fault was found in the level, THD+N, SINAD, noise, dynamic range, A-weighting, IMD, crosstalk, response, group delay, impulse or step analysers: they agree with the known answers and with the second analyser within the tolerances above.

## Re-run it

<!-- docs-run: skip="full validation, about 20 minutes and rootless Podman with the pinned reference containers" -->
```sh
pip install -e '.[dev]'
scripts/ci.sh                  # the fast subset: known answers and regressions, about 2 minutes
tools/reftool.sh build         # the pinned SoX and ffmpeg containers (rootless Podman)
scripts/validate.sh all --out validation   # everything on this page, about 20 minutes
```

`validate.sh` writes `validation/validation.md` (the tables above) and `validation.json`; with no containers it skips the SoX, ffmpeg and published-condition parts and says so. The separately written analyser is `tests/refanalyser.py`; the cases are in `tests/accuracy_cases.py`.

## See also

- [Measurement footprint](footprint.md)
- [Design](design.md)
- [Reference tools](reference-tools.md)

Part of the [DSD Toolbox](https://github.com/dsd-toolbox/dsd-toolbox).
