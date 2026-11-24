"""Conclusions: one test per rule with its boundary cases, and checks that every conclusion is backed."""

import copy
import json
import re
from pathlib import Path

import pytest

from dsd_measure import conclusions as cn
from dsd_measure.report import write_comparison, write_device_report

ROOT = Path(__file__).resolve().parent.parent
CLI = {"adapter": "cli", "class": "A", "name": "tool"}
REF = {"adapter": "reference", "class": "A", "name": "reference decoder"}


def metrics(klass="A", sinad=110.0, dr=112.0, smpte=-108.0, ccif=-105.0, **over):
    """Synthetic metrics of a device well clear of a -147 dB reference floor."""
    M = {
        "device_class": klass, "dsd_rate": 2822400,
        "reference_floor": {"dsd_rate": 2822400, "margin_db": 6.0,
                            "chain": {"thdn_db": -147.0, "thd_db": -163.0, "thdn_a_db": -150.0, "sinad_db": 147.0,
                                      "noise_a_dbfs": -151.6, "dr_a_db": 151.8},
                            "decoder_alone": {"thdn_db": -280.0, "thd_db": -310.0, "thdn_a_db": -282.0, "sinad_db": 280.0,
                                              "noise_a_dbfs": -351.0, "dr_a_db": 342.0}},
        "tone_0dbsacd": {"sinad_db": sinad, "thdn_db": -sinad, "thd_db": -sinad - 6, "thdn_a_db": -sinad - 2},
        "tone_peak": {"sinad_db": 40.0},
        "dynamic_range": {"dr_a_db": dr},
        "imd_smpte": {"imd_db": smpte}, "imd_ccif": {"imd_db": ccif},
        "gain_error_db": 0.002,
        "linearity": {"lowest_level_within_0p5_db": -123.0},
        "frequency_response": {"ripple_pp_db": 0.02, "at_hz": {"20": 0.0, "1000": 0.0, "10000": -0.01, "20000": -0.02}},
        "crosstalk": {"1000": {"left_to_right_db": -150.0, "right_to_left_db": -150.0, "gain_diff_db": 0.0}},
        "noise": {"a_weighted_dbfs": -60.0, "bands": {"20-20000": -58.0, "20000-40000": -80.0, "40000-96000": -40.0}},
        "multitone": {"headline": {"distortion_free_range_db": 30.0}},
        "jtest": {"largest_sideband_db": -20.0},
        "impulse": {"filter_type": "linear phase", "pre_ringing_ms": 0.67, "post_ringing_ms": 0.67},
        "filter_summary": {"minus_0p1_db_hz": 20900.0, "minus_3_db_hz": 21800.0, "stopband_worst_db": -140.0, "stopband_tested_hz": [24100.0, 34100.0]},
        "group_delay_us": {"at_1k": 0.0, "at_20k": 0.3},
        "polarity": "normal",
        "overload_recovery": {"recovery_ms": 400.0},
    }
    M.update(over)
    return M


FMT16 = {"container": "wav", "kind": "int", "bits": 16, "rate": 352800, "text": "16-bit integer", "quantisation_sinad_db": 101.5,
         "quantisation_sinad_dithered_db": 96.8}


def by_id(cs):
    return {c["id"]: c for c in cs}


def dev(M, device=CLI):
    return by_id(cn.device_conclusions(M, device))


# ----------------------------------------------------------------------------- overall verdict

@pytest.mark.parametrize("worst, verdict", [
    (140.0, "margin-120"), (120.0, "margin-120"), (119.99, "margin-87"),
    (87.0, "margin-87"), (86.99, "margin-low"), (40.0, "margin-low")])
def test_overall_tiers_and_boundaries(worst, verdict):
    c = dev(metrics(sinad=worst, dr=150, smpte=-150, ccif=-150))["overall"]
    assert c["verdict"] == verdict
    assert c["verdict"] == verdict and "tone_0dbsacd.sinad_db" in c["metrics"]
    assert "not a listening test" in c["text"]


def test_overall_names_the_weakest_figure_and_rounds_down():
    c = dev(metrics(sinad=130, dr=131, smpte=-125, ccif=-119.6))["overall"]
    assert c["verdict"] == "margin-87"
    assert "at least 119 dB" in c["text"] and "19 kHz with 20 kHz" in c["text"]  # 119.6 is never shown as 120


