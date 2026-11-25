"""0.1.3: long records are made and analysed in pieces (issue 3), and a class B device with a
48 kHz-family input has its impulse and step read on the 44.1 kHz grid (issue 7).

The streaming tests hold two promises: the pieces give the same numbers as the whole record
(bit for bit where the arithmetic is the same, see each test), and the working memory does not
grow with the length of the record.
"""

import tracemalloc
from fractions import Fraction

import numpy as np
import pytest
from scipy import signal

from dsd_measure import analyse as an
from dsd_measure import decode, encode, measure
from dsd_measure import signals as sg
from dsd_measure.adapters import Reference
from dsd_measure.levels import PEAK_DBFS

# ---------------------------------------------------------------- the pieces give the whole


def _random_cuts(x, rng, lo=1, hi=5000):
    cuts, i = [], 0
    while i < len(x):
        j = i + int(rng.integers(lo, hi))
        cuts.append(x[i:j])
        i = j
    return cuts


@pytest.mark.parametrize("L,ntaps", [(2, 2047), (2, 255), (3, 255), (5, 255)])
def test_upsample_pieces_do_not_depend_on_how_the_input_arrives(L, ntaps, monkeypatch):
    monkeypatch.setattr(encode, "PIECE", 3000)
    rng = np.random.default_rng(3)
    x = rng.standard_normal(20011)
    h = signal.firwin(ntaps, 1.0 / L, window=("kaiser", 15.0))
    whole = encode._upsample(x, L, h)
    cut = np.concatenate(list(encode._upsample_pieces(_random_cuts(x, rng), len(x), L, h)))
    assert np.array_equal(whole, cut)


def test_modulator_pieces_are_the_whole_record():
    """The loop state carries across pieces: the same bits, the same overload count and peak."""
    rng = np.random.default_rng(4)
    u = 0.5 * np.sin(2 * np.pi * 1000 * np.arange(300_000) / 2822400) + 0.001 * rng.standard_normal(300_000)
    b, a = encode.design_ntf(8, 1.3, fs=2822400)
    for use_c in (True, False):
        n = 300_000 if use_c else 3000
        whole, over, wmax = encode._modulate(u[:n], b, a, use_c=use_c)
        state, v, o, w = (np.zeros(8), np.zeros(8)), np.empty(n, dtype=np.int8), 0, 0.0
        for i in range(0, n, 977):
            _, oo, w = encode._modulate(u[i : min(n, i + 977)], b, a, use_c=use_c, state=state, wmax0=w,
                                        v=v[i : min(n, i + 977)])
            o += oo
        assert np.array_equal(whole, v) and over == o and wmax == w


def test_streamed_bitstream_is_the_one_shot_bitstream(monkeypatch):
    """encode() interpolates and modulates piece by piece; the one-shot way (whole interpolation, then
    one modulator call) gives the same bitstream, hash for hash, across several pieces of every stage."""
    import hashlib
    monkeypatch.setattr(encode, "PIECE", 4096)
    x = sg.sine(1000.0, PEAK_DBFS, 88200, 20000)
    bits, info = encode.encode(x, 88200, 2822400, order=8, hinf=1.3)
    b, a = encode.design_ntf(8, 1.3, fs=2822400)
    once, over, wmax = encode._modulate(encode.interpolate(x, 32), b, a)
    assert hashlib.sha256(bits.tobytes()).hexdigest() == hashlib.sha256(once.tobytes()).hexdigest()
    assert info["overload_samples"] == over and info["max_w"] == round(wmax, 3)


def test_decoder_pieces_are_the_whole_record(monkeypatch):
    monkeypatch.setattr(decode, "PIECE", 3000)
    rng = np.random.default_rng(5)
    for rate, out in ((2822400, 352800), (2822400, 88200), (11289600, 176400)):
        bits = np.where(rng.random(1_300_007) > 0.5, 1, -1).astype(np.int8)
        x, fs = bits.astype(np.float64), rate  # the whole record, stage by stage
        for q in decode.stage_plan(rate, out):
            taps, fs_out = decode.decimator(fs, q, decode.keep_edge(out))
            x = signal.resample_poly(x, 1, q, window=taps)
            fs = fs_out
        assert np.array_equal(decode.decode(bits, rate, out), x)


