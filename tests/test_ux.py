"""What a user is told: --plan, the run log, signals --list and the report's "What was measured" block."""

import json

from dsd_measure import adapters, cli, measure, plan
from dsd_measure.report import write_device_report
from dsd_measure.run import run_suite, summary_line

SUITE = """\
[suite]
name = "two decoders"
profile = "quick"
out = "out-report"

[[device]]
name = "my decoder"
adapter = "cli"
class = "A"
command = "mytool --in {input} --out {output}"

[[device]]
name = "reference decoder"
adapter = "reference"
class = "A"
out_rate = 44100
"""


def test_plan_prints_devices_signals_and_report_and_runs_nothing(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "suite.toml").write_text(SUITE)
    assert cli.main(["run", "suite.toml", "--plan"]) == 0
    out = capsys.readouterr().out
    assert "nothing has been run" in out
    assert "Device 1: my decoder" in out and "Device 2: reference decoder" in out
    # the command line is filled in for one example signal, with no placeholders left
    assert "mytool --in /tmp/dsd-measure-example/in1.dsf --out /tmp/dsd-measure-example/out1.wav" in out
    assert "{input}" not in out
    assert "synthetic, deterministic test signals" in out
    assert "1 kHz tones, 1.5 s each" in out and "DSD64" in out and "profile: quick" in out
    assert "Estimated time" in out
    assert "out-report/my-decoder/index.html" in out and "out-report/comparison/index.html" in out
    assert not (tmp_path / "out-report").exists()


def test_plan_for_class_b_and_missing_preset_tool(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PATH", "")
    (tmp_path / "s.toml").write_text('[[device]]\nname = "m"\nadapter = "sacd_extract"\nclass = "B"\n')
    assert cli.main(["run", "s.toml", "--plan", "--profile", "full"]) == 0
    out = capsys.readouterr().out
    assert "class B: PCM to DSD modulator" in out and "warning:" in out
    assert "PCM at 88200 Hz, 32-bit integer WAV" in out and "stability" in out and "alias_tones" not in out


def test_quick_plan(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert cli.main(["quick", "reference", "--plan", "-o", "rep"]) == 0
    out = capsys.readouterr().out
    assert "dsd-measure quick reference" in out and "reference modulator" in out and "rep/comparison/index.html" in out
    assert not (tmp_path / "rep").exists()


def test_signals_list(capsys):
    assert cli.main(["signals", "--list"]) == 0
    out = capsys.readouterr().out
    for name in plan.TESTS:
        assert name in out
    assert "none is music" in out and "signals.json" in out


def test_every_test_has_a_plain_sentence_and_a_time():
    for name, t in plan.TESTS.items():
        assert t["what"].endswith(".") and t["why"].endswith(".") and t["klass"] in ("A", "B", "AB")
        for prof in ("quick", "full"):
            assert plan.SECONDS[prof]["A"].get(name) is not None


def test_run_log_lines_and_summary(tmp_path):
    lines = []
    a = adapters.Reference("t", klass="B", out_rate=44100)
    r = measure.measure_device(a, "quick", only=["polarity", "alias_tones"], log=lambda m, end="\n": lines.append((m, end)))
    text = "".join(m + e for m, e in lines)
    assert "-> t: polarity (asymmetric pulse, small) ... done in" in text
    assert "-> t: alias_tones (tones above the output Nyquist, 0 dB SACD) ... skipped: class A only" in text
    assert summary_line("t", r).startswith("  t: SINAD not measured")


def test_report_header_what_was_measured(tmp_path):
    a = adapters.Cli("tool", "mytool {input} {output}", klass="A", gain_db=6.0206)
    r = measure.measure_device(adapters.Reference("t", klass="A", out_rate=44100), "quick", only=["polarity"], log=lambda *_, **__: None)
    m = plan.measured(a, "quick", 88200, None, "suite")
    meta = {"device": a.describe(), "profile": "quick", "reference_chain": "1", "measured": m}
    write_device_report(tmp_path / "d", "tool", r, meta)
    html = (tmp_path / "d" / "index.html").read_text()
    md = (tmp_path / "d" / "index.md").read_text()
    assert html.index("What was measured") < html.index("Summary")
    for needle in ("mytool /tmp/dsd-measure-example/in1.dsf", "gain applied to its output: +6.0206 dB", "Synthetic and deterministic",
                   f"dsd-measure {__import__('dsd_measure').__version__}", "tone_1k_0dbsacd.wav"):
        assert needle in html
    assert "## What was measured" in md and "no music" in md
    assert len(m["source_signal_sha256"]) == 5 and all(len(h) == 64 for h in m["source_signal_sha256"].values())
    assert m["source_signal_sha256"] == plan.source_hashes(88200)


def test_run_suite_end_to_end_log_and_header(tmp_path):
    (tmp_path / "s.toml").write_text('[suite]\nname = "tiny"\n[[device]]\nname = "ref"\nadapter = "reference"\nclass = "A"\nout_rate = 44100\n')
    lines = []
    run_suite(tmp_path / "s.toml", tmp_path / "rep", only=["polarity", "impulse"], log=lambda m="", end="\n": lines.append(m + end))
    text = "".join(lines)
    assert "Device 1 of 1: ref" in text and "Report:" in text and "ref: SINAD not measured" in text
    meta = json.loads((tmp_path / "rep" / "ref" / "provenance.json").read_text())
    assert meta["measured"]["generator"].startswith("dsd-measure")
