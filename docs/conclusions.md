[dsd-measure](../README.md) › [Documentation](README.md) › Conclusions

# Conclusions

Every report opens with a few sentences that say what the numbers mean. This page lists the rules behind those sentences, the thresholds they use and the published work each threshold rests on, so that anyone can check a conclusion or disagree with it.

## What a conclusion is

A conclusion is one plain sentence made by a fixed rule from the figures in `results.json`. The same figures always give the same sentence. Each one has:

- an `id` (for example `overall`) and a `verdict` from the table below;
- `metrics`: the keys in `results.json` it used;
- `evidence`: those figures as shown in the report, under "Evidence" in the Conclusions block;
- `thresholds`: the rows of the threshold table it applied.

The list is in `results.json` under `conclusions` (for a comparison, in `comparison/results.json`).

Conclusions cover the synthetic test signals and the software path that was measured. They are not a listening test, and they say nothing about a DAC, an amplifier or a recording.

## Verdicts

| Verdict | Meaning |
|---|---|
| Transparent | Everything measured is beyond the range of human hearing. |
| Inaudible in normal listening | Quieter than the noise of a CD, but inside the range of hearing under extreme conditions. |
| Audible risk | Above the noise of a CD. It may or may not be heard; listen for yourself. |
| Measurement floor | The tool measuring itself: the best figures any report can show. |
| At the reference floor | The tool, not the device, limits these figures. |
| Finding | A measured property with a settled meaning. |
| No consensus | Measured, but research does not agree on whether it is audible. |
| Indistinguishable by measurement | Every difference is below the floor or the thresholds. |
| Technical difference | A measurable difference that is below the audibility thresholds. |
| May matter | A difference at a level where it may be audible or may affect a comparison. |
| Not comparable | The devices do different jobs. |
| Not concluded | Measured, but not validated or not used by any rule in this version. |

No verdict names a winner. A comparison says where devices differ and whether the difference reaches a threshold.

## Thresholds

"Below the reference level" means in dB below a 1 kHz tone at 0 dB SACD (-6.02 dBFS), the level the distortion tests use. This is 6 dB stricter than a figure quoted against full scale.

