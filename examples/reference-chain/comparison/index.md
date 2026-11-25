# Comparison report

**Result: every device here is the built-in reference chain, so this is the measurement floor of the tool, not a result for a product.**

## Conclusions

- Every device here is the built-in reference chain. This is the measurement floor, not a result for a product: the built-in reference chain reads SINAD 147.1 dB and dynamic range 151.7 dB (A-weighted) at DSD64. A DSD to PCM converter within 6 dB of these figures (SINAD above 141.1 dB) cannot be ranked by this tool.
- The parts of the chain agree: SINAD is 146.9 dB for reference decoder and 146.9 dB for reference modulator, a spread of less than 0.01 dB.
- Not compared in this version: filter and ringing, polarity, multitone, J-Test, peak-level SINAD and modulator stability. These figures are not validated yet or not used by any rule, and converters often differ most in their filters and ultrasonic noise, so this comparison is not the whole picture.

Conclusions cover the synthetic test signals and the software path measured here. They are not a listening test and say nothing about a DAC, an amplifier or a recording. [How the conclusions are drawn](https://github.com/dsd-toolbox/dsd-measure/blob/main/docs/conclusions.md).

## What was measured

- **Devices:** reference decoder; reference modulator. Every device was fed the identical signals.
- **Source signals:** Synthetic and deterministic test signals made by the toolkit (tones, two-tone pairs, multitone, J-Test, impulses; no music), encoded to DSD by the built-in reference modulator.
- **Reference chain:** reference modulator and decoder at DSD64: THD+N -147.1 dB, dynamic range (A) 151.7 dB. A device figure within 6 dB of it is marked as limited by the measurement.
- **Profile and date:** full, 2026-11-24, dsd-measure 0.1.3, reference chain 2.

> Levels: dBFS is relative to PCM full scale. 0 dB SACD is the reference tone level, 50 % modulation, -6.02 dBFS; noise in dBFS is referred to the rms of a full-scale sine, as in AES17. Distortion and noise figures are in dB below the 1 kHz tone unless they say dBFS. Bandwidth 20 Hz to 20 kHz, unweighted unless marked A-weighted. SINAD is THD+N turned positive. Because the tone is 6 dB below full scale, a noise-limited device would read about 6 dB higher at full scale; compare reports made at the same level. These are not AES17 measurements: only the 20 kHz band edge and the dBFS convention follow it; the tone (1 kHz, not 997 Hz), the weighting (A, not CCIR-RMS), the notch, the level and the dither differ (docs/methodology-limits.md).

| Metric | reference-decoder | reference-modulator |
|---|---|---|
| SINAD, 1 kHz at 0 dB SACD (-6.02 dBFS) | 146.9 dB (THD+N -146.9 dB, under 0.0001 %) (floor) | 146.9 dB (THD+N -146.9 dB, under 0.0001 %) |
| THD, 1 kHz (harmonics only) | -164.0 dB (under 0.0001 %) (floor) | -164.1 dB (under 0.0001 %) |
| Dynamic range, A-weighted | 150.3 dB (floor) | 150.3 dB |
| Noise 20 Hz-20 kHz, A-weighted | -162.4 dBFS (floor) | -162.5 dBFS |
| SINAD at the peak level (+3.1 dB SACD, -2.9 dBFS) | 129.1 dB (reference modulator order 8, max gain 1.3: floor 129.2 dB) (floor) | 129.1 dB |
| Filter type | linear phase | not shown (a modulator's filter is the reference decoder's) |
| Ringing before / after the pulse | 0.67 / 0.67 ms | not shown (a modulator's filter is the reference decoder's) |
| -0.1 dB / -3 dB frequency | 20.94 kHz / 21.78 kHz | not shown (a modulator's filter is the reference decoder's) |
| Stopband (upper bound) | -159 dB or deeper, tones 24.1 to 34.1 kHz | not shown (a modulator's filter is the reference decoder's) |
| Passband ripple 20 Hz-20 kHz | 0.000 dB peak to peak | 0.000 dB peak to peak |
| Response at 20 kHz re 1 kHz | -0.000 dB | -0.000 dB |
| Group delay 20 kHz re 1 kHz | -0.0 microseconds | not shown (a modulator's filter is the reference decoder's) |
| IMD SMPTE 60 Hz + 7 kHz, 0 dB SACD | -143.9 dB (floor) | -143.9 dB |
| IMD CCIF 19 + 20 kHz | -134.7 dB (floor) | -133.3 dB |
| IMD sweep, worst CCIF / SMPTE | -134.9 / -93.1 dB | -134.6 / -93.1 dB |
| Multitone distortion-free range | 154.5 dB (floor) | 154.5 dB |
| Crosstalk, worst of 1 and 10 kHz | -179 dB (floor) | -179 dB |
| Channel gain difference | +0.0000 dB, phase -0.000 deg | +0.0000 dB, phase -0.000 deg |
| Worst alias image, tones above Nyquist | -159 dB re tone | not shown (a modulator's filter is the reference decoder's) |
| Overload recovery (50 ms burst) | under 10 ms | under 10 ms |
| Gain error at 0 dB SACD | +0.000 dB | +0.000 dB |
| Polarity | normal | normal |
| DC offset | -211 dBFS | -168 dBFS |
| Output format | 64-bit float, 44.1 kHz | not run |
| Reference floor (reference modulator + decoder, DSD64) | THD+N -147.1 dB, DR(A) 151.7 dB | not run |
| Ultrasonic density at 50 / 100 / 200 kHz | not run | -88 / -81 / -72 dBFS/Hz |
| Ultrasonic noise, highest 1/3 octave | not run | -70 dBFS/Hz at 226 kHz (band edge) |
| Integrated 20-40 / 40-96 kHz | not run | -79 / -35 dBFS |
| Stable at +3.1 dB SACD peak | not run | yes |
| DSD128 (1 kHz, 0 dB SACD) | not run | SINAD 176 dB, DR(A) 176 dB, ultrasonic -92 dBFS/Hz at 100 kHz |
| DSD256 (1 kHz, 0 dB SACD) | not run | SINAD 178 dB, DR(A) 177 dB, ultrasonic -141 dBFS/Hz at 100 kHz |
| Reference floor (reference decoder alone, DSD64) | not run | THD+N -280.9 dB, DR(A) 342.1 dB |

## Notes

- reference-decoder: Ultrasonic noise is limited by the device output rate.
- reference-modulator: The impulse, step, filter and group-delay measurements of a modulator include the reference decoder's own filter, so they describe the reference decoder, not the device. They are kept in results.json under reference_decoder_only and are not shown in the report tables or plots.

Measured with dsd-measure 0.1.3, [github.com/dsd-toolbox/dsd-measure](https://github.com/dsd-toolbox/dsd-measure).