def _old_stability_report(bits, window=28):
    b = (np.asarray(bits) > 0).astype(np.int32)
    c = np.concatenate([[0], np.cumsum(b, dtype=np.int64)])
    dens = (c[window:] - c[:-window]) / window
    mod = 2 * dens - 1
    edges = np.concatenate([[-1], np.flatnonzero(np.diff(b.astype(np.int8)) != 0), [len(b) - 1]])
    rep = {"max_density": float(dens.max()), "min_density": float(dens.min()),
           "max_modulation_pct": float(100 * mod.max()), "min_modulation_pct": float(100 * mod.min()),
           "saturated": bool(dens.max() >= 1.0 or dens.min() <= 0.0),
           "longest_run": int(np.max(np.diff(edges))), "mean_density": float(np.mean(b > 0))}
    return rep, dens


def test_stability_scan_is_the_whole_record_report():
    rng = np.random.default_rng(6)
    bits = np.where(rng.random(200_003) > 0.3, 1, -1).astype(np.int8)
    bits[5000:5100] = 1  # a long run, across a cut
    bits[-60:] = -1
    want, dens = _old_stability_report(bits)
    for step in (1 << 22, 4096, 977):
        scan = an.StabilityScan(row=10_000)
        scan.PIECE = step
        scan.feed(bits)
        assert scan.report() == want
        top, bottom, mean = scan.rows()
        k = len(dens) // 10_000
        m = (2 * dens[: k * 10_000] - 1).reshape(k, 10_000) * 100
        assert len(top) == k
        assert np.allclose(top, m.max(1), rtol=0, atol=1e-9) and np.allclose(bottom, m.min(1), rtol=0, atol=1e-9)
        assert np.allclose(mean, m.mean(1), rtol=0, atol=1e-9)
    assert an.stability_report(bits, 2822400) == want
    # a saturated record
    assert an.stability_report(np.ones(100), 2822400)["saturated"]


def test_stability_scan_refuses_a_record_shorter_than_the_window():
    scan = an.StabilityScan()
    scan.feed(np.ones(10))
    with pytest.raises(ValueError):
        scan.report()


# ---------------------------------------------------------------- memory does not grow with the record


def _peak(fn):
    tracemalloc.start()
    try:
        fn()
        return tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()


def test_encode_memory_is_the_bits_not_the_float_records(monkeypatch):
    """Eight seconds at DSD64 (22.6 M bits): the old encoder held about 17 bytes per bit at its peak
    (the interpolated record twice, as float64); the pieces keep one byte per bit and a few small pieces."""
    monkeypatch.setattr(encode, "PIECE", 1 << 15)
    x = sg.sine(1000.0, -6.0, 88200, 88200 * 8)
    n = len(x) * 32
    peak = _peak(lambda: encode.encode(x, 88200, 2822400, order=8, hinf=1.3))
    assert peak < 3 * n, f"peak {peak / n:.2f} bytes per bit"


def test_analysis_memory_is_one_piece(monkeypatch):
    """The old stability report made about 28 bytes of arrays per bit."""
    monkeypatch.setattr(an.StabilityScan, "PIECE", 1 << 18)
    bits = np.where(np.random.default_rng(7).random(30_000_000) > 0.5, 1, -1).astype(np.int8)
    peak = _peak(lambda: an.stability_report(bits, 2822400))
    assert peak < 0.5 * len(bits), f"peak {peak / len(bits):.3f} bytes per bit"


