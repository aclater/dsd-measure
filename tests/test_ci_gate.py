"""The release gate as a GitHub Actions building block: the action, the workflows, the examples and the page
that shows them. None of it needs GitHub: the files are read, and the action's input check is run as the runner runs it."""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from dsd_measure import cli

yaml = pytest.importorskip("yaml")

ROOT = Path(__file__).resolve().parent.parent
ACTION = ROOT / ".github" / "actions" / "gate" / "action.yml"
WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
EXAMPLES = ROOT / "examples" / "ci"
PAGE = (ROOT / "docs" / "ci-gate.md").read_text()
YAML_FILES = [ACTION, *WORKFLOWS, EXAMPLES / "gate.yml"]


def _load(path):
    return yaml.safe_load(path.read_text())


def _steps(doc):
    if "runs" in doc:
        return doc["runs"]["steps"]
    return [s for job in doc["jobs"].values() for s in job.get("steps", [])]


@pytest.mark.parametrize("path", YAML_FILES, ids=lambda p: p.name)
def test_every_action_is_pinned_to_a_full_commit(path):
    for step in _steps(_load(path)):
        ref = step.get("uses")
        if ref is None or ref.startswith("./"):
            continue
        assert re.fullmatch(r"[\w.-]+/[\w./-]+@[0-9a-f]{40}", ref), ref
    text = path.read_text()
    for line in text.splitlines():
        if "uses:" in line and "./" not in line:
            assert re.search(r"#\s*v?\d", line) or "latest dsd-measure release" in line, f"no version comment: {line.strip()}"


@pytest.mark.parametrize("path", [ACTION, *WORKFLOWS, EXAMPLES / "gate.yml"], ids=lambda p: p.name)
def test_no_expression_in_a_script(path):
    for step in _steps(_load(path)):
        assert "${{" not in step.get("run", ""), step.get("name")


@pytest.mark.parametrize("path", [*WORKFLOWS, EXAMPLES / "gate.yml"], ids=lambda p: p.name)
def test_workflows_are_read_only_and_keep_no_credentials(path):
    doc = _load(path)
    assert doc["permissions"] == {"contents": "read"} or path.name == "scorecard.yml"
    assert "pull_request_target" not in (doc.get(True) or doc.get("on"))
    for step in _steps(doc):
        if str(step.get("uses", "")).startswith("actions/checkout@"):
            assert step["with"]["persist-credentials"] is False


def test_the_action_has_its_documented_inputs_and_outputs():
    doc = _load(ACTION)
    assert set(doc["inputs"]) == {"suite", "previous", "candidate", "out", "artifact-name"}
    assert set(doc["outputs"]) == {"result", "report"}
    assert doc["runs"]["using"] == "composite"
    assert all("shell" in s for s in doc["runs"]["steps"] if "run" in s)


def test_the_action_installs_from_its_own_checkout():
    text = ACTION.read_text()
    assert "$GITHUB_ACTION_PATH/../../.." in text
    assert "dsd-measure-ref" not in text
    assert (ACTION.parent / "../../..").resolve() == ROOT and (ROOT / "pyproject.toml").is_file()


def test_the_cache_is_saved_on_the_default_branch_only():
    steps = {s.get("name"): s for s in _load(ACTION)["runs"]["steps"]}
    save = steps["Save the encoded test signals (default branch only)"]
    assert "github.event_name == 'push'" in save["if"] and "default_branch" in save["if"]


def test_the_self_test_asserts_both_outcomes():
    text = (ROOT / ".github" / "workflows" / "gate-selftest.yml").read_text()
    assert 'test "$SAME" = pass' in text and 'test "$WORSE" = fail' in text and 'test "$WORSE_OUTCOME" = failure' in text
    assert "--noise-dbfs" in (ROOT / "tests" / "gate" / "fail.toml").read_text()
    assert "--noise-dbfs" not in (ROOT / "tests" / "gate" / "pass.toml").read_text()


@pytest.mark.parametrize("name", ["gate.yml", "gate.toml", "ffmpeg.toml", "sox.toml"])
def test_the_page_shows_each_example_file_unchanged(name):
    assert (EXAMPLES / name).read_text().rstrip("\n") in PAGE


def test_the_page_is_linked_from_the_indexes():
    for page in ("README.md", "docs/README.md", "docs/options.md"):
        assert "ci-gate.md" in (ROOT / page).read_text(), page
    assert PAGE.startswith("[dsd-measure](../README.md) › [Documentation](README.md) › Use dsd-measure in your project's CI")


# ---- the action's input check, run as the runner runs it

def _check_script():
    step = next(s for s in _load(ACTION)["runs"]["steps"] if s["name"] == "Check the inputs")
    return step["run"]


