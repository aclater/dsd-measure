<img src="https://raw.githubusercontent.com/aclater/dsd-measure/main/docs/assets/icon-256.png" alt="" width="96">

# dsd-measure

[![Licence](https://img.shields.io/badge/licence-MIT%20OR%20Apache--2.0-blue)](#licence-and-credits)

A reproducible measurement kit for DSD to PCM converters and PCM to DSD modulators, for audiophiles who read [Archimago](https://archimago.blogspot.com/), [ASR](https://www.audiosciencereview.com/) and [Stereophile](https://www.stereophile.com/content/measurements-maps-precision) measurements. One command runs the tests reviewers publish and writes a report that opens with its conclusions in plain sentences, each backed by a figure and a [published threshold](docs/conclusions.md), then a one-screen summary and a few key plots with the raw numbers beside them. Its own measurement floor is about -147 dB at DSD64 and is shown in every report, so a good device is not hidden by the tool.

## Platforms

| System | How | Guide |
|---|---|---|
| Linux (x86-64, aarch64) | `pipx` from this repository; needs a C compiler for the reference modulator | [Install](docs/install.md) |
| macOS | the same, with the Xcode command line tools | [Install](docs/install.md) |
| Windows | use WSL | [Install](docs/install.md) |

Tested on Fedora 43 in a container with Python 3.14.

## Quick start

```sh
sudo dnf install -y gcc git python3-pip pipx
pipx install git+https://github.com/aclater/dsd-measure
dsd-measure init
dsd-measure run suite.toml
xdg-open report/comparison/index.html
```

This measures the built-in reference decoder (DSD to PCM) and reference modulator (PCM to DSD) and takes a few minutes. A finished [example report](examples/README.md) of the reference chain is included. To measure your own converter, add a `[[device]]` table to `suite.toml` or run `dsd-measure quick dsd2pcm`; see [How it works](#how-it-works) and the [user guide](docs/user-guide.md). Add `--plan` to any `run` or `quick` command to see what it would do first.

## How it works

dsd-measure measures a **device under test**: your converter, a DSD to PCM decoder (class A) or a PCM to DSD modulator (class B). It can be a command-line tool, a plug-in, or a recording of a hardware DAC.

The **source data is synthetic**. The toolkit generates deterministic test signals itself (tones, two-tone pairs, a 32-tone multitone, J-Test, impulses and silence; no music), so anyone gets the same signals bit for bit. `dsd-measure signals --list` describes each one in a sentence.

- **Class A, DSD to PCM:** the signals are encoded to DSD by the built-in reference modulator and fed to your decoder as DSF or DFF files. The PCM it returns is analysed.
- **Class B, PCM to DSD:** the signals are fed to your modulator as PCM (WAV). The DSD it returns is turned back into PCM by the built-in reference decoder, then analysed.

**Compare** means that every `[[device]]` in one suite file is measured with the identical signals and shown side by side in a comparison report. The built-in reference chain is always the floor: the least distortion and noise the tool itself can see, so a result close to it is flagged as limited by the measurement, not by the device.

Before anything runs, `dsd-measure run suite.toml --plan` prints each device with its exact command line, the signals, the DSD rates, the profile, an estimated time and where the report goes. While it runs you get one line per test, and every report opens with a "What was measured" block. See the [user guide](docs/user-guide.md#what-a-run-does).

### Example: compare two decoders

Save this as `compare.toml`. It measures ffmpeg and the built-in reference decoder with the same signals:

```toml
[suite]
name = "two decoders"
profile = "quick"
out = "report"

[[device]]
name = "ffmpeg"
adapter = "cli"
class = "A"
input_ext = "dff"
command = "ffmpeg -v error -y -i {input} -c:a pcm_f32le {output}"

[[device]]
name = "reference decoder"
adapter = "reference"
class = "A"
out_rate = 352800
```

```sh
dsd-measure run compare.toml --plan
dsd-measure run compare.toml
xdg-open report/comparison/index.html
```

`input_ext = "dff"` hands ffmpeg a DFF file, because the distribution build of ffmpeg decodes DSD from DFF but not from DSF. `--plan` lists both devices, the exact ffmpeg command line, the signals and the time it will take. The run writes:

- `report/ffmpeg/` and `report/reference-decoder/`: one report per device, each starting with its conclusions and what was measured.
- `report/comparison/`: the two side by side. It opens by saying whether they can be told apart by measurement and where they differ, then one row per measurement, the better figure in bold, and the reference floor marked.
- A summary at the end of the run with SINAD, dynamic range and the floor flag for each device.

To measure a different tool, change the `command`: `{input}` is the DSF file the tool reads and `{output}` the WAV it must write.

## Documentation

- [User guide](docs/user-guide.md): measuring a converter, reading the report, troubleshooting.
- [Command line options](docs/options.md) and [suite file](docs/options.md#suite-file).
- [Conclusions](docs/conclusions.md): the rules behind each report's conclusions, with the thresholds and their sources.
- [Null test](docs/user-guide.md#compare-decoders-on-your-own-music): do two decoders differ on your own DSD file?
- [Measurement footprint](docs/footprint.md): what is measured, why, and exactly how.
- [Design](docs/design.md): the reference modulator and decoder, and the decisions behind them.
- [Accuracy](docs/accuracy.md): how the numbers are validated and where they stop being exact; `scripts/validate.sh` re-runs it.
- [Reference tools](docs/reference-tools.md): pinned black-box tools to compare against.
- [Example reports](examples/README.md): the reference chain, plus ready-made suites for decoders and SoX-DSD.
- [Changelog](CHANGELOG.md) and [contributing](CONTRIBUTING.md).

## Licence and credits

MIT OR Apache-2.0, at your option: see [LICENSE-MIT](LICENSE-MIT) and [LICENSE-APACHE](LICENSE-APACHE). The measurement set follows public practice by [Archimago](https://archimago.blogspot.com/), [Audio Science Review](https://www.audiosciencereview.com/), [Stereophile](https://www.stereophile.com/content/measurements-maps-precision) (John Atkinson), [RMAA](http://audio.rightmark.org/) and AES17, listed in the [footprint](docs/footprint.md#sources-and-credit).

Part of the [DSD Toolbox](https://github.com/aclater/dsd-toolbox).
