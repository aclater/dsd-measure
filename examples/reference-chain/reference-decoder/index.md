# reference decoder: measurement report

Class A (DSD to PCM converter); DSD64; profile full; reference chain 2.

**Result: this is the measurement floor of the built-in reference chain (SINAD 147.0 dB, the best figure the tool can show), not a result for a product.**

## Conclusions

- This is the measurement floor, not a result for a product: the built-in reference chain reads SINAD 147.0 dB and dynamic range 151.8 dB (A-weighted) at DSD64. A DSD to PCM converter within 6 dB of these figures (SINAD above 141.0 dB) cannot be ranked by this tool: it is at least that good.
- Flat response: the level varies by less than 0.01 dB from 20 Hz to 20 kHz and is down by less than 0.01 dB at 20 kHz, too little to change the tone.
- Image rejection: tones from 24.1 to 34.1 kHz come back as images at least 156 dB below the tone. The figure includes the device's own noise, so it is an upper bound on the images and the filter is at least this good.
- Level: unity gain within 0.01 dB, channels matched within 0.01 dB and quiet signals keep their level down to -126 dBFS.
- Overload: after a loud burst (the peak level SACD allows) of 50 ms at -2.9 dBFS the output is back to normal within 10 ms, the resolution of the test.
- Not concluded in this version: filter and ringing, polarity, multitone, J-Test and peak-level SINAD. These figures are either not validated yet or not used by any rule in this version, so they are in the table for reference only and are not part of any verdict here. The peak-level SINAD is shown with the floor of the reference modulator at that level.

