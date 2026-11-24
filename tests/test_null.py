"""The null test: streaming readers, resampling, alignment, and the three self-validations.

(a) a decoder against itself gives a perfect null; (b) a known small change (an added -100 dB tone,
a 0.1 dB gain, a fractional delay, an inverted polarity) is recovered accurately; (c) the reference
decoder against itself at different rates behaves as documented.
"""

import numpy as np
import pytest

from dsd_measure import decode, dsf, encode, wavio
from dsd_measure.dsdstream import DsdFile, convert
from dsd_measure.nulltest import devices
from dsd_measure.nulltest.analyse import Options, common_rate, compare, third_octave_bands
from dsd_measure.nulltest.run import run_null
from dsd_measure.nulltest.tracks import ArrayTrack, ResampledTrack, WavTrack
from dsd_measure.nulltest.verdict import tier


def music(n, fs, seed=1, top=0.4):
    """Band-limited, pink-ish noise with an exactly known spectrum (so shifts by FFT are exact)."""
    r = np.random.default_rng(seed)
    X = np.fft.rfft(r.standard_normal(n))
    f = np.fft.rfftfreq(n, 1 / fs)
    X *= (1 / np.sqrt(np.maximum(f, 30))) * (f < top * fs)
    x = np.fft.irfft(X, n)
    return x * 0.1 / np.std(x)


def fshift(x, d):
    """Delay by ``d`` samples (fractional) exactly, for a band-limited periodic signal."""
    f = np.fft.rfftfreq(len(x))
    return np.fft.irfft(np.fft.rfft(x) * np.exp(-2j * np.pi * f * d), len(x))


FS = 88200


@pytest.fixture(scope="module")
def base():
    return music(FS * 14, FS)


def run(a, b, fs=FS, **kw):
    r = compare(ArrayTrack(a, fs), ArrayTrack(b, fs), Options(**kw))
    return r, r["channels"][0]


# ---- readers

def test_dsd_file_ranges_match_whole_file_readers(tmp_path):
    rng = np.random.default_rng(0)
    bits = (rng.integers(0, 2, (2, 100003)) * 2 - 1).astype(np.int8)
    dsf.write_dsf(tmp_path / "a.dsf", bits, 2822400)
    dsf.write_dff(tmp_path / "a.dff", bits, 2822400)
    for name in ("a.dsf", "a.dff"):
        f = DsdFile(tmp_path / name)
        assert (f.channels, f.rate) == (2, 2822400) and f.samples in (100003, 100008)  # DFF counts whole bytes
        for ch in (0, 1):
            assert np.array_equal(f.bits(ch, 0, 100003), bits[ch])
            assert np.array_equal(f.bits(ch, 4093, 40011), bits[ch, 4093:40011])
        # outside the file reads as 0 (silence), not +-1
        assert np.array_equal(f.bits(0, -5, 0), np.zeros(5, np.int8))


def test_convert_is_bit_exact_both_ways(tmp_path):
    rng = np.random.default_rng(1)
    bits = (rng.integers(0, 2, (2, 70001)) * 2 - 1).astype(np.int8)
    dsf.write_dsf(tmp_path / "a.dsf", bits, 2822400)
    convert(tmp_path / "a.dsf", tmp_path / "b.dff", "dff")
    convert(tmp_path / "b.dff", tmp_path / "c.dsf", "dsf")
    for n in ("b.dff", "c.dsf"):
        f = DsdFile(tmp_path / n)
        assert f.samples >= 70001 and all(np.array_equal(f.bits(c, 0, 70001), bits[c]) for c in (0, 1))


def test_dst_is_refused(tmp_path):
    import struct
    prop = b"SND " + b"CMPR" + struct.pack(">Q", 4) + b"DST "
    body = b"DSD " + b"PROP" + struct.pack(">Q", len(prop)) + prop
    (tmp_path / "x.dff").write_bytes(b"FRM8" + struct.pack(">Q", len(body)) + body)
    with pytest.raises(ValueError, match="DST"):
        DsdFile(tmp_path / "x.dff")


def test_wav_track_matches_reader(tmp_path):
    x = np.random.default_rng(0).uniform(-0.5, 0.5, (2, 5000))
    for sub in ("float32", "pcm16", "pcm24", "pcm32"):
        wavio.write_wav(tmp_path / f"{sub}.wav", x, 44100, sub)
        t = WavTrack(tmp_path / f"{sub}.wav")
        ref, _ = wavio.read_wav(tmp_path / f"{sub}.wav")
        assert (t.channels, t.length, t.rate) == (2, 5000, 44100)
        assert np.array_equal(t.read(1, 100, 4000), ref[1, 100:4000])
        assert np.array_equal(t.read(0, -3, 2), np.concatenate([np.zeros(3), ref[0, :2]]))


