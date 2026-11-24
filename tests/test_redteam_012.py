"""The 0.1.2 review fixes: measurement language only, no AES17 claim, fairness inputs, every word length, the limits page."""

import copy
import json
import re
import stat
import sys
from pathlib import Path

import numpy as np
import pytest

from dsd_measure import adapters
from dsd_measure import conclusions as cn
from dsd_measure import outformat as of
from dsd_measure.report import write_comparison
from dsd_measure.run import run_suite

ROOT = Path(__file__).resolve().parent.parent

# ----------------------------------------------------------------------------- 1. wording

#: Words that make an audibility, ranking or compliance claim. They may not appear in any verdict, report text, README or doc.
BANNED = re.compile(
    r"\binaudible\b|\binaudibility\b|would be audible|not audible|technical, not|\btransparent\b|\bbeats\b|\bkinder\b|"
    r"audible risk|indistinguishable|far below audib|well below audib|below audibility|sounds better|\b\d+ dB better\b|"
    r"dB better than|is better than|at least (this|that) good|normal for DSD|pre-echo|music-like|the treble is|the usual .DR. figure|reviewers quote|not expected to sound|too little to change|AES17[- ]compliant|compliant with AES17|AP-grade",
    re.I)

#: Files whose text a reader sees. The changelog keeps its history and the examples are generated.
TEXT_FILES = [ROOT / "README.md", ROOT / "CONTRIBUTING.md", *sorted((ROOT / "docs").glob("*.md")),
              *sorted((ROOT / "src" / "dsd_measure").rglob("*.py")), *sorted((ROOT / "examples" / "suites").glob("*.toml")),
              ROOT / "examples" / "README.md"]


def test_no_audibility_or_ranking_words_in_the_tree():
    bad = []
    for p in TEXT_FILES:
        for n, line in enumerate(p.read_text().splitlines(), 1):
            m = BANNED.search(line)
            if m:
                bad.append(f"{p.relative_to(ROOT)}:{n}: {m.group(0)}")
    assert not bad, bad


def test_the_shipped_example_reports_use_the_same_language():
    bad = []
    for p in sorted((ROOT / "examples" / "reference-chain").rglob("index.md")):
        text = p.read_text()
        if BANNED.search(text) or re.search(r"quieter is better|is better\.|excellent\)|audible", text):
            bad.append(str(p.relative_to(ROOT)))
    assert not bad, bad


def test_verdict_labels_and_meanings_make_no_claim_about_hearing():
    for label, meaning in cn.VERDICTS.values():
        assert not re.search(r"audib|\bhear|heard|transparent|sound", label + " " + meaning, re.I), (label, meaning)
    for name, t in cn.THRESHOLDS.items():
        assert not BANNED.search(t["meaning"]), name


def test_cd_floor_threshold_is_not_called_settled_and_cites_both_sides():
    t = cn.THRESHOLDS["dither16_db"]
    assert t["settled"] is False
    text = t["meaning"]
    assert "14 dB" in text and "no input signal" in text and "Meyer and Moran" in text and "Reiss" in text and "small but" in text
    assert "calculation" in text


def test_unchecked_sources_are_marked():
    for name in ("range_120_db", "flat_db", "level_jnd_db", "group_delay_ms"):
        assert not cn.THRESHOLDS[name]["settled"]
        assert all("not checked" in label for label, _ in cn.THRESHOLDS[name]["sources"]), name
    doc = (ROOT / "docs" / "conclusions.md").read_text()
    assert doc.count("cited, not checked against the paper") >= 4


def _two_results(delta):
    ex = ROOT / "examples" / "reference-chain" / "reference-decoder" / "results.json"
    base = json.loads(ex.read_text())
    a = {**base, "plots": {}}
    b = copy.deepcopy(a)
    b["metrics"]["tone_0dbsacd"]["sinad_db"] -= delta
    b["metrics"]["tone_0dbsacd"]["thdn_db"] += delta
    return [("one", a), ("two", b)]


