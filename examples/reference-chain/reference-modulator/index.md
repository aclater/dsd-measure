# reference modulator: measurement report

Class B (PCM to DSD modulator); DSD64; profile full; reference chain 1.

> Levels: dBFS is relative to PCM full scale. 0 dB SACD is the reference tone level, 50 % modulation, -6.02 dBFS. Distortion and noise figures are in dB below the 1 kHz tone unless they say dBFS. Bandwidth 20 Hz to 20 kHz, unweighted unless marked A-weighted. SINAD is THD+N turned positive. Because the tone is 6 dB below full scale, a noise-limited device would read about 6 dB better at full scale; compare reports made at the same level.

| Metric | Value |
|---|---|
| SINAD, 1 kHz at 0 dB SACD (-6.02 dBFS) | 146.7 dB |
| THD+N, 1 kHz | -146.7 dB (under 0.0001 %) |
| THD, 1 kHz | -163.5 dB (under 0.0001 %) |
| Dynamic range, A-weighted | 150.5 dB |
| Noise 20 Hz-20 kHz, A-weighted | -151.6 dBFS |
| SINAD at the peak level (+3.1 dB SACD, -2.9 dBFS) | 122.7 dB |
| Filter type | linear phase |
| Ringing before / after the pulse | 1.41 / 1.41 ms |
| -0.1 dB / -3 dB frequency | 30.21 kHz / 40.55 kHz |
| Passband ripple 20 Hz-20 kHz | 0.000 dB peak to peak |
| Response at 20 kHz re 1 kHz | -0.000 dB |
| Group delay 20 kHz re 1 kHz | -1.4 microseconds |
| Ultrasonic noise peak | -61 dBFS at 280 kHz |
| Integrated 20-40 / 40-96 kHz | -82 / -38 dBFS |
| IMD SMPTE 60 Hz + 7 kHz, 0 dB SACD | -144.7 dB |
| IMD CCIF 19 + 20 kHz | -134.8 dB |
| IMD sweep, worst CCIF / SMPTE | -133.9 / -92.7 dB |
| Multitone distortion-free range | 104.2 dB |
| Crosstalk, worst of 1 and 10 kHz | -166 dB |
| Channel gain difference | +0.0000 dB, phase -0.000 deg |
| Overload recovery (50 ms burst) | under 10 ms |
| Gain error at 0 dB SACD | +0.000 dB |
| Polarity | normal |
| DC offset | -169 dBFS |
| Stable at +3.1 dB SACD peak | yes |
| DSD128 (1 kHz, 0 dB SACD) | SINAD 176 dB, DR(A) 176 dB, ultrasonic peak -60 dBFS |
| DSD256 (1 kHz, 0 dB SACD) | SINAD 178 dB, DR(A) 177 dB, ultrasonic peak -75 dBFS |
| Reference floor (reference decoder alone, DSD64) | THD+N -280.9 dB, DR(A) 342 dB |

Plots: see `plots/`. Raw numbers: `results.csv`, `results.json`.

- **fr**: The treble is flat: the response varies by 0.00 dB from 20 Hz to 20 kHz and is -0.00 dB at 20 kHz.
- **impulse**: The filter is linear phase. Ringing before the main pulse lasts 1.41 ms (more than 0 means a 'pre-echo'), after it 1.41 ms.
- **noise**: Background noise is -152 dBFS weighted for hearing (-149 dBFS unweighted); quieter is better.
- **levels**: At reference level distortion plus noise is -147 dB (excellent); higher SINAD (147 dB) is better.
- **multitone**: With 32 tones playing at once the cleanest range is 104 dB below the quietest tone; this shows how the device copes with music-like signals.
- **spectrum_1k**: A 1 kHz tone with total harmonic distortion -164 dB; the biggest unwanted tone is harmonic 3 at -167 dB.
- **filter**: How the filter treats frequencies above the audio band, from the impulse response; the dotted line marks 20 kHz.
- **step**: The step overshoots by 4.5 percent and settles within 1 percent in 0.19 ms.
- **group_delay**: Frequencies arrive 1 microseconds apart between 1 kHz and 20 kHz.
- **thdn_freq**: Distortion plus noise is -147 dB at 1 kHz and -147 dB at 20 kHz, so the treble is as clean as the midrange.
- **linearity**: Quiet sounds keep their level down to -123 dBFS within 0.5 dB.
- **imd_sweep**: Across the sweep the worst CCIF figure is -134 dB (pair centred on 19.5 kHz) and the worst SMPTE figure -93 dB; SMPTE rises at low level because the signal gets small.
- **overload**: After a 50 ms burst above the working range a quiet tone is back to its normal noise level within about 10 ms.
- **imd_smpte**: Mixing bass and treble creates under 0.0001 percent unwanted tones (SMPTE test).
- **imd_ccif**: Two very high tones leave under 0.0001 percent unwanted tones in the audible band (CCIF test).
- **tone_15k**: A 15 kHz tone: the strongest unwanted tone below 20 kHz is -156 dB down at 19.9 kHz.
- **jtest**: File-level J-Test: the largest sideband is -141 dB down (arithmetic only, not a clock test).
- **noise_wide**: The highest ultrasonic noise peak is -61 dBFS at 280 kHz.
- **density**: At the loudest allowed level the 28-bit window reaches 78.6 percent modulation; it never saturates.
