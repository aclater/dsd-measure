"""0.1.2 usability fixes: word length, presets, pre-flight, the null shortcut, the Result line, progress."""

import json
import stat
import sys
from pathlib import Path

import numpy as np
import pytest

from dsd_measure import adapters, cli, measure, plan, preflight
from dsd_measure import conclusions as cn
from dsd_measure import outformat as of
from dsd_measure.errors import MissingTool, UserError
from dsd_measure.run import run_suite
from dsd_measure.wavio import write_wav

STUB = Path(__file__).with_name("stubtool.py")
ROOT = Path(__file__).resolve().parents[1]


QUIET_NOISE = {"a_weighted_dbfs": -155.0, "bands": {"20-20000": -150.0, "20000-40000": -80.0, "40000-96000": -40.0}}


def stub(*flags):
    return f"{sys.executable} {STUB} {{input}} {{output}} " + " ".join(flags)


def quiet(*_a, **_k):
    pass


# ----------------------------------------------------------------------------- word length

@pytest.mark.parametrize("sub, bits, kind", [("pcm16", 16, "int"), ("pcm24", 24, "int"), ("pcm32", 32, "int"),
                                             ("float32", 32, "float"), ("float64", 64, "float")])
def test_wav_format_is_read_from_the_header(tmp_path, sub, bits, kind):
    write_wav(tmp_path / "a.wav", np.zeros((2, 100)), 352800, sub)
    f = of.wav_format(tmp_path / "a.wav")
    assert (f["bits"], f["kind"], f["rate"], f["channels"]) == (bits, kind, 352800, 2)


def test_flac_format_is_read_from_streaminfo(tmp_path):
    # STREAMINFO: 20 bits rate, 3 bits channels - 1, 5 bits bits per sample - 1, 36 bits samples
    v = (176400 << 44) | (1 << 41) | (23 << 36) | 1000
    body = b"\x00" * 10 + v.to_bytes(8, "big") + b"\x00" * 16
    (tmp_path / "a.flac").write_bytes(b"fLaC" + b"\x80\x00\x00\x22" + body)
    assert of.audio_format(tmp_path / "a.flac") == {"container": "flac", "kind": "int", "bits": 24, "rate": 176400, "channels": 2}


@pytest.mark.parametrize("bits", [16, 24])
def test_quantisation_limit_matches_a_rounded_tone(bits):
    from dsd_measure import analyse as an
    from dsd_measure import signals as sg
    fs, n = 352800, 2**18
    f = sg.coherent_freq(1000, fs, n)
    x = 0.5 * np.sin(2 * np.pi * f * np.arange(n + 6000) / fs)
    q = 2.0 ** (bits - 1)
    got = an.tone_metrics((np.round(x * q) / q)[-n - 3000:-3000], fs, f, n)["sinad_db"]
    assert abs(got - of.quantisation_sinad_db(bits, fs)) < 1.5


def test_the_adapter_records_what_the_tool_wrote(tmp_path):
    for fmt, bits, kind in (("pcm16", 16, "int"), ("float32", 32, "float")):
        a = adapters.Cli("t", stub("--format", fmt), workdir=tmp_path / fmt)
        rec = preflight.run(a, 88200, quiet)
        assert rec["output_format"]["bits"] == bits and rec["output_format"]["kind"] == kind
        assert a.log == []  # the pre-flight call is not part of the measurement's provenance


def test_a_16_bit_tool_is_not_judged_a_32_bit_float_tool_is(tmp_path):
    lines = []
    res = {}
    for fmt in ("pcm16", "float32"):
        a = adapters.Cli(fmt, stub("--format", fmt))
        res[fmt] = measure.measure_device(a, "quick", only=["levels"], log=lambda m, end="\n": lines.append(m))
        a.close()
    m16, m32 = res["pcm16"]["metrics"], res["float32"]["metrics"]
    # the same decoder: only the word length differs, and the 16-bit figure sits at the rounding limit
    assert abs(m16["tone_0dbsacd"]["sinad_db"] - m16["output_format"]["quantisation_sinad_db"]) < 2
    assert m32["tone_0dbsacd"]["sinad_db"] > 140
    assert cn.format_limit(m16) and not cn.format_limit(m32)
    from dsd_measure.run import summary_line
    assert "limited by its 16-bit output file, not judged" in summary_line("t16", res["pcm16"])
    assert "reference floor" in summary_line("t32", res["float32"])
    c16, c32 = cn.device_conclusions(m16, adapters.Cli("x", "x").describe()), cn.device_conclusions(m32, adapters.Cli("x", "x").describe())
    assert c16[0]["id"] == "overall" and c16[0]["verdict"] == "format-limited"
    assert c32[0]["verdict"] == "margin-120" or c32[0]["verdict"] == "margin-87"
    h16 = cn.device_headline(m16, {"adapter": "cli", "class": "A"}, "tool")
    assert h16.startswith("Result: not judged. tool wrote 16-bit integer PCM") and "floating-point" in h16 and "TPDF dither" in h16