@pytest.mark.parametrize("delta", [0.01, 3.0])
def test_comparison_table_marks_no_better_cell(tmp_path, delta):
    write_comparison(tmp_path / "c", _two_results(delta), {"profile": "quick"})
    html = (tmp_path / "c" / "index.html").read_text()
    assert "v best" not in html and "font-weight:700" not in html.split("</style>")[0].split(".best")[-1][:20]
    assert "No cell is marked" in html and "no repeatability interval has been measured yet" in html
    md = (tmp_path / "c" / "index.md").read_text()
    assert not BANNED.search(md) and not BANNED.search(html)


def test_comparison_says_how_far_apart_without_naming_the_better_one():
    from test_conclusions import CLI, metrics
    cs = cn.comparison_conclusions([("A", metrics(sinad=100.0, dr=120, smpte=-120, ccif=-120), CLI),
                                    ("B", metrics(sinad=130.0, dr=140, smpte=-140, ccif=-140), CLI)])
    text = " ".join(c["text"] for c in cs)
    assert "reads" in text and "a difference of" in text and ("ranks nothing" in text or "not a ranking" in text)
    assert "No repeatability interval has been measured yet" in text
    assert not BANNED.search(text) and "better" not in text.lower() and "worse" not in text.lower()


# ----------------------------------------------------------------------------- 2. AES17

def test_no_text_attributes_the_weighting_or_the_notch_to_aes17():
    for p in TEXT_FILES:
        for n, line in enumerate(p.read_text().splitlines(), 1):
            if "AES17" not in line:
                continue
            low = line.lower()
            if "a-weighting" in low and "not" not in low and "differ" not in low:
                pytest.fail(f"{p.name}:{n}: A-weighting attributed to AES17")
            assert "the aes17 method" not in low and "aes17 method" not in low, f"{p.name}:{n}"
            assert "follow it" not in low or "only" in low, f"{p.name}:{n}"


def test_the_limits_page_lists_each_aes17_difference():
    t = (ROOT / "docs" / "methodology-limits.md").read_text()
    for needle in ("997 Hz", "CCIR-RMS", "Q between 1.2 and 3", "5.2.8", "6.4.1", "6.3.2", "5.1.3"):
        assert needle in t, needle
    assert "Only the 20 kHz band edge and the dBFS-re-sine convention follow AES17-2020" in t


def test_legend_says_these_are_not_aes17_measurements():
    from dsd_measure.report import LEGEND
    assert "not AES17 measurements" in LEGEND and "997 Hz" in LEGEND and "CCIR-RMS" in LEGEND


# ----------------------------------------------------------------------------- 3. fairness inputs

def test_sox_default_modulator_is_sdm_8_and_the_level_mapping_is_recorded(tmp_path):
    a = adapters.ReftoolSox("s", "unused", klass="B", workdir=tmp_path)
    assert a.modulator == "sdm-8"
    m = a.level_mapping()
    assert "25 % modulation" in m and "50 %" in m
    b = adapters.ReftoolSox("s", "unused", klass="B", workdir=tmp_path, input_gain_db=6.0206)
    assert "50 % modulation" in b.level_mapping()
    assert a.describe()["detail"]["level_mapping"] == m
    assert adapters.ReftoolSox("s", "unused", klass="A").level_mapping().startswith("not applicable")


def _script(path, body):
    path.write_text("#!/bin/sh\n" + body)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def test_cli_adapter_records_version_and_executable_hash(tmp_path):
    exe = _script(tmp_path / "mytool", 'if [ "$1" = "--version" ]; then echo "mytool 4.5.6 (build 7)"; echo second; exit 0; fi\n')
    a = adapters.Cli("t", f"{exe} {{input}} {{output}}")
    v = a.tool_versions()
    assert v["version"] == "mytool 4.5.6 (build 7)" and v["sha256"] == adapters.sha256_file(exe)
    assert v["path"] == str(exe.resolve()) and v["program"] == str(exe)


def test_a_program_that_prints_no_version_is_recorded_as_none_not_guessed(tmp_path):
    exe = _script(tmp_path / "quiet", "exit 1\n")
    v = adapters.Cli("t", f"{exe} {{input}} {{output}}").tool_versions()
    assert v["version"] is None and v["sha256"]
    assert adapters.Cli("t", "no-such-program-here {input} {output}").tool_versions()["sha256"] is None


