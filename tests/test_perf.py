"""Speed work of 0.1.3: the FFT interpolator, the stimulus cache, the parallel runner, the gate.

Each test holds one promise the user guide makes: the fast paths give the numbers of the slow
ones (to rounding for the interpolator, exactly for the cache and the parallel runner).
"""

import json
import os
import sys
from pathlib import Path

import numpy as np
import pytest
from scipy import signal

from dsd_measure import cli, encode, gate, parallel, stimcache
from dsd_measure import signals as sg
from dsd_measure.measure import PROFILE_TESTS, PROFILES
from dsd_measure.run import run_suite

STUB = Path(__file__).with_name("stubtool.py")


def quiet(*_a, **_k):
    pass


# ---------------------------------------------------------------- interpolator

@pytest.mark.parametrize("L,ntaps", [(2, 2047), (2, 255), (3, 255), (5, 255), (7, 255), (2, 5), (3, 1)])
def test_fft_upsample_is_resample_poly_to_rounding(L, ntaps, monkeypatch):
    monkeypatch.setattr(encode, "PIECE", 4096)  # several pieces, so the joins are tested too
    rng = np.random.default_rng(3)
    h = signal.firwin(ntaps, 1.0 / L) if ntaps > 1 else np.ones(1)
    for n in (1, 2, 7, 500, 4095, 4096, 4097, 20000):
        x = rng.standard_normal(n)
        a = signal.resample_poly(x, L, 1, window=h)
        b = encode._upsample(x, L, h)
        assert a.shape == b.shape
        assert np.max(np.abs(a - b)) < 1e-13, (n, float(np.max(np.abs(a - b))))


@pytest.mark.parametrize("fs,ratio", [(88200, 32), (44100, 64), (352800, 8), (176400, 16), (88200, 64)])
def test_interpolator_matches_the_direct_form_below_minus_280_db(fs, ratio):
    x = sg.sine(1000.0, -6.02, fs, int(0.4 * fs)) + np.random.default_rng(1).standard_normal(int(0.4 * fs)) * 1e-3
    a = encode.interpolate(x, ratio, method="direct")
    b = encode.interpolate(x, ratio, method="fft")
    err = float(np.max(np.abs(a - b)))
    assert err < 1e-14, err  # full scale is 1: -280 dB


def test_interpolator_rejects_an_unknown_method():
    with pytest.raises(ValueError):
        encode.interpolate(np.zeros(8), 2, method="gpu")


# ---------------------------------------------------------------- stimulus cache

def _tone(n=8820, f=1000.0, fs=88200):
    return sg.sine(f, -6.02, fs, n)


def test_cache_returns_the_same_bits_and_info(stim_cache):
    x = _tone()
    b1, i1 = encode.encode(x, 88200)
    assert stimcache.stats() == {"hits": 0, "misses": 1, "written": 1}
    b2, i2 = encode.encode(x, 88200)
    assert stimcache.stats()["hits"] == 1
    assert b2.dtype == np.int8 and np.array_equal(b1, b2) and i1 == i2
    assert set(np.unique(b2)) == {-1, 1}
    files = list((stim_cache / "stimuli").glob("*.stim"))
    assert len(files) == 1 and (os.stat(files[0]).st_mode & 0o777) == 0o600
    assert (os.stat(stim_cache / "stimuli").st_mode & 0o777) == 0o700


def test_cached_bits_equal_uncached_bits(stim_cache, monkeypatch):
    x = _tone()
    encode.encode(x, 88200)
    cached, _ = encode.encode(x, 88200)
    monkeypatch.setenv("DSD_MEASURE_NO_CACHE", "1")
    fresh, _ = encode.encode(x, 88200)
    assert np.array_equal(cached, fresh)


def test_every_input_is_in_the_key():
    x = _tone()
    base = stimcache.key(x, 88200, 2822400, None, None, 1.0, "fft")
    y = x.copy()
    y[100] = np.nextafter(y[100], 1.0)  # one sample, one unit in the last place
    others = [stimcache.key(y, 88200, 2822400, None, None, 1.0, "fft"),
              stimcache.key(x[:-1], 88200, 2822400, None, None, 1.0, "fft"),
              stimcache.key(x, 44100, 2822400, None, None, 1.0, "fft"),
              stimcache.key(x, 88200, 5644800, None, None, 1.0, "fft"),
              stimcache.key(x, 88200, 2822400, 8, 1.3, 1.0, "fft"),
              stimcache.key(x, 88200, 2822400, 7, 1.3, 1.0, "fft"),
              stimcache.key(x, 88200, 2822400, 8, 1.4, 1.0, "fft"),
              stimcache.key(x, 88200, 2822400, None, None, 0.5, "fft"),
              stimcache.key(x, 88200, 2822400, None, None, 1.0, "direct")]
    assert len({base, *others}) == len(others) + 1
    assert stimcache.key(x.copy(), 88200, 2822400, None, None, 1.0, "fft") == base


