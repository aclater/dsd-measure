[dsd-measure](../README.md) › [Documentation](README.md) › Install

# Install

dsd-measure is a Python package with a command line tool. It needs Python 3.11 or later and a C compiler, because the reference modulator's inner loop is a small C file built the first time it is used.

## Linux

<!-- docs-run: packages=sudo timeout=1500 -->
```sh
sudo dnf install -y gcc git python3-pip pipx
# facts:install kind=pipx-git repo=dsd-toolbox/dsd-measure
pipx install git+https://github.com/dsd-toolbox/dsd-measure@v0.1.3
# /facts
dsd-measure --version
```

On Debian or Ubuntu use `sudo apt install -y build-essential git python3-pip pipx`. To work on the code, clone the repository and run `python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'`.

## macOS

These steps are for a Mac with Apple Silicon (M1 or later). Open the Terminal app (press Command and Space, type Terminal, press Return). Step 1 installs [Homebrew](https://brew.sh); it asks for your Mac password, may offer to install the Xcode command line tools (click Install; they provide git and the C compiler), and may take several minutes.

<!-- docs-run: skip="macOS commands; run on macOS by the release test plan (docs/release-test-plan.md), not in the Linux container" -->
```sh
curl -fsSL -o install-homebrew.sh https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh
/bin/bash install-homebrew.sh
```

Step 2 tells Terminal where Homebrew is, then installs ffmpeg and pipx:

<!-- docs-run: skip="macOS commands; run on macOS by the release test plan (docs/release-test-plan.md), not in the Linux container" -->
```sh
/opt/homebrew/bin/brew shellenv >> ~/.zprofile
source ~/.zprofile
brew install ffmpeg pipx
pipx ensurepath
```

Close the Terminal window and open a new one. Step 3 installs dsd-measure, runs the quick check and opens its report:

<!-- docs-run: skip="macOS commands; run on macOS by the release test plan (docs/release-test-plan.md), not in the Linux container" -->
```sh
# facts:install kind=pipx-git repo=dsd-toolbox/dsd-measure
pipx install git+https://github.com/dsd-toolbox/dsd-measure@v0.1.3
# /facts
dsd-measure --version
dsd-measure quick ffmpeg
open report/ffmpeg/index.html
```

## Windows

dsd-measure does not run natively on Windows yet; use WSL (the Windows Subsystem for Linux) with Ubuntu. This is written for Windows 11.

Step 1: open the Start menu, type PowerShell, right-click Windows PowerShell, choose Run as administrator, and run:

<!-- docs-run: skip="Windows PowerShell command, run on Windows by the release test plan (docs/release-test-plan.md), not in the Linux container" -->
```powershell
wsl --install -d Ubuntu
```

Restart Windows when it asks. (This first step was not tested as written; the steps after it were, in WSL2 on Windows 11.) After the restart an Ubuntu window opens (or open Ubuntu from the Start menu); it asks you to choose a user name and a password for Linux. Step 2, in the Ubuntu window:

<!-- docs-run: skip="WSL commands; the Ubuntu packages and pipx steps are run on Ubuntu by the release test plan (docs/release-test-plan.md), not in the Fedora container" -->
```sh
sudo apt update
sudo apt install -y build-essential git python3-pip pipx ffmpeg
pipx ensurepath
```

Close the Ubuntu window and open Ubuntu again. Step 3, install dsd-measure, run the quick check and open the report folder in File Explorer (double-click `index.html` there):

<!-- docs-run: skip="WSL commands; run in Ubuntu by the release test plan (docs/release-test-plan.md), not in the Fedora container" -->
```sh
# facts:install kind=pipx-git repo=dsd-toolbox/dsd-measure
pipx install git+https://github.com/dsd-toolbox/dsd-measure@v0.1.3
# /facts
dsd-measure --version
dsd-measure quick ffmpeg
cd report/ffmpeg
explorer.exe .
```

## Optional tools

dsd-measure can measure other converters as black boxes. [Reference tools](reference-tools.md) describes pinned containers for SoX-DSD, sacd_extract and FFmpeg, run with Podman. None is needed for the reference chain.

## See also

- [User guide](user-guide.md)
- [Command line options](options.md)

Part of the [DSD Toolbox](https://github.com/dsd-toolbox/dsd-toolbox).
