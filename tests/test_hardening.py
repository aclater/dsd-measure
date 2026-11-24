"""Security and robustness: private core cache, temp folders, exit codes, command templates,
timeouts, class B end to end, notes in reports."""

import os
import stat
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import numpy as np
import pytest

from dsd_measure import adapters, cli, dsf, encode, measure
from dsd_measure import signals as sg
from dsd_measure.levels import REF_DBFS
from dsd_measure.report import write_comparison, write_device_report

# ------------------------------------------------------------------ compiled core cache


def test_cache_dir_follows_xdg_and_is_created_private(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    assert encode._cache_dir() == tmp_path / "dsd-measure"
    lib = encode._build_lib()
    assert lib.parent == tmp_path / "dsd-measure"
    assert stat.S_IMODE(lib.parent.stat().st_mode) == 0o700
    assert not stat.S_IMODE(lib.stat().st_mode) & 0o022
    assert not list(lib.parent.glob(".build-*"))  # the temp file was renamed away


def test_planted_file_in_tmp_is_not_used(tmp_path, monkeypatch):
    """The old predictable /tmp path must be ignored, even when a file is waiting there."""
    import hashlib
    import tempfile
    src = Path(encode.__file__).with_name("csrc") / "dsm.c"
    old = Path(tempfile.gettempdir()) / f"dsd_measure_dsm_{hashlib.sha256(src.read_bytes()).hexdigest()[:12]}.so"
    planted = old.exists()
    if not planted:
        old.write_bytes(b"not a shared object")
    try:
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
        lib = encode._build_lib()
        assert lib.parent == tmp_path / "dsd-measure" and lib != old
        assert lib.read_bytes()[:4] == b"\x7fELF" or sys.platform == "darwin"
    finally:
        if not planted:
            old.unlink()


def test_cache_dir_permissions_are_checked(tmp_path):
    d = tmp_path / "c"
    d.mkdir(mode=0o700)
    os.chmod(d, 0o755)  # readable and listable by others: refused
    with pytest.raises(encode.UnsafeCacheError):
        encode._build_lib(d)
    os.chmod(d, 0o770)
    with pytest.raises(encode.UnsafeCacheError):
        encode._build_lib(d)
    os.chmod(d, 0o700)
    assert encode._build_lib(d).exists()


def test_cache_dir_symlink_and_foreign_owner_refused(tmp_path, monkeypatch):
    real = tmp_path / "real"
    real.mkdir(mode=0o700)
    (tmp_path / "link").symlink_to(real)
    with pytest.raises(encode.UnsafeCacheError):
        encode._build_lib(tmp_path / "link")
    d = tmp_path / "c"
    monkeypatch.setattr(os, "geteuid", lambda: os.getuid() + 1)  # as if the directory were another user's
    with pytest.raises(encode.UnsafeCacheError):
        encode._build_lib(d)


def test_planted_library_in_cache_is_refused_when_group_writable(tmp_path):
    d = tmp_path / "c"
    lib = encode._build_lib(d)
    os.chmod(lib, 0o777)
    with pytest.raises(encode.UnsafeCacheError):
        encode._build_lib(d)
    lib.unlink()
    lib.symlink_to("/bin/true")  # a link is never followed
    with pytest.raises(encode.UnsafeCacheError):
        encode._build_lib(d)


def test_concurrent_builds_leave_one_complete_library(tmp_path):
    code = ("from dsd_measure import encode; import sys; print(encode._build_lib(sys.argv[1]))")
    d = tmp_path / "c"
    procs = [subprocess.Popen([sys.executable, "-c", code, str(d)], stdout=subprocess.PIPE) for _ in range(4)]
    outs = {p.communicate()[0].strip() for p in procs}
    assert all(p.returncode == 0 for p in procs) and len(outs) == 1
    assert [f.name for f in d.iterdir() if f.name.startswith(".build-")] == []


# ------------------------------------------------------------------ command templates


def test_substitute_only_touches_input_and_output():
    sub = adapters.substitute
    assert sub("awk '{print $1}' {input} > {output}", input="a", output="b") == "awk '{print $1}' a > b"
    assert sub("x {0} {} {foo} {input}", input="i", output="o") == "x {0} {} {foo} i"
    assert sub("echo {{input}} {input}", input="i", output="o") == "echo {input} i"


def test_cli_adapter_without_shell_takes_the_command_literally(tmp_path):
    fs = 88200
    bits, _ = encode.encode(sg.sine(1000, REF_DBFS, fs, fs // 2), fs)
    dsf.write_dsf(tmp_path / "canned.dsf", bits, 2822400)
    ad = adapters.Cli("copy", f"cp '{tmp_path}/canned.dsf' {{output}}", klass="B", workdir=tmp_path / "w")
    got, _ = ad.pcm_to_dsd(np.zeros(fs // 2), fs)
    assert np.array_equal(got, bits)
    # no shell: a redirect or a command separator is just more arguments
    marker = tmp_path / "marker"
    ad = adapters.Cli("bad", f"cp {tmp_path}/canned.dsf {{output}} ; touch {marker}", klass="B",
                      workdir=tmp_path / "w2")
    with pytest.raises(RuntimeError):
        ad.pcm_to_dsd(np.zeros(fs // 2), fs)
    assert not marker.exists()


def test_cli_adapter_braces_in_a_shell_command(tmp_path):
    ad = adapters.Cli("brace", "awk 'BEGIN{x=1}' ; cp /dev/null {output}", klass="B", shell=True,
                      workdir=tmp_path)
    with pytest.raises(ValueError):  # the command ran (no KeyError); the empty output is not a DSF
        ad.pcm_to_dsd(np.zeros(1000), 88200)
    ad = adapters.Cli("brace", "sh -c 'echo {0}; exit 3'", klass="B", workdir=tmp_path)
    with pytest.raises(RuntimeError, match="failed"):
        ad.pcm_to_dsd(np.zeros(1000), 88200)


# ------------------------------------------------------------------ timeouts and process groups


def _alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    try:
        return "Z" not in Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0]
    except OSError:
        return False


@pytest.mark.parametrize("shell", [True, False])
def test_timeout_kills_the_whole_process_group(tmp_path, shell):
    pidfile = tmp_path / "pid"
    if shell:
        cmd = f"sleep 60 & echo $! > {pidfile}; wait"
    else:
        script = tmp_path / "s.py"
        script.write_text(textwrap.dedent(f"""
            import subprocess, sys
            p = subprocess.Popen(["sleep", "60"])
            open({str(pidfile)!r}, "w").write(str(p.pid))
            p.wait()
        """))
        cmd = [sys.executable, str(script)]
    t0 = time.time()
    with pytest.raises(TimeoutError):
        adapters.run_checked(cmd, shell=shell, timeout=2)
    assert time.time() - t0 < 20
    pid = int(pidfile.read_text())
    for _ in range(50):
        if not _alive(pid):
            break
        time.sleep(0.1)
    assert not _alive(pid), "a child of the timed-out command is still running"


# ------------------------------------------------------------------ temporary folders


def _our_tmp_dirs():
    import tempfile
    return {p for p in Path(tempfile.gettempdir()).glob("dsd-measure-*")}


def test_work_folder_is_removed_on_success_and_on_error():
    before = _our_tmp_dirs()
    ad = adapters.Cli("x", "cp /dev/null {output}", klass="B")
    with pytest.raises(ValueError):
        ad.pcm_to_dsd(np.zeros(1000), 88200)
    made = _our_tmp_dirs() - before
    assert len(made) == 1  # exists while the adapter lives (it may hold a failed call's files)
    ad.close()
    assert not (_our_tmp_dirs() - before)
    ad.close()  # twice is fine


def test_named_work_folder_is_kept(tmp_path):
    ad = adapters.Cli("x", "cp /dev/null {output}", klass="B", workdir=tmp_path / "keep")
    with pytest.raises(ValueError):
        ad.pcm_to_dsd(np.zeros(1000), 88200)
    ad.close()
    assert (tmp_path / "keep").is_dir()


def test_run_suite_cleans_up_when_interrupted(tmp_path, monkeypatch):
    from dsd_measure import run
    suite = tmp_path / "s.toml"
    suite.write_text('[[device]]\nname = "d"\nadapter = "cli"\nclass = "B"\ncommand = "cp /dev/null {output}"\n')
    before = _our_tmp_dirs()

    def boom(adapter, *a, **k):
        adapter._tmp()
        adapter._work.path()
        raise KeyboardInterrupt

    monkeypatch.setattr(run, "measure_device", boom)
    with pytest.raises(KeyboardInterrupt):
        run.run_suite(suite, tmp_path / "out", "quick", log=lambda *_, **__: None)
    assert not (_our_tmp_dirs() - before)
    assert cli.main(["run", str(suite), "-o", str(tmp_path / "out")]) == cli.EXIT_INTERRUPTED
    assert not (_our_tmp_dirs() - before)


# ------------------------------------------------------------------ exit status


def test_exit_code_is_nonzero_when_tests_error(tmp_path, capsys):
    out = tmp_path / "r"
    rc = cli.main(["run", str(_suite(tmp_path, "true")), "-o", str(out), "--only", "polarity"])
    assert rc == cli.EXIT_TESTS_FAILED == 1
    assert "failed" in capsys.readouterr().out


def _suite(tmp_path, command):
    p = tmp_path / "suite.toml"
    p.write_text(f'[[device]]\nname = "d"\nadapter = "cli"\nclass = "A"\ncommand = "{command}"\n')
    return p


def test_exit_code_zero_when_all_run(tmp_path):
    p = tmp_path / "suite.toml"
    p.write_text('[[device]]\nname = "r"\nadapter = "reference"\nclass = "A"\nout_rate = 44100\n')
    assert cli.main(["run", str(p), "-o", str(tmp_path / "o"), "--only", "polarity"]) == cli.EXIT_OK == 0


def test_user_mistakes_are_a_one_line_error_with_code_2(tmp_path, capsys):
    assert cli.main(["run", str(tmp_path / "missing.toml")]) == cli.EXIT_FATAL == 2
    bad = tmp_path / "bad.toml"
    bad.write_text('[[device]]\nadapter = "nonsense"\n')
    assert cli.main(["run", str(bad), "-o", str(tmp_path / "o")]) == 2
    err = capsys.readouterr().err
    assert err.count("dsd-measure: error:") == 2 and "Traceback" not in err


# ------------------------------------------------------------------ class B end to end

_MODULATOR = textwrap.dedent("""
    import sys
    from dsd_measure import encode, wavio, dsf
    y, fs = wavio.read_wav(sys.argv[1])
    bits, _ = encode.encode(y[0], fs, 2822400)
    dsf.write_dsf(sys.argv[2], bits, 2822400)
""")


def _class_b_device(tmp_path):
    script = tmp_path / "mod.py"
    script.write_text(_MODULATOR)
    return adapters.Cli("standin", f"{sys.executable} {script} {{input}} {{output}}", klass="B")


def test_class_b_measurement_path_end_to_end(tmp_path):
    """A class B device behind a real command, through the runner, the analysis and the reports."""
    ad = _class_b_device(tmp_path)
    try:
        r = measure.measure_device(ad, "quick", only=["polarity", "impulse", "overload"], log=lambda *_, **__: None)
    finally:
        ad.close()
    assert r["errors"] == [] and r["not_run"] == {}, r["not_run"]
    M = r["metrics"]
    assert M["device_class"] == "B" and M["polarity"] == "normal"
    assert "impulse" not in M  # S5: a modulator's filter rows are the reference decoder's
    assert M["reference_decoder_only"]["impulse"]["filter_type"] == "linear phase"
    assert "overload_recovery" in M
    assert any("reference decoder" in n for n in r["notes"])
    assert len(ad.log) >= 3 and all(c["output_sha256"] for c in ad.log)
    meta = {"device": ad.describe(), "profile": "quick", "reference_chain": "1"}
    write_device_report(tmp_path / "rep", "standin", r, meta)
    page = (tmp_path / "rep" / "index.html").read_text()
    md = (tmp_path / "rep" / "index.md").read_text()
    assert "reference decoder" in page and "<h2>Notes</h2>" in page
    assert "## Notes" in md and "reference decoder" in md
    write_comparison(tmp_path / "cmp", [("standin", r), ("again", r)], {"profile": "quick"})
    assert "standin: The impulse, step, filter" in (tmp_path / "cmp" / "index.md").read_text()
    assert "standin: The impulse, step, filter" in (tmp_path / "cmp" / "index.html").read_text()


def test_class_b_reference_modulator_levels_and_stability_run():
    ad = adapters.Reference("b", klass="B")
    r = measure.measure_device(ad, "quick", only=["stability", "multitone"], log=lambda *_, **__: None)
    assert r["errors"] == [], r["not_run"]
    assert "stability" in r["metrics"] and "multitone" in r["metrics"]


def test_reports_without_notes_have_no_notes_section(tmp_path):
    ad = adapters.Reference("a", klass="A", out_rate=44100)
    r = measure.measure_device(ad, "quick", only=["polarity"], log=lambda *_, **__: None)
    write_device_report(tmp_path, "a", r, {"device": ad.describe(), "profile": "quick", "reference_chain": "1"})
    assert "Notes" not in (tmp_path / "index.html").read_text()