def test_a_version_command_and_a_declared_version(tmp_path):
    wrapper = _script(tmp_path / "wrap", "exit 3\n")
    vc = _script(tmp_path / "vc", "echo 'realtool 9.9'\n")
    a = adapters.Cli("t", f"{wrapper} x {{input}} {{output}}", version_command=str(vc), version="9.9 declared")
    v = a.tool_versions()
    assert v["version"] == "realtool 9.9" and v["declared_version"] == "9.9 declared"


def test_reference_and_import_adapters_identify_themselves(tmp_path):
    r = adapters.Reference("r").tool_versions()
    assert r["version"] and r["reference_chain"]
    i = adapters.Import("i", tmp_path).tool_versions()
    assert i["version"] is None and "cannot know" in i["note"]


def test_versions_and_hashes_reach_the_provenance_and_results(tmp_path):
    exe = Path(__file__).with_name("stubtool.py")
    suite = tmp_path / "s.toml"
    suite.write_text(f'[suite]\nname = "t"\nprofile = "quick"\n[[device]]\nname = "stub"\nadapter = "cli"\nclass = "A"\n'
                     f'command = "{sys.executable} {exe} {{input}} {{output}}"\nversion = "stub 1.0"\n')
    out, failed = run_suite(suite, tmp_path / "out", "quick", only=["levels"], log=lambda *a, **k: None)
    prov = json.loads((out / "stub" / "provenance.json").read_text())
    dv = prov["device_versions"]
    assert dv["declared_version"] == "stub 1.0" and dv["sha256"] == adapters.sha256_file(sys.executable)
    assert json.loads((out / "stub" / "results.json").read_text())["device_versions"] == dv
    assert "Device executable SHA-256" in (out / "stub" / "index.html").read_text()


def _cmp_metrics(out_rate, kind="float", bits=32):
    from test_conclusions import metrics
    M = metrics(sinad=140.0, dr=145.0, smpte=-140, ccif=-140)
    M["output_format"] = {"container": "wav", "kind": kind, "bits": bits, "rate": out_rate, "text": f"{bits}-bit {kind}"}
    M["dsd_rate"] = 2822400
    return M


def test_different_output_rates_are_not_like_for_like():
    from test_conclusions import CLI
    a, b = _cmp_metrics(352800), _cmp_metrics(176400)
    assert cn.like_for_like([("a", a), ("b", b)])[0] is False
    cs = cn.comparison_conclusions([("a", a, CLI), ("b", b, CLI)])
    ids = [c["id"] for c in cs]
    assert "cmp-conditions" in ids and "cmp-distortion" not in ids and "cmp-overall" not in ids
    c = next(c for c in cs if c["id"] == "cmp-conditions")
    assert c["verdict"] == "not-like-for-like" and "352.8 kHz" in c["text"] and "176.4 kHz" in c["text"]
    h = cn.comparison_headline([("a", a, CLI), ("b", b, CLI)], cs)
    assert h.startswith("Result: not like-for-like.") and "not compared" in h


def test_float32_and_float64_at_one_rate_are_like_for_like():
    from test_conclusions import CLI
    a, b = _cmp_metrics(352800, "float", 32), _cmp_metrics(352800, "float", 64)
    assert cn.like_for_like([("a", a), ("b", b)])[0] is True
    assert "cmp-conditions" not in [c["id"] for c in cn.comparison_conclusions([("a", a, CLI), ("b", b, CLI)])]


def test_a_comparison_run_warns_and_the_report_says_so(tmp_path):
    suite = tmp_path / "s.toml"
    suite.write_text('[suite]\nname = "t"\nprofile = "quick"\n'
                     '[[device]]\nname = "a"\nadapter = "reference"\nclass = "A"\nout_rate = 44100\n'
                     '[[device]]\nname = "b"\nadapter = "reference"\nclass = "A"\nout_rate = 88200\n')
    lines = []
    out, _ = run_suite(suite, tmp_path / "out", "quick", only=["levels"], log=lambda m="", end="\n": lines.append(m))
    assert any(l.startswith("WARNING: not like-for-like") for l in lines)  # noqa: E741
    cj = json.loads((out / "comparison" / "results.json").read_text())
    assert cj["like_for_like"] is False and "44.1 kHz" in cj["conditions"]["a"] and "88.2 kHz" in cj["conditions"]["b"]