| Threshold | Value | Unit | Meaning | Source |
|---|---:|---|---|---|
| `hearing_range_db` | 120 | dB below the reference level | Distortion and noise this far down are outside the range between the loudest sound a system plays and the quietest sound a listener can hear | [Fielder 1995](https://aes2.org/publications/elibrary-page/?id=7948), JAES 43(5): over 120 dB is needed only in the most demanding cases |
| `cd_floor_db` | 87 | dB below the reference level | The noise of a correctly dithered 16-bit channel, -93.3 dBFS, seen from the reference level. Listeners in controlled tests did not tell a 16-bit stage from high-resolution playback at normal volume | [Meyer and Moran 2007](https://aes2.org/publications/elibrary-page/?id=14195), JAES 55(9); [Reiss 2016](https://aes2.org/publications/elibrary-page/?id=18296), JAES 64(6), a meta-analysis that finds a small effect |
| `flat_db` | 0.1 | dB | A level or response difference this small is treated as none. It is a fifth of the smallest level change listeners detect | [Jesteadt, Wier and Green 1977](https://doi.org/10.1121/1.381278), JASA 61(1) |
| `level_jnd_db` | 0.5 | dB | About the smallest level change listeners detect on tones at normal volume (0.5 to 1 dB) | [Jesteadt, Wier and Green 1977](https://doi.org/10.1121/1.381278), JASA 61(1) |
| `same_db` | 1 | dB | Two distortion or noise figures closer than this are treated as the same. Reviews quote these figures to the nearest decibel | our convention |
| `floor_margin_db` | 6 | dB | A figure this close to the reference floor is limited by the tool | [The reference floor](footprint.md#the-reference-floor) |
| `group_delay_ms` | 1 | ms | About the smallest group delay difference heard in the midrange, on test pulses | [Blauert and Laws 1978](https://doi.org/10.1121/1.381841), JASA 63(5) |
| `pre_ringing` | none | | No threshold: contested. The report describes the filter and gives no verdict | [Jackson, Capp and Stuart 2014](https://aes2.org/publications/elibrary-page/?id=17497), AES Convention 137, reports audible filter effects; [Archimago 2015](https://archimago.blogspot.com/2015/04/internet-blind-test-linear-vs-minimum.html), an internet blind test of linear against minimum phase filters (results in its follow-up posts), found no consistent preference |
| `ultrasonic` | none | | No threshold: noise above 20 kHz is normal for DSD and is not heard as such, and there is no agreed limit for what amplifiers and tweeters tolerate. The report gives the level only | [Archimago 2022](https://archimago.blogspot.com/2022/06/notes-on-dac-dsd-1-bit-pdm-measurements.html) |
| `distortion_music` | none | | No threshold: above the CD floor, whether distortion is heard depends on its kind, the music and the volume, and published thresholds vary widely. The verdict is "audible risk", not "audible" | [de Santis and Henin 2007](https://projekter.aau.dk/projekter/files/9852082/07gr1061_Thesis.pdf), Aalborg University |

How `cd_floor_db` is derived: a 16-bit channel with TPDF dither has noise 93.3 dB below a full-scale sine (6.02 × 16 + 1.76 - 4.77). The reference level is 6.02 dB below full scale, so the same noise is 87.3 dB below the reference level, rounded down to 87.

The AES papers are behind the AES library's paywall; the links go to their abstracts. The Reiss paper is open access.

## The rules for one device

| Id | Uses | Rule |
|---|---|---|
| `overall` | SINAD at 1 kHz, dynamic range (A-weighted), SMPTE and CCIF intermodulation; background noise from analysis version 2 | Take the weakest figure, in dB below the reference level. 120 dB or more: transparent. 87 dB or more: inaudible in normal listening. Less: audible risk. The sentence names the weakest figure and rounds it down |
| `floor` | the reference floor | For the built-in reference chain only, in place of `overall`: these are the best figures a report can show, and a converter within 6 dB of them cannot be ranked |
| `response` | passband ripple, response at 20 kHz | 0.1 dB or less: flat. 0.5 dB or less: nearly flat, unlikely to be heard. More: uneven, may be heard |
| `level` | gain error, channel gain difference, linearity | Unity gain and matched channels when within 0.1 dB; otherwise the difference is stated, with a reminder to match levels before listening |
| `limits` | SINAD, THD, dynamic range against the reference floor | Counts the figures within 6 dB of the floor: they show the tool's limit, and the device is at least that good |
| `rates` | SINAD per DSD rate (modulators) | States SINAD at each rate measured |
| `filter` | filter type, ringing, -0.1 dB and -3 dB points, group delay | Describes the filter. No verdict on ringing: see `pre_ringing` |
| `stopband` | worst image of the alias tones (class A) | States how far below the tone the images are. Stands alone only when the `filter` rule is not used; otherwise it is part of that sentence. Analysis version 2 or later |
| `ultrasonic` | noise from 20 to 96 kHz | States the level. No verdict: see `ultrasonic`. Analysis version 2 or later; for a converter only when its output rate reaches 40 kHz or more |
| `stability` | saturation and drift in the long holds (modulators) | Stable when no hold saturated; otherwise unstable, with the level at which it saturated |
| `overload` | recovery after a 50 ms burst at the peak level | States the recovery time. Analysis version 2 or later |
| `pending` | everything not validated or not used | One line that names what was measured but not concluded |

## The rules for a comparison

Devices of the same class are compared in pairs with the same thresholds.

| Id | Rule |
|---|---|
| `cmp-distortion` | For each figure behind `overall`: the same when both devices are at the reference floor or within 1 dB. A technical difference when both are at least 87 dB below the reference level. May matter when one is not |
| `cmp-response` | The largest difference in response from 20 Hz to 20 kHz: 0.1 dB or less is the same, 0.5 dB or less a technical difference, more may be heard |
| `cmp-level` | A level difference above 0.1 dB may matter for any listening comparison: match levels first |
| `cmp-filter`, `cmp-ultrasonic` | Differences are described without a verdict |
| `cmp-overall` | "Indistinguishable by measurement" when every rule above says the same; "measure differently, but no difference reaches the audibility thresholds" when the differences are technical; otherwise it names where the devices differ |
| `cmp-classes` | A converter and a modulator are not compared |
| `floor`, `floor-agreement` | When every device is the built-in reference chain: the report is the measurement floor, and the parts of the chain should read the same |

## Which figures count

A rule only uses figures whose analysis has been checked independently. The rest appear in one "not concluded" line and never reach a verdict.

| Group | Figures | Status |
|---|---|---|
| `floor`, `sinad`, `thd`, `dr`, `gain`, `linearity`, `fr`, `imd`, `crosstalk` | reference floor, SINAD and THD+N, THD, dynamic range, gain, linearity, frequency response, single-point IMD, crosstalk and channel match | used |
| `noise`, `ultrasonic`, `stopband`, `overload` | background noise, ultrasonic noise, stopband, overload recovery | used when `metrics.analysis_version` is 2 or more (corrected definitions) |
| `filter`, `group_delay`, `polarity`, `stability` | filter type and ringing, group delay, polarity, modulator stability | not used until checked; for a modulator the filter rows describe the reference decoder and are never used |
| not used by any rule | peak-level SINAD, multitone, J-Test, alias images, DC offset, THD+N against frequency, the IMD sweep | listed as not concluded, or left to the table |

## What the conclusions do not claim

- That a device sounds good or bad. They say whether what it adds is above or below published thresholds.
- That one device is better than another when both are below those thresholds.
- Anything about [Audio Science Review](https://www.audiosciencereview.com/)'s chart colours. SINAD here is measured the way ASR measures it, but at 0 dB SACD (-6.02 dBFS) and not at full scale, and ASR's bands rank a device against the others it has tested; they are not audibility limits, so the verdicts do not use them.
- Compliance with [AES17](https://www.aes.org/publications/standards/). The 20 kHz bandwidth, A-weighting and the -60 dB dynamic range method follow it; the verdicts are ours.

## See also

- [User guide: reading the conclusions](user-guide.md#reading-the-conclusions)
- [Measurement footprint](footprint.md)
- [The reference floor](footprint.md#the-reference-floor)

Part of the [DSD Toolbox](https://github.com/aclater/dsd-toolbox).
