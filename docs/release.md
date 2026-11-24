[dsd-measure](../README.md) › [Documentation](README.md) › Release

# Release

How a dsd-measure release is made and checked. The [release test plan](release-test-plan.md) is the gate: every row passes on the exact commit that is tagged, and the tag comes after it.

## Before the tag

1. Run the whole [release test plan](release-test-plan.md) on the commit to be released and record the results.
2. Check that the version in `pyproject.toml`, `dsd-measure --version` and the top section of [the changelog](../CHANGELOG.md) are the same.
3. Tag that commit with an annotated tag, `v` plus the version.
4. Set the pin of the gate action to the commit of the tag. Print it with `git ls-remote https://github.com/dsd-toolbox/dsd-measure 'refs/tags/v0.1.3^{}'` (the tag of the release, with `^{}`), put the 40 hex digits in `examples/ci/gate.yml` and in the workflow of [docs/ci-gate.md](ci-gate.md) (the two must stay equal; `tests/test_ci_gate.py` checks it), and merge that as a docs-only change. A commit cannot contain its own SHA, so the pin always names a release that already exists.
5. Regenerate the facts regions (`docs_facts.py generate`, then `docs_facts.py check`; see the [release test plan](release-test-plan.md#docs-checks)). The install lines in `README.md` and `docs/install.md` name the latest published release; they say `v0.1.2` between the version bump and the tag of 0.1.3, and that is expected.

<!-- docs-audit:begin -->
## After the release: run the docs audit

After the release: run the docs audit. Do it once the tag, the packages and the release notes are public, and before the release is announced.

1. Run the `docs-audit` workflow from the Actions tab of the repository (Run workflow). It runs the docs lint, the link check with external URLs and the docs facts check, and fails if any of them does.
2. Open the checklist it prints: every page that mentions a version, a command-line option or a platform, to compare with the release just published. Fix each mismatch in a docs-only change, or write down why it is right.
3. Record the result in the release notes or the release checklist: the workflow run, and how many checklist items were fixed.

Every project also runs this audit each month (the `docs-monthly` workflow in the DSD Toolbox repository), so a missed audit shows up within a month.
<!-- docs-audit:end -->

## See also

- [Release test plan](release-test-plan.md): the checks that gate the tag.
- [Contributing](../CONTRIBUTING.md)
- [Changelog](../CHANGELOG.md)

Part of the [DSD Toolbox](https://github.com/dsd-toolbox/dsd-toolbox).
