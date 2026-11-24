[dsd-measure](../README.md) › [Documentation](README.md) › Reference tools

# Reference tools

dsd-measure compares its results with a few third-party tools, each run as a black box. This page says what they are, how the containers pin and build them, how to run them and how to check the result.

## The tools

| Tool | What it is for | Licence | Source |
|---|---|---|---|
| SoX-DSD | PCM to DSD with the `sdm` and `clans` modulators, and DSD to PCM | GPL-2.0-or-later | [mansr/sox](https://github.com/mansr/sox), commit `0be259eaa9ce3f3fa587a3ef0cf2c0b9c73167a2` |
| sacd_extract | SACD image to DSF or DSDIFF, the usual extraction reference | GPL-2.0-or-later | [sacd-ripper](https://github.com/sacd-ripper/sacd-ripper), tag `0.3.9.3` (commit `a3d981c935c3224217e2842cd492f9351106c81e`) |
| ffmpeg | Extra DSD to PCM decoder | LGPL-2.1-or-later | Fedora 43 `ffmpeg-free` 7.1.5 |
| SoX (stock) | Resampling and level references | GPL-2.0-or-later | Fedora 43 `sox` 14.4.2 |

Credit: SoX-DSD is Måns Rullgård's DSD work on top of SoX by Chris Bagwell, Lance Norskog and the SoX contributors. It is the tool used for DSD upconversion in many published listening comparisons. sacd_extract comes from the sacd-ripper project, and its 0.3.9.3 release is the enhanced client by euflo. FFmpeg is by the FFmpeg developers.

dsd-measure never copies code from these tools. Each tool is built in its own container and run as a separate program, so the GPL applies to the tool and not to dsd-measure. sacd_extract is also a clean-room boundary: its build system is run unchanged and its source is not read.

## How the images are built

Each image is under `containers/<tool>/Containerfile`. All use Fedora 43 (`registry.fedoraproject.org/fedora:43` to build, `fedora-minimal:43` to run).

| Image | Build | Pin |
|---|---|---|
| `sox-dsd` | autotools, static `sox` binary only, no optional codecs | commit tarball, SHA-256 `795e90314462e4b0f028d731c748d52aa95391688a09c5ef9752d1cddb5b8072` |
| `sacd-extract` | the project's own CMake build in `tools/sacd_extract` | tag tarball, SHA-256 `2f3078041e151dd41156506668e6f158be2be1f2813d26d4ff140761fbe9e72d` |
| `ffmpeg-sox` | distro packages, no build | Fedora 43 repositories |

The build downloads the tarball and stops if the SHA-256 differs. The runtime stage holds only the binary and the libraries it needs, runs as an unprivileged user and has no shell entry point.

Two build notes:

- sacd_extract 0.3.9.3 does not compile with GCC 15 under default flags, because newer compilers treat pointer-type mismatches as errors. The Containerfile relaxes those diagnostics with compiler flags and changes nothing else. The binary is therefore the project's release, built with a current compiler.
- Fedora's `ffmpeg-free` has only the interleaved DSD decoders (`dsd_lsbf`, `dsd_msbf`). It cannot decode DSF, which is planar. Feed ffmpeg DSDIFF (`.dff`) files, or decode DSF with SoX-DSD.

Image identifiers change when an image is rebuilt, because package updates and build times differ. Record the identifiers in `versions.json` for every report.

## Run the tools

The wrapper `tools/reftool.sh` needs rootless Podman. Every run uses `--network=none`, drops all capabilities, mounts the input directory read-only at `/in` and the output directory at `/out`, and keeps the container file system read-only.

Build the images and write the version record:

<!-- docs-run: skip="needs the pinned reference containers (rootless Podman), which a docs-run container cannot start" -->
```sh
tools/reftool.sh build
tools/reftool.sh versions versions.json
```

Make a DSD64 file with each modulator (a 1 kHz, 24-bit, 96 kHz mono WAV in `in/tone.wav`):

<!-- docs-run: skip="needs the pinned reference containers (rootless Podman), which a docs-run container cannot start" -->
```sh
tools/reftool.sh sox-dsd in out /in/tone.wav /out/sdm-8.dsf rate -v 2822400 sdm -f sdm-8 -t 32 -n 32
tools/reftool.sh sox-dsd in out /in/tone.wav /out/clans-8.dsf rate -v 2822400 sdm -f clans-8 -t 32 -n 32
```

Decode DSD back to PCM. ffmpeg needs DSDIFF, so write that first:

<!-- docs-run: skip="needs the pinned reference containers (rootless Podman), which a docs-run container cannot start" -->
```sh
tools/reftool.sh sox-dsd in out /in/tone.wav /out/clans-8.dff rate -v 2822400 sdm -f clans-8 -t 32 -n 32
tools/reftool.sh sox-dsd in out /out/clans-8.dsf -e floating-point -b 32 /out/clans-8.wav rate -v 96000
tools/reftool.sh ffmpeg in out -i /out/clans-8.dff -ar 96000 -c:a pcm_f32le /out/clans-8-ffmpeg.wav
```

Extract the stereo area of an SACD image as DSF (the output directory must exist):

<!-- docs-run: skip="needs the pinned reference containers (rootless Podman), which a docs-run container cannot start" -->
```sh
tools/reftool.sh sacd-extract in out -2 -s -o /out/x -y /out/x -i /in/disc.iso
```

Resample with stock SoX:

<!-- docs-run: skip="needs the pinned reference containers (rootless Podman), which a docs-run container cannot start" -->
```sh
tools/reftool.sh sox in out /in/tone.wav /out/tone-48k.wav rate -v 48000
```

## Verify

Check the pins before trusting a result:

1. `tools/reftool.sh versions` prints the tool versions, source commits and image identifiers. The commits must match the table above.
2. Rebuild from scratch (`podman rmi` the images, then `tools/reftool.sh build`). A changed tarball hash stops the build.
3. Run the tone test below and compare with the expected values.

Tone test: a 5 s, 1 kHz, 24-bit, 96 kHz mono sine at -6 dBFS peak (RMS -9.01 dBFS), converted to DSD64 and back to 96 kHz PCM, measured over the middle 80 % with a Hann-windowed FFT. Run on 2026-11-23 with rootless Podman on a Ryzen AI Max+ 395 (not an isolated timing run, so treat times as indicative).

| Path | Frequency (Hz) | RMS (dBFS) | Encode (s) | Decode (s) |
|---|---:|---:|---:|---:|
| SoX-DSD `sdm-8`, decoded by SoX-DSD | 1000.000 | -15.03 | 23.3 | 0.8 |
| SoX-DSD `sdm-8`, decoded by ffmpeg (DSDIFF) | 1000.000 | -15.03 | 27.0 | 0.8 |
| SoX-DSD `clans-8`, decoded by SoX-DSD | 1000.000 | -15.03 | 27.5 | 0.7 |
| SoX-DSD `clans-8`, decoded by ffmpeg (DSDIFF) | 1000.000 | -15.03 | 28.9 | 0.9 |

The frequency is exact. The level is 6.02 dB below the input in every path, and both decoders agree. SoX-DSD scales its DSD output down by half, which leaves headroom for the modulator, so compare its files at -6 dB or apply `gain 6.02` after decoding. The `sdm-8` run reports `failed to converge` 121 times, `clans-8` 5 times; these are the modulator's own warnings, not errors.

sacd_extract was checked on a synthetic SACD image with stereo and multichannel areas: `-P` prints the disc information and `-2 -s` writes one DSF per track.

## See also

- [Documentation index](README.md)
- [mansr/sox](https://github.com/mansr/sox)
- [sacd-ripper](https://github.com/sacd-ripper/sacd-ripper)

Part of the [DSD Toolbox](https://github.com/dsd-toolbox/dsd-toolbox).
