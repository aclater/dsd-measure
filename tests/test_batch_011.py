"""Checks added when the 0.1.1 branches were integrated: the peak-level floor (B3), class B filter rows (S5),
the complete signal set (S13), the conclusions' version-2 keys, and the null test's command path."""

import json
import sys
from pathlib import Path

import numpy as np
import pytest

from dsd_measure import adapters, floor, measure
from dsd_measure import conclusions as cn
from dsd_measure import encode as enc
from dsd_measure import signals as sg
from dsd_measure.levels import PEAK_DBFS
from dsd_measure.report import summary_rows, write_device_report

EXAMPLES = Path(__file__).resolve().parent.parent / "examples" / "reference-chain"
QUIET = dict(log=lambda *a, **k: None)


# ----------------------------------------------------------------------------- B3: the peak level

def test_stability_guard_uses_order_8_at_the_peak_level_not_order_7():
    f0 = sg.coherent_freq(1000, 352800, 2**18)
    bits, info = enc.encode(sg.sine(f0, PEAK_DBFS, 88200, 88200), 88200, 2822400)
    assert info["overload_samples"] == 0
    assert (info["order"], info["hinf"]) == (8, 1.3)  # stable at the peak, about 129 dB: 7 dB better than order 7


def test_design_floor_is_measured_for_the_design_used_and_is_higher_than_the_0_db_floor():
    f = floor.design_floor(2822400, 8, 1.3)
    assert f["stable"] and 120 < f["sinad_db"] < 140
    zero = floor.reference_floor(2822400)["chain"]
    assert f["sinad_db"] < -zero["thdn_db"] - 10  # the peak-level floor is well above the 0 dB SACD floor


def test_peak_row_names_the_design_and_flags_a_figure_at_its_floor(tmp_path):
    ad = adapters.Reference("a", klass="A", out_rate=44100)
    r = measure.measure_device(ad, "quick", only=["reference_floor", "levels"], **QUIET)
    pk = r["metrics"]["tone_peak"]
    assert pk["design"] == "order 8, max gain 1.3" and pk["design_floor"]["sinad_db"] > 120
    rows = {x["label"]: x for x in summary_rows(r["metrics"])}
    row = rows["SINAD at the peak level (+3.1 dB SACD, -2.9 dBFS)"]
    assert row["flag"] and "order 8, max gain 1.3" in row["value"] and "floor" in row["value"]
    # every format carries it
    write_device_report(tmp_path, "a", r, {"device": ad.describe(), "profile": "quick", "reference_chain": "1"})
    assert "order 8, max gain 1.3" in (tmp_path / "index.md").read_text()
    assert "order 8, max gain 1.3" in (tmp_path / "index.html").read_text()
    assert "order 8, max gain 1.3" in (tmp_path / "results.csv").read_text() or "tone_peak.design" in (tmp_path / "results.csv").read_text()


def test_peak_flag_needs_a_floor_and_follows_it():
    M = {"reference_floor": {"chain": {"thdn_db": -147, "thd_db": -150, "thdn_a_db": -150, "dr_a_db": 150, "noise_a_dbfs": -160},
                             "decoder_alone": {"thdn_db": -280, "thd_db": -280, "thdn_a_db": -280, "dr_a_db": 340, "noise_a_dbfs": -330}},
         "tone_peak": {"sinad_db": 125.0, "design_floor": {"sinad_db": 129.0}}}
    assert "peak_sinad" in floor.flags("A", M)
    M["tone_peak"]["sinad_db"] = 100.0
    assert "peak_sinad" not in floor.flags("A", M)


# ----------------------------------------------------------------------------- S5: class B filter rows

def test_class_b_has_no_filter_rows_and_keeps_the_decoder_figures_under_their_own_name(tmp_path):
    ad = adapters.Reference("b", klass="B")
    r = measure.measure_device(ad, "quick", only=["impulse", "polarity"], **QUIET)
    M = r["metrics"]
    assert "impulse" not in M and "filter_summary" not in M and "group_delay_us" not in M and "step" not in M
    assert M["reference_decoder_only"]["impulse"]["filter_type"]
    labels = [x["label"] for x in summary_rows(M)]
    assert not any(w in lab for lab in labels for w in ("Filter type", "Ringing", "-0.1 dB", "Group delay"))
    assert "filter" not in r["plots"] and "impulse" not in r["plots"]
    assert any("reference decoder" in n for n in r["notes"])
    write_device_report(tmp_path, "b", r, {"device": ad.describe(), "profile": "quick", "reference_chain": "1"})
    for name in ("index.md", "index.html"):
        text = (tmp_path / name).read_text()
        assert "Filter type" not in text and "Ringing before" not in text


# ----------------------------------------------------------------------------- S13: the complete signal set