def test_format_limit_rules():
    from test_conclusions import FMT16, metrics
    assert cn.format_limit(metrics(sinad=101.4, output_format=FMT16))
    assert not cn.format_limit(metrics(sinad=130.0, output_format=FMT16))  # noise shaping beats plain rounding
    assert not cn.format_limit(metrics(sinad=60.0, output_format=FMT16))  # the device's own noise is lower still
    assert not cn.format_limit(metrics(sinad=101.4, output_format={**FMT16, "bits": 24, "quantisation_sinad_db": 149.7,
                                                                    "quantisation_sinad_dithered_db": 144.9}))
    assert not cn.format_limit(metrics(sinad=101.4, output_format={**FMT16, "kind": "float", "bits": 32}))
    assert not cn.format_limit(metrics(sinad=101.4))
    assert not cn.format_limit(metrics(klass="B", sinad=101.4, output_format=FMT16))


def test_comparison_does_not_rank_a_file_format():
    from test_conclusions import CLI, FMT16, metrics
    FLT = {"container": "wav", "kind": "float", "bits": 32, "rate": 352800, "text": "32-bit float"}
    a, b = metrics(sinad=146.0, dr=150.0, output_format=FLT), metrics(sinad=101.4, dr=103.7, output_format=FMT16)
    cs = cn.comparison_conclusions([("good", a, CLI), ("narrow", b, CLI)])
    ids = [c["id"] for c in cs]
    assert "cmp-format" in ids and "cmp-distortion" not in ids and "cmp-overall" not in ids
    assert "cmp-conditions" in ids  # a different word length is not like-for-like
    h = cn.comparison_headline([("good", a, CLI), ("narrow", b, CLI)], cs)
    assert h.startswith("Result: not like-for-like.") and "16-bit integer out at 352.8 kHz" in h
    # the same format at the same rate: the format rule alone speaks
    c = metrics(sinad=101.0, dr=103.0, output_format=FMT16)
    cs2 = cn.comparison_conclusions([("one", c, CLI), ("narrow", b, CLI)])
    ids2 = [x["id"] for x in cs2]
    assert "cmp-format" in ids2 and "cmp-conditions" not in ids2 and "cmp-distortion" not in ids2
    assert cn.comparison_headline([("one", c, CLI), ("narrow", b, CLI)], cs2).startswith("Result: not compared in distortion and noise")


def test_report_says_the_word_length_and_the_result_first(tmp_path):
    a = adapters.Cli("t", stub("--format", "pcm16"))
    pre = preflight.run(a, 88200, quiet)
    res = measure.measure_device(a, "quick", only=["levels"], log=quiet)
    a.close()
    from dsd_measure.report import write_device_report
    meta = {"device": a.describe(), "profile": "quick", "reference_chain": "2", "preflight": pre,
            "measured": plan.measured(a, "quick", 88200, None, "s")}
    head = write_device_report(tmp_path / "r", "t", res, meta)
    html = (tmp_path / "r" / "index.html").read_text()
    md = (tmp_path / "r" / "index.md").read_text()
    assert head.startswith("Result: not judged")
    assert html.index("class=result") < html.index("Conclusions")
    assert f"**{head}**" in md.splitlines()[4]
    assert json.loads((tmp_path / "r" / "results.json").read_text())["headline"] == head
    assert "Output format" in html and "16-bit integer as written by the device (WAV)" in html


# ----------------------------------------------------------------------------- presets and unknown names

