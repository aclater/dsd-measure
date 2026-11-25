"""Every report and plot names the dsd-measure version that measured (the 'Measured with' line)."""

import copy
import re
from pathlib import Path

import pytest

from dsd_measure import __version__, adapters, measure, plan
from dsd_measure.report import write_comparison, write_device_report

LINE = "Measured with dsd-measure"
URL = "https://github.com/dsd-toolbox/dsd-measure"


@pytest.fixture(scope="module")
def result():
    a = adapters.Reference("t", klass="A", out_rate=44100)
    r = measure.measure_device(a, "quick", only=["impulse", "polarity", "levels"], log=lambda *_, **__: None)
    return a, r


def _check_page(folder, version):
    page, md = (folder / "index.html").read_text(), (folder / "index.md").read_text()
    assert page.count(f"<footer>{LINE} {version}, <a href='{URL}'>") == 1
    assert md.count(f"{LINE} {version}, [github.com/dsd-toolbox/dsd-measure]({URL}).") == 1
    svgs = sorted((folder / "plots").glob("*.svg"))
    assert svgs
    for f in svgs:
        text = f.read_text()
        assert text.count(f"{LINE} {version}, {URL}") == 1, f.name


def test_device_report_and_plots_carry_the_line(tmp_path, result):
    a, r = result
    write_device_report(tmp_path / "d", "t", r, {"device": a.describe(), "profile": "quick", "reference_chain": "1"})
    _check_page(tmp_path / "d", __version__)


def test_a_report_names_the_version_recorded_in_the_results_not_the_running_one(tmp_path, result):
    a, r = result
    meta = {"device": a.describe(), "profile": "quick", "reference_chain": "1", "versions": {"dsd_measure": "0.0.1"}}
    write_device_report(tmp_path / "d", "t", r, meta)
    _check_page(tmp_path / "d", "0.0.1")
    write_device_report(tmp_path / "e", "t", r, {**meta, "versions": {}})  # nothing recorded: the running version
    _check_page(tmp_path / "e", __version__)


def test_the_line_keeps_plots_reproducible(tmp_path, result):
    a, r = result
    meta = {"device": a.describe(), "profile": "quick", "reference_chain": "1"}
    write_device_report(tmp_path / "a", "t", r, meta)
    write_device_report(tmp_path / "b", "t", r, meta)
    for f in (tmp_path / "a" / "plots").glob("*.svg"):
        assert f.read_bytes() == (tmp_path / "b" / "plots" / f.name).read_bytes()
        text = f.read_text()
        assert not re.search(r"\d{4}-\d\d-\d\d", text)  # no date
        assert str(Path.home()) not in text and str(tmp_path) not in text  # no path of this machine


def test_comparison_report_and_plots_carry_the_line(tmp_path, result):
    a, r = result
    write_comparison(tmp_path / "c", [("one", r), ("two", copy.deepcopy(r))], {"profile": "quick"})
    _check_page(tmp_path / "c", __version__)
    m = plan.measured(a, "quick", 88200, r["metrics"].get("reference_floor"), "t")
    measured = [{**m, "versions": {"dsd_measure": "0.0.2"}}] * 2
    write_comparison(tmp_path / "c2", [("one", r), ("two", copy.deepcopy(r))], {"profile": "quick", "measured": measured})
    _check_page(tmp_path / "c2", "0.0.2")


def test_null_report_and_plots_carry_the_line(tmp_path):
    import numpy as np

    from dsd_measure import dsf, encode
    from dsd_measure.nulltest.analyse import Options
    from dsd_measure.nulltest.run import run_null
    fs = 88200
    x = 0.3 * np.sin(2 * np.pi * 1000 * np.arange(fs * 6) / fs)
    bits, _ = encode.encode(x, fs, 2822400)
    src = tmp_path / "t.dsf"
    dsf.write_dsf(src, bits, 2822400)
    run_null(src, ["reference@352800", "reference@176400"], Options(trim_start=0.3, trim_end=0.3), tmp_path / "n", log=lambda *_: None)
    _check_page(tmp_path / "n", __version__)


def test_a_hostile_recorded_version_is_escaped_in_html_and_restricted_in_markdown(tmp_path, result):
    a, r = result
    hostile = "1.0<script>alert(1)</script>[x](javascript:y)\n# h $\\frac{1}{0}$"
    meta = {"device": a.describe(), "profile": "quick", "reference_chain": "1", "versions": {"dsd_measure": hostile}}
    write_device_report(tmp_path / "d", "t", r, meta)
    page, md = (tmp_path / "d" / "index.html").read_text(), (tmp_path / "d" / "index.md").read_text()
    footer = page[page.index("<footer>"):page.index("</footer>")]
    assert "<script>" not in footer and "&lt;script&gt;" in footer
    line = next(x for x in md.splitlines() if x.startswith(LINE))
    version = line[len(LINE) + 1:line.index(", [github")]
    assert re.fullmatch(r"[A-Za-z0-9._+~?-]+", version) and version.startswith("1.0?script?alert")
    assert "[x]" not in md and "<script>" not in md
    for f in (tmp_path / "d" / "plots").glob("*.svg"):  # plots take the same restricted text: no math text, no markup
        svg = f.read_text()
        assert svg.count(f"{LINE} 1.0?script?alert") == 1 and "frac{" not in svg and "alert(1)" not in svg