def _check(tmp_path, **given):
    (tmp_path / "ci").mkdir(exist_ok=True)
    (tmp_path / "ci" / "gate.toml").write_text("")
    env = {**os.environ, "GITHUB_WORKSPACE": str(tmp_path), "SUITE": "ci/gate.toml", "OLD": "previous", "NEW": "candidate",
           "OUT": "quality-gate", "ARTIFACT": "quality-gate", "PATH": str(Path(sys.executable).parent) + os.pathsep + os.environ["PATH"]}
    env.update(given)
    return subprocess.run(["sh", "-e", "-c", _check_script()], env=env, capture_output=True, text=True, cwd=tmp_path)


def test_the_input_check_accepts_the_defaults(tmp_path):
    r = _check(tmp_path)
    assert r.returncode == 0, r.stderr


@pytest.mark.parametrize("bad", [
    {"SUITE": "../gate.toml"}, {"SUITE": "/etc/passwd"}, {"SUITE": "ci/missing.toml"}, {"SUITE": "ci/$(id).toml"},
    {"OUT": "../out"}, {"OUT": "/tmp/out"}, {"OUT": "out;rm"}, {"OLD": "a/b"}, {"NEW": "x y"}, {"OLD": "candidate"},
    {"ARTIFACT": "a b"}, {"ARTIFACT": ""}, {"NEW": "../x"},
])
def test_the_input_check_refuses_with_exit_status_2(tmp_path, bad):
    r = _check(tmp_path, **bad)
    assert r.returncode == 2 and "gate:" in r.stderr, (bad, r.returncode, r.stderr)


def test_the_input_check_refuses_a_suite_that_leaves_the_workspace_through_a_link(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "s.toml").write_text("")
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "link").symlink_to(outside)
    (ws / "ci").mkdir()
    (ws / "ci" / "gate.toml").write_text("")
    env = {**os.environ, "GITHUB_WORKSPACE": str(ws), "SUITE": "link/s.toml", "OLD": "previous", "NEW": "candidate",
           "OUT": "q", "ARTIFACT": "q"}
    r = subprocess.run(["sh", "-e", "-c", _check_script()], env=env, capture_output=True, text=True, cwd=ws)
    assert r.returncode == 2 and "inside the workspace" in r.stderr


# ---- what the page says `dsd-measure gate` does

M = {"analysis_version": 2, "device_class": "A", "dsd_rate": 2822400, "tone_0dbsacd": {"sinad_db": 120.0},
     "noise": {"a_weighted_dbfs": -130.0}}


def _put(tmp_path, name, **changes):
    m = json.loads(json.dumps(M))
    for k, v in changes.items():
        if v is None:
            m.pop(k, None)
        else:
            m[k] = v
    (tmp_path / name).mkdir()
    (tmp_path / name / "results.json").write_text(json.dumps({"metrics": m}))
    return str(tmp_path / name)


def test_gate_exit_status_for_a_figure_that_is_no_longer_measured(tmp_path, capsys):
    old, gone = _put(tmp_path, "old"), _put(tmp_path, "gone", noise=None)
    assert cli.main(["gate", old, gone]) == 1
    assert "no longer measured: Noise 20 Hz-20 kHz, A-weighted" in capsys.readouterr().out


@pytest.mark.parametrize("key,value,what", [("analysis_version", 3, "analysis version"), ("device_class", "B", "device class"),
                                            ("dsd_rate", 5644800, "DSD rate")])
def test_gate_refuses_results_made_under_other_conditions(tmp_path, capsys, key, value, what):
    old, other = _put(tmp_path, "old"), _put(tmp_path, "other", **{key: value})
    assert cli.main(["gate", old, other]) == 2
    assert f"{what} differs" in capsys.readouterr().err


def test_gate_names_every_worse_figure_in_one_readable_last_line(tmp_path, capsys):
    old = _put(tmp_path, "old")
    worse = _put(tmp_path, "worse", tone_0dbsacd={"sinad_db": 100.0}, noise={"a_weighted_dbfs": -100.0})
    assert cli.main(["gate", old, worse]) == 1
    last = capsys.readouterr().out.strip().splitlines()[-1]
    assert last == "FAIL: worse beyond repeatability: SINAD, 1 kHz at 0 dB SACD; Noise 20 Hz-20 kHz, A-weighted"


# ---- review fixes: figures that are not numbers, nothing compared, results without their conditions

