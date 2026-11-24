[dsd-measure](../README.md) › [Documentation](README.md) › Use dsd-measure in your project's CI

# Use dsd-measure in your project's CI

A converter can get worse without any test failing: a new filter, a changed dither or a different word length moves the measured figures. This page shows how to run dsd-measure's release gate on every pull request and push, so a figure that gets worse beyond the measurement's repeatability fails the build.

The policy the gate implements is: every pull request and every push to the main branch measures the new build against the previous release, and fails when a figure is worse. The bytes of the converter's output may change; quality is judged on the measured figures. Within one release the output stays deterministic.

## What the gate checks

`dsd-measure gate` compares the figures of two device reports one by one and exits with status 1 when a figure of the new build is worse than the old one by more than its repeatability, or was measured before and is not now. The figures, the direction that counts as better and the repeatability of each are in the table of [Command line options](options.md#release-gate); the measured spread behind them is in [Accuracy](accuracy.md#repeatability).

What it does not check:

- **Bytes.** Two outputs that differ bit for bit pass when every figure is the same or better.
- **Anything it does not measure.** The gate profile runs four tests (see the [user guide](user-guide.md#speed)). A change that only shows in another test, such as the frequency response or a rate other than the one in the suite, is not seen.
- **Small changes.** A figure that moves by less than its repeatability is "same". That is the point of the repeatability, and it is also the size of regression the gate cannot see. Two figures have repeatabilities of one step: the lowest level within 0.5 dB (6.1 dB, one step of the level ladder) and the worst alias image (6.0 dB). A change of those two that is smaller than a step is "same"; see the [table](options.md#release-gate).
- **Music.** The test signals are synthetic. [`dsd-measure null`](user-guide.md#compare-decoders-on-your-own-music) compares decoders on your own files.

## The workflow

The 40 zeros after `@` in the workflow below stand for the commit to pin: replace them with the commit of a dsd-measure release (see [Pin the action](#pin-the-action)). The action first ships in dsd-measure 0.1.3. To print the commit of that release once its tag exists:

<!-- docs-run: skip="needs the release tag to exist" -->
```sh
git ls-remote https://github.com/dsd-toolbox/dsd-measure 'refs/tags/v0.1.3^{}'
```

The release tag is an annotated tag; the `^{}` makes the command print the commit that the tag points to, which is the one to pin (without it the command prints the tag object).

Copy two files into your repository: the workflow `.github/workflows/gate.yml` and the suite `ci/gate.toml`. The example is for a DSD to PCM converter that you build from source with Cargo; change the two build steps and the two `command` lines for your own tool.

<!-- docs-run: skip="a GitHub Actions workflow, not a command" -->
```yaml
name: Quality gate

on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read

concurrency:
  group: quality-gate-${{ github.ref }}
  cancel-in-progress: true

jobs:
  quality-gate:
    name: Audio quality gate
    runs-on: ubuntu-24.04
    timeout-minutes: 30
    steps:
      - name: Check out this commit
        uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
      - name: Check out the previous release
        uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          ref: PREVIOUS_TAG
          path: previous
          persist-credentials: false
      - uses: actions/setup-python@6d4fd22b20465ccc0f7354476588e8df7c9ca0e0 # v7.1.0
        with:
          python-version: "3.13"
      - name: Build the previous release
        run: cargo build --release --locked --manifest-path previous/Cargo.toml
      - name: Build this commit
        run: cargo build --release --locked
      - name: Measure both and compare
        uses: dsd-toolbox/dsd-measure/.github/actions/gate@0000000000000000000000000000000000000000 # the commit of the latest dsd-measure release, see "Pin the action"
        with:
          suite: ci/gate.toml
```

<!-- docs-run: skip="a suite file for the workflow above" -->
```toml
[suite]
name = "release gate"
in_rate = 88200

[[device]]
name = "previous"
adapter = "cli"
class = "A"
command = "previous/target/release/CONVERTER {input} {output}"

[[device]]
name = "candidate"
adapter = "cli"
class = "A"
command = "target/release/CONVERTER {input} {output}"
```

Two words are yours to set. `PREVIOUS_TAG` is the tag of your previous release (for example `v1.4.0`). `CONVERTER` is the file name of your converter's program. The converter must take the input file and the output file as its two arguments, as `{input}` and `{output}` stand for them; see the `cli` adapter in [Command line options](options.md#suite-file) for the other forms.

The workflow runs `ci/gate.toml` with the gate profile, compares the device `previous` with the device `candidate`, writes the table into the job summary, and uploads the report folder as an artifact. A job that builds two versions needs no more than the steps above; the action is a composite action, not a reusable workflow, because your build steps and the measurement must run in the same job on the same runner.

### Inputs and outputs of the action

| Input | Default | Meaning |
|---|---|---|
| `suite` | required | The suite file, relative to the workspace |
| `previous` | `previous` | Name of the device that is the previous release |
| `candidate` | `candidate` | Name of the device that is the new build |
| `out` | `quality-gate` | Report folder, relative to the workspace |
| `artifact-name` | `quality-gate` | Name of the uploaded artifact; give each gate job of one workflow run its own |

Device names may hold letters, digits, dash and underscore only. The action refuses anything else, a suite or folder outside the workspace and a path with `..`, with exit status 2.

| Output | Meaning |
|---|---|
| `result` | `pass`, `fail` (a figure is worse or no longer measured, exit status 1) or `error` (the run could not complete, exit status 2) |
| `report` | The report folder |

### What the runner needs

- **Python 3.11 or later with `venv`.** Set it up before the action, as the example does. The action installs dsd-measure into its own virtual environment in the runner's temporary folder, so it works with the system Python of an Ubuntu runner and changes nothing else. A converter command that starts `python3` finds that environment's Python first while the measurement runs.
- **A C compiler named `cc`.** dsd-measure compiles a small core on first use. Ubuntu and macOS runners have one.
- **Memory.** The gate profile of two devices peaked at 3.4 GiB with four jobs when it was measured (see [Performance](performance.md#memory-and-disk)). The figure the run plans with is higher, 1.6 GiB plus 0.6 GiB per job, which is 4.0 GiB for four jobs; the default number of jobs is lowered when less memory is available than that.
- **Network.** pip downloads NumPy, SciPy and Matplotlib, and the cache service restores the cache. Nothing else is fetched. The pin of the action fixes dsd-measure itself; these three packages are installed from PyPI at their current versions, so the pin does not cover them.

This repository's own workflow (`gate-selftest`) runs the action on `ubuntu-24.04` and `macos-15` for every pull request and push. How long a gate takes on a hosted runner has not been measured yet; the times in [Performance](performance.md) are from a desktop machine.

## Choose OLD and NEW

- **OLD is the previous release as your users install it.** A release binary, a package at its version or a build of the previous tag. Do not use the previous commit of the branch: the gate would then only ever compare one step, and many small losses add up unseen.
- **NEW is the build of this commit.**
- **Same suite, same settings.** Both devices are in one suite file, so they get the same signals, the same DSD rate and the same profile. Give both the same output rate and word length: a converter that writes a different format measures differently, and a change of format is a change the gate should show.
- **Same job, same runner.** The two builds run one after the other on one machine, so the machine's speed or load cannot differ between them.
- **The first release.** There is no previous release to compare with, so there is no gate yet. Release as usual, then add the workflow with that release as `PREVIOUS_TAG`.
- **Move OLD at each release.** After a release, change `PREVIOUS_TAG` to the new tag in the same commit that prepares the next version. A quality loss that was accepted for a release (see below) is then the baseline of the next one.

## Read a failure

The job summary shows the table. A row looks like this:

```text
Figure                                previous  candidate   change  repeatability       verdict
SINAD, 1 kHz at 0 dB SACD              146.645    101.425  -45.220            0.6         worse
```

`change` is the new value minus the old one, in dB. `repeatability` is the largest difference two runs of the same converter show from noise alone. `worse` means the new build is worse by more than that; `same` means it moved less; `better` means it improved by more than that; `missing` means the figure was measured for the previous release and not for the new build, or is NaN or infinite in the new one (the gate fails on it); `not measured` means neither has it. The last line says `PASS` or `FAIL` and names the figures.

The exit status tells why the job failed:

| Status | Meaning |
|---|---|
| 1 | A figure is worse beyond its repeatability or is no longer measured. The `result` output is `fail`. |
| 2 | The gate could not run: a bad suite file, a missing tool, a refused comparison (different analysis version, device class, DSD rate, input rate, output rate or profile, a result that does not record them, or no figure measured in both) or a bad input. The `result` output is `error`. |

When the gate fails:

1. Download the artifact `quality-gate`. It holds `gate.txt`, `gate.json` and, for each device, the full report with plots (`previous/index.html`, `candidate/index.html`) and the comparison.
2. Reproduce it on your machine with the same two commands: `dsd-measure run ci/gate.toml --profile gate -o quality-gate`, then `dsd-measure gate quality-gate/previous quality-gate/candidate`.
3. Open the report of the candidate and look at the test behind the worse figure (for instance the noise test for a noise figure).
4. Fix the converter, or, when the change is intended, say so where your users will read it (your changelog) and move OLD at the next release. Do not make the gate pass by changing the figures.

`--scale X` multiplies every repeatability by X. A scale above 1 makes the gate blind to the losses between 1 and X times the repeatability, for every figure at once, and the action does not offer it. Use it on the command line to find out how far a figure moved, not to turn a failing job green.

## How the cache keeps it fast

Most of a run is encoding the test signals with the reference modulator, and the encoded signals are the same for every run of the same dsd-measure. The action keeps them in the runner's cache, under a name that `dsd-measure cache --key` prints. The name changes exactly when the entries could no longer be read (another dsd-measure, NumPy or SciPy, or another machine type), so a restored cache is always usable and a missing one only makes the run slower. Both devices of a run read the same cached signals.

What a restored cache can and cannot do:

- Each entry holds the SHA-256 of its content, and dsd-measure checks it on every read; a short, altered or foreign file is deleted and encoded again. This protects against damage, not against someone who can write the cache: a writer can make a file with a matching checksum.
- The folder must be private to the user; dsd-measure refuses to use it otherwise. The action creates it with mode 700 and sets the mode again after the restore.
- GitHub scopes caches by branch. A pull request restores caches of its own merge ref and of the base branch, and writes only its own; it cannot write the cache of the default branch. The action saves the cache only for a push to the default branch, so a pull request, including one from a fork, never writes a cache that another run restores. Whoever can push to the default branch, or run a workflow there, can write it; that is the same trust your build already needs.
- Entries are named by a hash of the signal, so a wrong entry would be a wrong stimulus, not code that runs: the files are read as data.

The first pull request after a change to the suite file, a new dsd-measure or a new runner image runs without a restored cache until the default branch has saved one.

## Pin the action

Pin the action by the full commit SHA of a dsd-measure release and never by a branch or a tag: a tag can be moved. The workflow above carries 40 zeros where the SHA goes. The one pin also fixes the tool, because the action installs dsd-measure from its own checkout. Read what the checkout holds: the runner downloads the whole repository at the pinned ref into its `_actions` folder, and GitHub documents `github.action_path` as the way to reach files in the same repository as the action; the action installs from `$GITHUB_ACTION_PATH/../../..`, the root of that checkout.

The action first ships with dsd-measure 0.1.3. A commit cannot contain its own SHA, so the example in the repository names the commit of a release only after that release is tagged: the [release steps](release.md) set it then, and until it is set the example carries 40 zeros. The command that prints the commit of a release tag is the one above the workflow.

Update the pin when you want a new dsd-measure: change the SHA (and, if you track it, the version in the comment) in the workflow. A new dsd-measure can change what the gate profile measures; the gate then refuses to compare results of different analysis versions, which is why both devices are always measured in the same job.

## Worked examples

Both suites compare the tool you have now with the one you are about to install, with the same arguments, in the same suite. Put the old program in `previous/` and the new one in `candidate/`.

### ffmpeg

Compare the ffmpeg you ship with the one you are upgrading to. The output is 32-bit float on purpose: ffmpeg writes 16-bit by default, which would measure the file format and not the decoder.

<!-- docs-run: skip="needs two ffmpeg builds in previous/ and candidate/" -->
```toml
[suite]
name = "ffmpeg gate"
in_rate = 88200

[[device]]
name = "previous"
adapter = "ffmpeg"
class = "A"
command = "previous/ffmpeg -v error -y -i {input} -c:a pcm_f32le {output}"

[[device]]
name = "candidate"
adapter = "ffmpeg"
class = "A"
command = "candidate/ffmpeg -v error -y -i {input} -c:a pcm_f32le {output}"
```

<!-- docs-run: skip="runs the suite above" -->
```sh
dsd-measure run ffmpeg.toml --profile gate -o report
dsd-measure gate report/previous report/candidate
```

This was run here with the same ffmpeg 9.0.2 binary as both devices: every figure is "same" and the exit status is 0. With `-c:a pcm_s16le` in the candidate's command instead, every noise and distortion figure is worse (SINAD at 0 dB SACD 146.645 against 101.425 dB, in the 16-bit rounding noise) and the exit status is 1. That is the gate working as intended: a change of word length is a change of quality.

### SoX

The same suite for SoX with DSD support (`sox-dsd` is the adapter name, the program is `sox`).

<!-- docs-run: skip="needs two SoX builds in previous/ and candidate/" -->
```toml
[suite]
name = "SoX gate"
in_rate = 88200

[[device]]
name = "previous"
adapter = "sox-dsd"
class = "A"
command = "previous/sox {input} -b 32 -e floating-point {output} rate -v 352800"

[[device]]
name = "candidate"
adapter = "sox-dsd"
class = "A"
command = "candidate/sox {input} -b 32 -e floating-point {output} rate -v 352800"
```

This suite has not been run: SoX was not installed where this page was written. The command is the `sox-dsd` preset's own, with the program path changed, and the run and the comparison are the same two commands as for ffmpeg.

## See also

- [Command line options](options.md#release-gate): the gate command, its figures and repeatability
- [User guide](user-guide.md#speed): the gate profile, the cache and jobs
- [Accuracy](accuracy.md#repeatability): how the repeatability was measured
- [Performance](performance.md): run times and memory

Part of the [DSD Toolbox](https://github.com/dsd-toolbox/dsd-toolbox).
