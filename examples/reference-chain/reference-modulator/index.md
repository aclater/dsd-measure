# reference modulator: measurement report

Class B (PCM to DSD modulator); DSD64; profile full; reference chain 2.

**Result: this is the measurement floor of the built-in reference chain (SINAD 147.1 dB, the highest figure the tool can show), not a result for a product.**

## Conclusions

- This is the measurement floor, not a result for a product: the built-in reference chain reads SINAD 147.1 dB and dynamic range 151.7 dB (A-weighted) at DSD64. A DSD to PCM converter within 6 dB of these figures (SINAD above 141.1 dB) cannot be ranked by this tool.
- Flat response: the level varies by less than 0.01 dB from 20 Hz to 20 kHz (read at the tones measured) and is down by less than 0.01 dB at 20 kHz.
- Ultrasonic noise: -35 dBFS between 20 and 96 kHz. Noise shaping puts noise there by design. There is no agreed limit, so no verdict is given.
- Level: unity gain within 0.01 dB, channels matched within 0.01 dB and quiet signals keep their level down to -126 dBFS.
- Overload: after a burst of 50 ms at 0.0 dBFS the output is back to normal within 10 ms (the test resolves about 10 ms).
- By rate: SINAD is 147 dB at DSD64, 176 dB at DSD128 and 178 dB at DSD256. Ultrasonic noise from 20 to 96 kHz is -61 dBFS at DSD128 and -107 dBFS at DSD256.
- Not concluded in this version: polarity, modulator stability, multitone, J-Test and peak-level SINAD. These figures are either not validated yet or not used by any rule in this version, so they are in the table for reference only and are not part of any verdict here. The peak-level SINAD is shown with the floor of the reference modulator at that level.