def test_ranged_resampling_equals_whole():
    x = music(FS * 3, FS)
    t = ResampledTrack(ArrayTrack(x, FS), 44100)
    whole = t.read(0, 0, t.length)
    parts = np.concatenate([t.read(0, s, min(s + 30011, t.length)) for s in range(0, t.length, 30011)])
    assert np.max(np.abs(whole - parts)) < 1e-12


def test_resampler_passband_and_alias_rejection():
    n = FS * 4
    for f0, expect in ((10000, 1.0), (30000, 0.0)):
        x = np.sin(2 * np.pi * f0 * np.arange(n) / FS) * 0.5
        y = ResampledTrack(ArrayTrack(x, FS), 44100).read(0, 20000, 120000)
        amp = np.sqrt(2) * np.std(y)
        assert abs(amp - 0.5 * expect) < (1e-6 if expect else 1e-7)


def test_awkward_ratio_is_refused_and_upsampling_is_refused():
    with pytest.raises(ValueError, match="awkward"):
        ResampledTrack(ArrayTrack(np.zeros(10), 44099), 48000)
    with pytest.raises(ValueError, match="resampling up"):
        common_rate(44100, 88200, 176400)


# ---- (a) perfect null

def test_same_track_against_itself_is_a_perfect_null(base):
    r, c = run(base, base)
    assert c["identical"] and c["null_depth_db"] > 250
    assert abs(c["delay_samples"]) < 1e-9 and abs(c["gain_db"]) < 1e-9 and not c["polarity_inverted"]


# ---- (b) known small changes are recovered

def test_added_tone_at_minus_100_db_is_measured(base):
    n = len(base)
    amp = 10 ** (-100 / 20) * np.std(base) * np.sqrt(2)  # a tone 100 dB below the music's RMS
    b = base + amp * np.sin(2 * np.pi * 1000 * np.arange(n) / FS)
    r, c = run(base, b)
    assert c["null_depth_db"] == pytest.approx(100.0, abs=0.05)
    bands = {round(x["centre_hz"]): x for x in c["bands"]}
    assert bands[1000]["diff_dbfs"] > bands[500]["diff_dbfs"] + 40  # it sits in the 1 kHz band


def test_gain_of_0p1_db_is_recovered_and_matched_out(base):
    g = 10 ** (0.1 / 20)
    r, c = run(base, base * g)
    assert -c["gain_db"] == pytest.approx(0.1, abs=1e-6)
    assert c["null_depth_db"] > 250 or c["null_depth_db"] > 200


def test_fractional_delay_is_recovered_to_a_thousandth_of_a_sample(base):
    for d in (0.3, -1.7, 12.45):
        r, c = run(base, fshift(base, d))
        assert c["delay_samples"] == pytest.approx(d, abs=1e-3)
        assert c["null_depth_db"] > 120, d


def test_delay_gain_polarity_and_tone_together(base):
    n = len(base)
    amp = 10 ** (-90 / 20) * np.std(base) * np.sqrt(2)
    b = -0.9 * (fshift(base, 7.6) + amp * np.sin(2 * np.pi * 2000 * np.arange(n) / FS))
    r, c = run(base, b)
    assert c["polarity_inverted"] and c["delay_samples"] == pytest.approx(7.6, abs=1e-3)
    assert -c["gain_db"] == pytest.approx(20 * np.log10(0.9), abs=1e-3)
    assert c["null_depth_db"] == pytest.approx(90.0, abs=0.5)


def test_polarity_keep_leaves_inversion_in_the_difference(base):
    r, c = run(base, -base, polarity="keep")
    assert not c["polarity_inverted"] and c["null_depth_db"] < 3


def test_gain_none_reports_the_level_difference_as_the_difference(base):
    r, c = run(base, base * 1.1, gain="none")
    assert c["null_depth_db"] == pytest.approx(20.0, abs=0.3)


def test_different_rates_are_resampled_to_the_lower(base):
    a = base
    b = ResampledTrack(ArrayTrack(a, FS), 44100)
    bb = np.array([b.read(0, 0, b.length)])
    r = compare(ArrayTrack(a, FS), ArrayTrack(bb, 44100), Options())
    assert r["common_rate"] == 44100 and "A" in r["resampled"] and "B" not in r["resampled"]
    assert r["channels"][0]["null_depth_db"] > 100


def test_channel_count_mismatch_is_refused(base):
    with pytest.raises(ValueError, match="channels"):
        compare(ArrayTrack(base, FS), ArrayTrack(np.array([base, base]), FS), Options())


def test_bands_are_third_octaves_and_stop_below_the_analysis_limit():
    b = third_octave_bands(0.45 * 44100)
    assert b[0][0] == pytest.approx(19.7, abs=0.1) and b[-1][2] <= 0.45 * 44100
    assert all(abs(hi / lo - 2 ** (1 / 3)) < 1e-9 for _, lo, hi in b)


