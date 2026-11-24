[dsd-measure](../README.md) › [Documentation](README.md) › User guide

# User guide

How to measure a converter, read the report and fix the usual problems.

## Measure a converter

Pick the class. A DSD to PCM converter (class A) is given DSD files made by the reference modulator and its PCM output is analysed. A PCM to DSD modulator (class B) is given PCM files and its DSD output is decoded by the reference decoder and analysed.

Any command-line tool works through a template with `{input}` and `{output}`:

```sh
dsd-measure quick --command 'dsd2pcm {input} -o {output}' --class A my-decoder
```

For several devices at once write a suite file (`dsd-measure init` writes an example):

```toml
[suite]
name = "my comparison"
profile = "quick"
out = "report"

[[device]]
name = "my decoder"
adapter = "cli"
class = "A"
command = "dsd2pcm {input} -o {output}"

[[device]]
name = "reference decoder"
adapter = "reference"
class = "A"
out_rate = 44100
```

Run it with `dsd-measure run suite.toml`. Two or more devices also give a comparison report.

## Devices you cannot run

For a player or plug-in that cannot be scripted, write the test signals with `dsd-measure signals signals/`, feed them to the device by hand, put the results back as `<test>.wav` (class A) or `<test>.dsf` (class B) in one folder and use the `import` adapter with `directory = "results"`. The report marks these devices as imported.

## Read the report

Open `index.html`. The row of big numbers (SINAD, dynamic range, noise, filter, ultrasonic noise) and the table under it are the whole result in one screen. Below it are seven key plots, each with one sentence saying what the numbers mean. "More plots" holds the detail, "Not run" lists what was skipped and why, and "Provenance" lists tool versions and file hashes. The same numbers are in `results.csv` and `results.json`, and each plot is a separate SVG in `plots/`.

Some terms:

- **Reference floor**: what the measurement itself cannot see below. A figure marked "at the reference floor" is within 6 dB of it and may be limited by the tool, not the device. At DSD64 the floor is about -147 dB THD+N; use `dsd_rate = 5644800` for class A devices that accept DSD128 and the floor drops to about -176 dB.
- **SINAD** and **THD+N**: how far the unwanted sound is below a 1 kHz tone. 100 dB or more is excellent.
- **Dynamic range**: the noise floor measured with a quiet -60 dB tone, the usual "DR" figure.
- **Multitone distortion-free range**: how clean the output stays with 32 tones at once.
- **Ultrasonic noise** (modulators): the shaped noise above 20 kHz, which is normal for DSD but should be low and steady.

## Stereo, rates and the other tests

Crosstalk and channel match use a stereo pair automatically. For a class B modulator, `rates = [5644800, 11289600]` adds a DSD128 and DSD256 table (THD+N, dynamic range, ultrasonic peak, stability). Class A devices that read DSD128 are measured with `dsd_rate = 5644800`. A recorded analogue path can be imported (see above) and analysed as class A.

## Profiles

`quick` takes a few minutes and uses shorter signals and 6 dB level steps; `full` follows the footprint (3 dB steps, 15 s noise, 60 s stability holds) and takes much longer. The report always says which one was used.

## Troubleshooting

- **No C compiler.** Install `gcc` (Linux) or the Xcode command line tools (macOS). Without it the slow Python modulator is used and a run takes hours.
- **A test says "not run".** The reason is in the report. A tool that cannot make a file, or an import folder with a missing file, is reported and the other tests still run.
- **Levels differ by 6.02 dB.** Some tools map WAV full scale to 0 dB SACD. Set `gain_db` on the device to undo it; the gain is recorded in the report.
- **FLAC output.** Set `output_ext = "flac"` on a `cli` device; ffmpeg converts it for reading.

## See also

- [Command line options](options.md)
- [Measurement footprint](footprint.md)
- [Design](design.md)

Part of the [DSD Toolbox](https://github.com/aclater/dsd-toolbox).
