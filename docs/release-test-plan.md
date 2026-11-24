[dsd-measure](../README.md) › [Documentation](README.md) › Release test plan

# Release test plan

The checks that run on the integrated release tree before dsd-measure is tagged. Every step is a literal command with a pass condition, so anyone can repeat it and get the same verdict. A release is ready when every row of the results table passes on the exact commit that will be tagged.

## Before you start

Use a clean checkout of the commit to be released, a machine with Python 3.11 or later, a C compiler, Podman and about 20 GB of free disk space. Run heavy steps at the lowest priority and under a memory cap, so they do not disturb other work.

```sh
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
. .venv/bin/activate
```

## The steps

| # | Step | Command | Passes when |
|---|---|---|---|
| 1 | Local CI | `sh scripts/ci.sh` | ruff reports no findings and every test not marked slow passes |
| 2 | Full test suite, slow tests included | `systemd-run --user --scope -q -p MemoryMax=6G -p MemorySwapMax=0 nice -n 19 python3 -m pytest -q tests` | no failures and no errors; skips are listed in the results |
| 3 | Accuracy validation | `sh tools/reftool.sh build` then `sh scripts/validate.sh all` | the last line reports 0 failures; every skipped section is named in the output |
| 4 | Public-text audit | `sh scripts/audit-public.sh` | prints "public-text audit passed" |
| 5 | Quick start in a fresh container | `sh scripts/container-check.sh quickstart` and `sh scripts/container-check.sh selftest`, see [Quick start in a fresh container](#quick-start-in-a-fresh-container) | both exit 0; the Quick start's last terminal line starts with `Result:` and `report/ffmpeg/index.md` opens with it; the self-test writes `report/comparison`; `dsd-measure --version` prints the release version |
| 6 | README two-decoder example | `sh scripts/container-check.sh compare`, see [The two-decoder example](#the-two-decoder-example) | `--plan` lists both devices, the run exits 0 and both device reports and the comparison exist |
| 7 | Plan mode | `dsd-measure run examples/suites/ref.toml --plan` | prints devices, signals, rates, profile and report paths, and measures nothing |
| 8 | Null test smoke run | see [Null test smoke run](#null-test-smoke-run) | the report folder holds `index.html` and `results.json`, and the reference decoder at two rates nulls to more than 140 dB below 18 kHz and more than 100 dB in the 18 to 20 kHz band |
| 9 | Workflow audit | `zizmor .github/workflows` | "No findings to report" |
| 10 | Link check | `python3 scripts/check-links.py` then the [manual links](#links-that-block-automated-clients) | no `BROKEN` line; every `MANUAL` link resolves by hand |
| 11 | Example reports | see [Example reports](#example-reports) | the committed reports carry the release version, the reference-chain conclusions, and the decoder and modulator columns agree |
| 11a | Class A at every output rate | see [Class A at every output rate](#class-a-at-every-output-rate) | the reference decoder at 88.2, 176.4 and 352.8 kHz reads the multitone range of 44.1 kHz (150.7 dB within 1 dB) and a stopband of -120 dB or deeper, with the tones named |
| 11b | A 48 kHz-family device | see [Other device conditions](#other-device-conditions) | impulse (filter, group delay) is "not run" with a reason, as the multitone is |
| 11c | A delayed device | see [Other device conditions](#other-device-conditions) | filter type, ringing, step overshoot and overload recovery equal the aligned device's; polarity right for an inverted one |
| 12 | Version and changelog | `dsd-measure --version` and `grep -n '^## 0' CHANGELOG.md` | the version equals `pyproject.toml` and the top changelog section |

## Class A at every output rate

These steps would have caught the 0.1.1 candidate's multitone and stopband faults above 44.1 kHz.

```sh
python3 -m pytest -q -m slow tests/test_rereview_011.py -k "multitone_range or stopband_tones or not_measurable"
```

The tests run the reference decoder as a class A device at 44.1, 88.2, 176.4 and 352.8 kHz and check the multitone range, the stopband range and the "not measurable" rows of wide-band outputs.

## Other device conditions

```sh
python3 -m pytest -q tests/test_rereview_011.py -k "48k"
python3 -m pytest -q -m slow tests/test_rereview_011.py -k "late_device"
```

The first is a stub that writes 48 kHz PCM. The second runs the reference decoder 300, 1000 and 3000 samples late (and inverted) beside an aligned copy.

## Quick start in a fresh container

The README's Quick start, run from the release tree instead of from GitHub. The container starts from an empty Fedora image, so a missing package in the install line shows up here.

```sh
sh scripts/container-check.sh quickstart
```

The `quickstart` mode installs the committed files of the tree with `pipx`, then runs `dsd-measure --version`, `dsd-measure quick ffmpeg --plan` and `dsd-measure quick ffmpeg`, and checks the last terminal line and the first line of `report/ffmpeg/index.md` for the `Result:` sentence. It takes about three minutes. The `selftest` mode is the older Quick start: `dsd-measure init`, `dsd-measure run suite.toml` and a listing of `report/comparison`, which holds `index.html`, `index.md` and `results.csv`; it takes about five minutes. After the release is public, repeat it once with the README's own line, `pipx install git+https://github.com/dsd-toolbox/dsd-measure`.

## The two-decoder example

The README's worked example measures ffmpeg and the built-in reference decoder with the same signals. FFmpeg comes from the Fedora `ffmpeg-free` package. The numbers it produces are not copied into any committed text.

```sh
sh scripts/container-check.sh compare
```

The script cuts the example's suite out of the README itself, so the README is what is tested. It passes when `--plan` names both devices and the exact ffmpeg command line, the run exits 0, and `report` holds `ffmpeg`, `reference-decoder` and `comparison`.

## Null test smoke run

The null test needs a DSD file. The reference modulator makes one: the multitone signal of a run, as a DSF file.

```sh
dsd-measure signals null-source --only multitone
dsd-measure null --source null-source/multitone.dsf --device reference@352800 --device reference@176400 -o null-report
```

The first device is the baseline. The two devices are the same decoder at two output rates, so the difference is only the extra filtering at 176.4 kHz: `null-report/index.html` shows a null depth of more than 140 dB below 18 kHz, about 104 dB in the 18 to 20 kHz band (the common-rate resampler's edge) and the depth band "d100" (100 dB or more).

## Links that block automated clients

`scripts/check-links.py` fetches every link. The AES library, the AES standards page, ISO and the DOI resolver refuse automated clients (HTTP 403), so the script lists them as `MANUAL`. Open each in a browser, or search for its title and confirm that the page exists and is the cited work, then write "checked by hand" with the date in the results. ITU, Springer and the Aalborg thesis answer automated clients and are checked by the script.

## Example reports

The committed reports in `examples/reference-chain` are regenerated for every release, with the full profile, on a machine that has nothing else running:

```sh
nice -n 19 dsd-measure run examples/suites/ref.toml --profile full -o examples/reference-chain
```

Then check:

- `examples/reference-chain/reference-decoder/index.md` starts with the Conclusions block and "What was measured", and every report folder names the release version.
- The decoder and the modulator are two halves of one chain, so their columns agree: `tests/test_batch_011.py::test_example_columns_agree` compares SINAD, dynamic range, noise and multitone range and fails when they differ by more than their stated limits.
- `sh scripts/audit-public.sh` still passes, because the reports carry paths and names.

## Recording the results

Copy the table, add the commit, the machine (by CPU model), the date and the result of each step, and put it in the release pull request. A failing step is fixed on the branch and the whole plan runs again on the new head, not only the failing step.

## See also

- [Accuracy](accuracy.md): what `scripts/validate.sh` checks.
- [Reference tools](reference-tools.md): the pinned containers used by step 3.
- [Contributing](../CONTRIBUTING.md)
- [Changelog](../CHANGELOG.md)

Part of the [DSD Toolbox](https://github.com/dsd-toolbox/dsd-toolbox).
