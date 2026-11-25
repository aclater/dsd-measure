<img src="https://raw.githubusercontent.com/dsd-toolbox/dsd-measure/main/docs/assets/icon-256.png" alt="" width="96">

# dsd-measure

[![CI](https://github.com/dsd-toolbox/dsd-measure/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/dsd-toolbox/dsd-measure/actions/workflows/ci.yml)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/dsd-toolbox/dsd-measure/badge)](https://scorecard.dev/viewer/?uri=github.com/dsd-toolbox/dsd-measure)
[![Release](https://img.shields.io/github/v/release/dsd-toolbox/dsd-measure)](https://github.com/dsd-toolbox/dsd-measure/releases/latest)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](pyproject.toml)
[![Licence: MIT OR Apache-2.0](https://img.shields.io/badge/licence-MIT%20OR%20Apache--2.0-blue)](#licence-and-credits)

A deterministic measurement kit for DSD to PCM converters and PCM to DSD modulators, for audiophiles who read [Archimago](https://archimago.blogspot.com/), [ASR](https://www.audiosciencereview.com/) and [Stereophile](https://www.stereophile.com/content/measurements-maps-precision) measurements. The kit measures: it makes no statement about hearing, it is not an AES17 instrument, and it has not been validated by anyone outside the authors; [what it can and cannot claim](docs/methodology-limits.md) is listed.

## Platforms

| System | How | Guide |
|---|---|---|
| Linux (x86-64, aarch64) | `pipx` from this repository; needs a C compiler for the reference modulator | [Install](docs/install.md) |
| macOS (Apple Silicon) | Homebrew, then `pipx`; steps in the guide | [Install](docs/install.md) |
| Windows 11 | WSL with Ubuntu, then the Linux steps; steps in the guide | [Install](docs/install.md) |

Tested on: Fedora 43 in a container; macOS 27.2 in a VM on Apple hardware (Apple Silicon); Windows 11 with WSL2 and Ubuntu 26.04 in a VM. Every Quick start command was run as written except these: on macOS the Homebrew installer (Homebrew was already in the VM) and `open` (the VM has no desktop session to open a browser in); on Windows `wsl --install -d Ubuntu` with its restart (the test installed WSL and Ubuntu in a headless VM instead).

## Quick start

Pick your system. All three run the same check at the end: `dsd-measure quick ffmpeg` measures ffmpeg as a DSD to PCM decoder and writes a report.

### Linux (Fedora)

<!-- docs-run: packages=sudo group=quick-start drop="^xdg-open" expect="Result:" timeout=3000 -->
```sh
sudo dnf install -y gcc git python3-pip pipx ffmpeg-free
# facts:install kind=pipx-git repo=dsd-toolbox/dsd-measure
pipx install git+https://github.com/dsd-toolbox/dsd-measure@v0.1.3
# /facts
dsd-measure quick ffmpeg
xdg-open report/ffmpeg/index.html
```

On Debian or Ubuntu use `sudo apt install -y build-essential git python3-pip pipx ffmpeg` instead of the first line.

### macOS (Apple Silicon)

Open the Terminal app (press Command and Space, type Terminal, press Return) and run these steps in order. The first one installs [Homebrew](https://brew.sh), the package manager the next steps use; it asks for your Mac password and may take several minutes.

<!-- docs-run: skip="macOS commands; run on macOS by the release test plan (docs/release-test-plan.md), not in the Linux container" -->
```sh
curl -fsSL -o install-homebrew.sh https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh
/bin/bash install-homebrew.sh
```

When it finishes, tell Terminal where Homebrew is, then install ffmpeg and pipx:

<!-- docs-run: skip="macOS commands; run on macOS by the release test plan (docs/release-test-plan.md), not in the Linux container" -->
```sh
/opt/homebrew/bin/brew shellenv >> ~/.zprofile
source ~/.zprofile
brew install ffmpeg pipx
pipx ensurepath
```

Close the Terminal window and open a new one, so that `pipx` programs are found. Then install dsd-measure, run the check (two to five minutes) and open the report:

<!-- docs-run: skip="macOS commands; run on macOS by the release test plan (docs/release-test-plan.md), not in the Linux container" -->
```sh
# facts:install kind=pipx-git repo=dsd-toolbox/dsd-measure
pipx install git+https://github.com/dsd-toolbox/dsd-measure@v0.1.3
# /facts
dsd-measure quick ffmpeg
open report/ffmpeg/index.html
```

If macOS asks to install the command line developer tools during the first step, click Install and let it finish; Homebrew needs them, and so does dsd-measure's C compiler.

### Windows 11 (through WSL)

dsd-measure does not run natively on Windows yet. It runs inside WSL, the Linux that Windows can install for itself. Step 1: open the Start menu, type PowerShell, right-click Windows PowerShell, choose Run as administrator, and run:

<!-- docs-run: skip="Windows PowerShell command, run on Windows by the release test plan (docs/release-test-plan.md), not in the Linux container" -->
```powershell
wsl --install -d Ubuntu
```

Restart Windows when it asks. (This first step was not tested as written; the steps after it were, in WSL2 on Windows 11.) After the restart an Ubuntu window opens by itself (or open Ubuntu from the Start menu); it asks you to choose a user name and a password for Linux. Step 2: in that Ubuntu window run:

<!-- docs-run: skip="WSL commands; the Ubuntu packages and pipx steps are run on Ubuntu by the release test plan (docs/release-test-plan.md), not in the Fedora container" -->
```sh
sudo apt update
sudo apt install -y build-essential git python3-pip pipx ffmpeg
pipx ensurepath
```

Close the Ubuntu window and open Ubuntu again from the Start menu. Step 3:

<!-- docs-run: skip="WSL commands; run in Ubuntu by the release test plan (docs/release-test-plan.md), not in the Fedora container" -->
```sh
# facts:install kind=pipx-git repo=dsd-toolbox/dsd-measure
pipx install git+https://github.com/dsd-toolbox/dsd-measure@v0.1.3
# /facts
dsd-measure quick ffmpeg
cd report/ffmpeg
explorer.exe .
```

The last line opens the report folder in Windows File Explorer; double-click `index.html` there.

This measures ffmpeg, as a DSD to PCM decoder, with the tool's synthetic test signals, and takes two to five minutes. The report opens with one sentence that starts "Result:" and says what ffmpeg's weakest figure in the audio band measures, or that it was not judged; the same sentence ends the terminal output. Replace `ffmpeg` with `dsd2pcm` or `sox-dsd` for those tools, or use `--command` for any other (see [Measure a decoder you have installed](docs/user-guide.md#measure-a-decoder-you-have-installed)). To compare two decoders on your own music instead, run `dsd-measure null track.dsf ffmpeg`.

To check the tool itself, `dsd-measure init` writes a suite file and `dsd-measure run suite.toml` measures the built-in reference decoder and modulator; that report says plainly that it shows the measurement floor, not a result for a product. A finished [example report](examples/README.md) of it is included. Add `--plan` to any `run` or `quick` command to see what it would do first.

## How it works

One command runs the kinds of test reviewers publish, on files and writes a report that opens with its conclusions in plain sentences, each backed by a figure and a stated [reference line](docs/conclusions.md) with its source and status, then a one-screen summary and a few key plots with the raw numbers beside them. Its own measurement floor is about -147 dB at DSD64 and is shown in every report, so a reader can see where the tool, not the device, sets a figure.

dsd-measure measures a **device under test**: your converter, a DSD to PCM decoder (class A) or a PCM to DSD modulator (class B). It can be a command-line tool, a plug-in, or a recording of a hardware DAC.

The **source data is synthetic**. The toolkit generates deterministic test signals itself (tones, two-tone pairs, a 32-tone multitone, J-Test, impulses and silence; no music), so a run regenerates the same signals on the same package versions (equality across platforms is not verified). `dsd-measure signals --list` describes each one in a sentence.

- **Class A, DSD to PCM:** the signals are encoded to DSD by the built-in reference modulator and fed to your decoder as DSF or DFF files. The PCM it returns is analysed.
- **Class B, PCM to DSD:** the signals are fed to your modulator as PCM (WAV). The DSD it returns is turned back into PCM by the built-in reference decoder, then analysed.

**Compare** means that every `[[device]]` in one suite file is measured with the identical signals and shown side by side in a comparison report. The built-in reference chain is always the floor: the least distortion and noise the tool itself can see, so a result close to it is flagged as limited by the measurement, not by the device.

Before anything runs, `dsd-measure run suite.toml --plan` prints each device with its exact command line, the signals, the DSD rates, the profile, an estimated time and where the report goes. Before measuring, a pre-flight check converts one short signal with each device and stops with the tool's own error if that fails. While it runs you get one numbered line per test with the time left, and the last line is the one-sentence `Result:`. Every report opens with that sentence and a "What was measured" block. See the [user guide](docs/user-guide.md#what-a-run-does).

### Example: compare two decoders

Save this as `compare.toml`. It measures ffmpeg and the built-in reference decoder with the same signals:

```toml
[suite]
name = "two decoders"
profile = "quick"
out = "report"

[[device]]
name = "ffmpeg"
adapter = "ffmpeg"
class = "A"

[[device]]
name = "reference decoder"
adapter = "reference"
class = "A"
out_rate = 352800
```

<!-- docs-run: skip="needs compare.toml, saved by hand from the block above; scripts/container-check.sh compare runs it from the README" -->
```sh
dsd-measure run compare.toml --plan
dsd-measure run compare.toml
xdg-open report/comparison/index.html
```

The `ffmpeg` adapter is a preset for `ffmpeg -v error -y -i {input} -c:a pcm_f32le {output}`. It asks for 32-bit float output on purpose: ffmpeg writes 16-bit WAV by default, and a 16-bit file cannot read above about 92 dB at a 44.1 kHz output rate and 101 dB at 352.8 kHz, so the report would describe the file format, not ffmpeg (dsd-measure detects that and says so). Some builds of ffmpeg read DSD from DFF files but not from DSF files; the pre-flight then gives ffmpeg DFF files. `--plan` lists both devices, the exact ffmpeg command line, the signals and the time it will take. The run writes:

- `report/ffmpeg/` and `report/reference-decoder/`: one report per device, each starting with its conclusions and what was measured.
- `report/comparison/`: the two side by side. It opens by saying whether they measure the same in the audio band and where they differ, notes when they were measured at different output rates or formats ("not like-for-like"), then gives one row per measurement with the reference floor marked. No cell is marked as better, because no repeatability interval has been measured yet.
- A summary at the end of the run with SINAD, dynamic range and the floor flag for each device.

To measure a different tool, use `adapter = "cli"` and give its `command`: `{input}` is the DSF file the tool reads and `{output}` the WAV it must write; ask the tool for float or 32-bit output.

## Documentation

- [User guide](docs/user-guide.md): measuring a converter, reading the report, troubleshooting.
- [Command line options](docs/options.md) and [suite file](docs/options.md#suite-file).
- [Use dsd-measure in your project's CI](docs/ci-gate.md): the release gate as a GitHub Actions step.
- [Conclusions](docs/conclusions.md): the rules behind each report's conclusions, with the thresholds and their sources.
- [Methodology limits](docs/methodology-limits.md): what dsd-measure can and cannot claim today.
- [Null test](docs/user-guide.md#compare-decoders-on-your-own-music): do two decoders differ on your own DSD file?
- [Measurement footprint](docs/footprint.md): what is measured, why, and exactly how.
- [Design](docs/design.md): the reference modulator and decoder, and the decisions behind them.
- [Accuracy](docs/accuracy.md): how the numbers are validated and where they stop being exact; `scripts/validate.sh` re-runs it.
- [Reference tools](docs/reference-tools.md): pinned black-box tools to compare against.
- [Example reports](examples/README.md): the reference chain, plus ready-made suites for decoders and SoX-DSD.
- [Changelog](CHANGELOG.md) and [contributing](CONTRIBUTING.md).

## How to cite

See [CITATION.cff](CITATION.cff); GitHub's "Cite this repository" button reads it, and each release is archived with a DOI on Zenodo.

## Licence and credits

**Code** is licensed under MIT OR Apache-2.0, at your option: see [LICENSE-MIT](LICENSE-MIT) and [LICENSE-APACHE](LICENSE-APACHE). [NOTICE](NOTICE) holds the attributions to keep with it. This covers all code, scripts, workflows and suite files, and the icons in `docs/assets/`.

**Documentation and measurement data** are licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) ([LICENSES/CC-BY-4.0.txt](LICENSES/CC-BY-4.0.txt)): this README, the pages under `docs/` (the methodology and the measurement footprint included) and the example reports and measurement data under `examples/`. Code examples and commands in these files may also be used under the code licence. Not covered: facts and figures cited from other sources, which keep their own terms.

**Your own reports are yours.** A report that you generate with dsd-measure is your own work and your own results. It is not CC BY, and you owe the project nothing for it. Every report and plot says "Measured with dsd-measure" and the version that measured it, so a reader can find the method.

**How to credit** the documentation: "dsd-measure documentation, the dsd-measure authors, https://github.com/dsd-toolbox/dsd-measure, CC BY 4.0". To cite the software, see [CITATION.cff](CITATION.cff).

**Credits.** The measurement set follows public practice by [Archimago](https://archimago.blogspot.com/), [Audio Science Review](https://www.audiosciencereview.com/), [Stereophile](https://www.stereophile.com/content/measurements-maps-precision) (John Atkinson), [RMAA](http://audio.rightmark.org/) and the conventions of AES17 (only the 20 kHz band edge and the dBFS reference; see [methodology limits](docs/methodology-limits.md#what-follows-aes17)), listed in the [footprint](docs/footprint.md#sources-and-credit). No code is copied from them.

Part of the [DSD Toolbox](https://github.com/dsd-toolbox/dsd-toolbox).
