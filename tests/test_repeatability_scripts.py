"""The repeatability ensemble's perturbation must reach the interpolator that encode() really uses.

In the 0.1.3 candidate encode() stopped calling ``interpolate`` for the FFT method, the ensemble's
hook on it did nothing, and twelve "perturbed" runs were one run twelve times.
"""

import importlib.util
import json
import os
from pathlib import Path

import numpy as np
import pytest

from dsd_measure import encode, signals

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts" / "repeatability"


def _load(name):
    spec = importlib.util.spec_from_file_location(f"repeatability_{name}", SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize("method", ["fft", "direct"])
def test_the_perturbation_changes_the_bitstream_of_each_interpolator(method):
    member = _load("member")
    x = signals.sine(1000.0, -6.02, 88200, 8820)
    keep = (encode.INTERPOLATOR, encode.interpolate, encode._interpolate_pieces)
    try:
        encode.INTERPOLATOR = method
        plain, _ = encode.encode(x, 88200)
        member.perturb(method, "1")
        one, _ = encode.encode(x, 88200)
        again, _ = encode.encode(x, 88200)
        encode.interpolate, encode._interpolate_pieces = keep[1], keep[2]
        member.perturb(method, "2")
        two, _ = encode.encode(x, 88200)
    finally:
        encode.INTERPOLATOR, encode.interpolate, encode._interpolate_pieces = keep
    assert np.array_equal(one, again)  # one seed, one bitstream
    assert not np.array_equal(plain, one) and not np.array_equal(one, two)


def test_the_two_methods_get_the_same_noise():
    member = _load("member")
    x = signals.sine(1000.0, -6.02, 88200, 4410)
    keep = (encode.INTERPOLATOR, encode.interpolate, encode._interpolate_pieces)
    try:
        base = encode.interpolate(x, 32, method="direct")
        member.perturb("direct", "3")
        d = encode.interpolate(x, 32, method="direct") - base
        encode.interpolate = keep[1]
        base_f = np.concatenate(list(encode._interpolate_pieces(x, 32)))
        member.perturb("fft", "3")
        f = np.concatenate(list(encode._interpolate_pieces(x, 32))) - base_f
    finally:
        encode.INTERPOLATOR, encode.interpolate, encode._interpolate_pieces = keep
    assert 0.5e-14 < np.std(d) < 2e-14
    assert np.allclose(d, f, atol=1e-17)


def test_stats_refuses_an_ensemble_that_was_not_perturbed(tmp_path):
    stats = _load("stats")
    for m in ("direct", "fft"):
        for n in (1, 2, 3):
            d = tmp_path / f"{m}-{n}" / "dev"
            d.mkdir(parents=True)
            value = 1.0 if m == "fft" else 1.0 + n / 10
            (d / "results.json").write_text(json.dumps({"metrics": {"a": {"b": value}}}))
    with pytest.raises(SystemExit, match="fft ensemble has 3 identical members"):
        stats.main(tmp_path)


def test_one_sh_works_from_any_directory_with_relative_paths(tmp_path):
    """A relative script path, OUTDIR and PYTHON still give absolute paths to the member and an absolute cache folder."""
    import subprocess
    (tmp_path / "out").mkdir()
    stub = tmp_path / "py.sh"  # no measurement runs: the stub records what it was given
    stub.write_text('#!/bin/sh\necho "$DSD_MEASURE_CACHE_DIR|$1|$PWD" > "$4.args"\n')
    stub.chmod(0o755)
    rel = os.path.relpath(SCRIPTS / "one.sh", tmp_path)
    r = subprocess.run(["sh", rel, "out", "./py.sh", "fft", "7"], cwd=tmp_path, capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout.strip() == "fft 7: exit 0", (r.stdout, r.stderr)
    cache, member, cwd = (tmp_path / "out" / "fft-7.args").read_text().strip().split("|")
    assert os.path.isabs(cache) and cache.startswith(str((tmp_path / "out").resolve()))
    assert member == str(SCRIPTS / "member.py") and cwd == str((tmp_path / "out").resolve())
    assert not Path(cache).exists()  # removed at the end


def test_one_sh_stops_when_the_output_folder_is_missing(tmp_path):
    import subprocess
    r = subprocess.run(["sh", str(SCRIPTS / "one.sh"), str(tmp_path / "nowhere"), "python3", "fft", "1"],
                       capture_output=True, text=True)
    assert r.returncode == 2


@pytest.mark.parametrize("value", ["cache", "./cache", "~/cache"])
def test_a_relative_cache_dir_is_an_error_for_both_caches(monkeypatch, capsys, value):
    from dsd_measure import cli, encode, stimcache
    monkeypatch.setenv("DSD_MEASURE_CACHE_DIR", value)
    with pytest.raises(ValueError, match="must be an absolute path"):
        encode._cache_dir()
    with pytest.raises(ValueError, match="must be an absolute path"):
        stimcache.directory()
    assert cli.main(["cache"]) == 2
    assert "DSD_MEASURE_CACHE_DIR must be an absolute path" in capsys.readouterr().err


def _ensemble(root, direct, fft):
    for m, count in (("direct", direct), ("fft", fft)):
        for n in range(1, count + 1):
            d = root / f"{m}-{n}" / "dev"
            d.mkdir(parents=True)
            (d / "results.json").write_text(json.dumps({"metrics": {"a": {"b": n + (0.5 if m == "fft" else 0)}}}))


@pytest.mark.parametrize("direct,fft,message", [(3, 2, "differ in size: direct 3, fft 2"), (1, 1, "at least 2 members"),
                                                (0, 0, "at least 2 members")])
def test_stats_refuses_ensembles_of_unequal_or_too_small_size(tmp_path, direct, fft, message):
    _ensemble(tmp_path, direct, fft)
    with pytest.raises(SystemExit, match=message):
        _load("stats").main(tmp_path)


def test_stats_refuses_a_member_without_results(tmp_path):
    _ensemble(tmp_path, 3, 3)
    (tmp_path / "fft-2" / "dev" / "results.json").unlink()
    with pytest.raises(SystemExit, match="fft ensemble has members without any results.json: fft-2"):
        _load("stats").main(tmp_path)
    (tmp_path / "fft-2" / "dev").rmdir()
    with pytest.raises(SystemExit, match="fft-2"):
        _load("stats").main(tmp_path)


def test_stats_reads_a_good_ensemble(tmp_path, capsys):
    _ensemble(tmp_path, 3, 3)
    _load("stats").main(tmp_path)
    assert "members: direct 3, fft 3" in capsys.readouterr().out
