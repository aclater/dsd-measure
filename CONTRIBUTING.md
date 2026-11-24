# Contributing

Bug reports, new adapters and new measurements are welcome. Please open an issue first for anything large.

## Set up

```sh
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
PYTHON=.venv/bin/python scripts/ci.sh
```

`scripts/ci.sh` runs the lint (ruff) and the tests under a memory cap when `systemd-run` exists. The same checks run on GitHub in `.github/workflows/ci.yml` (Python 3.11 and 3.13).

## Rules

- Every metric has a known-answer test: a synthetic signal whose result you can state in advance.
- A change that can alter a result bumps `REFERENCE_CHAIN_VERSION` and the changelog.
- Documentation follows the page layout of the existing pages: breadcrumb, one `#` title, a short lead, a See also list.
- Tools whose source you may not read (for example proprietary or restricted decoders) are run as black boxes only; adapters never need their source.
- Update the README and `docs/` in the same pull request.

Part of the [DSD Toolbox](https://github.com/aclater/dsd-toolbox).

## Public-text audit

`scripts/audit-public.sh` checks tracked files and commit identities against a list of
private names that is kept outside the repository. Locally it reads the file named by
`DSDM_PRIVATE_NAMES_FILE` (default `~/.config/dsd-measure/private-names.regex`, mode 0600);
in CI it reads the `PRIVATE_NAMES` repository variable. With no list, or a list it cannot
use, the audit fails.
