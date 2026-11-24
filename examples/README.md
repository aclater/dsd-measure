[dsd-measure](../README.md) › Examples

# Examples

Finished reports, made with the `full` profile. Each folder holds one report per device and, for the reference chain, a `comparison` report with the devices side by side. Open `index.html` in a browser; `index.md` is the same summary as text, and `results.csv` and `results.json` hold every number. The separate `plots/` folders are left out here to save space (the HTML pages contain the plots).

| Folder | Devices | Suite |
|---|---|---|
| [reference-chain](reference-chain/comparison/index.md) | the reference decoder (class A) and reference modulator (class B, DSD64, DSD128 and DSD256) | [ref.toml](suites/ref.toml) |

The reference device is the measurement floor itself, so its rows are marked "at the reference floor". Third-party tools (SoX-DSD, ffmpeg-free, sacd_extract) run as black boxes from the pinned containers in [tools/reftool.sh](../tools/reftool.sh); [dec.toml](suites/dec.toml) and [sox.toml](suites/sox.toml) are ready-made suites for decoders and for SoX-DSD. [quick-start.toml](suites/quick-start.toml) is what `dsd-measure init` writes.

Part of the [DSD Toolbox](https://github.com/aclater/dsd-toolbox).