def test_decoder_memory_is_the_output_not_float_bits(monkeypatch):
    monkeypatch.setattr(decode, "PIECE", 1 << 13)
    bits = np.where(np.random.default_rng(8).random(20_000_000) > 0.5, 1, -1).astype(np.int8)
    peak = _peak(lambda: decode.decode(bits, 2822400, 352800))
    assert peak < 1.6 * len(bits), f"peak {peak / len(bits):.3f} bytes per bit"  # the old decoder: more than 8 bytes per bit


# ---------------------------------------------------------------- class B with a 48 kHz-family input


class Resampled(Reference):
    """A class B test device that takes a 48 kHz-family input: the reference modulator behind a
    resampler to the 44.1 kHz grid (the reference modulator itself needs an input rate that divides the DSD rate)."""

    def pcm_to_dsd(self, x, fs):
        g = measure.grid_rate(fs)
        if g != fs:
            f = Fraction(g, fs)
            up, down = f.numerator, f.denominator
            h = signal.firwin(120 * max(up, down) + 1, 0.95 / max(up, down), window=("kaiser", 0.1102 * (160 - 8.7)))
            x = signal.resample_poly(x, up, down, window=h)
        return super().pcm_to_dsd(x, g)


def test_grid_rate():
    assert [measure.grid_rate(r) for r in (44100, 88200, 176400, 352800)] == [44100, 88200, 176400, 352800]
    assert [measure.grid_rate(r) for r in (48000, 96000, 192000, 384000)] == [88200, 176400, 352800, 705600]


def _impulse_run(adapter, in_rate):
    return measure.measure_device(adapter, "quick", in_rate=in_rate, only=["impulse"], log=lambda *a, **k: None,
                                  finish=False)


@pytest.mark.parametrize("in_rate", [48000, 96000])
def test_class_b_impulse_runs_with_a_48k_family_input(in_rate):
    """Issue 7: this raised "out_rate must divide the DSD rate" in the reference decoder."""
    res = _impulse_run(Resampled("modulator", klass="B"), in_rate)
    assert not res["errors"] and "impulse" not in res["not_run"], res["not_run"]
    assert res["metrics"]["impulse"]["output_rate"] == measure.grid_rate(in_rate)
    assert "step" in res["metrics"]


