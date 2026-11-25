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
| `analyse` | One function per metric, each tested against a signal with a known answer and against a separately written second analyser (`tests/refanalyser.py`); see [accuracy](accuracy.md) |
| `measure` | The tests of the footprint, run against one adapter |
| `report` | HTML, Markdown, SVG, CSV and JSON |
| `plan` | The test catalogue: what each test uses and why, `--plan`, `signals --list` and the report's "What was measured" data |
| `run`, `cli` | The suite file, the run log and the command line |
| `stimcache` | The per-user cache of encoded test signals: key, integrity check, size limit |
| `parallel` | The tests of a suite in worker processes, joined into the result of a serial run |
| `gate` | The release gate: two results compared figure by figure against the repeatability |
| `dsdstream` | DSF and DFF read in ranges, and converted bit-exactly, without loading the file |
| `nulltest` | The real-music null test: `tracks` (ranged readers, resampler), `devices`, `align`, `analyse`, `verdict`, `report`, `run` |

## Decisions

**Everything goes through arrays.** Adapters take and return arrays, so the tests do not care whether a device is a library, a command or a folder of files. File adapters write inputs to a work folder, hash them and read the output back.

**One analysis grid.** In-band analysis uses the bin spacing of a 2^18-point FFT at 352.8 kHz for every output rate, so a coherent 1 kHz tone is the same bin number everywhere and results are comparable across devices. Why: a device that outputs 44.1 kHz and one that outputs 352.8 kHz then differ only in their own behaviour.

**A window with a wide lobe, and its cost.** Spectra use a 7-term Blackman-Harris window (sidelobes below -180 dB). Its main lobe is 7 bins wide each side, so the tone and notch use a 10-bin margin. Why: a plain 4-term window leaves leakage near -90 dB, which would hide a good converter's floor.

**The reference modulator is high-order and guarded.** It is a single-bit error-feedback loop with Legendre zeros in the audio band and Butterworth poles scaled to a chosen largest noise-transfer gain (Schreier and Temes, *Understanding Delta-Sigma Data Converters*, sec. 4.3 and 4.4.1). The first version was 5th order at gain 1.3 and read only about 106 dB SINAD, which would have masked every good device. Order 8 at gain 1.45 reads about 147 dB at DSD64 and is stable at 0 dB SACD but not at the +3.1 dB SACD peak, so the encoder runs a ladder of designs and moves down when the quantiser input exceeds 2 (the largest value seen in a healthy loop is about 1.2). At the peak level the ladder lands on order 8 at gain 1.3 (the quantiser input stays near 0.9, and it reads about 129 dB SINAD at DSD64); order 7 at gain 1.3, which 0.1.0 used there, read 122.5 dB. Gains from 1.34 up overload at the peak level for low tones. Orders 7 and 8 at gain 1.5 and above were rejected: they run at 0 dB SACD with the quantiser input above 2, too close to instability to be a reference. Each report lists the design used per signal. The dsd2pcm quality tools' modulator is the 5th-order starting point and is credited in [reference tools](reference-tools.md).

**The reference decoder is long and linear-phase.** A chain of Kaiser-windowed FIR stages with 160 dB stopband, flat to 20 kHz, written from public DSP principles. It is the "perfect DAC": its own response is known, so what remains is the modulator under test. Every report shows its own floor, measured with an ideal sine and with loud out-of-band tones (see the [reference floor](footprint.md#the-reference-floor)).

**The C core.** The modulator's loop is a data-dependent recurrence, so it cannot be vectorised in NumPy. It is a 30-line C file built on first use; a slow Python fallback exists for completeness.

**The interpolator runs in the frequency domain.** The filters in front of the reference modulator are long (2047 taps, then 255 per stage) and the direct-form polyphase filter was 79 % of a run. Each stage is now one FFT overlap-add convolution per polyphase branch (`scipy.signal.oaconvolve`), about six times faster on one core (the 2047-tap first stage 24 times), with the same taps. Why not shorter filters: stages only as long as their image rejection needs were measured too and moved the signal by 2e-8 (-155 dB), which is a different reference; the FFT form moves it by rounding only (-287 dB). Why SciPy's own routine: a hand-written overlap-save was no faster. The modulator is chaotic, so the bitstream differs and the equivalence is shown statistically ([repeatability](accuracy.md#repeatability)).

**Encoded signals are cached, results are not.** The modulator's output is a pure function of its input and the software, so it is stored once per user, named by a hash of every input, and checked by hash on each read. Why not cache the figures: the analysis is what a release of dsd-measure changes, and a figure that is always computed cannot be stale. Why a hash of the encoder's source in the name: a change to the encoder between releases then cannot read old entries.

**Parallel by test, in processes.** Every test of every device has its own stimuli and device calls, so the tests are the unit of parallel work; each runs in a worker process with its own adapter and work folder, and the pieces are joined in run order. The device delay, which three tests share, is measured once and handed to them. Why processes: the work is NumPy, SciPy and external tools, and worker processes need no locking. Why not threads inside the FFT: the transforms are short blocks, and threading them gained little where worker processes give about 4 times on a 14-core laptop CPU ([performance](performance.md)). A run with any number of jobs writes the `results.json` of a serial run; a test holds that.

**What was measured and not adopted.** The modulator core runs at the latency of its feedback sum (18 ns per sample on an i9-13900H P-core); other compiler flags and a rewrite with the state in registers stayed within 9 % and byte-identical, so the core is unchanged, and a faster sum would need another order of additions, which is another bitstream. A C decimation kernel for the decoder was byte-identical to SciPy's and 1.1 times faster, not worth a second compiled file. An FFT interpolator in 64-bit float on a consumer GPU (RTX 4070 Ti) was about 4 times faster than one laptop P-core. That is no more than the worker processes give on a multi-core machine, nothing on a cached run, and a second set of rounding (so a second set of bitstreams); 32-bit float on the GPU has an error of -130 dB, above the reference floor. There is no GPU path.

**The impulse is measured on all alignments.** A decimating filter's output samples depend on where the impulse falls relative to the output grid; one alignment can hide all ringing. Class A impulses are run at eight sub-sample offsets and the output samples interleaved into one response at 352.8 kHz resolution. Every point is a real output sample; nothing is interpolated.

**Honest gaps.** A test that cannot run says "not run" with a reason and never records a zero. The footprint lists what a given version runs.

**The null test works in blocks.** Every reader returns any sample range on request and zeros outside the file, so the test needs memory for a block, not a track. The reference decoder is evaluated per range with real neighbouring bits on both sides, which gives the same samples as decoding the whole file, except within the filter length of the file's own ends (which are trimmed). Gain, delay and the verdict use 20 Hz to 20 kHz only: Why: two good decoders legitimately differ above 20 kHz (one passes shaped noise, one removes it), and a gain fitted over that noise leaves a flat error in the whole audio band.

## Determinism

Generators are deterministic and seeded; plots use a fixed hash salt and no dates, so the same inputs give byte-identical reports on the same package versions. Each report records tool versions, input and output hashes, the suite file hash and the profile.

## See also

- [Measurement footprint](footprint.md)
- [Reference tools](reference-tools.md)
- [User guide](user-guide.md)

Part of the [DSD Toolbox](https://github.com/dsd-toolbox/dsd-toolbox).