def test_key_follows_the_encoder_source_and_versions(monkeypatch):
    x = _tone(100)
    base = stimcache.key(x, 88200, 2822400, None, None, 1.0)
    tag = stimcache.gate_key()
    assert tag.startswith("dsd-measure-stimuli-") and tag == stimcache.gate_key()
    for target, name, value in ((encode, "CFLAGS", encode.CFLAGS + ["-DX"]), (np, "__version__", "0.0.0")):
        monkeypatch.setattr(stimcache, "_TAG", None)
        monkeypatch.setattr(target, name, value)
        assert stimcache.key(x, 88200, 2822400, None, None, 1.0) != base
        assert stimcache.gate_key() != tag
        monkeypatch.undo()
    monkeypatch.setattr(stimcache, "_TAG", None)
    assert stimcache.key(x, 88200, 2822400, None, None, 1.0) == base


@pytest.mark.parametrize("damage", ["flip", "truncate", "empty", "magic", "header"])
def test_a_damaged_entry_is_dropped_and_encoded_again(stim_cache, damage):
    x = _tone()
    good, _ = encode.encode(x, 88200)
    (f,) = (stim_cache / "stimuli").glob("*.stim")
    raw = bytearray(f.read_bytes())
    if damage == "flip":
        raw[-5] ^= 0x10  # one bit of the DSD payload
    elif damage == "truncate":
        raw = raw[: len(raw) // 2]
    elif damage == "empty":
        raw = bytearray()
    elif damage == "magic":
        raw[0:4] = b"XXXX"
    else:
        raw[len(stimcache.MAGIC) : len(stimcache.MAGIC) + 8] = (2**40).to_bytes(8, "little")
    f.write_bytes(raw)
    stimcache.reset_stats()
    again, _ = encode.encode(x, 88200)
    assert np.array_equal(good, again)
    assert stimcache.stats() == {"hits": 0, "misses": 1, "written": 1}
    assert stimcache._parse(f.read_bytes()) is not None  # the entry is whole again


def test_no_cache_writes_nothing(stim_cache, monkeypatch):
    monkeypatch.setenv("DSD_MEASURE_NO_CACHE", "1")
    encode.encode(_tone(), 88200)
    assert not (stim_cache / "stimuli").exists()
    assert stimcache.stats() == {"hits": 0, "misses": 0, "written": 0}


def test_eviction_deletes_the_entries_read_longest_ago(stim_cache):
    keys = []
    for i in range(6):
        x = _tone(8820, 500.0 + 100 * i)
        encode.encode(x, 88200)
        keys.append(stimcache.key(x, 88200, 2822400, None, None, 1.0, "fft"))
    d = stim_cache / "stimuli"
    sizes = {k: (d / f"{k}.stim").stat().st_size for k in keys}  # nearly equal (the header text varies)
    size = max(sizes.values())
    for i, k in enumerate(keys):  # ages: entry 0 oldest ... entry 5 newest, then entry 1 is read
        os.utime(d / f"{k}.stim", (1_000_000 + i, 1_000_000 + i))
    encode.encode(_tone(8820, 600.0), 88200)  # a hit: entry 1 becomes the newest
    assert stimcache.stats()["hits"] == 1
    freed = stimcache.evict(limit=int(3.5 * size))
    left = {p.stem for p in d.glob("*.stim")}
    assert left == {keys[1], keys[4], keys[5]}
    assert freed == sum(sizes[k] for k in (keys[0], keys[2], keys[3]))
    kept = sum(sizes[k] for k in left)
    assert stimcache.usage()["entries"] == 3 and stimcache.usage()["bytes"] == kept
    assert stimcache.clear() == kept and stimcache.usage()["entries"] == 0


def test_the_size_limit_is_kept_while_writing(stim_cache, monkeypatch):
    x = _tone(8820, 500.0)
    encode.encode(x, 88200)
    size = next((stim_cache / "stimuli").glob("*.stim")).stat().st_size
    monkeypatch.setenv("DSD_MEASURE_CACHE_MAX_MB", str(4 * size / 2**20))
    for i in range(1, 30):
        encode.encode(_tone(8820, 500.0 + 10 * i), 88200)
        assert stimcache.usage()["bytes"] <= 4 * size + size
    assert stimcache.usage()["entries"] >= 3


def test_a_cache_folder_open_to_others_is_refused(stim_cache):
    encode.encode(_tone(), 88200)
    os.chmod(stim_cache / "stimuli", 0o777)
    try:
        with pytest.raises(encode.UnsafeCacheError):
            encode.encode(_tone(), 88200)
    finally:
        os.chmod(stim_cache / "stimuli", 0o700)


def test_a_run_stops_at_once_when_the_cache_folder_is_not_private(stim_cache, tmp_path, capsys):
    stim_cache.mkdir()
    os.chmod(stim_cache, 0o755)  # as a CI restore step leaves a folder it created
    s = tmp_path / "s.toml"
    s.write_text('[[device]]\nname = "r"\nadapter = "reference"\nclass = "A"\n')
    assert cli.main(["run", str(s), "-o", str(tmp_path / "out"), "--only", "polarity"]) == cli.EXIT_FATAL
    assert "accessible to others" in capsys.readouterr().err and not (tmp_path / "out").exists()
    os.chmod(stim_cache, 0o700)
    assert cli.main(["run", str(s), "-o", str(tmp_path / "out"), "--only", "polarity"]) == 0


def test_a_cached_entry_that_is_a_symlink_is_refused(stim_cache, tmp_path):
    x = _tone()
    encode.encode(x, 88200)
    (f,) = (stim_cache / "stimuli").glob("*.stim")
    other = tmp_path / "elsewhere.stim"
    f.rename(other)
    f.symlink_to(other)
    with pytest.raises(encode.UnsafeCacheError):
        encode.encode(x, 88200)


def test_cache_command_shows_keys_and_clears(stim_cache, capsys):
    encode.encode(_tone(), 88200)
    assert cli.main(["cache"]) == 0
    assert "1 test signals" in capsys.readouterr().out
    assert cli.main(["cache", "--key"]) == 0
    assert capsys.readouterr().out.strip() == stimcache.gate_key()
    assert cli.main(["cache", "--clear"]) == 0
    assert "0 test signals" in capsys.readouterr().out


# ---------------------------------------------------------------- parallel runner

def _suite(tmp_path, devices, extra=""):
    p = tmp_path / "suite.toml"
    p.write_text('[suite]\nname = "t"\nprofile = "quick"\n' + extra + "\n" + "\n".join(devices) + "\n")
    return p


REF_A = '[[device]]\nname = "ref a"\nadapter = "reference"\nclass = "A"\nout_rate = 44100\n'
REF_B = '[[device]]\nname = "ref b"\nadapter = "reference"\nclass = "B"\n'


def _stub_dev(name="stub", extra=""):
    cmd = f"{sys.executable} {STUB} {{input}} {{output}} --format pcm24"
    return f'[[device]]\nname = "{name}"\nadapter = "cli"\nclass = "A"\ncommand = {json.dumps(cmd)}\n{extra}'


def _load(out):
    res = {}
    for f in sorted(Path(out).rglob("*.json")):
        d = json.loads(f.read_text())
        d.pop("timing_s", None)
        d.pop("command", None)
        if "measured" in d:
            d["measured"].pop("date", None)
        if isinstance(d.get("preflight"), dict):
            d["preflight"].pop("seconds", None)
        res[str(f.relative_to(out))] = d
    return res


FAST = ["impulse", "tone_15k", "polarity", "overload", "imd", "stability"]


def test_parallel_run_equals_serial_run(tmp_path, stim_cache, monkeypatch):
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join(sys.path))
    s = _suite(tmp_path, [REF_A, REF_B, _stub_dev()])
    _, f1 = run_suite(s, tmp_path / "serial", only=FAST, log=quiet, jobs=1)
    lines = []
    _, f3 = run_suite(s, tmp_path / "par", only=FAST, log=lambda m="", end="\n": lines.append(m), jobs=3)
    assert f1 == f3 == {}
    a, b = _load(tmp_path / "serial"), _load(tmp_path / "par")
    assert sorted(a) == sorted(b) and len(a) >= 7
    for k in a:
        assert json.dumps(a[k]) == json.dumps(b[k]), k  # same values, same key order
    prov = a["stub/provenance.json"]
    assert len(prov["adapter_calls"]) >= 5 and prov["adapter_calls"][0]["output_format"]["bits"] == 24
    assert a["stub/results.json"]["metrics"]["output_format"]["bits"] == 24
    assert a["stub/results.json"]["metrics"]["latency"]["seconds"] is not None
    assert "reference_decoder_only" in a["ref-b/results.json"]["metrics"]
    done = [m for m in lines if "] -> " in m]
    assert len(done) == 3 * len(FAST) and any(m.startswith(f"[{len(done)}/{len(done)}]") for m in done)
    assert any("3 jobs" in m for m in lines)


