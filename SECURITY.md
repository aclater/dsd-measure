# Security policy

dsd-measure reads audio files that tools and devices produce and runs commands you give it, so it should be run on data you trust. A suite file's `command` entries run as shell commands with your privileges: only run suite files you trust (see the [user guide](docs/user-guide.md#a-suite-file-is-a-program-only-run-suite-files-you-trust)). The compiled modulator core is built and loaded only from a private per-user cache directory.

## Supported versions

| Version | Security fixes |
|---|---|
| 0.1.x, latest release | Yes |

## Reporting a vulnerability

Do not open a public issue. Use the repository's **Security** tab, **Report a vulnerability**, and include the version, the platform and the files or command that trigger the problem.

## Scope

In scope: the WAV and DSF readers, the adapter code that runs commands, the report writer. Out of scope: the third-party tools you choose to measure.

Part of the [DSD Toolbox](https://github.com/aclater/dsd-toolbox).
