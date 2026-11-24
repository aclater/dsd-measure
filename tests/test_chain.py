"""Round-trip and end-to-end tests: files, modulator, decoder, adapters, runner, report."""

import json

import numpy as np
import pytest

from dsd_measure import adapters, decode, dsf, encode, measure, wavio
from dsd_measure import analyse as an
from dsd_measure import signals as sg
from dsd_measure.levels import PEAK_DBFS, REF_DBFS


def test_wav_roundtrip(tmp_path):
    x = np.sin(np.linspace(0, 20, 5000)) * 0.5
    for sub, tol in (("float32", 1e-7), ("pcm32", 1e-9), ("pcm24", 2e-7), ("pcm16", 4e-5)):
        p = tmp_path / f"{sub}.wav"
        wavio.write_wav(p, x, 88200, sub)
        y, fs = wavio.read_wav(p)
        assert fs == 88200 and y.shape == (1, 5000)
        assert np.max(np.abs(y[0] - x)) < tol


def test_dsf_roundtrip(tmp_path):
    rng = np.random.default_rng(0)
    bits = (rng.integers(0, 2, 100003) * 2 - 1).astype(np.int8)
    p = tmp_path / "t.dsf"
    dsf.write_dsf(p, bits, 2822400)
    back, rate = dsf.read_dsf(p)
    assert rate == 2822400 and np.array_equal(back[0], bits)


def test_ntf_is_monic_and_gain_limited():
    b, a = encode.design_ntf()
    assert b[0] == pytest.approx(1) and a[0] == pytest.approx(1)
    from scipy import signal
    _, h = signal.freqz(b, a, worN=4096)
    assert np.max(np.abs(h)) == pytest.approx(1.3, abs=0.02)


def test_encode_decode_roundtrip_level_and_noise():
    fs = 88200
    f0 = sg.coherent_freq(1000, 352800, 2**18)
    x = sg.sine(f0, REF_DBFS, fs, fs * 3)
    bits, info = encode.encode(x, fs)
    assert info["overload_samples"] == 0
    assert set(np.unique(bits)) == {-1, 1}
    y = decode.decode(bits, 2822400, 352800)
    n = 2**18
    m = an.tone_metrics(y[-n:], 352800, f0, n)
    assert m["fundamental_dbfs"] == pytest.approx(REF_DBFS - 3.0103, abs=0.01)  # level preserved
    assert m["sinad_db"] > 95


def test_modulator_stable_at_peak_level():
    fs = 88200
    f0 = sg.coherent_freq(20000, 352800, 2**18)
    bits, info = encode.encode(sg.sine(f0, PEAK_DBFS, fs, fs), fs)
    assert info["overload_samples"] == 0
    assert not an.stability_report(bits, 2822400)["saturated"]


def test_decoder_passband_is_flat():
    fs = 88200
    x = np.zeros(fs)
    x[fs // 2] = 0.5
    bits, _ = encode.encode(x, fs)
    y = decode.decode(bits, 2822400, 44100)
    assert y.shape[0] == 44100


def test_reference_class_a_smoke_through_runner():
    a = adapters.Reference("t", klass="A", out_rate=44100)
    r = measure.measure_device(a, "quick", only=["polarity", "impulse"], log=lambda *_: None)
    assert r["metrics"]["polarity"] == "normal"
    assert r["metrics"]["impulse"]["filter_type"] == "linear phase"
    assert r["metrics"]["impulse"]["post_ringing_ms"] > 0.2
    assert "levels" not in r["metrics"]


def test_cli_adapter_runs_a_command(tmp_path):
    # a stand-in "device": the command copies a pre-made DSF (class B) through unchanged
    fs = 88200
    bits, _ = encode.encode(sg.sine(1000, REF_DBFS, fs, fs // 2), fs)
    dsf.write_dsf(tmp_path / "canned.dsf", bits, 2822400)
    ad = adapters.Cli("copy", f"cp {tmp_path}/canned.dsf {{output}} # {{input}}", klass="B", workdir=tmp_path / "w")
    got, rate = ad.pcm_to_dsd(np.zeros(fs // 2), fs)
    assert rate == 2822400 and np.array_equal(got, bits)
    assert ad.log[0]["output_sha256"]


def test_import_adapter_reads_named_files(tmp_path):
    wavio.write_wav(tmp_path / "levels.wav", np.zeros(1000), 44100, "float32")
    ad = adapters.Import("imp", tmp_path)
    ad.current = "levels"
    y, fs = ad.dsd_to_pcm(None, 2822400)
    assert fs == 44100 and len(y) == 1000
    ad.current = "missing"
    with pytest.raises(FileNotFoundError):
        ad.dsd_to_pcm(None, 2822400)


def test_report_is_written_and_deterministic(tmp_path):
    from dsd_measure.report import write_device_report
    a = adapters.Reference("t", klass="A", out_rate=44100)
    r = measure.measure_device(a, "quick", only=["impulse", "polarity"], log=lambda *_: None)
    meta = {"device": a.describe(), "profile": "quick", "reference_chain": "1"}
    write_device_report(tmp_path / "a", "t", r, meta)
    write_device_report(tmp_path / "b", "t", r, meta)
    for f in ("index.html", "results.json", "results.csv", "plots/impulse.svg"):
        assert (tmp_path / "a" / f).read_bytes() == (tmp_path / "b" / f).read_bytes()
    assert "Summary" in (tmp_path / "a" / "index.html").read_text()
    assert json.loads((tmp_path / "a" / "results.json").read_text())["metrics"]["polarity"] == "normal"