def test_gate_treats_a_figure_that_is_not_a_number_as_not_measured():
    from dsd_measure import gate
    old = {"noise": {"a_weighted_dbfs": -130.0}}
    for bad in (float("nan"), float("inf"), float("-inf")):
        rows = {r["key"]: r["verdict"] for r in gate.compare(old, {"noise": {"a_weighted_dbfs": bad}})}
        assert rows["noise.a_weighted_dbfs"] == "missing"
        assert not gate.passed(gate.compare(old, {"noise": {"a_weighted_dbfs": bad}}))
        rows = {r["key"]: r["verdict"] for r in gate.compare({"noise": {"a_weighted_dbfs": bad}}, old)}
        assert rows["noise.a_weighted_dbfs"] == "new"


def test_gate_command_fails_a_nan_figure_in_the_new_result(tmp_path, capsys):
    old = _put(tmp_path, "old")
    (tmp_path / "nan").mkdir()
    (tmp_path / "nan" / "results.json").write_text(json.dumps({"metrics": {**M, "noise": {"a_weighted_dbfs": float("nan")}}}))
    assert cli.main(["gate", old, str(tmp_path / "nan")]) == 1
    assert "no longer measured: Noise 20 Hz-20 kHz, A-weighted" in capsys.readouterr().out


def test_gate_does_not_pass_when_nothing_was_compared(tmp_path, capsys):
    from dsd_measure import gate
    assert not gate.passed(gate.compare({}, {}))
    assert "PASS" not in gate.text(gate.compare({}, {}))
    cond = {k: M[k] for k in ("analysis_version", "device_class", "dsd_rate")}
    for name in ("a", "b"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "results.json").write_text(json.dumps({"metrics": cond}))
    assert cli.main(["gate", str(tmp_path / "a"), str(tmp_path / "b"), "--json", str(tmp_path / "g.json")]) == 2
    cap = capsys.readouterr()
    assert "PASS" not in cap.out and "no gate figure was measured in both results" in cap.err
    assert not (tmp_path / "g.json").exists()


@pytest.mark.parametrize("key", ["analysis_version", "device_class", "dsd_rate"])
def test_gate_refuses_results_that_do_not_record_their_conditions(tmp_path, capsys, key):
    old, other = _put(tmp_path, "old", **{key: None}), _put(tmp_path, "other", **{key: None})
    assert cli.main(["gate", old, other]) == 2
    assert "is not recorded in the old result and the new result" in capsys.readouterr().err
    assert cli.main(["gate", _put(tmp_path, "full"), other]) == 2


def _with_provenance(tmp_path, name, profile="quick", in_rate=88200, out_rate=None, **changes):
    d = Path(_put(tmp_path, name, **changes))
    m = json.loads((d / "results.json").read_text())
    if out_rate:
        m["metrics"]["output_format"] = {"rate": out_rate}
    (d / "results.json").write_text(json.dumps(m))
    (d / "provenance.json").write_text(json.dumps({"profile": profile, "in_rate": in_rate}))
    return str(d)


@pytest.mark.parametrize("other,what", [({"profile": "full"}, "profile differs ('quick' and 'full')"),
                                        ({"in_rate": 176400}, "input rate differs (88200 and 176400)"),
                                        ({"out_rate": 96000}, "output rate differs (88200 and 96000)")])
def test_gate_refuses_runs_made_under_other_settings(tmp_path, capsys, other, what):
    old = _with_provenance(tmp_path, "old", out_rate=88200)
    assert cli.main(["gate", old, _with_provenance(tmp_path, "new", **{"out_rate": 88200, **other})]) == 2
    assert what in capsys.readouterr().err


def test_gate_profile_and_quick_profile_are_comparable(tmp_path, capsys):
    old = _with_provenance(tmp_path, "old", profile="gate")
    assert cli.main(["gate", old, _with_provenance(tmp_path, "new", profile="quick")]) == 0
    assert cli.main(["gate", old, _with_provenance(tmp_path, "gate2", profile="gate")]) == 0
    assert cli.main(["gate", old, _with_provenance(tmp_path, "full", profile="full")]) == 2


def test_gate_without_provenance_checks_only_the_recorded_conditions(tmp_path):
    assert cli.main(["gate", _put(tmp_path, "old"), _with_provenance(tmp_path, "new", profile="full")]) == 0


def test_the_measurement_output_is_printed_with_workflow_commands_switched_off():
    step = ACTION.read_text().split("- name: Measure both versions")[1].split("- name: Compare")[0]
    start, run, end = (step.index(x) for x in ('echo "::stop-commands::$token"', 'dsd-measure run "$SUITE"', 'echo "::$token::"'))
    assert "secrets.token_hex" in step and start < run < end
    assert step.index("::error title=Audio quality gate::the measurement run failed") > end  # the exit-status handling is unchanged