def test_parallel_run_without_the_cache_equals_serial_too(tmp_path, monkeypatch):
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join(sys.path))
    s = _suite(tmp_path, [REF_A])
    run_suite(s, tmp_path / "serial", only=["impulse", "overload"], log=quiet, jobs=1, cache=False)
    run_suite(s, tmp_path / "par", only=["impulse", "overload"], log=quiet, jobs=2, cache=False)
    a, b = _load(tmp_path / "serial"), _load(tmp_path / "par")
    assert all(json.dumps(a[k]) == json.dumps(b[k]) for k in a) and len(a) == len(b)


def test_a_failing_device_fails_the_same_way_in_parallel(tmp_path, monkeypatch):
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join(sys.path))
    state = tmp_path / "calls"
    cmd = f"{sys.executable} {STUB} {{input}} {{output}} --fail-after 1 --state {state}"
    dev = f'[[device]]\nname = "bad"\nadapter = "cli"\nclass = "A"\ncommand = {json.dumps(cmd)}\n'
    s = _suite(tmp_path, [dev])
    _, failed = run_suite(s, tmp_path / "par", only=["tone_15k", "polarity"], log=quiet, jobs=2, cache=False)
    assert failed == {"bad": ["tone_15k", "polarity"]}
    nr = json.loads((tmp_path / "par" / "bad" / "results.json").read_text())["not_run"]
    assert all("simulated failure" in nr[t] for t in ("tone_15k", "polarity"))