def test_overall_says_at_least_when_the_weakest_figure_is_at_the_floor():
    c = dev(metrics(sinad=143.0, dr=150, smpte=-150, ccif=-150))["overall"]
    assert c["verdict"] == "margin-120" and "the tool cannot show more" in c["text"]
    assert "the tool cannot show more" not in dev(metrics(sinad=130, dr=150, smpte=-150, ccif=-150))["overall"]["text"]


def test_unvalidated_figures_never_reach_a_verdict():
    """Peak-level SINAD, noise, multitone, the J-Test and the stopband are poor here, and must be ignored."""
    cs = dev(metrics(sinad=130, dr=130, smpte=-130, ccif=-130))
    assert cs["overall"]["verdict"] == "margin-120"
    used = {m for c in cs.values() if c["id"] != "pending" for m in c["metrics"]}
    for bad in ("tone_peak", "noise", "multitone", "jtest", "filter_summary", "impulse", "overload_recovery", "polarity"):
        assert not any(m.split(".")[0] == bad for m in used), bad
    p = cs["pending"]
    assert p["verdict"] == "pending" and "peak-level SINAD" in p["text"] and "filter and ringing" in p["text"]
    assert "ultrasonic" not in cs and "filter" not in cs


def test_noise_counts_from_analysis_version_2():
    M = metrics(sinad=130, dr=130, smpte=-130, ccif=-130, analysis_version=2)
    c = dev(M)["overall"]
    assert c["verdict"] == "margin-low" and "background noise" in c["text"].lower()  # -60 dBFS is 53 dB below the reference
    assert "is 53 dB below" in c["text"]
    M["noise"]["a_weighted_dbfs"] = -140.0
    assert dev(M)["overall"]["verdict"] == "margin-120"


def test_no_overall_without_a_validated_figure():
    assert "overall" not in dev({"device_class": "A", "polarity": "normal"})


# ----------------------------------------------------------------------------- floor, limits

def test_reference_device_gets_the_floor_conclusion_not_a_verdict():
    cs = dev(metrics(sinad=146.7, dr=150.5), REF)
    assert "overall" not in cs and "limits" not in cs
    f = cs["floor"]
    assert f["verdict"] == "floor" and "147.0 dB" in f["text"] and "within 6 dB" in f["text"] and "141.0 dB" in f["text"]
    assert "cannot be ranked" in f["text"]


@pytest.mark.parametrize("sinad, flagged", [(141.0, True), (140.99, False)])
def test_limits_boundary_at_six_db(sinad, flagged):
    cs = dev(metrics(sinad=sinad, dr=120))
    assert ("limits" in cs) == flagged
    if flagged:
        assert "1 figure (SINAD)" in cs["limits"]["text"] and "tool's limit, not the device's" in cs["limits"]["text"]


def test_limits_counts_figures():
    M = metrics(sinad=146.0, dr=150.0)
    M["tone_0dbsacd"]["thd_db"] = -160.0
    t = dev(M)["limits"]["text"]
    assert "3 figures (SINAD, THD and dynamic range)" in t


# ----------------------------------------------------------------------------- response, level

@pytest.mark.parametrize("ripple, start, verdict", [
    (0.1, "Flat response", "fact"), (0.11, "Nearly flat response", "fact"),
    (0.5, "Nearly flat response", "fact"), (0.51, "Uneven response", "notable")])
def test_response_boundaries(ripple, start, verdict):
    M = metrics()
    M["frequency_response"]["ripple_pp_db"] = ripple
    c = dev(M)["response"]
    assert c["text"].startswith(start) and c["verdict"] == verdict


@pytest.mark.parametrize("gain, unity", [(0.1, True), (-0.1, True), (0.11, False), (-6.02, False)])
def test_level_gain_boundary(gain, unity):
    c = dev(metrics(gain_error_db=gain))["level"]
    assert ("unity gain within" in c["text"]) == unity
    assert c["verdict"] == ("fact" if unity else "notable")
    if not unity:
        assert "match levels" in c["text"] and ("higher" if gain > 0 else "lower") in c["text"]


def test_level_never_understates_a_difference():
    c = dev(metrics(gain_error_db=0.0123))["level"]
    assert "unity gain within 0.02 dB" in c["text"]
    assert "channels matched within 0.01 dB" in c["text"] and "-123 dBFS" in c["text"]
    assert "polarity" not in c["text"]  # not validated yet


