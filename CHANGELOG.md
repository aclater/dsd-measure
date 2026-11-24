# Changelog

All notable changes are listed here, newest first. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## Unreleased

### Fixed

- Install instructions: `pipx install git+…` needs git, which a minimal system lacks; the install lines now include it.

## 0.1.0

### Added

- The measurement footprint ([docs/footprint.md](docs/footprint.md)): 19 tests of DSD to PCM converters (class A) and PCM to DSD modulators (class B), with the reduced methods listed honestly.
- A reference modulator (single bit, Legendre zeros, order 8 down to 5 behind a stability guard) and a long linear-phase reference decoder, and the reference floor in every report: about -147 dB THD+N at DSD64 and -176 dB at DSD128, with the decoder alone below -280 dB. Figures within 6 dB of the floor are marked.
- Tests: SINAD, THD and THD+N at several levels, THD+N against level and frequency, dynamic range, noise, frequency response, filter, impulse and step, group delay, SMPTE and CCIF IMD and the IMD sweep, 32-tone multitone, J-Test, linearity, 15 kHz tone, crosstalk and channel match, alias tones, overload recovery, polarity, DC, gain, stability at the peak level, and a DSD128 and DSD256 rate table.
- Reports as HTML with inline SVG, Markdown, CSV and JSON; a comparison report with two or more devices side by side.
- Adapters: `reference`, `cli` (DSF or DFF in), `import`, `sox-dsd`, and presets for dsd2pcm and sacd_extract; pinned black-box reference tool containers (SoX-DSD, ffmpeg-free, sacd_extract) through `tools/reftool.sh`.
- Example reports in `examples/`.

Part of the [DSD Toolbox](https://github.com/aclater/dsd-toolbox).
