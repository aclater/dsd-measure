"""Regression tests for the fresh-eyes review of the 0.1.2 candidate."""
import struct

import pytest

from dsd_measure import outformat as of
from dsd_measure.adapters import with_args
from dsd_measure.nulltest.verdict import apply_format_limit


def _wav(path, fmt_body, data=b"\0\0", pre=b"", post=b""):
    chunks = pre + b"fmt " + struct.pack("<I", len(fmt_body)) + fmt_body + post + b"data" + struct.pack("<I", len(data)) + data
    path.write_bytes(b"RIFF" + struct.pack("<I", 4 + len(chunks)) + b"WAVE" + chunks)
    return path


def _fmt(tag=1, ch=1, rate=44100, bits=16):
    return struct.pack("<HHIIHH", tag, ch, rate, rate * ch * bits // 8, ch * bits // 8, bits)


def test_fmt_after_a_large_chunk(tmp_path):
    big = b"LIST" + struct.pack("<I", 200000) + bytes(200000)
    assert of.wav_format(_wav(tmp_path / "a.wav", _fmt(), pre=big))["bits"] == 16


def test_short_fmt_chunk_is_a_value_error(tmp_path):
    with pytest.raises(ValueError):
        of.wav_format(_wav(tmp_path / "a.wav", b"\1\0\1\0"))


def test_rate_zero_is_a_value_error(tmp_path):
    with pytest.raises(ValueError):
        of.wav_format(_wav(tmp_path / "a.wav", _fmt(rate=0)))


def test_extensible_valid_bits(tmp_path):
    ext = _fmt(tag=0xFFFE, bits=32) + struct.pack("<HHHI", 22, 16, 0, 0) + struct.pack("<H", 1) + bytes(14)
    assert of.wav_format(_wav(tmp_path / "a.wav", ext))["bits"] == 16


def test_float_and_32_bit_are_never_limited_and_24_bit_may_be(tmp_path):
    assert not of.limits_result(of.wav_format(_wav(tmp_path / "a.wav", _fmt(tag=3, bits=32))))
    assert not of.limits_result(of.wav_format(_wav(tmp_path / "c.wav", _fmt(bits=32))))
    assert of.limits_result(of.wav_format(_wav(tmp_path / "b.wav", _fmt(bits=24))))


def test_tone_shift_moves_the_limit():
    base = of.quantisation_sinad_db(16, 44100)
    assert of.quantisation_sinad_db(16, 44100, tone_shift_db=6.0) == pytest.approx(base + 6.0)
    assert of.summary({"container": "wav", "kind": "int", "bits": 16, "rate": 44100}, -6.0)["quantisation_sinad_db"] == pytest.approx(base - 6.0, abs=0.06)


def test_with_args_keeps_a_quoted_program_path():
    assert with_args('"/opt/my tools/dsd2pcm" {input} {output}', "--filter pysacd") == '"/opt/my tools/dsd2pcm" --filter pysacd {input} {output}'
    assert with_args("dsd2pcm {input} {output}", "-x") == "dsd2pcm -x {input} {output}"


def test_null_noise_follows_the_applied_gain():
    fmt = {"container": "wav", "kind": "int", "bits": 16, "rate": 352800}
    noise = 10 * __import__("math").log10((2.0 ** -15) ** 2 / 12 * 20000 / 176400)
    ch = {"diff_rms_audio_dbfs": noise - 7.0, "music_rms_audio_dbfs": -20.0}
    v = apply_format_limit({"details": [], "headline": ""}, ch, [("a", fmt, -7.0)])
    assert v.get("format_limited") == ["a"]
    v = apply_format_limit({"details": [], "headline": ""}, ch, [("a", fmt)])
    assert not v.get("format_limited")