def test_verdict_words_do_not_call_a_shallow_null_audible():  # N11
    from dsd_measure.nulltest.verdict import TIERS, verdict
    assert not any("potentially audible" in t or "different sounds" in t or "likely audible" in t for _, _, t in TIERS)
    ch = {"channel": "L", "null_depth_db": 27.0, "polarity_inverted": False, "gain_db": -0.10, "bands": []}
    v = verdict([ch])
    assert "27 dB" in v["headline"] and "cannot say whether that is audible" in v["headline"]
    assert "fitted gain" in v["details"][0]
    ident = verdict([{**ch, "null_depth_db": 400.0}])
    assert "level matching (device B is 0.10 dB louder" in ident["headline"]  # a copy 0.1 dB louder is not plain "identical"


def test_tiers():
    assert tier(400)[0] == "identical" and tier(110)[0] == "far-below" and tier(45)[0] == "borderline"
    assert tier(5)[0] == "audible"


# ---- (c) the reference decoder at different rates, and the real end-to-end path

@pytest.fixture(scope="module")
def dsd_source(tmp_path_factory):
    fs, n = 88200, 88200 * 4
    x = music(n, fs, top=0.2) * 1.2
    bits, _ = encode.encode(x, fs, 2822400)
    p = tmp_path_factory.mktemp("src") / "m.dsf"
    dsf.write_dsf(p, bits, 2822400)
    return p


def test_chunked_reference_decode_equals_whole_file_decode(dsd_source):
    f = DsdFile(dsd_source)
    full = decode.decode(f.bits(0, 0, f.samples).astype(float), f.rate, 352800)
    t = devices.RefDecoderTrack(f, 352800)
    assert np.max(np.abs(t.read(0, 100000, 400001) - full[100000:400001])) < 1e-12


def test_reference_at_two_rates_matches_below_20k_and_differs_above(dsd_source, tmp_path):
    run_ = run_null(dsd_source, ["reference@352800", "reference@176400"], Options(trim_start=0.3, trim_end=0.3),
                    tmp_path / "r", log=lambda *_: None)
    res = run_["pairs"][0]["result"]
    assert res["common_rate"] == 176400 and "A" in res["resampled"]
    c = res["channels"][0]
    audio = [b for b in c["bands"] if not b["ultrasonic"] and b["high_hz"] < 17500]  # this source has no music above 17.6 kHz
    assert min(b["depth_db"] for b in audio) > 120  # identical filter response up to 20 kHz
    # the band that holds 20 kHz is cut there: the part below is audio, the part above is ultrasonic
    assert any(b["high_hz"] == 20000.0 and not b["ultrasonic"] for b in c["bands"])
    assert any(b["low_hz"] == 20000.0 and b["ultrasonic"] for b in c["bands"])
    # above 20 kHz the 176.4 kHz decoder rolls off while the 352.8 kHz one does not: documented difference
    assert min(b["depth_db"] for b in c["bands"] if b["ultrasonic"]) < 40
    assert run_["pairs"][0]["verdict"]["tier"] == "far-below"


def test_reference_against_itself_and_through_a_command(dsd_source, tmp_path):
    script = tmp_path / "dec.py"
    script.write_text("import sys, numpy as np\nfrom dsd_measure.dsf import read_dsf\nfrom dsd_measure import decode, wavio\n"
                      "from dsd_measure.dsdstream import DsdFile\n"
                      "f = DsdFile(sys.argv[1])\n"
                      "wavio.write_wav(sys.argv[2], np.array([decode.decode(f.bits(c, 0, f.samples).astype(float), f.rate, 352800) for c in range(f.channels)]), 352800, 'float32')\n")
    cmd = f"viacmd={__import__('sys').executable} {script} {{input}} {{output}}"
    r = run_null(dsd_source, ["reference@352800", "reference@352800", cmd, "swapped=dff: " + cmd.split("=", 1)[1]],
                 Options(trim_start=0.3, trim_end=0.3, diff_wav=True), tmp_path / "o", log=lambda *_: None)
    self_pair, cli_pair, dff_pair = r["pairs"][0], r["pairs"][1], r["pairs"][2]
    assert self_pair["verdict"]["tier"] == "identical" and self_pair["b"] != self_pair["a"]
    assert cli_pair["result"]["channels"][0]["null_depth_db"] > 120  # float32 file against float64: about -144 dBFS
    assert dff_pair["result"]["channels"][0]["null_depth_db"] > 120  # DFF conversion did not change a bit
    assert (tmp_path / "o" / "index.html").exists() and (tmp_path / "o" / f"difference-{cli_pair['b']}.wav").exists()
    t = WavTrack(tmp_path / "o" / f"difference-{cli_pair['b']}.wav")
    assert t.channels == 1 and t.rate == 352800