def test_level_channel_mismatch():
    M = metrics()
    M["crosstalk"]["1000"]["gain_diff_db"] = 0.8
    c = dev(M)["level"]
    assert "channels differ by 0.80 dB" in c["text"] and c["verdict"] == "notable"


# ----------------------------------------------------------------------------- gated rules

def test_filter_rule_when_enabled(monkeypatch):
    monkeypatch.setattr(cn, "UNREVIEWED_VALIDATED", True)
    c = dev(metrics())["filter"]
    assert c["verdict"] == "no-threshold" and c["text"].startswith("Linear phase filter, flat within 0.1 dB up to 20.9 kHz")
    assert "0.67 ms before" in c["text"] and "does not agree on a limit" in c["text"] and "no verdict" in c["text"]
    assert "rejects images" not in c["text"]  # the stopband needs analysis version 2
    M = metrics(analysis_version=2)
    M["impulse"] = {"filter_type": "minimum phase", "pre_ringing_ms": 0.0, "post_ringing_ms": 1.2}
    M["group_delay_us"] = {"at_1k": 0.0, "at_20k": 300.0}
    c = dev(M)["filter"]
    assert c["text"].startswith("Minimum phase filter") and "0.30 ms" in c["text"] and "below the 1 ms reference line" in c["text"]
    assert "rejects images by at least 140 dB (tones from 24.1 to 34.1 kHz)" in c["text"] and "polarity is correct" in dev(M)["level"]["text"]
    assert "filter" not in dev(metrics(klass="B"))  # for a modulator the filter rows describe the reference decoder


def test_ultrasonic_rule_from_analysis_version_2():
    M = metrics(klass="B", analysis_version=2, ultrasonic={"integrated_dbfs": {"20000-40000": -82.0, "40000-96000": -38.0,
                                                                              "96000-192000": -29.0}})
    c = dev(M)["ultrasonic"]
    assert c["verdict"] == "no-threshold" and "-38 dBFS between 20 and 96 kHz" in c["text"] and "no agreed limit" in c["text"]
    assert cn.ultrasonic_level(M)[0] == pytest.approx(-38.0, abs=0.01)
    del M["ultrasonic"]  # a class A device: whatever its output rate carries
    assert "-40 dBFS between 20 and 96 kHz" in dev(M)["ultrasonic"]["text"]
    assert "ultrasonic" not in dev(metrics(klass="B", ultrasonic={"integrated_dbfs": {"20000-40000": -82.0}}))


def test_stability_rule_when_enabled(monkeypatch):
    lv = {"0 dB SACD": {"saturated": False, "thdn_drift_db": 0.18}, "+3.1 dB SACD (peak)": {"saturated": False, "thdn_drift_db": -0.03}}
    M = metrics(klass="B", stability={"hold_s": 60.0, "levels": lv})
    assert "stability" not in dev(M) and "modulator stability" in dev(M)["pending"]["text"]
    monkeypatch.setattr(cn, "UNREVIEWED_VALIDATED", True)
    c = dev(M)["stability"]
    assert c["text"].startswith("Stable") and "0.18 dB" in c["text"] and "overload" not in c["text"]
    lv["+3.1 dB SACD (peak)"]["saturated"] = True
    c = dev(M)["stability"]
    assert c["text"].startswith("Unstable") and c["verdict"] == "notable"


def test_rates_rule():
    M = metrics(klass="B", rates={"DSD128": {"sinad_db": 175.8}, "DSD256": {"sinad_db": 177.8}})
    assert dev(M)["rates"]["text"] == "By rate: SINAD is 110 dB at DSD64, 176 dB at DSD128 and 178 dB at DSD256."


# ----------------------------------------------------------------------------- comparison

def cmp(a, b, da=CLI, db=CLI):
    return by_id(cn.comparison_conclusions([("A", a, da), ("B", b, db)]))


def test_comparison_indistinguishable():
    cs = cmp(metrics(), metrics(sinad=110.9))  # under 1 dB apart
    assert cs["cmp-overall"]["verdict"] == "same"
    assert "A and B measure the same in the audio band" in cs["cmp-overall"]["text"]
    assert cs["cmp-distortion"]["verdict"] == "same"