def test_a_named_work_folder_keeps_its_device_in_one_worker(tmp_path, monkeypatch):
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join(sys.path))
    work = tmp_path / "work"
    s = _suite(tmp_path, [_stub_dev(extra=f"workdir = {json.dumps(str(work))}\n"), REF_A])
    run_suite(s, tmp_path / "par", only=["tone_15k", "polarity"], log=quiet, jobs=2, cache=False)
    names = sorted(p.name for p in work.iterdir())
    # the pre-flight took number 1; then the tone, the delay probe and the pulse, numbered in run order
    assert names == [f"{io}{n}.{ext}" for io, ext in (("in", "dsf"), ("out", "wav")) for n in (1, 2, 3, 4)]


def test_merge_puts_the_delay_probe_where_a_serial_run_makes_it():
    class A:
        klass = "B"
        log = []

    def piece(name, log, ntf, mark=None, notes=()):
        return {"res": {"metrics": {name: 1}, "plots": {}, "not_run": {}, "errors": [], "notes": list(notes),
                        "timing_s": {name: 0.1}, "reference_chain_ntf": dict(ntf)}, "log": list(log), "mark": mark}

    probe = {"lat": (0.0, 1), "log": ["probe"], "ntf": {"latency": "p"}}
    pieces = [piece("levels", ["l1", "l2"], {"levels": 1}),
              piece("impulse", ["i1", "i2"], {"impulse": 1, "step": 1}, mark=(0, 0), notes=["delay"]),
              piece("overload", ["o1"], {"overload": 1}, mark=(1, 1), notes=["delay", "own"])]
    a = A()
    res = parallel.merge(a, pieces, probe)
    assert a.log == ["l1", "l2", "probe", "i1", "i2", "o1"]
    assert list(res["reference_chain_ntf"]) == ["levels", "latency", "impulse", "step", "overload"]
    assert res["notes"] == ["delay", "own"] and list(res["metrics"]) == ["levels", "overload", "reference_decoder_only"]
    a2 = A()
    a2.log = []
    res = parallel.merge(a2, pieces[2:], probe)  # overload alone asks for the delay after its own call
    assert a2.log == ["o1", "probe"] and list(res["reference_chain_ntf"]) == ["overload", "latency"]


