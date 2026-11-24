[dsd-measure](../README.md) › [Documentation](README.md) › Design

# Design

How dsd-measure is built and why. The measurements themselves are defined in the [footprint](footprint.md).

## Shape

| Module | Job |
|---|---|
| `signals` | Deterministic test signals: coherent tones, multitone, J-Test, SMPTE, CCIF, steps, impulses |
| `encode` | The reference PCM to DSD modulator |
| `decode` | The reference DSD to PCM decoder |
| `adapters` | A device or tool as "DSD to PCM" or "PCM to DSD" |
| `analyse` | One function per metric, each tested against a signal with a known answer |
| `measure` | The tests of the footprint, run against one adapter |
| `report` | HTML, Markdown, SVG, CSV and JSON |
| `run`, `cli` | The suite file and the command line |

## Decisions

**Everything goes through arrays.** Adapters take and return arrays, so the tests do not care whether a device is a library, a command or a folder of files. File adapters write inputs to a work folder, hash them and read the output back.

**One analysis grid.** In-band analysis uses the bin spacing of a 2^18-point FFT at 352.8 kHz for every output rate, so a coherent 1 kHz tone is the same bin number everywhere and results are comparable across devices. Why: a device that outputs 44.1 kHz and one that outputs 352.8 kHz then differ only in their own behaviour.

**A window with a wide lobe, and its cost.** Spectra use a 7-term Blackman-Harris window (sidelobes below -180 dB). Its main lobe is 7 bins wide each side, so the tone and notch use a 10-bin margin. Why: a plain 4-term window leaves leakage near -90 dB, which would hide a good converter's floor.

**The reference modulator is high-order and guarded.** It is a single-bit error-feedback loop with Legendre zeros in the audio band and Butterworth poles scaled to a chosen largest noise-transfer gain (Schreier and Temes, *Understanding Delta-Sigma Data Converters*, sec. 4.3 and 4.4.1). The first version was 5th order at gain 1.3 and read only about 106 dB SINAD, which would have masked every good device. Order 8 at gain 1.45 reads about 147 dB at DSD64 and is stable at 0 dB SACD but not at the +3.1 dB SACD peak, so the encoder runs a ladder of designs and moves down when the quantiser input exceeds 2 (the largest value seen in a healthy loop is about 1.2). Orders 7 and 8 at gain 1.5 and above were rejected: they run at 0 dB SACD with the quantiser input above 2, too close to instability to be a reference. Each report lists the design used per signal. The dsd2pcm quality tools' modulator is the 5th-order starting point and is credited in [reference tools](reference-tools.md).

**The reference decoder is long and linear-phase.** A chain of Kaiser-windowed FIR stages with 160 dB stopband, flat to 20 kHz, written from public DSP principles. It is the "perfect DAC": its own response is known, so what remains is the modulator under test. Every report shows its own floor, measured with an ideal sine and with loud out-of-band tones (see the [reference floor](footprint.md#the-reference-floor)).

**The C core.** The modulator's loop is a data-dependent recurrence, so it cannot be vectorised in NumPy. It is a 30-line C file built on first use; a slow Python fallback exists for completeness.

**The impulse is measured on all alignments.** A decimating filter's output samples depend on where the impulse falls relative to the output grid; one alignment can hide all ringing. Class A impulses are run at eight sub-sample offsets and the output samples interleaved into one response at 352.8 kHz resolution. Every point is a real output sample; nothing is interpolated.

**Honest gaps.** A test that cannot run says "not run" with a reason and never records a zero. The footprint lists what a given version runs.

## Determinism

Generators are deterministic and seeded; plots use a fixed hash salt and no dates, so the same inputs give byte-identical reports on the same package versions. Each report records tool versions, input and output hashes, the suite file hash and the profile.

## See also

- [Measurement footprint](footprint.md)
- [Reference tools](reference-tools.md)
- [User guide](user-guide.md)

Part of the [DSD Toolbox](https://github.com/aclater/dsd-toolbox).
