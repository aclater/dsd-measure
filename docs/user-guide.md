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

You choose what is measured with the suite file (devices, `profile`, `in_rate`, `dsd_rate`, `rates`) and `--only TEST`. You cannot yet bring your own music; a [real-music difference test](roadmap.md) is planned.

### See the plan first

Add `--plan` to `run` or `quick`. Nothing is measured; the command prints and exits:

```sh
dsd-measure run suite.toml --plan
dsd-measure quick reference --plan
```

For each device it shows the class, adapter, the exact command line with `{input}` and `{output}` filled in for one example signal, what the device is fed and what it returns. Then come the signals (name, level, rate, duration), the DSD rates, the profile, an estimated time and where each report goes. The time covers the reference chain only; a slow external tool adds its own run time.

### The run log

A run prints one line per test (the example is the two-decoder comparison from the README, shortened), then the report path:

```text
Device 1 of 2: ffmpeg (class A, DSD to PCM converter, adapter cli)
-> ffmpeg: reference_floor (reference chain alone, 1 kHz 0 dB SACD, -60 dB SACD, silence) ... done in 7.6 s
-> ffmpeg: levels (1 kHz tones, +3.1 to -120 dB SACD) ... done in 18.5 s
-> ffmpeg: stability (long loud tones, 0 dB SACD, +3.1 dB SACD) ... skipped: class B only

Finished in 3.6 min. Report: report/comparison/index.html
```

After the report path, one line per device gives its SINAD, its dynamic range and whether it is at the reference floor.

`-v` adds the device details (command, what it is fed, gain) before each device.

### What was measured

Every report opens with a short "What was measured" block: the device and the exact command it was run with, the adapter, the gain applied and the input and output rates; the source signals with the generator version; the reference chain and its floor; and the profile, date and tool versions. The details (word lengths, SHA-256 hashes of the reference signal files, versions) are collapsed under it. The same block is in `index.md` and in `provenance.json` under `measured`.

## Measure a converter

Pick the class. A DSD to PCM converter (class A) is given DSD files made by the reference modulator and its PCM output is analysed. A PCM to DSD modulator (class B) is given PCM files and its DSD output is decoded by the reference decoder and analysed.

Any command-line tool works through a template with `{input}` and `{output}`:

```sh
dsd-measure quick --command 'dsd2pcm {input} -o {output}' --class A my-decoder
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
command = "dsd2pcm {input} -o {output}"

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
| 1 | The report was written, but one or more tests raised an error (for example the tool made no output file); they are listed under "Not run, and why" and on the terminal. Tests skipped on purpose, such as class A only tests on a modulator, do not count |
| 2 | A fatal error and no report: missing or invalid suite file, unknown adapter, a tool that is not installed, a compiled-core cache that is not private (see below) |
| 130 | Interrupted with Ctrl-C |

Temporary files made for a run are removed when it ends, however it ends. To keep a device's input and output files, set `workdir` on the device.

## Devices you cannot run

For a player or plug-in that cannot be scripted, write the test signals with `dsd-measure signals signals/` (add `--class B` for a modulator; see them described with `dsd-measure signals --list`). This writes every signal a run feeds a device, one file per test (a DSF for class A, a WAV for class B), and `signals.json` with the list, rates and hashes. Feed each file to the device by hand, put the results back under the same name as `<test>.wav` (class A) or `<test>.dsf` (class B) in one folder and use the `import` adapter with `directory = "results"`. It takes about two minutes and 60 MB for class A at the quick profile. The report marks these devices as imported.

## Compare decoders on your own music

The null test answers "do the outputs of these two decoders differ on my music, and by how much?" It decodes one DSD file you supply with two or more decoders, lines the outputs up, subtracts them and reports how far below the music the difference is. It is separate from the synthetic measurements above: it cannot be repeated without your file, and it shows that decoders differ, not which one is right.

Run it on any DSF or DFF file (the file is only read):

```sh
dsd-measure null --source track.dsf --device reference@352800 --device reference@176400 --out null-report
xdg-open null-report/index.html
```

`reference@352800` is the built-in decoder at 352.8 kHz output. The first device is the baseline; every other device is compared with it. Add a tool with `NAME=COMMAND`, using `{input}` and `{output}` as in the `cli` adapter, and start the command with `dff:` for a tool that reads DFF (the file is converted without changing a bit):

```sh
dsd-measure null --source track.dsf --device reference@352800 --device 'dsd2pcm=dsd2pcm {input} {output} --rate 176400' --device 'ffmpeg=dff: ffmpeg -v error -y -i {input} -c:a pcm_f32le {output}' --diff-wav --out null-report
```

The report starts with one line of verdict, such as "Difference -161 dB relative to the music (null depth 161 dB): far below audibility", then the numbers, three plots and a "What was compared" block with the source file hash, each device's command, rates and the alignment used.

What happens to the outputs before they are subtracted:

- **Rates.** If the devices output different rates, both are brought to the lower one with a Kaiser polyphase resampler (160 dB stopband, flat to 0.45 times the rate). The analysis stops at 0.45 times the common rate. A common rate above either device's own rate is refused, because it would only invent samples, and so is a ratio that is not a small fraction (use `--rate` to pick a simpler common rate).
- **Delay.** Found from the cross-correlation of several loud passages, then refined to a fraction of a sample, and applied with a 512-tap windowed-sinc filter. It is reported in samples and microseconds.
- **Level.** A least-squares gain is fitted and reported, so a decoder that is simply louder does not look different. Use `--gain none` to keep levels as they are.
- **Polarity.** An inverted decoder is detected and flipped, and the report says so. Use `--polarity keep` to leave it.
- **Band.** The gain, delay and verdict use 20 Hz to 20 kHz only, so a decoder that passes or removes ultrasonic noise does not spoil the match in the audio band. Ultrasonic bands are still shown.
- **Edges.** The first and last 0.5 s are cut (`--trim-start`, `--trim-end`) because decoders start up with a transient. `--start` and `--duration` pick a part of a long track.

Memory use does not depend on the length of the track: a full album track is read, decoded and compared in blocks of about two million samples.

Reading the verdict:

| Null depth | Verdict |
|---|---|
| identical | The two outputs match to floating-point rounding |
| 100 dB or more | Far below audibility |
| 80 to 100 dB | Well below audibility |
| 60 to 80 dB | Below audibility in normal listening |
| 40 to 60 dB | A shallow null: a difference this size can be heard on revealing music, but a null test cannot say whether it can; listen blind |
| 20 to 40 dB | A deep difference, usually different filters or phase (see the bands); a null test cannot say whether it is audible; listen blind (ABX) |
| under 20 dB | A large difference: check the alignment and the level match first |

These tiers are rules of thumb, not a psychoacoustic model; the report explains them and links its sources: [ISO 226](https://www.iso.org/standard/34222.html) for the threshold of hearing in quiet, [Zwicker and Fastl](https://link.springer.com/book/10.1007/978-3-662-09562-1) for masking, [Clark 1982](https://aes2.org/publications/elibrary-page/?id=3839) for matching levels before a blind test, [Meyer and Moran 2007](https://www.aes.org/e-lib/browse.cfm?elib=14195) for a blind test of a 16-bit loop and [ITU-R BS.1116](https://www.itu.int/rec/R-REC-BS.1116) for the method. A small difference is not an error: two correct decoders with different filters differ, mostly above 20 kHz.

To listen to the difference, add `--diff-wav`. The WAV is 32-bit float at the common rate and at its true level, which is usually very quiet but includes any ultrasonic content, so start with the volume at zero. `--diff-gain-db 40` raises it by 40 dB for the WAV only; the numbers never change.

A suite file can hold the same settings in a `[null]` table next to the `[[device]]` tables; see [options](options.md#null-test). Run it with `dsd-measure null --suite suite.toml`.

## Read the report

Open `index.html`. It starts with the conclusions (see [below](#reading-the-conclusions)) and what was measured. The row of big numbers (SINAD, dynamic range, noise, filter, ultrasonic noise) and the table under it are the whole result in one screen. Below it are seven key plots, each with one sentence saying what the numbers mean. "Notes" (when present) lists caveats that apply to the numbers, such as which filter a class B row really describes. "More plots" holds the detail, "Not run" lists what was skipped and why, and "Provenance" lists tool versions and file hashes. The same numbers are in `results.csv` and `results.json`, and each plot is a separate SVG in `plots/`.

Some terms:

- **Reference floor**: what the measurement itself cannot see below. A figure marked "at the reference floor" is within 6 dB of it and may be limited by the tool, not the device. At DSD64 the floor is about -147 dB THD+N; use `dsd_rate = 5644800` for class A devices that accept DSD128 and the floor drops to about -176 dB.
- **SINAD** and **THD+N**: how far the unwanted sound is below a 1 kHz tone. 100 dB or more is excellent.
- **Dynamic range**: the noise floor measured with a quiet -60 dB tone, the usual "DR" figure.
- **Multitone distortion-free range**: how clean the output stays with 32 tones at once.
- **Ultrasonic noise** (modulators): the shaped noise above 20 kHz, which is normal for DSD but should be low and steady.

## Reading the conclusions

Every report starts with a "Conclusions" block of a few sentences. Each sentence is made by a fixed rule from the figures in the report, so the same figures always give the same sentence. "Evidence" under the block lists the figures and thresholds each sentence used; [Conclusions](conclusions.md) gives the rules and the published sources.

A device report says, in this order:

- **The overall verdict.** It takes the weakest of SINAD, dynamic range and the two intermodulation tests, in dB below a reference-level tone, and names it. "Transparent" means at least 120 dB down, beyond the range of hearing. "Inaudible in normal listening" means at least 87 dB down, quieter than the noise of a CD. "Audible risk" means less than that: it may or may not be heard, so listen for yourself.
- **Response and level.** Whether the response is flat (within 0.1 dB), whether gain is unity and the channels match. A level difference matters when you compare two devices by ear: match levels first.
- **At the reference floor.** Which figures are within 6 dB of the tool's own limit. Those show the tool's limit; the device is at least that good.
- **Image rejection, ultrasonic noise and overload recovery.** The worst image of the alias tones (converters), the noise between 20 and 96 kHz (no verdict: there is no agreed limit) and how long the output takes to settle after a loud burst.
- **Not concluded.** Figures that are measured but not validated, or not used by any rule, in this version, such as the filter and ringing, polarity, modulator stability, multitone, the J-Test and the peak-level SINAD (which is shown with the floor of the reference modulator at that level). They are in the table for reference and never reach a verdict.

The report for the built-in reference chain has no verdict. It says that its figures are the measurement floor: a converter within 6 dB of them cannot be ranked by this tool.

A comparison report says whether the devices are "indistinguishable by measurement" (every difference is below the floor or the thresholds), whether they "measure differently, but no difference reaches the audibility thresholds" (a technical difference), or where they differ in a way that may matter. It never names a winner. A converter and a modulator in one suite are not compared, because they do different jobs.

Where research does not agree, for example on whether the ringing of a linear-phase filter is audible, the sentence says so and gives no verdict. The conclusions cover the synthetic signals and the software path measured; they are not a listening test.

## Stereo, rates and the other tests

Crosstalk and channel match use a stereo pair automatically. For a class B modulator, `rates = [5644800, 11289600]` adds a DSD128 and DSD256 table (THD+N, dynamic range, ultrasonic peak, stability). Class A devices that read DSD128 are measured with `dsd_rate = 5644800`. A recorded analogue path can be imported (see above) and analysed as class A.

## Profiles

`quick` takes a few minutes and uses shorter signals and 6 dB level steps; `full` follows the footprint (3 dB steps, 15 s noise, 60 s stability holds) and takes much longer. The report always says which one was used.

## Troubleshooting

- **No C compiler.** Install `gcc` (Linux) or the Xcode command line tools (macOS). Without it the slow Python modulator is used and a run takes hours.
- **"cache directory ... is accessible to others".** The compiled modulator core is built once into `$XDG_CACHE_HOME/dsd-measure` (or `~/.cache/dsd-measure`), which must belong to you and not be accessible to anyone else, and the library inside must not be writable by others. dsd-measure refuses to load code from anywhere else. Fix it with `chmod 700 ~/.cache/dsd-measure`, or delete the folder and run again.
- **A test says "not run".** The reason is in the report. A tool that cannot make a file, or an import folder with a missing file, is reported and the other tests still run.
- **Levels differ by 6.02 dB.** Some tools map WAV full scale to 0 dB SACD. Set `gain_db` on the device to undo it; the gain is recorded in the report.
- **FLAC output.** Set `output_ext = "flac"` on a `cli` device; ffmpeg converts it for reading.

## See also

- [Command line options](options.md)
- [Conclusions](conclusions.md)
- [Roadmap](roadmap.md)
- [Measurement footprint](footprint.md)
- [Design](design.md)
- [Roadmap](roadmap.md)

Part of the [DSD Toolbox](https://github.com/aclater/dsd-toolbox).