Conclusions cover the synthetic test signals and the software path measured here. They are not a listening test and say nothing about a DAC, an amplifier or a recording. [How the conclusions are drawn](https://github.com/dsd-toolbox/dsd-measure/blob/main/docs/conclusions.md).

## What was measured

- **Device:** reference decoder: class A, DSD to PCM converter, adapter reference. Run as: built-in (no external command). in: DSD 2822400 Hz, 1 bit; out: PCM at 44100 Hz; no gain applied.
- **Source signals:** Synthetic and deterministic test signals made by the toolkit (tones, two-tone pairs, multitone, J-Test, impulses; no music), encoded to DSD by the built-in reference modulator.
- **Reference chain:** reference modulator and decoder at DSD64: THD+N -147.0 dB, dynamic range (A) 151.8 dB. A device figure within 6 dB of it is marked as limited by the measurement.
- **Profile and date:** full, 2026-11-24, dsd-measure 0.1.2, reference chain 2.

> Levels: dBFS is relative to PCM full scale. 0 dB SACD is the reference tone level, 50 % modulation, -6.02 dBFS; noise in dBFS is referred to the rms of a full-scale sine (AES17, ASR). Distortion and noise figures are in dB below the 1 kHz tone unless they say dBFS. Bandwidth 20 Hz to 20 kHz, unweighted unless marked A-weighted. SINAD is THD+N turned positive. Because the tone is 6 dB below full scale, a noise-limited device would read about 6 dB better at full scale; compare reports made at the same level.

| Metric | Value |
|---|---|
| SINAD, 1 kHz at 0 dB SACD (-6.02 dBFS) | 146.7 dB (THD+N -146.7 dB, under 0.0001 %)  (at the reference floor) |
| THD, 1 kHz (harmonics only) | -163.5 dB (under 0.0001 %)  (at the reference floor) |
| Dynamic range, A-weighted | 150.5 dB  (at the reference floor) |
| Noise 20 Hz-20 kHz, A-weighted | -162.4 dBFS  (at the reference floor) |
| SINAD at the peak level (+3.1 dB SACD, -2.9 dBFS) | 129.2 dB (reference modulator order 8, max gain 1.3: floor 129.2 dB)  (at the reference floor) |
| Filter type | linear phase |
| Ringing before / after the pulse | 0.67 / 0.67 ms |
| -0.1 dB / -3 dB frequency | 20.94 kHz / 21.78 kHz |
| Stopband (upper bound) | -156 dB or deeper, tones 24.1 to 34.1 kHz |
| Passband ripple 20 Hz-20 kHz | 0.000 dB peak to peak |
| Response at 20 kHz re 1 kHz | -0.000 dB |
| Group delay 20 kHz re 1 kHz | +0.0 microseconds |
| IMD SMPTE 60 Hz + 7 kHz, 0 dB SACD | -144.7 dB  (at the reference floor) |
| IMD CCIF 19 + 20 kHz | -136.8 dB  (at the reference floor) |
| IMD sweep, worst CCIF / SMPTE | -135.3 / -92.7 dB |
| Multitone distortion-free range | 154.3 dB  (at the reference floor) |
| Crosstalk, worst of 1 and 10 kHz | -179 dB  (at the reference floor) |
| Channel gain difference | +0.0000 dB, phase -0.000 deg |
| Worst alias image, tones above Nyquist | -156 dB re tone |
| Overload recovery (50 ms burst) | under 10 ms |
| Gain error at 0 dB SACD | +0.000 dB |
| Polarity | normal |
| DC offset | -211 dBFS |
| Output word length | 64-bit float |
| Reference floor (reference modulator + decoder, DSD64) | THD+N -147.0 dB, DR(A) 151.8 dB |

## Notes

- Ultrasonic noise is limited by the device output rate.

Plots: see `plots/`. Raw numbers: `results.csv`, `results.json`.

- **fr**: The treble is flat: the response varies by 0.00 dB from 20 Hz to 20 kHz and is -0.00 dB at 20 kHz.
- **impulse**: The filter is linear phase. Ringing before the main pulse lasts 0.67 ms (more than 0 means a 'pre-echo'), after it 0.67 ms.
- **noise**: Background noise is -162 dBFS weighted for hearing (-159 dBFS unweighted); quieter is better.
- **levels**: At reference level distortion plus noise is -147 dB (excellent); higher SINAD (147 dB) is better.
- **multitone**: With 32 tones playing at once the cleanest range is 154 dB below the quietest tone; this shows how the device copes with music-like signals.
- **spectrum_1k**: A 1 kHz tone with total harmonic distortion -164 dB; the biggest unwanted tone is harmonic 3 at -167 dB.
- **filter**: How the filter treats frequencies above the audio band, from the impulse response; the dotted line marks 20 kHz.
- **step**: The step overshoots by 6.8 percent and settles within 1 percent in 0.32 ms.
- **group_delay**: Frequencies arrive 0 microseconds apart between 1 kHz and 20 kHz.
- **thdn_freq**: Distortion plus noise is -147 dB at 1 kHz and -147 dB at 20 kHz, so within the 20 kHz band the treble is as clean as the midrange (harmonics of a tone above 10 kHz fall outside that band).
- **linearity**: Quiet sounds keep their level down to -126 dBFS within 0.5 dB.
- **imd_sweep**: Across the sweep the worst CCIF figure is -135 dB (pair centred on 19.5 kHz) and the worst SMPTE figure -93 dB; SMPTE rises at low level because the signal gets small.
- **alias**: Tones above the output's own limit leave images no louder than -156 dB relative to the tone (worst at 20.0 kHz); lower is better.
- **overload**: After a 50 ms burst above the working range a quiet tone is back to its normal noise level within about 10 ms.
- **imd_smpte**: Mixing bass and treble creates under 0.0001 percent unwanted tones (SMPTE test).
- **imd_ccif**: Two very high tones leave under 0.0001 percent unwanted tones in the audible band (CCIF test).
- **tone_15k**: A 15 kHz tone: the strongest unwanted tone below 20 kHz is -156 dB down at 19.9 kHz.
- **jtest**: File-level J-Test: no sideband stands above the noise (noise -160 dB re the carrier in 1.35 Hz bins; arithmetic only, not a clock test).
