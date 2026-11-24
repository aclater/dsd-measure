"""scripts/audit-public.sh reads its private-names list from outside the repository and fails closed."""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "audit-public.sh"
DUMMY = "zzplantedzz"


def git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    (r / "scripts").mkdir(parents=True)
    shutil.copy(SCRIPT, r / "scripts" / "audit-public.sh")
    (r / "README.md").write_text("clean text\n")
    git(r, "init", "-q")
    git(r, "config", "user.name", "Tester")
    git(r, "config", "user.email", "tester@example.org")
    git(r, "add", "-A")
    git(r, "commit", "-qm", "init")
    return r


def run(repo, tmp_path, names=None, mode=0o600, env_names=None, file_path=None):
    env = {k: v for k, v in os.environ.items() if k not in ("PRIVATE_NAMES", "DSDM_PRIVATE_NAMES_FILE")}
    env["HOME"] = str(tmp_path / "home")
    if names is not None:
        f = tmp_path / "names.regex"
        f.write_text(names)
        f.chmod(mode)
        env["DSDM_PRIVATE_NAMES_FILE"] = str(f)
    if file_path is not None:
        env["DSDM_PRIVATE_NAMES_FILE"] = str(file_path)
    if env_names is not None:
        env["PRIVATE_NAMES"] = env_names
    return subprocess.run(["sh", str(repo / "scripts" / "audit-public.sh")], env=env,
                          capture_output=True, text=True)


def test_clean_tree_passes(repo, tmp_path):
    r = run(repo, tmp_path, names=DUMMY)
    assert r.returncode == 0 and "passed" in r.stdout


def test_env_list_used_in_ci(repo, tmp_path):
    assert run(repo, tmp_path, env_names=DUMMY).returncode == 0
    (repo / "a.txt").write_text(f"x {DUMMY} y\n")
    git(repo, "add", "a.txt")
    assert run(repo, tmp_path, env_names=DUMMY).returncode != 0


def test_planted_name_in_tracked_file_fails(repo, tmp_path):
    (repo / "notes.txt").write_text(f"see {DUMMY.upper()}\n")
    git(repo, "add", "notes.txt")
    r = run(repo, tmp_path, names=DUMMY)
    assert r.returncode == 1


def test_script_is_not_excluded_from_the_scan(repo, tmp_path):
    with open(repo / "scripts" / "audit-public.sh", "a") as f:
        f.write(f"# {DUMMY}\n")
    git(repo, "add", "-A")
    assert run(repo, tmp_path, names=DUMMY).returncode == 1


def test_planted_name_in_commit_identity_fails(repo, tmp_path):
    git(repo, "config", "user.name", DUMMY)
    git(repo, "commit", "-q", "--allow-empty", "-m", "x")
    assert run(repo, tmp_path, names=DUMMY).returncode == 1


def test_missing_list_fails(repo, tmp_path):
    r = run(repo, tmp_path)
    assert r.returncode == 2 and "no private-names list" in r.stderr


def test_missing_file_fails(repo, tmp_path):
    assert run(repo, tmp_path, file_path=tmp_path / "absent").returncode == 2


def test_invalid_regex_fails(repo, tmp_path):
    assert run(repo, tmp_path, names="(unbalanced").returncode == 2


@pytest.mark.parametrize("names", ["", "  \n", "a|", "|a", "a||b", "a\nb"])
def test_degenerate_list_fails(repo, tmp_path, names):
    assert run(repo, tmp_path, names=names).returncode == 2


@pytest.mark.parametrize("mode", [0o640, 0o604, 0o644, 0o660, 0o666])
def test_list_with_group_or_other_access_refused(repo, tmp_path, mode):
    r = run(repo, tmp_path, names=DUMMY, mode=mode)
    assert r.returncode == 2 and "mode" in r.stderr


def test_mode_0400_accepted(repo, tmp_path):
    assert run(repo, tmp_path, names=DUMMY, mode=0o400).returncode == 0