def test_default_jobs(monkeypatch):
    monkeypatch.delenv("DSD_MEASURE_JOBS", raising=False)
    monkeypatch.setattr(parallel, "available_gib", lambda: None)
    monkeypatch.setattr(parallel, "cgroup_gib", lambda: None)
    for n, want in ((1, 1), (2, 2), (4, 4), (6, 4), (8, 4), (16, 8), (32, 16), (128, 16)):
        monkeypatch.setattr(parallel, "cores", lambda n=n: n)
        assert parallel.default_jobs() == want
    monkeypatch.setenv("DSD_MEASURE_JOBS", "3")
    assert parallel.default_jobs() == 3


def test_default_jobs_fit_the_available_memory(monkeypatch):
    monkeypatch.delenv("DSD_MEASURE_JOBS", raising=False)
    monkeypatch.setattr(parallel, "cores", lambda: 32)
    monkeypatch.setattr(parallel, "cgroup_gib", lambda: None)
    for gib, quick, full in ((64, 16, 16), (16, 16, 8), (8, 10, 1), (4, 4, 1), (1, 1, 1)):
        monkeypatch.setattr(parallel, "available_gib", lambda gib=gib: gib)
        assert (parallel.default_jobs("quick"), parallel.default_jobs("gate"), parallel.default_jobs("full")) == (quick, quick, full)
    assert parallel.available_gib() is None or parallel.available_gib() > 0


def _cgroup_tree(tmp_path, limits):
    """A fake cgroup v2 tree a/b/c with (memory.max, memory.current, cpu.max) per level, outermost first."""
    proc = tmp_path / "cgroup"
    proc.write_text("0::/a/b/c\n")
    folder = tmp_path / "sys"
    for name, (mmax, cur, cpu) in zip(("a", "b", "c"), limits, strict=True):
        folder = folder / name
        folder.mkdir(parents=True)
        (folder / "memory.max").write_text(f"{mmax}\n")
        (folder / "memory.current").write_text(f"{cur}\n")
        (folder / "cpu.max").write_text(f"{cpu}\n")
    return str(tmp_path / "sys"), str(proc)


