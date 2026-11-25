[dsd-measure](../README.md) › [Documentation](README.md) › Command line options

# Command line options

Every command of `dsd-measure` and every key of the suite file.

## Commands

| Command | What it does |
|---|---|
| `dsd-measure run SUITE [-o DIR] [--profile gate\|quick\|full] [--only TEST ...] [-j N] [--no-cache] [--plan] [-v]` | Run a suite file and write the report folder. `--plan` prints what would run and exits; `-v` shows device details; `-j N` sets the number of worker processes and `--no-cache` switches the cache of encoded test signals off (see [Speed](user-guide.md#speed)) |
| `dsd-measure quick CONVERTER [--command TEMPLATE] [--args ARGS] [--class A\|B] [-o DIR] [--profile P] [-j N] [--no-cache] [--plan] [-v]` | One device, no suite file. `CONVERTER` is a preset (`ffmpeg`, `dsd2pcm`, `sox-dsd`, `sacd_extract`), `reference` (both halves of the reference chain) or any name with `--command`. `--plan` prints what would run and exits |
| `dsd-measure null FILE [DEVICE ...] [OPTIONS]` | The real-music null test on your own DSF or DFF file, for example `dsd-measure null track.dsf ffmpeg`; see [Null test](#null-test) |
| `dsd-measure gate OLD NEW [--scale X] [--json FILE]` | Release gate: compare two device report folders (or `results.json` files) and exit 1 when a figure of `NEW` is worse than `OLD` beyond its repeatability; see [Release gate](#release-gate) |
| `dsd-measure cache [--clear] [--key]` | Show the cache of encoded test signals (folder, entries, size); `--clear` empties it; `--key` prints the name to save and restore the folder under in a CI system |
| `dsd-measure` | With no command, prints three lines saying what to type |
| `dsd-measure init [PATH]` | Write an example `suite.toml` |
| `dsd-measure signals DIR [--class A\|B] [--profile quick\|full] [--only TEST ...] [--rate HZ] [--rates HZ ...]` | Write every test signal a run feeds a device (a DSF per test for class A, a WAV per test for class B) and `signals.json`, for devices you run by hand |
| `dsd-measure signals --list` | Print the catalogue of test signals, one plain sentence each |
| `dsd-measure versions` | Print tool versions |

Exit status: 0 everything ran, 1 the report was written but some tests raised an error (for `gate`: a figure is worse; for `null`, and for a suite's `[null]` table: an alignment could not be trusted), 2 a fatal error (no report; for `gate`: the two results cannot be compared), 130 Ctrl-C. See the [user guide](user-guide.md#exit-status).

Tests for `--only`: `reference_floor`, `levels`, `thdn_freq`, `frequency_response`, `impulse`, `noise`, `imd`, `multitone`, `tone_15k`, `jtest`, `polarity`, `stability`, `crosstalk`, `imd_sweep`, `alias_tones`, `overload`, `rate_table`. The `gate` profile runs `reference_floor`, `levels`, `noise` and `alias_tones` unless `--only` names others.

| Environment variable | Meaning |
|---|---|
| `DSD_MEASURE_JOBS` | Number of worker processes when `-j` is not given |
| `DSD_MEASURE_NO_CACHE` | `1` switches the cache of encoded test signals off, as `--no-cache` does |
| `DSD_MEASURE_CACHE_DIR` | Folder for the cache (an absolute path) instead of `$XDG_CACHE_HOME/dsd-measure` or `~/.cache/dsd-measure` |
| `DSD_MEASURE_CACHE_MAX_MB` | Size limit of the cached test signals in MiB (default 4096) |

## Output of a run and of --plan

`--plan` prints, per device, the class, adapter, example command line, what it is fed and returns, then the signals, DSD rates, profile, estimated time and report paths. A run first checks each device with a short pre-flight conversion, then prints `[n/total] -> device: test (signal, level) ... done in Xs, about M:SS left` or `... skipped: reason` for each test, then the report path, one summary line per device (SINAD, dynamic range, reference-floor flag) and a last line, `Result: ...`, with the one-sentence result that opens the report. See the [user guide](user-guide.md#what-a-run-does).

## Suite file

TOML. `[suite]` sets `name`, `profile` (`gate`, `quick` or `full`), `in_rate` (PCM rate fed to the device, default 88200), `out` (report folder) and `jobs` (worker processes, as `-j`). Each `[[device]]` has `name`, `class` (`A` or `B`), `adapter` and the adapter's keys, plus `version` (a version string to record beside the one the program prints), `gain_db` (applied to the output, default 0), `dsd_rate` (the DSD rate fed to a class A device or requested from a class B modulator, default 2822400) and `rates` (extra DSD rates for the rate table, for example `[5644800, 11289600]`).

| Adapter | Keys | Notes |
|---|---|---|
| `reference` | `out_rate` (class A, default 352800) | The built-in decoder (class A) or modulator (class B) |
| `cli` | `command`, `shell` (default `false`), `input_ext` (`dsf` or `dff`), `output_ext`, `workdir`, `timeout` (seconds, default 3600), `version_command` (a command that prints the tool's version, for a command that starts a wrapper script) | `{input}` and `{output}` in the command (other braces are left alone; `{{input}}` is the literal text); run without a shell unless `shell = true`, as your user, so only use commands you trust; a timed-out command is killed with its children; class A reads WAV or FLAC, class B reads DSF. `tools/reftool-file.sh` runs a pinned container tool in the same way |
| `dsd2pcm`, `sox-dsd`, `sacd_extract` | `command` (optional) | Presets for `cli`; the tool must be on `PATH` |
| `sox-dsd` with `reftool` | `reftool`, `out_rate`, `modulator` (`sdm-8` by default, `clans-8`, `auto`) | The pinned container wrapper. Every report records the level mapping it used. SoX-DSD maps PCM full scale to 50 % modulation, so a -6 dBFS test tone reaches its modulator at 25 %: `input_gain_db` (class B, default 0; use 6.0206 for the footprint's 0 dB SACD) raises the PCM first, and `gain_db` restores unity gain (default `6.0206 - input_gain_db`). `trellis` is `"default"` (default, SoX's own settings) or `"32x32"` (`-t 32 -n 32`, the default before 0.1.3). Set `REFTOOL_RELABEL=1` where a confined user cannot run containers unconfined |
| `import` | `directory` | Reads `<test>.wav` or `<test>.dsf` made elsewhere |

## Null test

`dsd-measure null` decodes one source file with two or more devices and measures the difference. The first device is the baseline; when one decoder is named, the built-in reference decoder is the baseline. The method is in the [user guide](user-guide.md#compare-decoders-on-your-own-music) and the [footprint](footprint.md#real-music-null-test).

| Option | Default | Meaning |
|---|---|---|
| `FILE` or `--source FILE` | | DSF or DFF file (not DST-compressed); read only. Given first on the command line, or with `--source` |
| `DEVICE ...` or `--device TEXT` | | The decoders, positional or repeated with `--device`: a preset name (`ffmpeg`, `dsd2pcm`, `sox-dsd`, `sacd_extract`), `reference` or `reference@RATE` (the built-in decoder, default 352800 Hz; the rate must divide the DSD rate), `NAME=COMMAND` (a template with `{input}` and `{output}`; start the command with `dff:` to give the tool a DFF file), or the name of a `[[device]]` in `--suite` |
| `--suite FILE` | | Suite file with `[[device]]` tables and an optional `[null]` table; the options below override the table |
| `-o`, `--out DIR` | `null-report` | Report folder |
| `--trim-start`, `--trim-end` SECONDS | 0.5 | Cut at each end |
| `--start`, `--duration` SECONDS | whole file | Analyse part of the track |
| `--rate HZ` | the lower of the two device rates | Common rate; not above either device's rate |
| `--max-delay SECONDS` | 0.5 | Longest delay searched either way |
| `--polarity auto\|keep` | `auto` | Detect and undo an inverted device, or leave it |
| `--gain match\|none` | `match` | Least-squares level match, or none |
| `--channels N ...` | all | Channels to compare |
| `--diff-wav` | off | Also write `difference-<device>.wav` (32-bit float, common rate) |
| `--diff-gain-db DB` | 0 | Gain on the difference WAV only |
| `--keep-work` | off | Keep the decoders' output files in `.work/` |

The delay, polarity, gain and the null depth use 20 Hz to 20 kHz, or the band both devices pass when that is narrower. `results.json` has, per pair, `trust` (`untrustworthy`, `reason`, `not_like_for_like`, `bandwidth_hz` for A and B, `min_correlation`) and `null_band_hz`; per channel, `null_depth_db` (in band) and `null_depth_fullband_db`. Up to 0.1.2 `null_depth_db` was the full-band figure. A pair whose in-band correlation after alignment is below 0.5 is marked untrustworthy and the command exits with status 1; see the [user guide](user-guide.md#compare-decoders-on-your-own-music).

In a suite file the same keys go in a `[null]` table, with `source`, `devices` (a list of device names or `--device` texts) and `out` as well:

```toml
[null]
source = "track.dsf"
devices = ["reference@352800", "reference@176400"]
out = "null-report"
trim_start = 0.5
diff_wav = true
```

`dsd-measure run suite.toml --only null` runs only the null test of a suite that has a `[null]` table; a plain `run` measures the devices and then runs it too.

The report folder holds `index.html`, `index.md`, `results.json`, `bands.csv` (third-octave levels), `seconds.csv` (levels per second), `provenance.json`, `plots/*.svg` and the optional WAV files.

## Release gate

`dsd-measure gate OLD NEW` reads the `results.json` of two device report folders made with the same suite and profile and compares these figures. A change inside the repeatability is "same"; outside it the figure is "better" or "worse". Any "worse", or a figure that was measured in `OLD` and is not in `NEW`, fails the gate (exit status 1). The bytes of the converter's output are not compared.

| Figure | Better when | Repeatability (dB) |
|---|---|---:|
| SINAD, 1 kHz at 0 dB SACD | higher | 0.6 |
| THD, 1 kHz at 0 dB SACD | lower | 1.5 |
| THD+N A-weighted, 1 kHz at 0 dB SACD | lower | 0.6 |
| SINAD at the peak level | higher | 0.6 |
| Dynamic range, A-weighted | higher | 0.5 |
| Noise 20 Hz to 20 kHz, A-weighted | lower | 0.2 |
| Noise 20 Hz to 20 kHz | lower | 0.2 |
| Gain error at 1 kHz | closer to zero | 0.001 |
| Lowest level within 0.5 dB | lower | 6.1 |
| Worst alias image | lower | 6.0 |

The repeatability is three standard deviations of the difference between two runs whose noise differs, measured on the reference chain (see [Accuracy](accuracy.md#repeatability)); the lowest level moves in steps of the level ladder, so one step is allowed. `--scale X` multiplies every repeatability and `--json FILE` writes the table as JSON. A NaN or infinite figure counts as not measured: in `NEW` where `OLD` had a number it fails like a figure that is no longer measured, and in `OLD` it is "not measured" there. The gate refuses to compare, with exit status 2 and no `--json` file, when

- nothing was compared (no figure was measured in both results, so there is nothing to pass);
- the two results differ in analysis version, device class or DSD rate, or one of them does not record them;
- both arguments are report folders with a `provenance.json` and they differ in input rate, in the output rate of the device (`output_format.rate` in `results.json`, recorded for class A devices only) or in profile. The `gate` and `quick` profiles are comparable, because the gate profile uses the quick profile's signals; `full` is comparable with neither.

When you give a `results.json` file, or a folder without `provenance.json`, only the analysis version, device class and DSD rate are checked: the input rate, the output rate and the profile are not, so make sure both were measured the same way. To run the gate on every pull request, see [Use dsd-measure in your project's CI](ci-gate.md).

## Report folder

```text
report/<device>/index.html, index.md, results.csv, results.json, provenance.json, plots/*.svg      (each opens with "What was measured")
report/comparison/index.html, index.md, results.csv, plots/*.svg      (two or more devices)
```

Every report page (HTML and Markdown) ends with the line "Measured with dsd-measure X.Y.Z" and the project address, and every plot carries it in small grey text under the figure. The version is the one that did the measuring. The reports are yours: see [Licence and credits](../README.md#licence-and-credits).

## See also

- [User guide](user-guide.md)
- [Measurement footprint](footprint.md)
- [Roadmap](roadmap.md)

Part of the [DSD Toolbox](https://github.com/dsd-toolbox/dsd-toolbox).