def test_impulse_and_step_positions_sit_on_grid_samples():
    """Every impulse position (and step edge) of a class B record is a whole grid sample, so nothing is
    shifted by a rounding of the position (a half-sample shift moves the whole measured response in time)."""
    for in_rate in (44100, 88200, 176400, 352800, 48000, 96000, 192000, 384000):
        num, den, sp, half = measure.grid_layout(in_rate)
        assert Fraction(num, den) == Fraction(measure.grid_rate(in_rate), in_rate)
        assert sp % den == 0 and sp >= 8192 and half % den == 0
        assert all((half + j * sp) * num % den == 0 for j in range(64))
        per = -(-16384 // (2 * den)) * 2 * den  # the step record's period, as in measure.py
        assert all((per // 2 + i * per) * num % den == 0 for i in range(1, 9))
        if den == 1:  # a 44.1 kHz-family input: the positions are those of 0.1.2
            assert (sp, half) == (8192, 4096)


def test_48k_family_impulse_reads_the_same_response_as_the_neighbouring_44k_rate():
    """The reference modulator is flat in band, so the response through the reference decoder at
    88.2 kHz must be the same whether the input was 88.2 kHz or 48 kHz (through a resampler whose own
    response is flat to 0.01 dB below 20 kHz)."""
    def response(adapter, in_rate):
        res = _impulse_run(adapter, in_rate)
        p = res["plots"]["impulse"]
        h = np.zeros(2**17)
        h[: len(p["h"])] = p["h"]
        f, mag, _ = an.response_from_impulse(h, p["fs"], nfft=2**17)
        return f, mag - np.interp(1000, f, mag)
    f, ref = response(Reference("reference", klass="B"), 88200)
    f2, dev = response(Resampled("modulator", klass="B"), 48000)
    band = (f >= 20) & (f <= 20000)
    assert np.max(np.abs(dev[band] - ref[band])) < 0.01
    assert np.ptp(ref[band]) < 0.01  # the reference itself is flat, so the comparison means something


def test_48k_family_impulse_is_not_shifted_in_time():
    """A half grid sample (5.7 us at 88.2 kHz) of shift in the impulse positions moves the peak and the
    group delay; the 48 kHz reading must equal the 88.2 kHz reading to a small fraction of a sample."""
    a = _impulse_run(Reference("reference", klass="B"), 88200)
    b = _impulse_run(Resampled("modulator", klass="B"), 48000)
    pa, pb = a["plots"]["impulse"], b["plots"]["impulse"]
    assert pa["fs"] == pb["fs"] == 88200
    shift = (pb["center"] - pa["center"]) / pa["fs"] * 1e6
    gd = [r["metrics"]["group_delay_us"]["at_1k"] for r in (a, b)]
    print(f"peak shift {shift:.3f} us, group delay at 1 kHz {gd[0]:.3f} us and {gd[1]:.3f} us")
    assert abs(shift) < 0.5 * 1e6 / 88200 * 0.2  # a fifth of a half sample is far below the shift this catches
    assert abs(gd[1] - gd[0]) < 1.0


# ---------------------------------------------------------------- DSF files in pieces


def _whole_dsf(bits, rate):
    """The DSF bytes as 0.1.2 made them: the whole record packed in memory at once."""
    import struct

    from dsd_measure.dsf import BLOCK
    b = np.atleast_2d(bits)
    ch, n = b.shape
    pad = (-n) % (BLOCK * 8)
    idle = np.unpackbits(np.array([0x69], np.uint8), bitorder="little")
    tail = np.tile(idle[(n + np.arange(pad)) % 8], (ch, 1)).astype(np.uint8)
    bb = np.concatenate([(b > 0).astype(np.uint8), tail], axis=1)
    packed = np.packbits(bb.reshape(ch, -1, 8), axis=2, bitorder="little").reshape(ch, -1)
    data = packed.reshape(ch, -1, BLOCK).transpose(1, 0, 2).reshape(-1).tobytes()
    fmt = struct.pack("<4sQIIIIIIQI4x", b"fmt ", 52, 1, 0, ch if ch <= 6 else 7, ch, rate, 1, n, BLOCK)
    return (struct.pack("<4sQQQ", b"DSD ", 28, 28 + 52 + 12 + len(data), 0) + fmt
            + struct.pack("<4sQ", b"data", 12 + len(data)) + data)


@pytest.mark.parametrize("ch,n", [(1, 5), (1, 100_001), (2, 32768 * 3 + 17), (3, 40_000)])
def test_dsf_in_pieces_is_the_whole_file(tmp_path, monkeypatch, ch, n):
    from dsd_measure import dsf
    monkeypatch.setattr(dsf, "GROUP", 3)
    bits = np.where(np.random.default_rng(9).random((ch, n)) > 0.5, 1, -1).astype(np.int8)
    p = tmp_path / "x.dsf"
    dsf.write_dsf(p, bits, 2822400)
    assert p.read_bytes() == _whole_dsf(bits, 2822400)
    back, rate = dsf.read_dsf(p)
    assert rate == 2822400 and back.dtype == np.int8 and np.array_equal(back, bits)


def test_dsf_writer_memory_is_one_group(tmp_path, monkeypatch):
    """The whole-record writer made about four bytes of arrays per bit."""
    from dsd_measure import dsf
    monkeypatch.setattr(dsf, "GROUP", 16)
    bits = np.where(np.random.default_rng(10).random(40_000_000) > 0.5, 1, -1).astype(np.int8)
    peak = _peak(lambda: dsf.write_dsf(tmp_path / "x.dsf", bits, 2822400))
    assert peak < 0.3 * len(bits), f"peak {peak / len(bits):.3f} bytes per bit"
