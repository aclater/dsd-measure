<img src="https://raw.githubusercontent.com/aclater/dsd-measure/main/docs/assets/icon-256.png" alt="" width="96">

# dsd-measure

[![Licence](https://img.shields.io/badge/licence-MIT%20OR%20Apache--2.0-blue)](#licence-and-credits)

A reproducible measurement kit for DSD to PCM converters and PCM to DSD modulators, for audiophiles who read [Archimago](https://archimago.blogspot.com/), [ASR](https://www.audiosciencereview.com/) and [Stereophile](https://www.stereophile.com/content/measurements-maps-precision) measurements. One command runs the tests reviewers publish and writes a report that opens with a one-screen summary and a few key plots, each with a plain-language line, with the raw numbers beside it. Its own measurement floor is about -147 dB at DSD64 and is shown in every report, so a good device is not hidden by the tool.

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

This measures the built-in reference decoder (DSD to PCM) and reference modulator (PCM to DSD) and takes a few minutes. A finished [example report](examples/README.md) of the reference chain is included. To measure your own converter, add a `[[device]]` table to `suite.toml` or run `dsd-measure quick dsd2pcm`; see the [user guide](docs/user-guide.md).

## Known issues in 0.1.0

An independent review found that some report figures in 0.1.0 reflect the analysis rather than the device: the stopband, the class B multitone range, the ultrasonic noise peak, the noise headline, overload recovery, the J-Test sideband, multitone at 48 kHz-family rates, and the peak-level SINAD of class A devices. Corrected definitions, each with a regression test, are coming in 0.1.1. Until then, rely on THD, THD+N/SINAD, dynamic range, gain, linearity, frequency response, single-point IMD, crosstalk and the reference floor, which the review confirmed.

## Documentation

- [User guide](docs/user-guide.md): measuring a converter, reading the report, troubleshooting.
- [Command line options](docs/options.md) and [suite file](docs/options.md#suite-file).
- [Measurement footprint](docs/footprint.md): what is measured, why, and exactly how.
- [Design](docs/design.md): the reference modulator and decoder, and the decisions behind them.
- [Reference tools](docs/reference-tools.md): pinned black-box tools to compare against.
- [Example reports](examples/README.md): the reference chain, plus ready-made suites for decoders and SoX-DSD.
- [Changelog](CHANGELOG.md) and [contributing](CONTRIBUTING.md).

## Licence and credits

MIT OR Apache-2.0, at your option: see [LICENSE-MIT](LICENSE-MIT) and [LICENSE-APACHE](LICENSE-APACHE). The measurement set follows public practice by [Archimago](https://archimago.blogspot.com/), [Audio Science Review](https://www.audiosciencereview.com/), [Stereophile](https://www.stereophile.com/content/measurements-maps-precision) (John Atkinson), [RMAA](http://audio.rightmark.org/) and AES17, listed in the [footprint](docs/footprint.md#sources-and-credit).

Part of the [DSD Toolbox](https://github.com/aclater/dsd-toolbox).
