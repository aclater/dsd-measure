[dsd-measure](../README.md) › [Documentation](README.md) › Command line options

# Command line options

Every command of `dsd-measure` and every key of the suite file.

## Commands

| Command | What it does |
|---|---|
| `dsd-measure run SUITE [-o DIR] [--profile quick\|full] [--only TEST ...] [--plan] [-v]` | Run a suite file and write the report folder. `--plan` prints what would run and exits; `-v` shows device details |
| `dsd-measure quick CONVERTER [--command TEMPLATE] [--args ARGS] [--class A\|B] [-o DIR] [--profile P] [--plan] [-v]` | One device, no suite file. `CONVERTER` is a preset (`ffmpeg`, `dsd2pcm`, `sox-dsd`, `sacd_extract`), `reference` (both halves of the reference chain) or any name with `--command`. `--plan` prints what would run and exits |
| `dsd-measure null FILE [DEVICE ...] [OPTIONS]` | The real-music null test on your own DSF or DFF file, for example `dsd-measure null track.dsf ffmpeg`; see [Null test](#null-test) |
| `dsd-measure` | With no command, prints three lines saying what to type |
| `dsd-measure init [PATH]` | Write an example `suite.toml` |
| `dsd-measure signals DIR [--class A\|B] [--profile quick\|full] [--only TEST ...] [--rate HZ] [--rates HZ ...]` | Write every test signal a run feeds a device (a DSF per test for class A, a WAV per test for class B) and `signals.json`, for devices you run by hand |
| `dsd-measure signals --list` | Print the catalogue of test signals, one plain sentence each |
| `dsd-measure versions` | Print tool versions |

Exit status: 0 everything ran, 1 the report was written but some tests raised an error, 2 a fatal error (no report), 130 Ctrl-C. See the [user guide](user-guide.md#exit-status).

Tests for `--only`: `reference_floor`, `levels`, `thdn_freq`, `frequency_response`, `impulse`, `noise`, `imd`, `multitone`, `tone_15k`, `jtest`, `polarity`, `stability`, `crosstalk`, `imd_sweep`, `alias_tones`, `overload`, `rate_table`.

## Output of a run and of --plan

`--plan` prints, per device, the class, adapter, example command line, what it is fed and returns, then the signals, DSD rates, profile, estimated time and report paths. A run first checks each device with a short pre-flight conversion, then prints `[n/total] -> device: test (signal, level) ... done in Xs, about M:SS left` or `... skipped: reason` for each test, then the report path, one summary line per device (SINAD, dynamic range, reference-floor flag) and a last line, `Result: ...`, with the one-sentence result that opens the report. See the [user guide](user-guide.md#what-a-run-does).

## Suite file

TOML. `[suite]` sets `name`, `profile` (`quick` or `full`), `in_rate` (PCM rate fed to the device, default 88200) and `out` (report folder). Each `[[device]]` has `name`, `class` (`A` or `B`), `adapter` and the adapter's keys, plus `gain_db` (applied to the output, default 0), `dsd_rate` (the DSD rate fed to a class A device or requested from a class B modulator, default 2822400) and `rates` (extra DSD rates for the rate table, for example `[5644800, 11289600]`).

| Adapter | Keys | Notes |
|---|---|---|
| `reference` | `out_rate` (class A, default 352800) | The built-in decoder (class A) or modulator (class B) |
| `cli` | `command`, `shell` (default `false`), `input_ext` (`dsf` or `dff`), `output_ext`, `workdir`, `timeout` (seconds, default 3600) | `{input}` and `{output}` in the command (other braces are left alone; `{{input}}` is the literal text); run without a shell unless `shell = true`, as your user, so only use commands you trust; a timed-out command is killed with its children; class A reads WAV or FLAC, class B reads DSF. `tools/reftool-file.sh` runs a pinned container tool in the same way |
| `dsd2pcm`, `sox-dsd`, `sacd_extract` | `command` (optional) | Presets for `cli`; the tool must be on `PATH` |
| `sox-dsd` with `reftool` | `reftool`, `out_rate`, `modulator` (`sdm-8`, `clans-8`, `auto`) | The pinned container wrapper. SoX-DSD maps PCM full scale to 50 % modulation, so a -6 dBFS test tone reaches its modulator at 25 %: `input_gain_db` (class B, default 0; use 6.0206 for the footprint's 0 dB SACD) raises the PCM first, and `gain_db` restores unity gain (default `6.0206 - input_gain_db`). `trellis` is `"32x32"` (default, `-t 32 -n 32`) or `"default"` (SoX's own settings). Set `REFTOOL_RELABEL=1` where a confined user cannot run containers unconfined |
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

## Report folder

```text
report/<device>/index.html, index.md, results.csv, results.json, provenance.json, plots/*.svg      (each opens with "What was measured")
report/comparison/index.html, index.md, results.csv, plots/*.svg      (two or more devices)
```

## See also

- [User guide](user-guide.md)
- [Measurement footprint](footprint.md)
- [Roadmap](roadmap.md)

Part of the [DSD Toolbox](https://github.com/dsd-toolbox/dsd-toolbox).
