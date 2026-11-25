"""The null test: streaming readers, resampling, alignment, and the three self-validations.

(a) a decoder against itself gives a perfect null; (b) a known small change (an added -100 dB tone,
a 0.1 dB gain, a fractional delay, an inverted polarity) is recovered accurately; (c) the reference
decoder against itself at different rates behaves as documented.
"""

import re

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
    assert c["null_depth_fullband_db"] == pytest.approx(100.0, abs=0.05)  # 100 dB below the music's full-band RMS
    assert 98.5 < c["null_depth_db"] < 100.0  # the headline is in band: this music has some power above 20 kHz
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
    assert c["null_depth_fullband_db"] == pytest.approx(90.0, abs=0.5)
    assert 88.5 < c["null_depth_db"] < 90.0  # in band: this music has some power above 20 kHz


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
    assert not any(re.search(r"audib|inaudib|hearing|potentially|likely", t) for _, _, t in TIERS if "heard" not in t)
    assert not any("audib" in t for _, _, t in TIERS)
    ch = {"channel": "L", "null_depth_db": 27.0, "polarity_inverted": False, "gain_db": -0.10, "bands": []}
    v = verdict([ch])
    assert "27 dB" in v["headline"] and "depth band 20 to 40 dB" in v["headline"]
    assert "fitted gain" in v["details"][0]
    ident = verdict([{**ch, "null_depth_db": 400.0}])
    assert "level matching (device B is 0.10 dB louder" in ident["headline"]  # a copy 0.1 dB louder is not plain "identical"


def test_tiers():
    assert tier(400)[0] == "identical" and tier(110)[0] == "d100" and tier(45)[0] == "d40"
    assert tier(5)[0] == "d0"


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
    assert run_["pairs"][0]["verdict"]["tier"] == "d100"


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


# ---- alignment in the audio band (issue 4): ultrasonic noise must not steer the delay, polarity or level

def shaped_noise(n, fs, lo, hi, level, seed):
    """Noise that rises with frequency from ``lo`` to ``hi`` (like the ultrasonic noise of a DSD output)."""
    X = np.fft.rfft(np.random.default_rng(seed).standard_normal(n))
    f = np.fft.rfftfreq(n, 1 / fs)
    X *= np.where((f >= lo) & (f < hi), f / hi, 0.0)
    x = np.fft.irfft(X, n)
    return x * level / np.std(x)


def device_pair(fs, cut_a, cut_b, delay=0.0, gain=1.0, level=0.3):
    """The same music through two devices; each adds its own ultrasonic noise up to its own cut-off."""
    n = fs * 8
    m = music(n, fs, top=0.2)
    a = m + shaped_noise(n, fs, 22000, cut_a, level, 11)
    b = gain * (fshift(m, delay) + shaped_noise(n, fs, 22000, cut_b, level, 12))
    return a, b


def test_ultrasonic_noise_does_not_steer_the_alignment():
    for gain in (1.0, 0.7079, -0.7079, 0.1):  # matched, 3 dB down, inverted, 20 dB down
        a, b = device_pair(88200, 39000, 39000, delay=3.4, gain=gain)
        r, c = run(a, b)
        assert c["delay_samples"] == pytest.approx(3.4, abs=1e-3), gain
        assert c["polarity_inverted"] == (gain < 0)
        assert abs(c["gain_db"]) == pytest.approx(-20 * np.log10(abs(gain)), abs=0.01)
        assert c["correlation"] > 0.99 and c["null_depth_db"] > 100, gain
        assert not r["trust"]["untrustworthy"] and not r["trust"]["not_like_for_like"], gain