def test_comparison_same_when_both_are_at_the_floor():
    cs = cmp(metrics(sinad=146.9, dr=151), metrics(sinad=142.0, dr=147), )
    assert cs["cmp-distortion"]["verdict"] == "same" and cs["cmp-overall"]["verdict"] == "same"


@pytest.mark.parametrize("worse, verdict, phrase", [
    (125.0, "difference-low", "both are at least 120 dB below it"),
    (100.0, "difference-low", "both are below the 87 dB noise level of dithered 16-bit"),
    (87.0, "difference-low", "both are below the 87 dB noise level of dithered 16-bit"),
    (86.9, "notable", "less than the 87 dB noise level of dithered 16-bit")])
def test_comparison_distortion_tiers(worse, verdict, phrase):
    cs = cmp(metrics(sinad=worse, dr=140, smpte=-140, ccif=-140), metrics(sinad=140, dr=140, smpte=-140, ccif=-140))
    c = cs["cmp-distortion"]
    assert c["verdict"] == verdict and phrase in c["text"]
    assert cs["cmp-overall"]["verdict"] == verdict
    if verdict == "difference-low":
        assert "B reads" in c["text"] and "a difference of" in c["text"] and "No repeatability interval" in c["text"]
        assert "ranks nothing" in cs["cmp-overall"]["text"]


def test_comparison_one_db_boundary():
    assert cmp(metrics(sinad=110), metrics(sinad=110.99))["cmp-distortion"]["verdict"] == "same"
    assert cmp(metrics(sinad=110), metrics(sinad=111.0))["cmp-distortion"]["verdict"] == "difference-low"


@pytest.mark.parametrize("d, verdict", [(0.1, "same"), (0.11, "difference-low"), (0.5, "difference-low"), (0.51, "notable")])
def test_comparison_response_boundaries(d, verdict):
    b = metrics()
    b["frequency_response"]["at_hz"]["20000"] = -0.02 - d
    assert cmp(metrics(), b)["cmp-response"]["verdict"] == verdict


def test_comparison_level_difference_asks_for_level_matching():
    cs = cmp(metrics(), metrics(gain_error_db=-6.02))
    assert cs["cmp-level"]["verdict"] == "notable" and "A reads 6.02 dB higher in output level" in cs["cmp-level"]["text"]
    assert "Match the levels before any listening comparison" in cs["cmp-level"]["text"]
    assert cs["cmp-overall"]["verdict"] == "notable" and "in level" in cs["cmp-overall"]["text"]
    assert cmp(metrics(), metrics(gain_error_db=0.1))["cmp-level"]["verdict"] == "same"


def test_comparison_never_names_a_winner_and_lists_what_is_not_compared():
    for a, b in ((metrics(), metrics()), (metrics(sinad=60), metrics()), (metrics(), metrics(gain_error_db=3))):
        cs = cmp(a, b)
        text = " ".join(c["text"] for c in cs.values()).lower()
        assert not re.search(r"\b(winner|wins|beats|best|superior)\b", text)
        assert "not compared in this version" in text and "not the whole picture" in text


def test_comparison_of_different_classes_and_of_the_reference_chain():
    cs = cmp(metrics(), metrics(klass="B"), CLI, {"adapter": "cli", "class": "B"})
    assert cs["cmp-classes"]["verdict"] == "not-comparable" and "cmp-overall" not in cs
    cs = cmp(metrics(sinad=146.71), metrics(klass="B", sinad=146.73), REF, {"adapter": "reference", "class": "B"})
    assert cs["floor"]["text"].startswith("Every device here is the built-in reference chain. This is the measurement floor")
    assert "agree" in cs["floor-agreement"]["text"] and cs["floor-agreement"]["verdict"] == "fact"
    cs = cmp(metrics(sinad=146.7), metrics(klass="B", sinad=140.0), REF, {"adapter": "reference", "class": "B"})
    assert cs["floor-agreement"]["verdict"] == "notable"


def test_three_devices_are_compared_in_pairs():
    cs = cn.comparison_conclusions([(n, metrics(), CLI) for n in "ABC"])
    assert [c["id"] for c in cs if c["id"].startswith("cmp-overall")] == ["cmp-overall-1", "cmp-overall-2", "cmp-overall-3"]


# ----------------------------------------------------------------------------- every conclusion is backed