def test_signals_writes_what_a_run_feeds_and_the_import_workflow_completes(tmp_path):
    only = ["polarity", "impulse"]
    m = adapters.write_signal_set(tmp_path / "sig", "A", "quick", only=only)
    assert m["errors"] == []
    files = {e["tag"] for e in m["files"]}
    assert files == {"polarity", "impulse", "step", "latency"}  # the impulse test also feeds a step; every time-domain test first finds the delay
    assert json.loads((tmp_path / "sig" / "signals.json").read_text())["files"] == m["files"]
    # play the part of the device: decode each DSF with the reference decoder, save <tag>.wav
    from dsd_measure.dsf import read_dsf
    from dsd_measure.wavio import write_wav
    res = tmp_path / "results"
    res.mkdir()
    ref = adapters.Reference("ref", out_rate=352800)
    for e in m["files"]:
        bits, rate = read_dsf(tmp_path / "sig" / e["file"])
        y, fs = ref.dsd_to_pcm(bits, rate)
        write_wav(res / f"{e['tag']}.wav", y, fs, "float32")
    r = measure.measure_device(adapters.Import("hand", res, klass="A"), "quick", only=only, **QUIET)
    assert r["errors"] == [] and r["not_run"] == {}
    assert r["metrics"]["polarity"] == "normal"


def test_signals_for_class_b_are_wav_files(tmp_path):
    m = adapters.write_signal_set(tmp_path, "B", "quick", only=["polarity"])
    assert [e["file"] for e in m["files"]] == ["latency.wav", "polarity.wav"]  # the delay probe comes first


# ----------------------------------------------------------------------------- conclusions and analysis version 2

def _example(name):
    p = EXAMPLES / name / "results.json"
    if not p.exists():
        pytest.skip("examples not generated")
    d = json.loads(p.read_text())
    return d.get("metrics", d)


@pytest.mark.parametrize("name", ["reference-decoder", "reference-modulator"])
def test_v2_rules_turn_on_with_the_real_keys_and_off_for_version_1(name):
    M = _example(name)
    assert M["analysis_version"] == 2
    on = {c["id"] for c in cn.device_conclusions(M)}
    v1 = dict(M, analysis_version=1)
    off = {c["id"] for c in cn.device_conclusions(v1)}
    if name == "reference-decoder":
        assert {"stopband", "overload", "limits"} <= on
        assert not ({"stopband", "overload"} & off)
        # background noise is one of the figures behind the overall verdict only from version 2 on
        assert any(p == "noise.a_weighted_dbfs" for c in cn.device_conclusions(M) if c["id"] == "limits" for p in c["metrics"])
    else:
        assert "ultrasonic" in on and "ultrasonic" not in off
        txt = next(c for c in cn.device_conclusions(M) if c["id"] == "ultrasonic")["text"]
        assert "20 and 96 kHz" in txt


def test_ultrasonic_level_survives_a_band_key_with_a_dot_and_ignores_a_44_1_khz_decode():
    M = {"noise": {"bands": {"20-20000": -150.0, "20000-22050.0": -140.0}}}
    assert cn.ultrasonic_level(M) is None  # only the decoder's transition band: not ultrasonic noise
    M = {"noise": {"bands": {"20000-40000": -80.0, "40000-96000": -60.0}}}
    lvl, lo, hi, paths, bands = cn.ultrasonic_level(M)
    assert (lo, hi) == (20000.0, 96000.0) and lvl == pytest.approx(-60.0, abs=0.1) and len(paths) == 2


# ----------------------------------------------------------------------------- the null test's command path