# ----------------------------------------------------------------------------- 4. word length

@pytest.mark.parametrize("bits, rate, plain, dithered", [
    (16, 44100, 92.5, 87.7), (24, 44100, 140.7, 135.9), (24, 88200, 143.7, 138.9), (24, 176400, 146.7, 141.9), (24, 352800, 149.7, 144.9),
    (20, 88200, 119.6, 114.8)])
def test_integer_bounds_for_any_word_length(bits, rate, plain, dithered):
    assert of.quantisation_sinad_db(bits, rate) == pytest.approx(plain, abs=0.06)
    assert of.quantisation_sinad_db(bits, rate, dithered=True) == pytest.approx(dithered, abs=0.06)
    s = of.summary({"container": "wav", "kind": "int", "bits": bits, "rate": rate})
    assert s["quantisation_sinad_db"] == pytest.approx(plain, abs=0.06)
    assert s["quantisation_sinad_dithered_db"] == pytest.approx(dithered, abs=0.06)
    assert of.limits_result({"kind": "int", "bits": bits}) and not of.limits_result({"kind": "float", "bits": 32})


def _fmt_metrics(bits, rate, sinad):
    from test_conclusions import metrics
    f = {"container": "wav", "kind": "int", "bits": bits, "rate": rate, "text": f"{bits}-bit integer"}
    return metrics(sinad=sinad, dr=sinad + 3, smpte=-sinad, ccif=-sinad, output_format={**f, **of.summary(f)})


def test_a_perfect_decoder_writing_dithered_24_bit_at_44k_is_not_ranked():
    from test_conclusions import CLI, metrics
    m = _fmt_metrics(24, 44100, 135.9)  # the dithered bound
    assert cn.format_limit(m)
    c = cn.device_conclusions(m, CLI)[0]
    assert c["id"] == "overall" and c["verdict"] == "format-limited"
    assert "24-bit integer PCM" in c["text"] and "140.7 dB (plain rounding) or 135.9 dB (TPDF dither)" in c["text"]
    h = cn.device_headline(m, CLI, "tool")
    assert h.startswith("Result: not judged.") and "135.9 dB" in h
    float_dev = metrics(sinad=146.0, dr=150.0)
    float_dev["output_format"] = {"container": "wav", "kind": "float", "bits": 32, "rate": 44100, "text": "32-bit float"}
    cs = cn.comparison_conclusions([("float", float_dev, CLI), ("int24", m, CLI)])
    ids = [c["id"] for c in cs]
    assert "cmp-distortion" not in ids and "cmp-overall" not in ids  # no 11 dB "difference" from the container


@pytest.mark.parametrize("bits, rate, sinad, limited", [
    (24, 44100, 135.9, True), (24, 44100, 140.7, True), (24, 44100, 146.0, True), (24, 44100, 148.0, False),
    (24, 44100, 128.0, False),  # the device's own noise is well below its format
    (20, 88200, 115.0, True), (32, 352800, 147.0, False), (16, 44100, 88.0, True), (16, 44100, 98.0, True), (16, 44100, 99.0, False), (16, 44100, 105.0, False)])
def test_format_limit_at_every_width(bits, rate, sinad, limited):
    assert bool(cn.format_limit(_fmt_metrics(bits, rate, sinad))) == limited


def test_float_output_is_never_format_limited():
    from test_conclusions import metrics
    M = metrics(sinad=146.0)
    M["output_format"] = {"container": "wav", "kind": "float", "bits": 32, "rate": 44100, "text": "32-bit float"}
    assert cn.format_limit(M) is None