def test_different_passbands_are_flagged_and_aligned_in_the_common_band():
    fs = 176400
    a, b = device_pair(fs, 40000, 79000, delay=0.37, level=1.0)
    r, c = run(a, b, fs=fs)
    assert c["delay_samples"] == pytest.approx(0.37, abs=1e-3)
    t = r["trust"]
    assert t["not_like_for_like"] and not t["untrustworthy"]
    assert t["bandwidth_hz"]["A"] == pytest.approx(40000, rel=0.1) and t["bandwidth_hz"]["B"] > 70000
    assert r["null_band_hz"] == [20.0, 20000.0] and c["null_depth_db"] > 100
    assert c["null_depth_db"] > c["null_depth_fullband_db"] + 20  # the full-band figure is the noise, not the null


def lowpassed(x, fs, cut, floor, seed):
    """A device that passes ``x`` up to ``cut`` and adds its own noise floor."""
    f = np.fft.rfftfreq(len(x), 1 / fs)
    return np.fft.irfft(np.fft.rfft(x) * (f < cut), len(x)) + floor * np.random.default_rng(seed).standard_normal(len(x))


@pytest.mark.parametrize("fs,cut_a,cut_b,band_hi", [(88200, 18000, 15000, 15000), (176400, 30000, 40000, 20000),
                                                    (88200, 15000, 18000, 15000)])
def test_two_devices_cut_at_different_frequencies_are_both_seen(fs, cut_a, cut_b, band_hi):
    """Above the higher cut both are noise and the ratio is flat again, so the lower cut is the departure and
    the higher one is where it ends."""
    n = fs * 8
    m = music(n, fs, top=0.45)
    a, b = lowpassed(m, fs, cut_a, 1e-6, 1), lowpassed(m, fs, cut_b, 1e-6, 2)
    r, c = run(a, b, fs=fs)
    t = r["trust"]
    print(f"{fs} Hz, cuts {cut_a} and {cut_b}: estimated {t['bandwidth_hz']}")
    assert t["not_like_for_like"] and t["cut_seen"] == {"A": True, "B": True}
    assert t["bandwidth_hz"]["A"] == pytest.approx(cut_a, rel=0.1) and t["bandwidth_hz"]["B"] == pytest.approx(cut_b, rel=0.1)
    assert r["null_band_hz"][1] == pytest.approx(min(band_hi, 0.45 * fs if band_hi > 20000 else band_hi), rel=0.1)
    assert t["null_band_affected"] is (min(cut_a, cut_b) < 20000)


@pytest.mark.parametrize("floor_a,floor_b", [(1e-6, 1e-6), (1e-6, 2e-5)])
def test_a_source_with_little_high_frequency_energy_is_not_a_cut(floor_a, floor_b):
    """The music ends at 17.6 kHz; both devices pass up to 40 kHz. Two noise floors that differ by 25 dB, far below
    the music, are not a cut."""
    fs = 88200
    n = fs * 8
    m = music(n, fs, top=0.2)
    r, c = run(lowpassed(m, fs, 40000, floor_a, 1), lowpassed(m, fs, 40000, floor_b, 2), fs=fs)
    assert not r["trust"]["not_like_for_like"] and r["trust"]["cut_seen"] == {"A": False, "B": False}


def test_a_cut_above_the_null_band_is_information_not_a_warning():
    fs = 176400
    a, b = device_pair(fs, 40000, 79000, level=1.0)
    lines = []
    r = compare(ArrayTrack(a, fs), ArrayTrack(b, fs), Options(), log=lines.append)
    t = r["trust"]
    assert t["not_like_for_like"] and not t["null_band_affected"] and t["bandwidth_hz"]["A"] == pytest.approx(40000, rel=0.1)
    assert r["null_band_hz"] == [20.0, 20000.0]
    passbands = [x for x in lines if "passbands differ" in x]
    assert passbands and "not affected" in passbands[0] and not any("WARNING: not like-for-like" in x for x in lines)
    from dsd_measure.nulltest.verdict import verdict
    assert "is not affected" in " ".join(verdict(r["channels"], t)["details"])


