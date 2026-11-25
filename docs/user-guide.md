[dsd-measure](../README.md) › [Documentation](README.md) › User guide

# User guide

How to measure a converter, read the report and fix the usual problems.

## What a run does

The device under test is your converter. The source data is a set of synthetic, deterministic test signals that the toolkit generates itself (tones, two-tone pairs, a multitone, J-Test, impulses and silence; no music). Run `dsd-measure signals --list` for the catalogue, with one plain sentence on what each signal is and why audiophiles care.

| Class | Your device is fed | What is analysed |
|---|---|---|
| A, DSD to PCM | DSD (DSF or DFF) made from the signals by the built-in reference modulator | the PCM your device returns |
| B, PCM to DSD | the signals as 32-bit WAV | the DSD your device returns, decoded to PCM by the built-in reference decoder |

To compare devices, put them in one suite file, one `[[device]]` table each. Every device gets the identical signals and the report folder gets a `comparison` report. The reference chain is the floor: figures within 6 dB of it are marked, because the measurement, not the device, may be the limit.

You choose what is measured with the suite file (devices, `profile`, `in_rate`, `dsd_rate`, `rates`) and `--only TEST`. These synthetic measurements use no music; to compare decoders on your own DSD file use the [null test](#compare-decoders-on-your-own-music).

### See the plan first

Add `--plan` to `run` or `quick`. Nothing is measured; the command prints and exits:

<!-- docs-run: skip="needs suite.toml from dsd-measure init, which no earlier block creates" -->
```sh
dsd-measure run suite.toml --plan
dsd-measure quick reference --plan
```

For each device it shows the class, adapter, the exact command line with `{input}` and `{output}` filled in for one example signal, what the device is fed and what it returns. Then come the signals (name, level, rate, duration), the DSD rates, the profile, an estimated time and where each report goes. The time covers the reference chain only; a slow external tool adds its own run time.

### The run log

Before anything is measured, the pre-flight (see [below](#pre-flight-check)) converts one short signal with each device. Then a run prints one line per test, numbered, with the time left once the first tests have shown how fast the device is (the example is the two-decoder comparison from the README, shortened), and ends with the report path and a one-sentence result:

```text
Pre-flight: ffmpeg converted a 0.5 s test signal: 32-bit float, 352.8 kHz. OK

Device 1 of 2: ffmpeg (class A, DSD to PCM converter, adapter ffmpeg)
[ 1/17] -> ffmpeg: reference_floor (reference chain alone, 1 kHz 0 dB SACD, -60 dB SACD, silence) ... done in 7.6 s, about 1:24 left
[ 2/17] -> ffmpeg: levels (1 kHz tones, +3.1 to -120 dB SACD) ... done in 18.5 s, about 1:08 left
[12/17] -> ffmpeg: stability (long loud tones, 0 dB SACD, +3.1 dB SACD) ... skipped: class B only

Finished in 3.6 min. Report: report/comparison/index.html
Result: in the audio band, ffmpeg and reference decoder measure the same within the tolerance used here. Not compared in this version: filter and ringing.
```

After the report path, one line per device gives its SINAD, its dynamic range and whether it is at the reference floor. The last line, `Result:`, is the same sentence that opens the report; it is the answer in one line. The time left is an estimate from the planned times of the tests still to run, scaled by how long the first tests took.

`-v` adds the device details (command, what it is fed, gain) before each device.

### What was measured

Every report opens with a short "What was measured" block: the device and the exact command it was run with, the adapter, the gain applied and the input and output rates; the source signals with the generator version; the reference chain and its floor; and the profile, date and tool versions. The details (word lengths, SHA-256 hashes of the reference signal files, versions) are collapsed under it. The same block is in `index.md` and in `provenance.json` under `measured`.

## Measure a decoder you have installed

If ffmpeg is installed, one command measures it:

<!-- docs-run: group=quick-start -->
```sh
dsd-measure quick ffmpeg
```

The built-in presets are `ffmpeg`, `dsd2pcm`, `sox-dsd` and `sacd_extract`. Each has a standard command, shown by `--plan`. The `ffmpeg` preset asks for 32-bit float output (`-c:a pcm_f32le`), because ffmpeg writes 16-bit WAV by default and a 16-bit file cannot show a decoder better than about 92 dB (44.1 kHz output) to 101 dB (352.8 kHz) (see [output word length](#output-word-length)). Some builds of ffmpeg read DSD from DFF files but not from DSF files; the pre-flight tries DSF first and, if ffmpeg refuses it, gives ffmpeg DFF files and says so. A preset takes extra arguments after the program name, for example `dsd-measure quick dsd2pcm --args '--filter pysacd'` (in a suite file, `args = "--filter pysacd"`; for the null test, `dsd2pcm:--filter pysacd`). Any other name needs its command:

<!-- docs-run: skip="mytool is a placeholder for a tool the reader has installed" -->
```sh
dsd-measure quick mytool --command 'mytool {input} {output}'
```

`{input}` is the DSF file the tool reads and `{output}` the WAV it must write. An unknown name without `--command` prints this line with the name filled in, and lists the presets.

### Pre-flight check

Before anything is measured, each device converts one 0.5 s test signal. If the program is not installed, the command fails, the output is empty, silent or the wrong length, dsd-measure stops within a second, prints the tool's own error once, writes no report and exits with status 2. A suite with several devices is checked in full before the first one is measured. The pre-flight also reads the output file's word length and sample rate, and records them in the report.

### Output word length

A tool that writes integer PCM adds rounding noise whatever its decoder does. At 352.8 kHz, 16-bit output limits SINAD to about 101.5 dB with plain rounding or 96.8 dB with TPDF dither, and 24-bit output to about 149.7 dB or 144.9 dB; the same decoder reads 146.8 dB when it writes 32-bit float. So the report records the word length, kind and rate of every file the tool wrote ("Output format" in the table and the "What was measured" block) and the two bounds for an integer file. Whether a file was dithered is not detected. When the output is integer of fewer than 32 bits and the measured SINAD lies between 6 dB under the dithered bound and 6 dB over the plain bound, the verdict is "Not judged: output format" and the headline says so, instead of treating the format as a property of the decoder. A comparison does not compare the distortion and noise of such a device. The fix is to ask the tool for floating-point or 32-bit output (for ffmpeg, `-c:a pcm_f32le` before the output file).

## Measure a converter

Pick the class. A DSD to PCM converter (class A) is given DSD files made by the reference modulator and its PCM output is analysed. A PCM to DSD modulator (class B) is given PCM files and its DSD output is decoded by the reference decoder and analysed.

Any command-line tool works through a template with `{input}` and `{output}`:

<!-- docs-run: skip="needs dsd2pcm installed" -->
```sh
dsd-measure quick --command 'dsd2pcm {input} {output}' --class A my-decoder
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
command = "dsd2pcm {input} {output}"

[[device]]
name = "reference decoder"
adapter = "reference"
class = "A"
out_rate = 44100
```

Run it with `dsd-measure run suite.toml` (add `--plan` to see what it would do first). Two or more devices also give a comparison report.

### A suite file is a program: only run suite files you trust

The `command` of a `cli` device is run on your computer with your privileges, exactly as if you had typed it. A suite file from someone else can delete your files or send them away. Read the commands before you run it, and only run suite files you trust.

By default the command is split into words and run directly, without a shell: quotes group words, but pipes, redirects, `&&` and globs have no meaning. To use them set `shell = true` on the device, which runs the command with `/bin/sh -c` (the file names are quoted for you). If you run a pinned container tool through `tools/reftool-file.sh`, the same rule holds.

Only `{input}` and `{output}` are replaced; every other brace, as in `awk '{print $1}'`, is left alone. To write the literal text `{input}` use `{{input}}`. A command that runs longer than `timeout` seconds (default 3600) is stopped together with everything it started.

### Exit status

| Status | Meaning |
|---|---|
| 0 | Everything ran |
| 1 | The report was written, but one or more tests raised an error (for example the tool made no output file); they are listed under "Not run, and why" and on the terminal. Tests skipped on purpose, such as class A only tests on a modulator, do not count. For `null` and for a suite's `[null]` table, the report was written but the alignment of a pair could not be trusted (`run` names the pair on its last lines) |
| 2 | A fatal error and no report: missing or invalid suite file, unknown adapter or converter name, a tool that is not installed or fails its pre-flight, a compiled-core cache that is not private (see below) |
| 130 | Interrupted with Ctrl-C |

Temporary files made for a run are removed when it ends, however it ends. To keep a device's input and output files, set `workdir` on the device.

## Devices you cannot run

For a player or plug-in that cannot be scripted, write the test signals with `dsd-measure signals signals/` (add `--class B` for a modulator; see them described with `dsd-measure signals --list`). This writes every signal a run feeds a device, one file per test (a DSF for class A, a WAV for class B), and `signals.json` with the list, rates and hashes: `sha256` is the SHA-256 of the file (what `sha256sum` prints) and `samples_sha256` is the hash of the sample array it was made from. Feed each file to the device by hand, put the results back under the same name as `<test>.wav` (class A) or `<test>.dsf` (class B) in one folder and use the `import` adapter with `directory = "results"`. It takes about two minutes and 60 MB for class A at the quick profile. The report marks these devices as imported.

## Compare decoders on your own music

The null test answers "do the outputs of these two decoders differ on my music, and by how much?" It decodes one DSD file you supply with two or more decoders, lines the outputs up, subtracts them and reports how far below the music the difference is. It is separate from the synthetic measurements above: it cannot be repeated without your file, and it shows that decoders differ, not which one is right.

Run it on any DSF or DFF file (the file is only read), naming the decoder to compare:

<!-- docs-run: skip="needs a DSD file of the reader's own (track.dsf)" -->
```sh
dsd-measure null track.dsf ffmpeg
xdg-open null-report/index.html
```

When you name one decoder, the built-in reference decoder at 352.8 kHz is the baseline. A decoder is a preset (`ffmpeg`, `dsd2pcm`, `sox-dsd`, `sacd_extract`), `reference@RATE`, `NAME=COMMAND` or the name of a `[[device]]` in `--suite`. A missing tool is reported before the file is read. If a decoder writes 16-bit PCM and the difference sits at its rounding noise, the verdict says that the depth is limited by the output format and gives the ceiling; ask the tool for floating-point output and run again.

To choose the baseline, name two or more decoders, or use the long form:

<!-- docs-run: skip="needs a DSD file of the reader's own (track.dsf)" -->
```sh
dsd-measure null --source track.dsf --device reference@352800 --device reference@176400 --out null-report
```

`reference@352800` is the built-in decoder at 352.8 kHz output. The first device is the baseline; every other device is compared with it. Add a tool with `NAME=COMMAND`, using `{input}` and `{output}` as in the `cli` adapter, and start the command with `dff:` for a tool that reads DFF (the file is converted without changing a bit):

<!-- docs-run: skip="needs a DSD file of the reader's own (track.dsf) and dsd2pcm" -->
```sh
dsd-measure null --source track.dsf --device reference@352800 --device 'dsd2pcm=dsd2pcm {input} {output} --rate 176400' --device 'ffmpeg=dff: ffmpeg -v error -y -i {input} -c:a pcm_f32le {output}' --diff-wav --out null-report
```

The report starts with one line, `Result:`, such as "Difference -161 dB relative to the music (null depth 161 dB): depth band 100 dB or more", then the numbers, three plots and a "What was compared" block with the source file hash, each device's command, rates and the alignment used.

What happens to the outputs before they are subtracted:

- **Rates.** If the devices output different rates, both are brought to the lower one with a Kaiser polyphase resampler (160 dB stopband, flat to 0.45 times the rate). The analysis stops at 0.45 times the common rate. A common rate above either device's own rate is refused, because it would only invent samples, and so is a ratio that is not a small fraction (use `--rate` to pick a simpler common rate).
- **Delay.** Found from the normalised cross-correlation of several loud passages, in the band below (so ultrasonic noise, a level difference or an inverted device does not move the peak), then refined to a fraction of a sample, and applied with a 512-tap windowed-sinc filter. It is reported in samples and microseconds.
- **Level.** A least-squares gain is fitted and reported, so a decoder that is simply louder does not look different. Use `--gain none` to keep levels as they are.
- **Polarity.** An inverted decoder is detected and flipped, and the report says so. Use `--polarity keep` to leave it.
- **Band.** The delay, polarity, gain and the null depth use 20 Hz to 20 kHz only, so a decoder that passes or removes ultrasonic noise does not spoil the match in the audio band. The band is narrower when the devices' passbands are (see below). The bands above it are still shown, and the full-band depth is kept in `results.json` as `null_depth_fullband_db`; it is not the null depth.
- **Passbands.** The tool compares the two devices' spectra at the same frequencies (both decoded the same music), in twelfth-octave bands from 200 Hz to 0.45 times the rate, and looks for a device that is 20 dB or more below the other, relative to the ratio in 200 Hz to 8 kHz, over at least two bands in a row from some frequency above 2 kHz. That frequency is the estimated cut. The departure lasts until the other device's own cut (above it both outputs are noise and the ratio is flat again) or until the top, and where it ends below the top that end is the other device's estimated bandwidth. If the bandwidths differ, the pair is flagged "not like-for-like in band": the report and `results.json` (`trust.not_like_for_like`) give both estimated bandwidths, and alignment and the null depth use the common band, no higher than 20 kHz. When the lower cut is at or above the top of the null band (20 kHz), `trust.null_band_affected` is false, the log and the report give the bandwidths as information, and say that the null band is not affected. Two devices that are cut at the same place are not flagged, and neither are two noise floors that differ where both are far below the music (a band counts only where the stronger device is within 70 dB of its own level in the mid band). The bandwidths are estimates from the music itself: see [methodology limits](methodology-limits.md#null-test-passbands).
- **Trust.** If the in-band correlation of the two outputs after alignment is below 0.5, the log warns, `results.json` has `trust.untrustworthy` with the reason, and the `Result:` line says that the alignment could not be trusted instead of giving a depth band. The report is still written, and `dsd-measure null` exits with status 1 (see [exit status](#exit-status)).
- **Edges.** The first and last 0.5 s are cut (`--trim-start`, `--trim-end`) because decoders start up with a transient. `--start` and `--duration` pick a part of a long track.

Memory use does not depend on the length of the track: a full album track is read, decoded and compared in blocks of about two million samples.

Reading the depth band:

| Null depth | Depth band |
|---|---|
| identical | The two outputs match to floating-point rounding |
| 100 dB or more | Depth band 100 dB or more |
| 80 to 100 dB | Depth band 80 to 100 dB |
| 60 to 80 dB | Depth band 60 to 80 dB |
| 40 to 60 dB | Depth band 40 to 60 dB |
| 20 to 40 dB | Usually different filters or phase (see the bands) |
| under 20 dB | Check the alignment and the level match first |

These bands are plain ranges of depth. They say how far below the music the difference is and make no statement about hearing, which was not tested, for any band: a null test cannot say whether a difference is heard, and the only test of that is a blind listening test (ABX). The report explains this and lists sources for a reader who wants them: [ISO 226:2023](https://www.iso.org/standard/83117.html) for the threshold of hearing in quiet, [Zwicker and Fastl](https://link.springer.com/book/10.1007/978-3-662-09562-1) for masking (not checked by the authors), [Clark 1982](https://aes2.org/publications/elibrary-page/?id=3839) for matching levels before a blind test, [Meyer and Moran 2007](https://www.aes.org/e-lib/browse.cfm?elib=14195) for a blind test of a 16-bit loop and [ITU-R BS.1116](https://www.itu.int/rec/R-REC-BS.1116) for the method (not checked by the authors). A difference is not an error: two correct decoders with different filters differ, mostly above 20 kHz.

To listen to the difference, add `--diff-wav`. The WAV is 32-bit float at the common rate and at its true level, which is usually very quiet but includes any ultrasonic content, so start with the volume at zero. `--diff-gain-db 40` raises it by 40 dB for the WAV only; the numbers never change.

A suite file can hold the same settings in a `[null]` table next to the `[[device]]` tables; see [options](options.md#null-test). Run it with `dsd-measure null --suite suite.toml`.

## Read the report

Open `index.html`. It starts with one sentence, `Result:`, which says whether the device was judged and what its weakest figure measures (the same sentence ends the terminal output and is in `index.md` and `results.json`), then the conclusions (see [below](#reading-the-conclusions)) and what was measured. The row of big numbers (SINAD, dynamic range, noise, filter, ultrasonic noise) and the table under it are the whole result in one screen. Below it are seven key plots, each with one sentence saying what the numbers mean. "Notes" (when present) lists caveats that apply to the numbers, such as which filter a class B row really describes. "More plots" holds the detail, "Not run" lists what was skipped and why, and "Provenance" lists tool versions and file hashes. The same numbers are in `results.csv` and `results.json`, and each plot is a separate SVG in `plots/`.

Some terms:

- **Reference floor**: what the measurement itself cannot see below. A figure marked "at the reference floor" is within 6 dB of it and may be limited by the tool, not the device. At DSD64 the floor is about -147 dB THD+N; use `dsd_rate = 5644800` for class A devices that accept DSD128 and the floor drops to about -176 dB.
- **SINAD** and **THD+N**: how far everything that is not the 1 kHz tone is below it, in dB.
- **Dynamic range**: the noise floor measured with a quiet -60 dB tone, a -60 dB-method figure referred to 0 dB SACD, not the AES17 dynamic range.
- **Multitone distortion-free range**: the range between the tones and the highest residual with 32 tones at once.
- **Ultrasonic noise** (modulators): the shaped noise above 20 kHz; the level is reported, with no verdict.

## Reading the conclusions

Every report starts with a "Conclusions" block of a few sentences. Each sentence is made by a fixed rule from the figures in the report, so the same figures always give the same sentence. "Evidence" under the block lists the figures and thresholds each sentence used; [Conclusions](conclusions.md) gives the rules and the published sources.

A device report says, in this order:

- **The overall figure.** It takes the weakest of SINAD, dynamic range and the two intermodulation tests, in dB below a reference-level tone, and names it. "At least 120 dB down" and "At least 87 dB down" are reference lines from the literature (87 dB is the noise level of dithered 16-bit on this scale, 120 dB a dynamic range that Fielder cites for the most demanding cases, a source not checked against the paper); "Under 87 dB down" is below the lower one. None of the three is a statement about hearing: see [methodology limits](methodology-limits.md).
- **Response and level.** Whether the response is flat (within 0.1 dB), whether gain is unity and the channels match. Match levels before any listening comparison of two devices.
- **At the reference floor.** Which figures are within 6 dB of the tool's own limit. Those show the tool's limit; the tool cannot show more.
- **Image rejection, ultrasonic noise and overload recovery.** The worst image of the alias tones (converters), the noise between 20 and 96 kHz (no verdict: there is no agreed limit) and how long the output takes to settle after a loud burst.
- **Not judged: output format.** Shown instead of a verdict when the file the tool wrote (integer, any word length below 32 bits) may limit the figures; see [output word length](#output-word-length).
- **Not concluded.** Figures that are measured but not validated, or not used by any rule, in this version, such as the filter and ringing, polarity, modulator stability, multitone, the J-Test and the peak-level SINAD (which is shown with the floor of the reference modulator at that level). They are in the table for reference and never reach a verdict.

The report for the built-in reference chain has no verdict. It says that its figures are the measurement floor: a converter within 6 dB of them cannot be ranked by this tool.

A comparison report says whether the devices "measure the same" in the audio band within the tolerance used (every difference is below the floor or 1 dB, a convention: no repeatability interval has been measured yet), whether they "measure differently, but no difference reaches the thresholds", or where they differ by more than the tolerance. It marks no cell as better, ranks nothing and names no winner. Devices measured at different output rates or formats are marked "not like-for-like" and their distortion and noise are not compared. A converter and a modulator in one suite are not compared, because they do different jobs.

Where the literature does not agree on a threshold, for example for the ringing of a linear-phase filter, the sentence says so and gives no verdict. The conclusions cover the synthetic signals and the software path measured; they are not a listening test, and [methodology limits](methodology-limits.md) lists what they cannot claim.

## Stereo, rates and the other tests

Crosstalk and channel match use a stereo pair automatically. For a class B modulator, `rates = [5644800, 11289600]` adds a DSD128 and DSD256 table (THD+N, dynamic range, ultrasonic peak, stability). Class A devices that read DSD128 are measured with `dsd_rate = 5644800`. A recorded analogue path can be imported (see above) and analysed as class A.

## Profiles

`quick` runs every test with shorter signals and 6 dB level steps; `full` follows the footprint (3 dB steps, 15 s noise, 60 s stability holds) and takes much longer; `gate` runs four tests of the quick profile (the reference floor, the level steps, the noise and the alias tones) for a release check. The report always says which one was used. A figure of the gate profile is the same number the quick profile prints, because both use the same signals.

## Speed

Three things make a run fast, and none of them changes a number in the report. Measured times are in [Performance](performance.md).

- **The cache of encoded test signals.** Turning a test signal into DSD with the reference modulator is most of the work of a run, and the result is always the same for the same signal and the same software. Each encoded signal is kept in `~/.cache/dsd-measure/stimuli` and read back by later runs and by every further device of a suite. Signals are encoded in pieces, with the modulator's state carried from piece to piece, so the bits are the same as if the whole signal were encoded at once; a long hold is cached whole, as any other signal, packed at one bit per sample (85 MB for a 60 s hold at DSD256), and checked by its hash when read back. The first run fills the cache; a quick run of the reference chain adds about 90 MiB, a gate run about 30 MiB.
- **Jobs.** The tests of all devices run in parallel worker processes: all cores up to four, then half of them, at most 16. `-j N` (or `jobs = N` in the suite, or `DSD_MEASURE_JOBS`) sets the number; `-j 1` runs one test after the other in a single process. The tests finish out of order on the terminal, and the report is the same as with one job. A quick run of the reference chain needs about 2 GiB of memory with one job, 4 GiB with four and 6 GiB with eight; the full profile needs 7.5 GiB with one job and 15 GiB with eight. The default is lowered when less memory is available, and under the memory or CPU limit of a container or a systemd scope it counts what that limit leaves (80 % of the room below `memory.max`, and the CPUs of `cpu.max`). The long records (the 60 s stability holds, the level steps, the noise records) are made, decoded and analysed in pieces: the memory they need grows by one to two bytes per DSD sample of the record (the bit stream itself, one byte, and a copy of it in some tests), so a 60 s hold at DSD256 peaks at 1.4 GB in one test (see [Performance](performance.md#memory-and-disk)); the job figures above were measured before that change. A device with a `workdir` keeps its tests in one worker, so its numbered files stay in order.
- **The gate profile.** `--profile gate` measures only what a release check compares.

<!-- docs-run: skip="needs suite.toml and runs full-profile measurements; the cache and jobs paths are tested in tests/test_perf.py" -->
```sh
dsd-measure run suite.toml --profile gate
dsd-measure run suite.toml --jobs 2
dsd-measure run suite.toml --no-cache
dsd-measure cache
dsd-measure cache --clear
```

The cache is safe to delete at any time. An entry is named by a hash of everything it depends on: the samples of the signal, the rates, the modulator design, the dsd-measure version, the encoder's source, the NumPy and SciPy versions and the machine type. A change to any of them gives a new name, so an old entry is never read by mistake. Each file carries a checksum that is checked on every read; a damaged file is deleted and the signal is encoded again. The folder is private to you (mode 700) and dsd-measure refuses to use it otherwise, as for the compiled core. When the cached signals pass 4096 MiB the ones read longest ago are deleted first; `DSD_MEASURE_CACHE_MAX_MB` changes the limit and `DSD_MEASURE_CACHE_DIR` moves the folder. `--no-cache` (or `DSD_MEASURE_NO_CACHE=1`) neither reads nor writes it.

### A release gate in CI

To fail a build when a new version of a converter measures worse than the previous one, put both versions in one suite as two devices, run the gate profile, and compare the two device folders:

<!-- docs-run: skip="needs suite.toml and two finished report folders" -->
```sh
dsd-measure run suite.toml --profile gate
dsd-measure gate report/previous report/candidate
```

`dsd-measure gate` prints one row per figure with the old value, the new value and a verdict, and exits with status 1 when a figure is worse than before by more than the measurement's repeatability (the table is in [Command line options](options.md#release-gate)). It compares measured figures, not output bytes, so a converter may change its output and pass. Both versions get the identical signals from the cache, so the encoder runs once.

To keep the cache between CI runs, save and restore the folder `~/.cache/dsd-measure/stimuli` under the name that `dsd-measure cache --key` prints. The name changes exactly when the entries would no longer be read (a new dsd-measure, NumPy or SciPy version, or another machine type), so a restored folder is always usable, and a missing one only makes the run slower.

<!-- docs-run: group=quick-start -->
```sh
dsd-measure cache --key
install -d -m 700 ~/.cache/dsd-measure
```

Make the parent folder before the CI system restores `stimuli` into it, as above: a folder that a restore step creates is open to other users, and dsd-measure refuses a cache that is not private.

## Troubleshooting

- **No C compiler.** Install `gcc` (Linux) or the Xcode command line tools (macOS). Without it the slow Python modulator is used and a run takes hours.
- **"cache directory ... is accessible to others".** The compiled modulator core is built once into `$XDG_CACHE_HOME/dsd-measure` (or `~/.cache/dsd-measure`), and the encoded test signals are kept in its `stimuli` folder. Both must belong to you and not be accessible to anyone else, and the files inside must not be writable by others. dsd-measure refuses to load code from anywhere else. Fix it with `chmod 700 ~/.cache/dsd-measure`, or delete the folder and run again.
- **Out of memory, or the machine is slow during a run.** Use fewer jobs: `--jobs 2`, or `--jobs 1` for one process.
- **A test says "not run".** The reason is in the report. A tool that cannot make a file, or an import folder with a missing file, is reported and the other tests still run.
- **Levels differ by 6.02 dB.** Some tools map WAV full scale to 0 dB SACD. Set `gain_db` on the device to undo it; the gain is recorded in the report.
- **"unknown converter".** `quick` takes a preset (`ffmpeg`, `dsd2pcm`, `sox-dsd`, `sacd_extract`) or any name with `--command`. A DSD file given to `quick` or on its own is answered with the `null` command for it.
- **"... is not on PATH".** The program is not installed (for ffmpeg on Fedora: `sudo dnf install ffmpeg-free`), or give its full path in `--command`.
- **A 16-bit result.** "Not judged: output format": the tool wrote 16-bit PCM; see [output word length](#output-word-length).
- **FLAC output.** Set `output_ext = "flac"` on a `cli` device; ffmpeg converts it for reading.

## See also

- [Command line options](options.md)
- [Performance](performance.md)
- [Conclusions](conclusions.md)
- [Roadmap](roadmap.md)
- [Measurement footprint](footprint.md)

Part of the [DSD Toolbox](https://github.com/dsd-toolbox/dsd-toolbox).