def test_the_report_row_shows_width_rate_and_both_bounds():
    from dsd_measure.report import summary_rows
    base = json.loads((ROOT / "examples" / "reference-chain" / "reference-decoder" / "results.json").read_text())["metrics"]
    m = copy.deepcopy(base)
    m["tone_0dbsacd"]["sinad_db"] = 135.9
    m["output_format"] = of.summary({"container": "wav", "kind": "int", "bits": 24, "rate": 44100})
    m["output_format"]["text"] = "24-bit integer"
    v = {r["label"]: r for r in summary_rows(m)}["Output format"]["value"]
    assert "24-bit integer, 44.1 kHz" in v and "140.7 dB" in v and "135.9 dB" in v and "limits this result" in v
    m["output_format"] = {"container": "wav", "kind": "float", "bits": 32, "rate": 352800, "text": "32-bit float"}
    assert "32-bit float, 352.8 kHz" == {r["label"]: r for r in summary_rows(m)}["Output format"]["value"]


def test_the_preflight_warning_covers_24_bit():
    w = of.warning({"container": "wav", "kind": "int", "bits": 24, "rate": 44100})
    assert "140.7 dB with plain rounding or 135.9 dB with TPDF dither" in w and "floating-point" in w
    assert of.warning({"container": "wav", "kind": "float", "bits": 32, "rate": 44100}) is None


def test_null_test_format_limit_covers_24_bit():
    from dsd_measure.nulltest.verdict import apply_format_limit
    lsb = 2.0 ** (1 - 24)
    noise = float(10 * np.log10(lsb * lsb / 12 * (20000 / 22050)))
    v = {"headline": "h", "details": []}
    ch = {"diff_rms_audio_dbfs": noise + 3.0, "music_rms_audio_dbfs": -20.0}
    fmt = {"kind": "int", "bits": 24, "rate": 44100}
    out = apply_format_limit(v, ch, [("dev", fmt)])
    assert out.get("format_limited") == ["dev"]
    far = apply_format_limit({"headline": "h", "details": []}, {**ch, "diff_rms_audio_dbfs": noise + 30.0}, [("dev", fmt)])
    assert "format_limited" not in far


# ----------------------------------------------------------------------------- 5. the limits page

def test_the_limits_page_exists_is_linked_and_lists_the_not_claimed_items():
    page = (ROOT / "docs" / "methodology-limits.md").read_text()
    assert "# Methodology limits" in page and page.rstrip().endswith("Part of the [DSD Toolbox](https://github.com/dsd-toolbox/dsd-toolbox).")
    for needle in ("higher quality than", "output rate, one modulator or one output format", "Audibility of anything", "AES17 measurements or conformance",
                   "Independent validation", "same numbers on any machine", "repeatability interval", "idle tones",
                   "hardware DACs"):
        assert needle in page, needle
    assert "docs/methodology-limits.md" in (ROOT / "README.md").read_text()
    assert "methodology-limits.md" in (ROOT / "docs" / "README.md").read_text()


def test_the_example_sox_suite_runs_the_best_documented_settings_first():
    s = (ROOT / "examples" / "suites" / "sox.toml").read_text()
    assert s.index('modulator = "sdm-8"') < s.index('modulator = "clans-8"')
    assert "input_gain_db = 6.0206" in s


def test_citation_file_matches_the_release():
    import tomllib
    cff = (ROOT / "CITATION.cff").read_text()
    version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    assert f'version: "{version}"' in cff and "cff-version: 1.2.0" in cff
    assert "repository-code: \"https://github.com/dsd-toolbox/dsd-measure\"" in cff and "Apache-2.0" in cff
    assert "CITATION.cff" in (ROOT / "README.md").read_text()


def test_citation_license_is_one_spdx_string():
    lines = [ln for ln in (ROOT / "CITATION.cff").read_text().splitlines() if ln.startswith("license:")]
    assert lines == ["license: Apache-2.0"]  # Zenodo rejects a list or an expression
    readme = (ROOT / "README.md").read_text()
    assert "MIT OR Apache-2.0" in readme and "LICENSE-MIT" in readme and "LICENSE-APACHE" in readme