def test_a_pair_that_cannot_be_aligned_is_marked_untrustworthy():
    n = FS * 8
    a, b = music(n, FS, top=0.2), music(n, FS, seed=5, top=0.2)  # two unrelated recordings
    r, c = run(a, b)
    t = r["trust"]
    assert t["untrustworthy"] and "correlation" in t["reason"]
    from dsd_measure.nulltest.verdict import verdict
    v = verdict(r["channels"], r["trust"])
    assert v["tier"] == "untrustworthy" and "could not be trusted" in v["headline"] and "null depth" not in v["headline"]


def test_identical_devices_are_not_flagged(base):
    r, c = run(base, base)
    assert not r["trust"]["untrustworthy"] and not r["trust"]["not_like_for_like"]


@pytest.fixture(scope="module")
def dsd_streams():
    """One stream from the reference modulator, and the streams that modulate its 88.2 kHz decode scaled by a little and by -3 dB."""
    fs = 88200
    a, _ = encode.encode(music(fs * 5, fs, top=0.2) * 1.5, fs, 2822400)
    y = decode.decode(a.astype(float), 2822400, fs)
    return {"a": a.astype(float), **{k: encode.encode(y * g, fs, 2822400)[0].astype(float)
                                     for k, g in (("eps", 1 + 1e-9), ("3db", 10 ** (-3 / 20)))}}


def dsd_compare(streams, key, rate):
    opts = Options(rate=rate, max_delay=0.0003, trim_start=0.3, trim_end=0.3)
    r = compare(ArrayTrack(streams["a"], 2822400), ArrayTrack(streams[key], 2822400), opts)
    return r, r["channels"][0]


def test_two_dsd_outputs_differing_in_ultrasonic_noise_null_in_band(dsd_streams):
    r, c = dsd_compare(dsd_streams, "eps", None)  # at the DSD rate: the difference is mostly the two streams' own noise
    assert not r["trust"]["untrustworthy"] and not c["polarity_inverted"] and abs(c["delay_samples"]) < 0.01
    assert c["null_depth_db"] > 100
    assert c["null_depth_fullband_db"] < 10  # the full-band figure is the noise, which is not a result about the music
    assert r["trust"]["not_like_for_like"] is False


def test_two_dsd_outputs_3_db_apart_align_as_matched(dsd_streams):
    r, c = dsd_compare(dsd_streams, "3db", None)
    assert not c["polarity_inverted"] and abs(c["delay_samples"]) < 0.01
    assert -c["gain_db"] == pytest.approx(-3.0, abs=0.01) and c["null_depth_db"] > 100


@pytest.mark.slow
def test_two_dsd_outputs_resampled_to_88200_null_in_band(dsd_streams):
    r, c = dsd_compare(dsd_streams, "eps", 88200)  # resampling keeps noise up to 39.7 kHz in the full band
    assert c["null_depth_db"] > 100 and c["null_depth_fullband_db"] < 80


# ---------------------------------------------------------------- a suite's [null] table and the exit status

def _fake_null(monkeypatch, untrustworthy):
    def fake(source, devs, opts, out, *a, **k):
        return {"untrustworthy": untrustworthy,
                "pairs": [{"a": "reference", "b": "dev", "result": {"trust": {"untrustworthy": untrustworthy}}}]}
    monkeypatch.setattr("dsd_measure.nulltest.run.run_null", fake)


@pytest.mark.parametrize("untrustworthy,status", [(True, 1), (False, 0)])
def test_run_and_null_exit_the_same_way_for_an_alignment_that_cannot_be_trusted(tmp_path, monkeypatch, capsys, untrustworthy, status):
    from dsd_measure import cli
    _fake_null(monkeypatch, untrustworthy)
    suite = tmp_path / "s.toml"
    suite.write_text('[suite]\nname = "x"\n[null]\nsource = "t.dsf"\ndevices = ["reference", "ffmpeg"]\n')
    assert cli.main(["run", str(suite), "--only", "null", "-o", str(tmp_path / "r")]) == status
    out = capsys.readouterr().out
    assert ("dev against reference could not be trusted" in out) == untrustworthy
    assert cli.main(["null", "t.dsf", "ffmpeg"]) == status