Conclusions cover the synthetic test signals and the software path measured here. They are not a listening test and say nothing about a DAC, an amplifier or a recording. [How the conclusions are drawn](https://github.com/dsd-toolbox/dsd-measure/blob/main/docs/conclusions.md).

## What was measured

- **Device:** reference modulator: class B, PCM to DSD modulator, adapter reference. Run as: built-in (no external command). in: PCM 88200 Hz, 32-bit integer WAV; out: DSD at 2822400 Hz, 1 bit; no gain applied.
- **Source signals:** Synthetic and deterministic test signals made by the toolkit (tones, two-tone pairs, multitone, J-Test, impulses; no music), fed to the device as PCM.
- **Reference chain:** reference decoder alone at DSD64: THD+N -280.9 dB, dynamic range (A) 342.1 dB. A device figure within 6 dB of it is marked as limited by the measurement.
- **Profile and date:** full, 2026-11-24, dsd-measure 0.1.3, reference chain 2.

> Levels: dBFS is relative to PCM full scale. 0 dB SACD is the reference tone level, 50 % modulation, -6.02 dBFS; noise in dBFS is referred to the rms of a full-scale sine, as in AES17. Distortion and noise figures are in dB below the 1 kHz tone unless they say dBFS. Bandwidth 20 Hz to 20 kHz, unweighted unless marked A-weighted. SINAD is THD+N turned positive. Because the tone is 6 dB below full scale, a noise-limited device would read about 6 dB higher at full scale; compare reports made at the same level. These are not AES17 measurements: only the 20 kHz band edge and the dBFS convention follow it; the tone (1 kHz, not 997 Hz), the weighting (A, not CCIR-RMS), the notch, the level and the dither differ (docs/methodology-limits.md).

| Metric | Value |
|---|---|
| SINAD, 1 kHz at 0 dB SACD (-6.02 dBFS) | 146.9 dB (THD+N -146.9 dB, under 0.0001 %) |
| THD, 1 kHz (harmonics only) | -164.1 dB (under 0.0001 %) |
| Dynamic range, A-weighted | 150.3 dB |
| Noise 20 Hz-20 kHz, A-weighted | -162.5 dBFS |
| SINAD at the peak level (+3.1 dB SACD, -2.9 dBFS) | 129.1 dB |
| Passband ripple 20 Hz-20 kHz | 0.000 dB peak to peak |
| Response at 20 kHz re 1 kHz | -0.000 dB |
| Ultrasonic density at 50 / 100 / 200 kHz | -88 / -81 / -72 dBFS/Hz |
| Ultrasonic noise, highest 1/3 octave | -70 dBFS/Hz at 226 kHz (band edge) |
| Integrated 20-40 / 40-96 kHz | -79 / -35 dBFS |
| IMD SMPTE 60 Hz + 7 kHz, 0 dB SACD | -143.9 dB |
| IMD CCIF 19 + 20 kHz | -133.3 dB |
| IMD sweep, worst CCIF / SMPTE | -134.6 / -93.1 dB |
| Multitone distortion-free range | 154.5 dB |
| Crosstalk, worst of 1 and 10 kHz | -179 dB |
| Channel gain difference | +0.0000 dB, phase -0.000 deg |
| Overload recovery (50 ms burst) | under 10 ms |
| Gain error at 0 dB SACD | +0.000 dB |
| Polarity | normal |
| DC offset | -168 dBFS |
| Stable at +3.1 dB SACD peak | yes |
| DSD128 (1 kHz, 0 dB SACD) | SINAD 176 dB, DR(A) 176 dB, ultrasonic -92 dBFS/Hz at 100 kHz |
| DSD256 (1 kHz, 0 dB SACD) | SINAD 178 dB, DR(A) 177 dB, ultrasonic -141 dBFS/Hz at 100 kHz |
| Reference floor (reference decoder alone, DSD64) | THD+N -280.9 dB, DR(A) 342.1 dB |

## Notes

- The impulse, step, filter and group-delay measurements of a modulator include the reference decoder's own filter, so they describe the reference decoder, not the device. They are kept in results.json under reference_decoder_only and are not shown in the report tables or plots.

Plots: see `plots/`. Raw numbers: `results.csv`, `results.json`.

- **fr**: The response is flat: it varies by 0.00 dB from 20 Hz to 20 kHz and is -0.00 dB at 20 kHz.
- **noise**: Background noise is -162 dBFS A-weighted (-159 dBFS unweighted); a lower figure is less noise.
- **levels**: At reference level distortion plus noise is -147 dB, a SINAD of 147 dB; a higher SINAD is less distortion and noise.
- **multitone**: With 32 tones playing at once the cleanest range is 154 dB below the quietest tone.
- **spectrum_1k**: A 1 kHz tone with total harmonic distortion -164 dB; the biggest unwanted tone is harmonic 3 at -167 dB.
- **thdn_freq**: Distortion plus noise is -147 dB at 1 kHz and -147 dB at 20 kHz, so within the 20 kHz band the figure at 20 kHz is within 6 dB of the figure at 1 kHz (harmonics of a tone above 10 kHz fall outside that band).
- **linearity**: Quiet signals keep their level down to -126 dBFS within 0.5 dB.
- **imd_sweep**: Across the sweep the worst CCIF figure is -135 dB (pair centred on 19.5 kHz) and the worst SMPTE figure -93 dB; SMPTE rises at low level because the signal gets small.
- **overload**: After a 50 ms burst above the working range a quiet tone is back to its normal noise level within about 10 ms.
- **imd_smpte**: Mixing bass and treble creates under 0.0001 percent unwanted tones (SMPTE test).
- **imd_ccif**: Two very high tones leave under 0.0001 percent unwanted tones in the 20 Hz to 20 kHz band (CCIF test).
- **tone_15k**: A 15 kHz tone: the strongest unwanted tone below 20 kHz is -157 dB down at 19.9 kHz.
- **jtest**: File-level J-Test: no sideband stands above the noise (noise -159 dB re the carrier in 1.35 Hz bins; arithmetic only, not a clock test).
- **noise_wide**: Ultrasonic noise density: -88 dBFS/Hz at 50 kHz, -81 dBFS/Hz at 100 kHz, -72 dBFS/Hz at 200 kHz. The highest 1/3-octave band is -70 dBFS/Hz at 226 kHz (the band edge, not a feature of the noise).
- **density**: At the loudest allowed level the 28-bit window reaches 78.6 percent modulation; it never saturates.

Measured with dsd-measure 0.1.3, [github.com/dsd-toolbox/dsd-measure](https://github.com/dsd-toolbox/dsd-measure).