def test_cgroup_limits_are_read_from_every_level(tmp_path):
    g = 2**30
    root, proc = _cgroup_tree(tmp_path, [("max", 50 * g, "max 100000"), (4 * g, g, "200000 100000"), ("max", g // 2, "max 100000")])
    assert parallel.cgroup_gib(root, proc) == 3.0  # the 4 GiB scope with 1 GiB in use
    assert parallel.cgroup_cpus(root, proc) == 2
    (tmp_path / "sys/a/memory.max").write_text(f"{60 * g}\n")  # an outer limit with less room wins
    (tmp_path / "sys/a/memory.current").write_text(f"{58 * g}\n")
    (tmp_path / "sys/a/cpu.max").write_text("50000 100000\n")  # half a CPU is one job, not none
    assert parallel.cgroup_gib(root, proc) == 2.0
    assert parallel.cgroup_cpus(root, proc) == 1
    assert parallel.cgroup_gib(str(tmp_path / "none"), proc) is None  # no cgroup v2 files: no limit known
    assert parallel.cgroup_cpus(root, str(tmp_path / "missing")) is None


def test_default_jobs_fit_a_memory_limited_container(monkeypatch):
    # 0.1.3: under a 4 GiB memory limit on a 32-core machine with 76 GiB free, the default was 16 jobs
    # and the kernel killed the workers. The limit of the control group now counts.
    monkeypatch.delenv("DSD_MEASURE_JOBS", raising=False)
    monkeypatch.setattr(parallel, "cores", lambda: 32)
    monkeypatch.setattr(parallel, "available_gib", lambda: 76.0)
    for room, quick, full in ((4.0, 2, 1), (8.0, 8, 1), (16.0, 16, 5), (0.5, 1, 1)):
        monkeypatch.setattr(parallel, "cgroup_gib", lambda room=room: room)
        assert (parallel.default_jobs("quick"), parallel.default_jobs("gate"), parallel.default_jobs("full")) == (quick, quick, full)
    monkeypatch.setattr(parallel, "available_gib", lambda: None)  # not Linux's /proc/meminfo, but a limit is known
    monkeypatch.setattr(parallel, "cgroup_gib", lambda: 4.0)
    assert parallel.default_jobs("quick") == 2
    monkeypatch.setenv("DSD_MEASURE_JOBS", "6")  # an explicit number is the user's decision
    assert parallel.default_jobs("quick") == 6


def test_jobs_must_be_positive(tmp_path):
    s = _suite(tmp_path, [REF_A])
    with pytest.raises(ValueError):
        run_suite(s, tmp_path / "o", only=["polarity"], log=quiet, jobs=-1)


# ---------------------------------------------------------------- gate profile and gate comparison

def test_gate_profile_is_the_quick_profile_on_fewer_tests():
    assert PROFILES["gate"] == PROFILES["quick"]
    assert PROFILE_TESTS["gate"] == ("reference_floor", "levels", "noise", "alias_tones")


def test_gate_profile_plan_lists_only_its_tests(tmp_path, capsys):
    s = _suite(tmp_path, [REF_A])
    assert cli.main(["run", str(s), "--profile", "gate", "--plan"]) == 0
    out = capsys.readouterr().out
    listed = [ln.split()[0] for ln in out.split("Signals generated")[1].split("\n\n")[0].splitlines()[1:]]
    assert listed == ["reference_floor", "levels", "noise", "alias_tones"]
    assert "tests: 4," in out


@pytest.mark.slow
def test_gate_profile_figures_are_the_quick_profile_figures(tmp_path, stim_cache, monkeypatch):
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join(sys.path))
    s = _suite(tmp_path, [REF_A])
    run_suite(s, tmp_path / "gate", profile="gate", log=quiet, jobs=4)
    run_suite(s, tmp_path / "quick", profile="quick", only=list(PROFILE_TESTS["gate"]) + ["imd"], log=quiet, jobs=4)
    g = json.loads((tmp_path / "gate" / "ref-a" / "results.json").read_text())["metrics"]
    q = json.loads((tmp_path / "quick" / "ref-a" / "results.json").read_text())["metrics"]
    assert "imd_smpte" in q and "imd_smpte" not in g
    for k in g:
        assert g[k] == q[k], k
    rows = gate.compare(g, q)
    assert gate.passed(rows) and {r["verdict"] for r in rows} == {"same"}
    assert g["tone_0dbsacd"]["thdn_db"] <= -145.5  # the reference floor holds (-147 dB, +-0.2 dB of repeatability)


M0 = {"analysis_version": 2, "device_class": "A", "dsd_rate": 2822400,
      "tone_0dbsacd": {"sinad_db": 120.0, "thd_db": -140.0, "thdn_a_db": -122.0}, "tone_peak": {"sinad_db": 110.0},
      "dynamic_range": {"dr_a_db": 123.0}, "noise": {"a_weighted_dbfs": -130.0, "unweighted_dbfs": -127.0},
      "gain_error_db": 0.0001, "linearity": {"lowest_level_within_0p5_db": -120.0}, "alias_tones": {"worst_image_db": -100.0}}


def _with(**changes):
    m = json.loads(json.dumps(M0))
    for path, v in changes.items():
        d = m
        *head, last = path.split("__")
        for k in head:
            d = d[k]
        if v is None:
            del d[last]
        else:
            d[last] = v
    return m


def test_gate_judges_each_figure_by_direction_and_repeatability():
    rep = {r[1]: r[3] for r in gate.GATE_METRICS}
    r_sinad, r_noise = rep[("tone_0dbsacd", "sinad_db")], rep[("noise", "a_weighted_dbfs")]

    def verdicts(new):
        return {r["key"]: r["verdict"] for r in gate.compare(M0, new)}

    assert set(verdicts(M0).values()) == {"same"}
    assert verdicts(_with(tone_0dbsacd__sinad_db=120.0 - 0.9 * r_sinad))["tone_0dbsacd.sinad_db"] == "same"
    assert verdicts(_with(tone_0dbsacd__sinad_db=120.0 - 1.1 * r_sinad))["tone_0dbsacd.sinad_db"] == "worse"
    assert verdicts(_with(tone_0dbsacd__sinad_db=120.0 + 1.1 * r_sinad))["tone_0dbsacd.sinad_db"] == "better"
    assert verdicts(_with(noise__a_weighted_dbfs=-130.0 + 1.1 * r_noise))["noise.a_weighted_dbfs"] == "worse"
    assert verdicts(_with(noise__a_weighted_dbfs=-130.0 - 1.1 * r_noise))["noise.a_weighted_dbfs"] == "better"
    assert verdicts(_with(gain_error_db=-0.5))["gain_error_db"] == "worse"
    assert verdicts(_with(gain_error_db=-0.0001))["gain_error_db"] == "same"
    assert verdicts(_with(alias_tones=None))["alias_tones.worst_image_db"] == "missing"
    assert {r["key"]: r["verdict"] for r in gate.compare(_with(alias_tones=None), M0)}["alias_tones.worst_image_db"] == "new"
    assert not gate.passed(gate.compare(M0, _with(alias_tones=None)))
    assert gate.passed(gate.compare(M0, _with(tone_0dbsacd__sinad_db=140.0)))
    wide = gate.compare(M0, _with(tone_0dbsacd__sinad_db=120.0 - 1.1 * r_sinad), scale=2.0)
    assert gate.passed(wide)


def test_gate_command_exit_status_and_output(tmp_path, capsys):
    for name, m in (("old", M0), ("same", M0), ("worse", _with(tone_0dbsacd__sinad_db=100.0)),
                    ("better", _with(tone_0dbsacd__thd_db=-160.0)), ("other", _with(dsd_rate=5644800))):
        (tmp_path / name).mkdir()
        (tmp_path / name / "results.json").write_text(json.dumps({"metrics": m}))
    old = str(tmp_path / "old")
    assert cli.main(["gate", old, str(tmp_path / "same")]) == 0
    assert "PASS" in capsys.readouterr().out
    assert cli.main(["gate", old, str(tmp_path / "worse"), "--json", str(tmp_path / "g.json")]) == 1
    out = capsys.readouterr().out
    assert "FAIL: worse beyond repeatability: SINAD, 1 kHz at 0 dB SACD" in out
    saved = json.loads((tmp_path / "g.json").read_text())
    assert saved["pass"] is False and saved["rows"][0]["verdict"] == "worse"
    assert cli.main(["gate", old, str(tmp_path / "better")]) == 0
    assert "better: THD, 1 kHz at 0 dB SACD" in capsys.readouterr().out
    assert cli.main(["gate", old, str(tmp_path / "other")]) == 2  # not comparable
    assert "DSD rate differs" in capsys.readouterr().err
    assert cli.main(["gate", old, str(tmp_path / "nowhere")]) == 2


def test_interrupt_stops_the_workers_and_their_tools(tmp_path, monkeypatch):
    """Ctrl-C (or any error) in a parallel run: the tool a worker is running is killed and nothing is left."""
    import subprocess
    import time
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join(sys.path))
    marker = f"dsdm-sleeper-{os.getpid()}"
    tool = tmp_path / "slow.py"
    # converts the pre-flight signal at once, then hangs on every later call
    tool.write_text(f"import sys, time, runpy\nfrom pathlib import Path\nst = Path({str(tmp_path / 'n')!r})\n"
                    "n = int(st.read_text()) if st.exists() else 0\nst.write_text(str(n + 1))\n"
                    f"if n:\n    time.sleep(120)  # {marker}\n"
                    f"sys.argv = [{str(STUB)!r}] + sys.argv[1:3]\nrunpy.run_path({str(STUB)!r}, run_name='__main__')\n")
    cmd = f"{sys.executable} {tool} {{input}} {{output}} {marker}"
    slow = f'[[device]]\nname = "slow"\nadapter = "cli"\nclass = "A"\ncommand = {json.dumps(cmd)}\n'
    s = _suite(tmp_path, [slow, REF_B])

    def log(msg="", end="\n"):
        if "] -> ref b: polarity" in msg:  # the quick device is done, the slow one hangs in its tool
            time.sleep(1.0)
            raise KeyboardInterrupt

    t0 = time.time()
    with pytest.raises(KeyboardInterrupt):
        run_suite(s, tmp_path / "out", only=["polarity", "tone_15k"], log=log, jobs=3, cache=False)
    assert time.time() - t0 < 60
    for _ in range(50):
        left = subprocess.run(["pgrep", "-f", marker], capture_output=True, text=True).stdout.split()
        if not left:
            break
        time.sleep(0.2)
    assert not left, f"tool processes left running: {left}"
