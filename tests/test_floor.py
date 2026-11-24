"""The reference floor, the stability guard and the stereo path."""

import numpy as np
import pytest
from scipy import signal

from dsd_measure import adapters, encode, floor, report
from dsd_measure import signals as sg
from dsd_measure.levels import PEAK_DBFS, REF_DBFS


@pytest.mark.parametrize("order", [5, 7, 8])
def test_ntf_gain_for_each_order(order):
    b, a = encode.design_ntf(order, 1.4)
    _, h = signal.freqz(b, a, worN=1 << 14)
    assert np.max(np.abs(h)) == pytest.approx(1.4, abs=0.02)
    assert len(b) == order + 1


def test_guard_falls_back_at_peak_level_and_is_clean_at_reference_level():
    fs = 88200
    f0 = sg.coherent_freq(1000, 352800, 2**18)
    _, hi = encode.encode(sg.sine(f0, REF_DBFS, fs, fs * 2), fs)
    assert hi["order"] >= 7 and hi["overload_samples"] == 0
    _, pk = encode.encode(sg.sine(f0, PEAK_DBFS, fs, fs * 2), fs)
    assert pk["fallbacks"] > 0 and pk["overload_samples"] == 0  # a lower-order design took over


def test_reference_floor_meets_target_and_decoder_is_not_the_limit():
    f = floor.reference_floor(2822400)
    assert f["chain"]["thdn_db"] <= floor.TARGET_DB
    assert f["decoder_alone"]["thdn_db"] < f["chain"]["thdn_db"] - 80
    assert f["decoder_alone"]["alias_rejection_db"] < -150


def test_floor_flags_figures_within_six_db():
    f = floor.reference_floor(2822400)
    lim = f["chain"]
    M = {"device_class": "A", "reference_floor": f,
         "tone_0dbsacd": {"thdn_db": lim["thdn_db"] + 3, "thd_db": -100.0, "thdn_a_db": -100.0,
                          "sinad_db": 100.0, "thdn_percent": 1e-5, "thd_percent": 1e-5}}
    assert "thdn" in floor.flags("A", M) and "thd" not in floor.flags("A", M)
    M["tone_0dbsacd"]["thdn_db"] = lim["thdn_db"] + 20
    assert "thdn" not in floor.flags("A", M)
    rows = report.summary_rows(M)
    assert any(r["section"] == "Reference floor" for r in rows)


def test_reference_adapter_stereo_channels_are_independent():
    fs = 88200
    a = adapters.Reference("t", klass="A", out_rate=44100)
    f0 = sg.coherent_freq(1000, 352800, 2**18)
    tone = sg.sine(f0, REF_DBFS, fs, fs // 2)
    bits, _ = encode.encode(tone, fs)
    st = np.array([bits, -bits])
    y, rate = a.dsd_to_pcm(st, 2822400)
    mono, _ = a.dsd_to_pcm(bits, 2822400)
    assert y.shape[0] == 2 and rate == 44100
    assert np.array_equal(y[0], mono) and np.allclose(y[1], -mono)


def test_reference_modulator_clips_to_peak_level_and_says_so():
    a = adapters.Reference("t", klass="B")
    x = sg.sine(sg.coherent_freq(1000, 352800, 2**18), 0.0, 88200, 88200 // 4)
    bits, rate = a.pcm_to_dsd(x, 88200)
    assert rate == 2822400 and a.log[-1]["clipped_to_peak_level"] is True


def test_dff_roundtrip_header_and_bits(tmp_path):
    from dsd_measure import dsf
    rng = np.random.default_rng(1)
    bits = (rng.integers(0, 2, 8003) * 2 - 1).astype(np.int8)
    p = tmp_path / "t.dff"
    dsf.write_dff(p, np.array([bits, -bits]), 2822400)
    raw = p.read_bytes()
    assert raw[:4] == b"FRM8" and raw[12:16] == b"DSD " and b"SLFT" in raw and b"SRGT" in raw
    pos = 16  # walk the chunks to the data chunk
    while raw[pos : pos + 4] != b"DSD ":
        size = int.from_bytes(raw[pos + 4 : pos + 12], "big")
        pos += 12 + size + (size & 1)
    data = np.frombuffer(raw[pos + 12 :], np.uint8)
    left = np.unpackbits(data[0::2])[:8003].astype(np.int8) * 2 - 1
    right = np.unpackbits(data[1::2])[:8003].astype(np.int8) * 2 - 1
    assert np.array_equal(left, bits) and np.array_equal(right, -bits)


def test_package_data_lists_the_multitone_file():
    """The wheel must carry the shared multitone definition (it was once missing from the install)."""
    import tomllib
    from pathlib import Path
    cfg = tomllib.loads((Path(__file__).parents[1] / "pyproject.toml").read_text())
    assert "data/*.json" in cfg["tool"]["setuptools"]["package-data"]["dsd_measure"]
