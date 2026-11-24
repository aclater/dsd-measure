[dsd-measure](../README.md) › [Documentation](README.md) › Conclusions

# Conclusions

Every report opens with a few sentences that say what the numbers mean. This page lists the rules behind those sentences, the thresholds they use and the work each threshold cites, so that anyone can check a conclusion or disagree with it.

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
| At least 120 dB down | Every figure concluded is at least 120 dB below a reference-level tone. |
| At least 87 dB down | Every figure concluded is at least 87 dB below a reference-level tone, the noise level of dithered 16-bit on this scale. |
| Under 87 dB down | A figure is less than 87 dB below a reference-level tone, above the noise level of dithered 16-bit on this scale. |
| Measurement floor | The tool measuring itself: the best figures any report can show. |
| At the reference floor | The tool, not the device, limits these figures. |
| Finding | A measured property. |
| No agreed threshold | Measured; the literature gives no agreed threshold to compare it with. |
| Same within tolerance | Every difference is below the floor or the stated tolerance. |
| Difference between low figures | A measured difference between figures that are both at least 87 dB below a reference-level tone. |
| Notable difference | A measured difference larger than the stated tolerance, or one where a figure is above the 16-bit noise level. |
| Not comparable | The devices do different jobs. |
| Not like-for-like | The devices were measured at different output rates or formats, so the figures are listed but not compared. |
| Not judged: output format | The file format the tool wrote limits the figures, so they describe the format, not the converter. |
| Not concluded | Measured, but not validated or not used by any rule in this version. |

No verdict names a winner, and none says whether anything is heard: the tool measures levels and does not test listening. A comparison says where devices differ and whether the difference reaches a threshold. The tolerance in a comparison (1 dB) is a convention; no repeatability interval has been measured yet, so a difference is reported and not ranked.

## Thresholds

"Below the reference level" means in dB below a 1 kHz tone at 0 dB SACD (-6.02 dBFS), the level the distortion tests use. This is 6 dB stricter than a figure quoted against full scale.