def all_cases(monkeypatch):
    out = []
    lv = {"0 dB SACD": {"saturated": False, "thdn_drift_db": 0.18}}
    us = {"integrated_dbfs": {"20000-40000": -82.0, "40000-96000": -38.0}}
    for unrev in (False, True):
        monkeypatch.setattr(cn, "UNREVIEWED_VALIDATED", unrev)
        for ver in (1, 2):
            for M in (metrics(analysis_version=ver), metrics(sinad=100, analysis_version=ver), metrics(sinad=50, gain_error_db=1.0, analysis_version=ver),
                      metrics(sinad=146, dr=151, analysis_version=ver),
                      metrics(klass="B", analysis_version=ver, stability={"hold_s": 60.0, "levels": lv}, ultrasonic=us,
                              rates={"DSD128": {"sinad_db": 175.8, "ultrasonic": us}})):
                for d in (CLI, REF):
                    out.append((M, cn.device_conclusions(M, d)))
            a, b = metrics(analysis_version=ver), metrics(sinad=70, gain_error_db=2, analysis_version=ver)
            b["frequency_response"]["at_hz"]["20000"] = -1.0
            b["impulse"] = {"filter_type": "minimum phase", "pre_ringing_ms": 0.0, "post_ringing_ms": 1.0}
            b["noise"]["bands"]["40000-96000"] = -70.0
            for pair in ((a, a), (a, b), (a, metrics(sinad=125, dr=125, smpte=-125, ccif=-125, analysis_version=ver))):
                out.append((pair, cn.comparison_conclusions([("A", pair[0], CLI), ("B", pair[1], CLI)])))
            out.append(((a, a), cn.comparison_conclusions([("A", a, REF), ("B", a, REF)])))
    lim = metrics(sinad=101.4, dr=103.7, analysis_version=2, output_format=FMT16)
    out.append((lim, cn.device_conclusions(lim, CLI)))
    out.append(((a, lim), cn.comparison_conclusions([("A", a, CLI), ("B", lim, CLI)])))
    return out


def test_every_conclusion_cites_metrics_that_exist_and_backs_every_number(monkeypatch):
    seen = set()
    for M, cs in all_cases(monkeypatch):
        sources = M if isinstance(M, tuple) else (M,)
        for c in cs:
            seen.add(c["id"])
            assert c["metrics"] and c["evidence"], c["id"]
            assert c["label"] == cn.VERDICTS[c["verdict"]][0]
            for path in c["metrics"]:
                assert any(cn.lookup(s, path) is not None for s in sources), (c["id"], path)
            # every number in the sentence is a figure shown as evidence, part of its label, or a cited threshold
            backed = set()
            for e in c["evidence"]:
                backed |= {n.lstrip("-") for n in cn.numbers(e["value"]) + cn.numbers(e["label"])}
            for t in c["thresholds"]:
                v = cn.THRESHOLDS[t]["value"]
                if v is not None:
                    backed |= {f"{v:.0f}", f"{v:.1f}", f"{v:g}"}
            for n in cn.numbers(c["text"]):
                assert n.lstrip("-") in backed, (c["id"], n, c["text"])
    assert {"overall", "floor", "response", "level", "limits", "filter", "ultrasonic", "stability", "rates", "pending",
            "cmp-overall", "cmp-distortion", "cmp-response", "cmp-level", "cmp-filter", "cmp-ultrasonic", "floor-agreement"} <= seen


def test_wording_is_plain(monkeypatch):
    hype = re.compile(r"stunning|audiophile-grade|world-class|perfect|flawless|amazing|incredible|superb|pristine|winner", re.I)
    for _, cs in all_cases(monkeypatch):
        for c in cs:
            assert not hype.search(c["text"]), c["text"]
            assert c["text"].endswith(".") and "  " not in c["text"]
    for label, meaning in cn.VERDICTS.values():
        assert not hype.search(label + meaning)


def test_thresholds_are_documented_with_sources():
    doc = (ROOT / "docs" / "conclusions.md").read_text()
    for name, t in cn.THRESHOLDS.items():
        assert f"`{name}`" in doc, name
        if t["value"] is not None:
            assert f"| {t['value']:g} " in doc, name
        else:
            assert not t["settled"]
        for _, url in t["sources"]:
            assert url in doc, url
        assert t["settled"] or t["sources"], name
    for label, meaning in cn.VERDICTS.values():
        assert f"| {label} |" in doc and meaning in doc, label
    for group in sorted(cn.VALIDATED | cn.VALIDATED_FROM_V2 | cn.UNREVIEWED):
        assert f"`{group}`" in doc, group