def _null_source(tmp_path):
    from types import SimpleNamespace

    from dsd_measure.dsf import write_dsf
    bits = (np.random.default_rng(1).integers(0, 2, 2822400 // 10) * 2 - 1).astype(np.int8)
    p = tmp_path / "src.dsf"
    write_dsf(p, bits, 2822400)
    return SimpleNamespace(path=p, kind="dsf", rate=2822400)


def test_null_command_device_runs_without_a_shell_and_leaves_other_braces_alone(tmp_path):
    from dsd_measure.nulltest.devices import FileDevice
    script = tmp_path / "t.py"
    script.write_text("import sys, numpy as np\nfrom dsd_measure.wavio import write_wav\n"
                      "open(sys.argv[3], 'w').write(sys.argv[1])\n"
                      "write_wav(sys.argv[2], np.zeros(4410), 44100, 'float32')\n")
    seen = tmp_path / "seen"
    # ';touch ...' and {braces} are plain words: with a shell the first would run, the second would have crashed .format
    dev = FileDevice("t", f"{sys.executable} {script} ';touch {tmp_path / 'pwned'} {{x}}' {{output}} {seen}")
    assert dev.shell is False
    track, info = dev.prepare(_null_source(tmp_path), tmp_path / "w")
    assert seen.read_text() == f";touch {tmp_path / 'pwned'} {{x}}"
    assert not (tmp_path / "pwned").exists() and info["output_sha256"]
    assert track.rate == 44100


def test_null_command_device_shell_true_is_opt_in(tmp_path):
    from dsd_measure.nulltest.devices import FileDevice
    marker = tmp_path / "marker"
    dev = FileDevice("t", f"touch {marker} && python3 -c 'import sys;sys.exit(3)' {{output}}", shell=True)
    with pytest.raises(RuntimeError, match="command failed"):
        dev.prepare(_null_source(tmp_path), tmp_path / "w")
    assert marker.exists()  # '&&' only means something with a shell


def test_null_command_device_times_out(tmp_path):
    from dsd_measure.nulltest.devices import FileDevice
    dev = FileDevice("t", f"{sys.executable} -c \"import time; time.sleep(30)\" {{output}}", timeout=0.5)
    with pytest.raises(TimeoutError):
        dev.prepare(_null_source(tmp_path), tmp_path / "w")


# ----------------------------------------------------------------------------- nits from the review

def test_alias_image_is_read_at_the_folded_frequency():
    ad = adapters.Reference("a", klass="A", out_rate=44100)
    r = measure.measure_device(ad, "quick", only=["alias_tones"], **QUIET)
    rows = r["metrics"]["alias_tones"]["rows"]
    assert rows
    for row in rows:
        assert abs(row["alias_hz"] - (44100 - row["tone_hz"])) < 1.0  # not "the largest bin"
        assert row["image_db"] < -100  # the reference decoder rejects images


def test_noise_results_say_how_many_averages_were_used():
    from dsd_measure import analyse as an
    x = np.random.default_rng(1).standard_normal(2**18 * 3)
    out, _, _ = an.noise_floor(x, 352800, nfft=2**18, nseg=8)
    assert out["averages"] == 5  # a short record gets fewer than the 8 asked for, and says so
    assert an.welch_segments(2**18 * 20, 2**18, 8) == 8


def test_two_devices_that_share_a_report_folder_are_refused(tmp_path):
    from dsd_measure.run import run_suite
    s = tmp_path / "s.toml"
    s.write_text('[[device]]\nname = "my dac"\nadapter = "reference"\n[[device]]\nname = "my-dac"\nadapter = "reference"\n')
    with pytest.raises(ValueError, match="report folder"):
        run_suite(s, tmp_path / "o", "quick", log=lambda *a, **k: None)



def test_cli_signals_only_and_class_option(tmp_path, capsys):
    from dsd_measure import cli
    assert cli.main(["signals", str(tmp_path / "s"), "--only", "polarity"]) == 0
    assert "wrote 2 test signals (class A, profile quick)" in capsys.readouterr().out
    assert (tmp_path / "s" / "polarity.dsf").exists() and (tmp_path / "s" / "signals.json").exists()
    assert cli.main(["signals", str(tmp_path / "b"), "--class", "B", "--only", "polarity"]) == 0
    assert (tmp_path / "b" / "polarity.wav").exists()


# ----------------------------------------------------------------------------- the committed example

def test_example_columns_agree():
    """The reference chain's decoder and modulator are two halves of one chain: the same signals must read alike."""
    dec, mod = _example("reference-decoder"), _example("reference-modulator")
    assert dec["analysis_version"] == mod["analysis_version"] == 2
    pairs = [("SINAD", dec["tone_0dbsacd"]["sinad_db"], mod["tone_0dbsacd"]["sinad_db"], 1.0),
             ("dynamic range (A)", dec["dynamic_range"]["dr_a_db"], mod["dynamic_range"]["dr_a_db"], 1.0),
             ("noise (A)", dec["noise"]["a_weighted_dbfs"], mod["noise"]["a_weighted_dbfs"], 1.0),
             ("peak-level SINAD", dec["tone_peak"]["sinad_db"], mod["tone_peak"]["sinad_db"], 1.5),
             ("IMD CCIF", dec["imd_ccif"]["imd_db"], mod["imd_ccif"]["imd_db"], 2.5),  # the 44.1 kHz decoder column sees the 20 kHz tone on its roll-off
             ("multitone range", dec["multitone"]["headline"]["distortion_free_range_db"],
              mod["multitone"]["headline"]["distortion_free_range_db"], 5.0)]
    for name, a, b, tol in pairs:
        assert abs(a - b) <= tol, (name, a, b)


def test_example_reports_open_with_conclusions_and_the_release_version():
    from dsd_measure import __version__
    for name in ("reference-decoder", "reference-modulator"):
        md = (EXAMPLES / name / "index.md").read_text()
        if "Conclusions" not in md:
            pytest.skip("examples not generated")
        assert md.index("## Conclusions") < md.index("| Metric | Value |")
        assert f"dsd-measure {__version__}" in md