| Threshold | Value | Unit | Meaning | Source |
|---|---:|---|---|---|
| `range_120_db` | 120 | dB below the reference level | A reference line of 120 dB, cited from Fielder 1995 as a dynamic range needed only in the most demanding cases (not checked against the paper). A reference line only: audibility was not tested | [Fielder 1995](https://aes2.org/publications/elibrary-page/?id=7948), JAES 43(5): over 120 dB is needed only in the most demanding cases (cited, not checked against the paper) |
| `dither16_db` | 87 | dB below the reference level | The noise of a correctly dithered 16-bit channel (-93.3 dBFS) seen from the 0 dB SACD reference level (-6.02 dBFS): a calculation, not a listening result. Whether such noise is heard is not settled: Meyer and Moran 2007 report no detection at normal volume, but detection of the loop's noise floor in a brief two-subject test with no input signal at 14 dB of extra gain, and easily above it, and Reiss 2016 finds a small but statistically significant ability to discriminate high-resolution content and discusses the risk of bias in Meyer and Moran | [Meyer and Moran 2007](https://aes2.org/publications/elibrary-page/?id=14195), JAES 55(9); [Reiss 2016](https://aes2.org/publications/elibrary-page/?id=18296), JAES 64(6), a meta-analysis that finds a small but statistically significant effect |
| `flat_db` | 0.1 | dB | A level or response difference this small is treated as none. It is a fifth of the 0.5 dB level step below | [Jesteadt, Wier and Green 1977](https://doi.org/10.1121/1.381278), JASA 61(1) (cited, not checked against the paper) |
| `level_jnd_db` | 0.5 | dB | A level step of 0.5 dB, cited from Jesteadt, Wier and Green as about the smallest level change detected on tones (0.5 to 1 dB). A reference line only | [Jesteadt, Wier and Green 1977](https://doi.org/10.1121/1.381278), JASA 61(1) (cited, not checked against the paper) |
| `same_db` | 1 | dB | Two distortion or noise figures closer than this are treated as the same. This is a convention, not a measured repeatability: no repeatability interval has been measured yet | our convention |
| `floor_margin_db` | 6 | dB | A figure this close to the reference floor is limited by the tool | [The reference floor](footprint.md#the-reference-floor) |
| `group_delay_ms` | 1 | ms | A group delay difference of 1 ms, cited from Blauert and Laws as about the smallest difference detected in the midrange on test pulses. A reference line only | [Blauert and Laws 1978](https://doi.org/10.1121/1.381841), JASA 63(5) (cited, not checked against the paper) |
| `pre_ringing` | none | | No threshold. The literature does not agree on a limit for the ringing of a linear-phase filter before a transient, so the report describes the filter and gives no verdict | [Jackson, Capp and Stuart 2014](https://aes2.org/publications/elibrary-page/?id=17497), AES Convention 137, reports effects of filters in listening tests; [Archimago 2015](https://archimago.blogspot.com/2015/04/internet-blind-test-linear-vs-minimum.html), an internet blind test of linear against minimum phase filters (results in its follow-up posts), found no consistent preference |
| `ultrasonic` | none | | No threshold. Noise shaping puts noise above 20 kHz by design and there is no agreed limit for what amplifiers and tweeters tolerate, so the report gives the level only | [Archimago 2022](https://archimago.blogspot.com/2022/06/notes-on-dac-dsd-1-bit-pdm-measurements.html) |
| `distortion_music` | none | | No threshold. Above the 16-bit noise level the published thresholds for distortion vary widely with its kind, the music and the volume, so the report gives the level and no verdict | [de Santis and Henin 2007](https://projekter.aau.dk/projekter/files/9852082/07gr1061_Thesis.pdf), Aalborg University |

How `dither16_db` is derived: a 16-bit channel with TPDF dither has noise 93.3 dB below a full-scale sine (6.02 × 16 + 1.76 - 4.77). The reference level is 6.02 dB below full scale, so the same noise is 87.3 dB below the reference level, rounded down to 87. It is arithmetic, not a listening result.

"Cited, not checked against the paper" means the authors have not read the source: it is not in their library. The Meyer and Moran and Reiss statements above were checked against those papers. A reference line says nothing about hearing. The AES papers are behind the AES library's paywall; the links go to their abstracts. The Reiss paper is open access.

## The rules for one device

| Id | Uses | Rule |
|---|---|---|
| `overall` | SINAD at 1 kHz, dynamic range (A-weighted), SMPTE and CCIF intermodulation; background noise from analysis version 2 | Take the weakest figure, in dB below the reference level. 120 dB or more: at least 120 dB down. 87 dB or more: at least 87 dB down. Less: under 87 dB down. The sentence names the weakest figure and rounds it down. When the output file's integer word length may limit the figures it says "not judged: output format" instead |
| `floor` | the reference floor | For the built-in reference chain only, in place of `overall`: these are the best figures a report can show, and a converter within 6 dB of them cannot be ranked |
| `response` | passband ripple, response at 20 kHz | 0.1 dB or less: flat. 0.5 dB or less: nearly flat. More: uneven (a notable difference) |
| `level` | gain error, channel gain difference, linearity | Unity gain and matched channels when within 0.1 dB; otherwise the difference is stated, with a reminder to match levels before any listening comparison |
| `limits` | SINAD, THD, dynamic range against the reference floor | Counts the figures within 6 dB of the floor: they show the tool's limit, and the tool cannot show more |
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
| `cmp-distortion` | For each figure behind `overall`: the same when both devices are at the reference floor or within 1 dB (a convention). A difference between low figures when both are at least 87 dB below the reference level. A notable difference when one is not. Never says which is better, and says that no repeatability interval has been measured. Not made when the devices were measured at different output rates or formats (`cmp-conditions`) or when a word length may limit a figure (`cmp-format`) |
| `cmp-response` | The largest difference in response from 20 Hz to 20 kHz: 0.1 dB or less is the same, 0.5 dB or less a difference between low figures, more a notable difference |
| `cmp-level` | A level difference above 0.1 dB is a notable difference; match levels before any listening comparison |
| `cmp-filter`, `cmp-ultrasonic` | Differences are described without a verdict |
| `cmp-conditions` | "Not like-for-like" when the devices of one class were measured at different DSD rates, output rates or output formats: distortion and noise are not compared, and the run prints a warning |
| `cmp-overall` | "Measure the same" when every rule above says the same; "measure differently, but no difference reaches the thresholds" when the differences are between low figures; otherwise it names where the devices differ by more than the tolerance. It ranks nothing |
| `cmp-classes` | A converter and a modulator are not compared |
| `floor`, `floor-agreement` | When every device is the built-in reference chain: the report is the measurement floor, and the parts of the chain should read the same |

## Which figures count

A rule only uses figures whose analysis the authors have checked against known answers and a second analyser of their own. The rest appear in one "not concluded" line and never reach a verdict.

| Group | Figures | Status |
|---|---|---|
| `floor`, `sinad`, `thd`, `dr`, `gain`, `linearity`, `fr`, `imd`, `crosstalk` | reference floor, SINAD and THD+N, THD, dynamic range, gain, linearity, frequency response, single-point IMD, crosstalk and channel match | used |
| `noise`, `ultrasonic`, `stopband`, `overload` | background noise, ultrasonic noise, stopband, overload recovery | used when `metrics.analysis_version` is 2 or more (corrected definitions) |
| `filter`, `group_delay`, `polarity`, `stability` | filter type and ringing, group delay, polarity, modulator stability | not used until checked; for a modulator the filter rows describe the reference decoder and are never used |
| not used by any rule | peak-level SINAD, multitone, J-Test, alias images, DC offset, THD+N against frequency, the IMD sweep | listed as not concluded, or left to the table |

## What the conclusions do not claim

- That anything is or is not heard. The tool measures levels; it does not test listening, and the thresholds are reference lines from the literature, not audibility limits.
- That one device is higher quality than another. A comparison says where figures differ and by how much, under the stated conditions, and ranks nothing.
- Anything about [Audio Science Review](https://www.audiosciencereview.com/)'s chart colours. SINAD here is a file-domain figure at 0 dB SACD (-6.02 dBFS), not an analogue reading at full scale as ASR makes, and ASR's bands rank a device against the others it has tested, so the verdicts do not use them.
- Compliance with [AES17](https://www.aes.org/publications/standards/). Only the 20 kHz band edge and the dBFS reference follow AES17-2020; the test tone, weighting, notch, level and dither differ. [Methodology limits](methodology-limits.md#what-follows-aes17) lists each difference.

## See also

- [User guide: reading the conclusions](user-guide.md#reading-the-conclusions)
- [Methodology limits](methodology-limits.md)
- [Measurement footprint](footprint.md)
- [The reference floor](footprint.md#the-reference-floor)

Part of the [DSD Toolbox](https://github.com/dsd-toolbox/dsd-toolbox).