def fake_ffmpeg(tmp_path, monkeypatch, dff_only=False):
    """A script called ffmpeg on PATH that writes a 0.5 s float tone (and refuses DSF files when asked)."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    exe = bindir / "ffmpeg"
    exe.write_text(f"#!/bin/sh\nargs=\"$*\"\ninput=$(echo \"$args\" | sed -n 's/.*-i \\([^ ]*\\) .*/\\1/p')\n"
                   f"{'case $input in *.dsf) echo Invalid data found >&2; exit 1;; esac' if dff_only else ''}\n"
                   f"exec {sys.executable} {STUB} \"$input\" \"$(echo \"$args\" | awk '{{print $NF}}')\" --tone --format float32\n")
    exe.chmod(exe.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("PATH", f"{bindir}:/usr/bin:/bin")
    return exe


def test_ffmpeg_preset_writes_float(tmp_path, monkeypatch):
    fake_ffmpeg(tmp_path, monkeypatch)
    a = adapters.make_adapter({"adapter": "ffmpeg", "name": "ffmpeg", "class": "A"})
    assert "-c:a pcm_f32le" in a.command and a.command.split()[0] == "ffmpeg"
    assert a.input_ext == "dsf" and a.input_ext_fallback == "dff"
    rec = preflight.run(a, 88200, quiet)
    assert rec["output_format"]["kind"] == "float"


def test_ffmpeg_preset_falls_back_to_dff_when_dsf_is_refused(tmp_path, monkeypatch):
    fake_ffmpeg(tmp_path, monkeypatch, dff_only=True)
    a = adapters.make_adapter({"adapter": "ffmpeg", "name": "ffmpeg"})
    lines = []
    preflight.run(a, 88200, lines.append)
    assert a.input_ext == "dff" and any("reads DFF" in x for x in lines)
    # an explicit input_ext in a suite file is left alone
    b = adapters.make_adapter({"adapter": "ffmpeg", "input_ext": "dsf"})
    assert b.input_ext == "dsf" and b.input_ext_fallback is None


def test_preset_without_its_tool_says_what_to_do(monkeypatch):
    monkeypatch.setenv("PATH", "")
    with pytest.raises(MissingTool, match="ffmpeg is not on PATH.*Install it"):
        adapters.make_adapter({"adapter": "ffmpeg", "name": "ffmpeg"})


def test_unknown_converter_shows_presets_and_the_command_to_type(capsys):
    assert cli.main(["quick", "mytool"]) == cli.EXIT_FATAL
    err = capsys.readouterr().err
    assert err.count("dsd-measure: error:") == 1 and "ValueError" not in err
    assert "ffmpeg" in err and "dsd2pcm" in err and 'dsd-measure quick mytool --command "mytool {input} {output}"' in err


def test_a_dsd_file_given_to_quick_or_alone_points_to_null(capsys):
    for argv in (["quick", "track.dsf"], ["track.dsf"], ["track.dff"]):
        assert cli.main(argv) == cli.EXIT_FATAL
        err = capsys.readouterr().err
        assert f"dsd-measure null {argv[-1]} ffmpeg" in err


def test_bare_command_prints_the_guide(capsys):
    assert cli.main([]) == 0
    out = capsys.readouterr().out
    assert "dsd-measure quick ffmpeg" in out and "dsd-measure null track.dsf ffmpeg" in out and "dsd-measure run suite.toml" in out


def test_quick_plan_with_the_ffmpeg_preset(tmp_path, monkeypatch, capsys):
    fake_ffmpeg(tmp_path, monkeypatch)
    monkeypatch.chdir(tmp_path)
    assert cli.main(["quick", "ffmpeg", "--plan"]) == 0
    out = capsys.readouterr().out
    assert "pcm_f32le" in out and "Device 1: ffmpeg" in out


# ----------------------------------------------------------------------------- pre-flight

def test_missing_program_fails_in_one_message_and_writes_nothing(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert cli.main(["quick", "mytool", "--command", "nosuchtool {input} {output}"]) == cli.EXIT_FATAL
    err = capsys.readouterr().err
    assert err.count("\n") == 1 and "nosuchtool is not on PATH" in err
    assert not (tmp_path / "report").exists()


def test_a_bad_flag_prints_the_tools_own_error_once(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    bad = f"{sys.executable} -c \"import sys; print('unrecognised option --nonsense', file=sys.stderr); sys.exit(2)\" {{input}} {{output}}"
    out = capsys.readouterr()
    assert cli.main(["quick", "mytool", "--command", bad]) == cli.EXIT_FATAL
    cap = capsys.readouterr()
    assert cap.err.count("unrecognised option --nonsense") == 1 and cap.err.count("\n") == 1
    assert "skipped" not in cap.out and not (tmp_path / "report").exists()
    _ = out


def test_silent_and_empty_output_are_refused(tmp_path):
    with pytest.raises(UserError, match="silent"):
        preflight.run(adapters.Cli("s", stub("--silent")), 88200, quiet)
    with pytest.raises(UserError, match="could not convert"):
        preflight.run(adapters.Cli("e", "true"), 88200, quiet)


def test_a_short_file_is_refused(tmp_path):
    bad = adapters.Cli("s", f"{sys.executable} -c \"import sys; from dsd_measure.wavio import write_wav; import numpy as np; "
                            f"write_wav(sys.argv[2], 0.1*np.ones(1000), 44100, 'float32')\" {{input}} {{output}}")
    with pytest.raises(UserError, match="long"):
        preflight.run(bad, 88200, quiet)


def test_a_pre_flight_failure_stops_before_any_device_is_measured(tmp_path):
    suite = tmp_path / "s.toml"
    suite.write_text('[[device]]\nname = "ok"\nadapter = "reference"\nclass = "A"\nout_rate = 44100\n'
                     '[[device]]\nname = "bad"\nadapter = "cli"\nclass = "A"\ncommand = "nosuchtool {input} {output}"\n')
    lines = []
    with pytest.raises(UserError, match="nosuchtool"):
        run_suite(suite, tmp_path / "out", "quick", only=["polarity"], log=lines.append)
    assert not (tmp_path / "out").exists() and not any("-> ok" in x for x in lines)


def test_pre_flight_warns_about_a_16_bit_tool_with_the_fix(tmp_path, monkeypatch):
    lines = []
    a = adapters.Cli("t", stub("--format", "pcm16"))
    preflight.run(a, 88200, lines.append)
    text = "\n".join(lines)
    assert "16-bit integer" in text and "limits SINAD to about 101.5 dB" in text and "floating-point" in text
    assert "pcm_f32le" not in text  # the ffmpeg hint is for ffmpeg only
    b = adapters.Cli("ffmpeg", "ffmpeg -i {input} {output}")
    assert "-c:a pcm_f32le" in of.warning({"kind": "int", "bits": 16, "rate": 352800}, b.command)


# ----------------------------------------------------------------------------- the Result line and the counter

def test_run_ends_with_the_result_line(tmp_path):
    suite = tmp_path / "s.toml"
    suite.write_text('[[device]]\nname = "r"\nadapter = "reference"\nclass = "A"\nout_rate = 44100\n')
    lines = []
    run_suite(suite, tmp_path / "out", "quick", only=["polarity"], log=lambda m="", end="\n": lines.append(m))
    assert lines[-1].startswith("Result: this is the measurement floor of the built-in reference chain")
    assert "Finished in" in "\n".join(lines)


def test_headlines_for_each_verdict():
    from test_conclusions import CLI, metrics
    t = cn.device_headline(metrics(sinad=146, dr=150, smpte=-146, ccif=-146, analysis_version=2, noise=QUIET_NOISE), CLI, "tool")
    assert t.startswith("Result: tool measures 140 dB below a reference-level tone in its weakest figure in the audio band, ")
    assert "every concluded figure is at least 120 dB down" in t
    assert "Not judged in this version: filter and ringing." in t
    i = cn.device_headline(metrics(sinad=100, dr=112, analysis_version=2, noise=QUIET_NOISE), CLI, "tool")
    assert "at least 87 dB down" in i and "distortion plus noise on a 1 kHz tone (SINAD)" in i and "100 dB below" in i
    r = cn.device_headline(metrics(sinad=60, dr=112, analysis_version=2, noise=QUIET_NOISE), CLI, "tool")
    assert "less than 87 dB down" in r
    a, b = metrics(analysis_version=2), metrics(sinad=110.5, analysis_version=2)
    h = cn.comparison_headline([("A", a, CLI), ("B", b, CLI)], cn.comparison_conclusions([("A", a, CLI), ("B", b, CLI)]))
    assert h.startswith("Result: in the audio band, A and B measure the same within the tolerance used here.")
    assert "Not compared in this version" in h


def test_reference_floor_figures_are_shown_to_the_same_precision():
    f = {"dsd_rate": 2822400, "margin_db": 6.0, "ntf": "order 8", "chain": {"thdn_db": -147.0, "dr_a_db": 151.8},
         "decoder_alone": {"thdn_db": -280.0, "dr_a_db": 342.2}}
    m = plan.measured(adapters.Reference("r", klass="A", out_rate=44100), "quick", 88200, f, "s")
    assert "dynamic range (A) 151.8 dB" in plan.measured_summary(m)[2][1]


def test_every_number_in_a_headline_is_in_the_evidence():
    from test_conclusions import CLI, metrics
    M = metrics(sinad=100.4, dr=112, analysis_version=2, noise=QUIET_NOISE)
    h = cn.device_headline(M, CLI, "tool")
    ov = next(c for c in cn.device_conclusions(M, CLI) if c["id"] == "overall")
    backed = {n.lstrip("-") for e in ov["evidence"] for n in cn.numbers(e["value"]) + cn.numbers(e["label"])}
    backed |= {f"{cn.THRESHOLDS[t]['value']:.0f}" for t in ov["thresholds"]}
    assert all(n.lstrip("-") in backed for n in cn.numbers(h)), (h, backed)


def test_progress_counter_and_time_left(monkeypatch):
    monkeypatch.setitem(plan.SECONDS["quick"]["B"], "polarity", 100)
    lines = []
    a = adapters.Reference("t", klass="B", out_rate=44100)
    measure.measure_device(a, "quick", only=["polarity", "imd", "alias_tones"], log=lambda m, end="\n": lines.append((m, end)))
    text = "".join(m + e for m, e in lines)
    assert "[1/3] -> t: imd" in text and "[2/3] -> t: polarity" in text and "[3/3] -> t: alias_tones" in text
    assert "about 1:40 left" in text.split("[2/3]")[0]  # after the first test, from the planned time of the rest
    assert "left" not in text.split("[3/3]")[1]  # nothing left after the last one


def test_the_report_shows_a_command_template_not_a_made_up_path():
    a = adapters.Cli("tool", "mytool {input} {output}", klass="A")
    m = plan.measured(a, "quick", 88200, None, "s")
    text = dict(plan.measured_summary(m))["Device"]
    assert "Run as: mytool {input} {output} ({input} is the DSD file" in text and "/tmp/dsd-measure-example" not in text


def test_public_links_point_at_the_current_organisation():
    bad = []
    for p in [ROOT / "README.md", *(ROOT / "docs").glob("*.md"), *(ROOT / "src" / "dsd_measure").glob("*.py")]:
        for line in p.read_text().splitlines():
            if "github.com/aclater/dsd-measure" in line or "github.com/aclater/dsd-toolbox" in line:
                bad.append((p.name, line[:80]))
    assert not bad


# ----------------------------------------------------------------------------- the null shortcut

@pytest.fixture
def captured(monkeypatch):
    got = {}

    def fake(source, devs, opts, out, *a, **k):
        got.update(source=source, devs=list(devs), out=out)

    monkeypatch.setattr("dsd_measure.nulltest.run.run_null", fake)
    return got


def test_null_takes_a_file_and_a_preset_with_the_reference_as_baseline(captured):
    assert cli.main(["null", "track.dsf", "ffmpeg"]) == 0
    assert captured["source"] == "track.dsf" and captured["devs"] == ["reference", "ffmpeg"]


def test_null_old_forms_still_work(captured):
    cli.main(["null", "--source", "t.dsf", "--device", "reference", "--device", "x={input}"])
    assert captured["devs"] == ["reference", "x={input}"]
    cli.main(["null", "t.dsf", "reference@176400", "ffmpeg"])
    assert captured["devs"] == ["reference@176400", "ffmpeg"]  # two named: the first is the baseline
    cli.main(["null", "--source", "t.dsf", "ffmpeg"])
    assert captured["devs"] == ["reference", "ffmpeg"]


def test_null_without_a_decoder_says_what_to_type(capsys):
    assert cli.main(["null", "track.dsf"]) == cli.EXIT_FATAL
    assert "dsd-measure null track.dsf ffmpeg" in capsys.readouterr().err


def test_null_fails_fast_on_a_missing_tool_before_reading_the_file(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("PATH", "")
    assert cli.main(["null", str(tmp_path / "t.dsf"), "ffmpeg"]) == cli.EXIT_FATAL
    err = capsys.readouterr().err
    assert "ffmpeg is not on PATH" in err and "No such file" not in err


def test_null_parse_device_knows_presets(tmp_path, monkeypatch):
    from dsd_measure.nulltest.devices import parse_device
    fake_ffmpeg(tmp_path, monkeypatch)
    d = parse_device("ffmpeg")
    assert d.name == "ffmpeg" and "pcm_f32le" in d.command and d.input_ext_fallback == "dff"


def _null_run(tmp_path, fmt, bits_note=""):
    from dsd_measure import encode
    from dsd_measure import signals as sg
    from dsd_measure.dsf import write_dsf
    from dsd_measure.nulltest.analyse import Options
    from dsd_measure.nulltest.run import run_null
    rng = np.random.default_rng(3)
    n = 88200 * 6
    x = np.convolve(rng.standard_normal(n), np.ones(6) / 6, "same")  # band-limited noise as "music"
    x *= 0.25 / np.max(np.abs(x))
    bits, _ = encode.encode(x, 88200, 2822400)
    src = tmp_path / "m.dsf"
    write_dsf(src, bits, 2822400)
    del sg
    out = tmp_path / f"null-{fmt}"
    run_null(str(src), ["reference@352800", f"t={stub('--format', fmt)}"], Options(trim_start=0.5, trim_end=0.5), out, log=quiet)
    return json.loads((out / "results.json").read_text()), (out / "index.html").read_text()


@pytest.mark.slow
def test_null_depth_of_a_16_bit_decoder_is_called_a_format_limit(tmp_path):
    run16, html16 = _null_run(tmp_path, "pcm16")
    run32, html32 = _null_run(tmp_path, "float32")
    assert run16["devices"][1]["info"]["output_format"]["bits"] == 16
    v16, v32 = run16["pairs"][0]["verdict"], run32["pairs"][0]["verdict"]
    assert v16["format_limited"] == ["t"] and "Limited by the 16-bit output of t" in v16["headline"]
    assert "format_limited" not in v32 and v32["depth_db"] > v16["depth_db"] + 20
    assert "class=result>Result:" in html16 and "Limited by the 16-bit output" in html16
    assert "<th class=v>Null depth, 20 Hz to 20 kHz</th><th class=v>Null depth, full analysed band</th>" in html16


def test_apply_format_limit_only_when_the_difference_sits_at_the_rounding_noise():
    from dsd_measure.nulltest.verdict import apply_format_limit
    fmt = {"kind": "int", "bits": 16, "rate": 352800}
    ch = {"diff_rms_audio_dbfs": -106.0, "music_rms_audio_dbfs": -19.0}
    v = apply_format_limit({"headline": "H.", "details": []}, ch, [("t", fmt)])
    assert v["format_limited"] == ["t"] and "caps the null depth at about 92 dB" in v["details"][0]
    far = {"diff_rms_audio_dbfs": -140.0, "music_rms_audio_dbfs": -19.0}
    assert "format_limited" not in apply_format_limit({"headline": "H.", "details": []}, far, [("t", fmt)])
    assert "format_limited" not in apply_format_limit({"headline": "H.", "details": []}, ch, [("t", {**fmt, "kind": "float", "bits": 32})])


# ----------------------------------------------------------------------------- findings from the dsd2pcm suite work

def fake_tool(tmp_path, monkeypatch, name):
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    exe = bindir / name
    exe.write_text(f"#!/bin/sh\nexec {sys.executable} {STUB} \"$@\" --tone\n")
    exe.chmod(exe.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("PATH", f"{bindir}:/usr/bin:/bin")


def test_dsd2pcm_preset_takes_in_and_out_without_dash_o():
    assert adapters.PRESETS["dsd2pcm"] == "dsd2pcm {input} {output}"
    assert adapters.with_args("dsd2pcm {input} {output}", "--filter pysacd") == "dsd2pcm --filter pysacd {input} {output}"
    assert adapters.with_args("dsd2pcm {input} {output}", "") == "dsd2pcm {input} {output}"


def test_presets_take_extra_arguments(tmp_path, monkeypatch, capsys):
    fake_tool(tmp_path, monkeypatch, "dsd2pcm")
    a = adapters.make_adapter({"adapter": "dsd2pcm", "name": "d", "args": "--filter pysacd"})
    assert a.command == "dsd2pcm --filter pysacd {input} {output}"
    monkeypatch.chdir(tmp_path)
    assert cli.main(["quick", "dsd2pcm", "--args", "--filter pysacd", "--plan"]) == 0
    assert "dsd2pcm --filter pysacd " in capsys.readouterr().out
    from dsd_measure.nulltest.devices import parse_device
    d = parse_device("dsd2pcm:--filter pysacd")
    assert d.command == "dsd2pcm --filter pysacd {input} {output}" and d.name == "dsd2pcm --filter pysacd"


@pytest.mark.skipif(not __import__("os").environ.get("DSD2PCM_CLI"), reason="set DSD2PCM_CLI to the dsd2pcm-cli 0.1.2 binary (cargo install dsd2pcm-cli --version 0.1.2)")
def test_dsd2pcm_preset_runs_against_the_real_dsd2pcm_cli(tmp_path, monkeypatch):
    import os
    import shutil
    bindir = tmp_path / "bin"
    bindir.mkdir()
    shutil.copy(os.environ["DSD2PCM_CLI"], bindir / "dsd2pcm")
    monkeypatch.setenv("PATH", f"{bindir}:/usr/bin:/bin")
    a = adapters.make_adapter({"adapter": "dsd2pcm", "name": "dsd2pcm"})
    rec = preflight.run(a, 88200, quiet)
    assert rec["checked"].startswith("converted") and rec["output_format"]["bits"] > 0
    b = adapters.make_adapter({"adapter": "dsd2pcm", "name": "d2", "args": "--rate 176400"})
    assert preflight.run(b, 88200, quiet)["rate"] == 176400


def test_sinad_and_thdn_are_one_row_and_thd_has_its_own():
    from dsd_measure.report import summary_rows
    from test_conclusions import metrics
    M = metrics(sinad=110.0)
    M.pop("crosstalk")
    M.pop("reference_floor")
    M["tone_0dbsacd"].update(thdn_percent=0.0003, thd_percent=0.0001)
    labels = [r["label"] for r in summary_rows(M)]
    assert not any(label.startswith("THD+N") for label in labels)
    sinad = next(r for r in summary_rows(M) if r["label"].startswith("SINAD, 1 kHz"))
    assert "THD+N -110.0 dB" in sinad["value"]
    assert any(label.startswith("THD, 1 kHz (harmonics only)") for label in labels)


def test_summary_line_names_the_rows_at_their_own_floor(monkeypatch):
    from dsd_measure import report, run
    rows = [{"label": "SINAD, 1 kHz at 0 dB SACD", "value": "146.8 dB", "flag": False},
            {"label": "Dynamic range, A-weighted", "value": "150.5 dB", "flag": False},
            {"label": "SINAD at the peak level (+3.1 dB SACD)", "value": "129.3 dB", "flag": True}]
    monkeypatch.setattr(report, "summary_rows", lambda M: rows)
    line = run.summary_line("d", {"metrics": {}})
    assert "reference floor (limited by the measurement) in: SINAD at the peak level" in line and "clear of" not in line
    rows[2]["flag"] = False
    assert run.summary_line("d", {"metrics": {}}).endswith("clear of the reference floor")


def test_signals_json_records_the_file_hash_and_the_sample_hash(tmp_path):
    import hashlib

    from dsd_measure.adapters import write_signal_set
    m = write_signal_set(tmp_path, "B", "quick", only=["polarity"])
    e = m["files"][0]
    assert e["sha256"] == hashlib.sha256((tmp_path / e["file"]).read_bytes()).hexdigest()
    assert len(e["samples_sha256"]) == 64 and e["samples_sha256"] != e["sha256"]
    assert json.loads((tmp_path / "signals.json").read_text())["files"][0]["sha256"] == e["sha256"]


def test_stopband_is_reported_as_not_measurable_at_352k():
    from dsd_measure.report import summary_rows
    a = adapters.Reference("r", klass="A", out_rate=352800)
    r = measure.measure_device(a, "quick", only=["alias_tones"], log=quiet)
    assert r["metrics"]["stopband_status"]["measurable"] is False
    row = next(x for x in summary_rows(r["metrics"]) if x["label"].startswith("Stopband"))
    assert row["value"] == "not measurable at this output rate" and "352.8 kHz test signal" in row["hint"]
