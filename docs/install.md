[dsd-measure](../README.md) › [Documentation](README.md) › Install

# Install

dsd-measure is a Python package with a command line tool. It needs Python 3.11 or later and a C compiler, because the reference modulator's inner loop is a small C file built the first time it is used.

## Linux

```sh
sudo dnf install -y gcc git python3-pip pipx
pipx install git+https://github.com/aclater/dsd-measure
dsd-measure --version
```

On Debian or Ubuntu use `sudo apt install -y gcc git python3-pip pipx`. To work on the code, clone the repository and run `python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'`.

## macOS

Install the command line tools with `xcode-select --install`, then `brew install git pipx` and the `pipx install` line above.

## Windows

Use WSL with a Linux distribution and follow the Linux steps. Native Windows is not supported yet.

## Optional tools

dsd-measure can measure other converters as black boxes. [Reference tools](reference-tools.md) describes pinned containers for SoX-DSD, sacd_extract and FFmpeg, run with Podman. None is needed for the reference chain.

## See also

- [User guide](user-guide.md)
- [Command line options](options.md)

Part of the [DSD Toolbox](https://github.com/aclater/dsd-toolbox).