# ----------------------------------------------------------------------------- in the reports

def test_reports_lead_with_conclusions(tmp_path):
    ex = ROOT / "examples" / "reference-chain"
    res = {}
    for n in ("reference-decoder", "reference-modulator"):
        r = json.loads((ex / n / "results.json").read_text())
        r.pop("conclusions", None)
        res[n] = {**r, "plots": {}}
    meta = {"device": CLI, "profile": "full", "reference_chain": "1"}
    write_device_report(tmp_path / "d", "tool", res["reference-decoder"], meta)
    page, md = (tmp_path / "d" / "index.html").read_text(), (tmp_path / "d" / "index.md").read_text()
    assert page.index("<h2>Conclusions</h2>") < page.index("Summary") and "Evidence: the figures" in page
    assert md.index("## Conclusions") < md.index("| Metric | Value |")
    out = json.loads((tmp_path / "d" / "results.json").read_text())
    ids = [c["id"] for c in out["conclusions"]]
    assert ids[0] == "overall" and "limits" in ids and 3 <= len(ids) <= 7
    assert out["conclusions"][0]["text"] in md and out["conclusions"][0]["verdict"] == "margin-120"
    measured = [{"device": {"name": n.replace("-", " "), "class": k, "adapter": "reference"}} for n, k in
                (("reference-decoder", "A"), ("reference-modulator", "B"))]
    write_comparison(tmp_path / "c", list(res.items()), {"profile": "full"})
    md = (tmp_path / "c" / "index.md").read_text()
    assert md.index("## Conclusions") < md.index("| Metric |")
    cj = json.loads((tmp_path / "c" / "results.json").read_text())
    assert cj["devices"] == list(res) and cj["conclusions"][0]["id"] == "cmp-classes"
    both = cn.comparison_conclusions([(m["device"]["name"], res[n]["metrics"], m["device"]) for n, m in zip(res, measured, strict=True)])
    assert both[0]["id"] == "floor" and "cannot be ranked" in both[0]["text"]


def test_rules_do_not_change_their_input():
    M = metrics()
    before = copy.deepcopy(M)
    cn.device_conclusions(M, CLI)
    cn.comparison_conclusions([("A", M, CLI), ("B", M, CLI)])
    assert M == before


def test_images_count_towards_the_overall_verdict():  # N12: "Transparent" ignored image rejection
    M = metrics(sinad=130, dr=130, smpte=-130, ccif=-130, analysis_version=2)
    M["noise"]["a_weighted_dbfs"] = -140.0
    assert dev(M)["overall"]["verdict"] == "margin-120" and "distortion, noise and images" in dev(M)["overall"]["text"]
    M["filter_summary"]["stopband_worst_db"] = -20.0
    c = dev(M)["overall"]
    assert c["verdict"] == "margin-low" and "image rejection" in c["text"].lower() and "is 20 dB below" in c["text"]


def test_stopband_sentence_names_the_tones_and_says_upper_bound():  # N2
    M = metrics(analysis_version=2)
    c = dev(M)["stopband"]
    assert "tones from 24.1 to 34.1 kHz" in c["text"] and "upper bound" in c["text"] and "above" not in c["text"]


def test_overload_sentence_states_the_resolution():  # N12
    M = metrics(analysis_version=2)
    M["overload_recovery"] = {"recovery_ms": 0.0, "burst_level_dbfs": -2.9, "burst_ms": 50.0}
    t = dev(M)["overload"]["text"]
    assert "within 10 ms, the resolution of the test" in t and "loud burst" in t
    M["overload_recovery"]["recovery_ms"] = 32.0
    assert "within 32 ms (the test resolves about 10 ms)" in dev(M)["overload"]["text"]


def test_filter_rows_are_not_concluded_when_not_measurable(monkeypatch):  # N4
    monkeypatch.setattr(cn, "UNREVIEWED_VALIDATED", True)
    M = metrics(analysis_version=2)
    M["impulse"]["measurable"] = False
    M["group_delay_us"] = {"at_1k": 0.0, "at_20k": 300.0, "measurable": False}
    assert "filter" not in dev(M)
