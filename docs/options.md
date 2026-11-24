[dsd-measure](../README.md) › [Documentation](README.md) › Command line options

# Command line options

Every command of `dsd-measure` and every key of the suite file.

## Commands

| Command | What it does |
|---|---|
| `dsd-measure run SUITE [-o DIR] [--profile quick\|full] [--only TEST ...]` | Run a suite file and write the report folder |
| `dsd-measure quick CONVERTER [--command TEMPLATE] [--class A\|B] [-o DIR] [--profile P]` | One device, no suite file. `reference` measures both halves of the reference chain |
| `dsd-measure init [PATH]` | Write an example `suite.toml` |
| `dsd-measure signals DIR [--rate HZ]` | Write test signals as WAV files for devices you run by hand |
| `dsd-measure versions` | Print tool versions |

Tests for `--only`: `reference_floor`, `levels`, `thdn_freq`, `frequency_response`, `impulse`, `noise`, `imd`, `multitone`, `tone_15k`, `jtest`, `polarity`, `stability`, `crosstalk`, `imd_sweep`, `alias_tones`, `overload`, `rate_table`.

## Suite file

TOML. `[suite]` sets `name`, `profile` (`quick` or `full`), `in_rate` (PCM rate fed to the device, default 88200) and `out` (report folder). Each `[[device]]` has `name`, `class` (`A` or `B`), `adapter` and the adapter's keys, plus `gain_db` (applied to the output, default 0), `dsd_rate` (the DSD rate fed to a class A device or requested from a class B modulator, default 2822400) and `rates` (extra DSD rates for the rate table, for example `[5644800, 11289600]`).

| Adapter | Keys | Notes |
|---|---|---|
| `reference` | `out_rate` (class A, default 352800) | The built-in decoder (class A) or modulator (class B) |
| `cli` | `command`, `input_ext` (`dsf` or `dff`), `output_ext`, `workdir`, `timeout` | `{input}` and `{output}` in the command; class A reads WAV or FLAC, class B reads DSF. `tools/reftool-file.sh` runs a pinned container tool in the same way |
| `dsd2pcm`, `sox-dsd`, `sacd_extract` | `command` (optional) | Presets for `cli`; the tool must be on `PATH` |
| `sox-dsd` with `reftool` | `reftool`, `out_rate`, `modulator` (`sdm-8`, `clans-8`, `auto`) | The pinned container wrapper; `gain_db` defaults to 6.0206. Set `REFTOOL_RELABEL=1` where a confined user cannot run containers unconfined |
| `import` | `directory` | Reads `<test>.wav` or `<test>.dsf` made elsewhere |

## Report folder

```
report/<device>/index.html, index.md, results.csv, results.json, provenance.json, plots/*.svg
report/comparison/index.html, index.md, results.csv, plots/*.svg      (two or more devices)
```

## See also

- [User guide](user-guide.md)
- [Measurement footprint](footprint.md)

Part of the [DSD Toolbox](https://github.com/aclater/dsd-toolbox).
