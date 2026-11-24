"""Regression tests for the re-review of 0.1.1 (N1 to N8, N11, N12): each fails on the 0.1.1 candidate it was found in.

The fast tests use synthetic records. The slow tests run the measurement on the reference chain as a
class A device at several output rates, aligned and delayed.
"""

import numpy as np
import pytest

from dsd_measure import adapters, measure
from dsd_measure import analyse as an
from dsd_measure import decode as dec
from dsd_measure import signals as sg

QUIET = dict(log=lambda *a, **k: None)


class _Fixed48k(adapters.Adapter):
    kind = "stub"
    klass = "A"

    def dsd_to_pcm(self, bits, rate):
        return np.zeros(int(len(bits) / rate * 48000)), 48000


class Delayed(adapters.Reference):
    """The reference decoder with its output ``delay`` samples late (and optionally inverted)."""

    def __init__(self, delay=0, sign=1, **kw):
        super().__init__("delayed", klass="A", **kw)
        self.delay, self.sign = delay, sign

    def dsd_to_pcm(self, bits, rate):
        y, fs = super().dsd_to_pcm(bits, rate)
        y = np.concatenate([np.zeros(y.shape[:-1] + (self.delay,)), y], axis=-1)[..., : y.shape[-1]]
        return self.sign * y, fs


def _run(adapter, only):
    return measure.measure_device(adapter, "quick", only=only, **QUIET)


# ---------------------------------------------------------------- N1: decimate every record

def test_to_rate_keeps_the_band_and_removes_what_would_leak():
    fs, n = 352800, 352800 * 2
    t = np.arange(n) / fs
    y = np.sin(2 * np.pi * 21400 * t) + 1e-3 * np.sin(2 * np.pi * 60000 * t)  # a tone in the band, noise far above it
    z = dec.to_rate(y, fs, 44100, 21500.0)
    assert len(z) == n // 8
    p = np.abs(np.fft.rfft(z[2000:-2000] * np.hanning(len(z) - 4000)))
    f = np.fft.rfftfreq(len(z) - 4000, 1 / 44100)
    assert f[np.argmax(p)] == pytest.approx(21400, abs=5)
    assert dec.to_rate(y, fs, fs) is not None and np.array_equal(dec.to_rate(y, fs, fs), y)
    with pytest.raises(ValueError):
        dec.to_rate(y, 48000, 44100)


@pytest.mark.slow
@pytest.mark.parametrize("rate", [88200, 176400, 352800])
def test_multitone_range_of_class_a_does_not_depend_on_its_output_rate(rate):  # N1: 138, 109, 106 dB before
    m = _run(adapters.Reference("a", klass="A", out_rate=rate), {"multitone"})["metrics"]
    assert m["multitone"]["headline"]["distortion_free_range_db"] == pytest.approx(150.7, abs=1.0)
    assert m["multitone"]["analysis_rate"] == 44100 and m["multitone"]["output_rate"] == rate


# ---------------------------------------------------------------- N2: stopband

@pytest.mark.slow
@pytest.mark.parametrize("rate", [44100, 88200, 176400])
def test_stopband_tones_start_at_output_rate_minus_20k_and_read_deep(rate):  # N2: -9 dB at 88.2 kHz before
    m = _run(adapters.Reference("a", klass="A", out_rate=rate), {"alias_tones"})["metrics"]
    fs = m["filter_summary"]
    lo, hi = fs["stopband_tested_hz"]
    assert lo == pytest.approx(rate - 20000, abs=10) and lo >= rate - 20000 - 1e-6 and hi > lo
    assert fs["stopband_worst_db"] < -120, fs
    assert all(abs(r["alias_hz"] - (rate - r["tone_hz"])) < 1 and r["alias_hz"] <= 20000 + 1 for r in m["alias_tones"]["rows"])
    assert "upper bound" in fs["stopband_method"]


def test_stopband_row_carries_the_range_and_upper_bound_in_every_format():  # N2
    from dsd_measure.report import summary_rows
    M = {"filter_summary": {"stopband_worst_db": -133.0, "stopband_edge_hz": 24100.0, "stopband_tested_hz": [24100.0, 34100.0]}}
    rows = [r for r in summary_rows(M) if r["label"].startswith("Stopband")]
    assert len(rows) == 1 and "upper bound" in rows[0]["label"]
    assert rows[0]["value"] == "-133 dB or deeper, tones 24.1 to 34.1 kHz"


def test_stopband_is_validated_again_only_with_its_tests():
    from dsd_measure import conclusions as cn
    assert "stopband" in cn.VALIDATED_FROM_V2  # re-added after the tones moved; the two tests above guard it


# ---------------------------------------------------------------- N3: 48 kHz family

def test_impulse_filter_and_group_delay_are_not_run_at_48k():  # N3
    res = _run(_Fixed48k("stub"), {"impulse"})
    assert "44.1 kHz grid" in res["not_run"]["impulse"]
    for k in ("impulse", "filter_summary", "group_delay_us"):
        assert k not in res["metrics"]


# ---------------------------------------------------------------- N4: wide-band records

@pytest.mark.slow
def test_filter_rows_are_not_measurable_when_the_stream_noise_buries_them():  # N4
    from dsd_measure.report import summary_rows
    wide = _run(adapters.Reference("w", klass="A", out_rate=352800), {"impulse"})["metrics"]
    assert wide["impulse"]["floor_used_db"] > -60 and wide["impulse"]["measurable"] is False
    rows = {r["label"]: r["value"] for r in summary_rows(wide)}
    assert "not measurable" in rows["Filter type, ringing and cut-off"] and "Filter type" not in rows
    assert not any(k.startswith("Group delay") for k in rows)
    narrow = _run(adapters.Reference("n", klass="A", out_rate=44100), {"impulse"})["metrics"]
    assert narrow["impulse"]["measurable"] is True and narrow["impulse"]["filter_type"] == "linear phase"


# ---------------------------------------------------------------- N5: J-Test

def test_jtest_noise_that_varies_across_the_band_is_not_reported_as_sidebands():  # N5
    fs, n = 44100, 44100 * 24
    rng = np.random.default_rng(1)
    f = np.fft.rfftfreq(n, 1 / fs)
    shape = 10 ** ((f / 20000.0 * 25 - 12 * np.cos(2 * np.pi * f / 3300)) / 20)  # 25 dB tilt and 24 dB ripples
    noise = np.fft.irfft(np.fft.rfft(rng.standard_normal(n)) * shape, n)
    noise *= 10 ** (-135 / 20) / np.std(noise)
    carrier = 10 ** (-3 / 20) * np.sin(2 * np.pi * (fs / 4) * np.arange(n) / fs)
    r = an.jtest_metrics(carrier + noise, fs, nfft=nfft_for_jtest(fs), nseg=3, fs_nominal=44100)
    assert r["sidebands_detected"] == 0 and r["largest_sideband_db"] is None


def nfft_for_jtest(fs):
    return measure.nfft_for(fs)


def test_jtest_still_finds_a_real_sideband():
    fs, n = 44100, 44100 * 24
    t = np.arange(n) / fs
    sp = fs / 192
    x = 10 ** (-3 / 20) * np.sin(2 * np.pi * fs / 4 * t) + 10 ** (-100 / 20) * np.sin(2 * np.pi * (fs / 4 + 7 * sp) * t)
    x += np.random.default_rng(2).standard_normal(n) * 10 ** (-140 / 20)
    r = an.jtest_metrics(x, fs, nfft=measure.nfft_for(fs), nseg=3, fs_nominal=44100)
    assert r["sidebands_detected"] >= 1 and r["largest_sideband_order"] == 7


# ---------------------------------------------------------------- N6: wide-band THD

def test_wide_thd_of_an_ideal_20hz_sine_is_not_the_fundamental_skirt():  # N6: -61 dB before
    n, fs = 2**18, 352800
    f0 = sg.coherent_freq(20, fs, n)
    x = np.sin(2 * np.pi * f0 * np.arange(n) / fs)
    r = an.tone_metrics(x, fs, f0, n, thd_wide_hz=80000.0)
    assert r["thd_wide_db"] is None or r["thd_wide_db"] < -150


def test_wide_thd_does_not_count_shaped_noise_as_harmonics_across_runs():  # N6: -60.9 dB in one run, -44.1 in the next
    n, fs = 2**18, 352800
    f0 = sg.coherent_freq(10000, fs, n)
    t = np.arange(n) / fs
    f = np.fft.rfftfreq(n, 1 / fs)
    shape = 10 ** (np.clip((f - 20000) / 40000, 0, 1) * 40 / 20 - 6)  # noise rising 40 dB above 20 kHz
    for seed in range(12):
        noise = np.fft.irfft(np.fft.rfft(np.random.default_rng(seed).standard_normal(n)) * shape, n)
        x = np.sin(2 * np.pi * f0 * t) + 1e-3 * noise / np.std(noise) * 10 ** (-60 / 20)
        r = an.tone_metrics(x, fs, f0, n, thd_wide_hz=80000.0)
        assert r["thd_wide_db"] is None, (seed, r["thd_wide_db"])


# ---------------------------------------------------------------- N7: latency

@pytest.mark.slow
def test_a_late_device_reads_like_an_aligned_one():  # N7: minimum phase, 824 % overshoot, inverted, 32 ms recovery at 1000 samples
    only = {"impulse", "polarity", "overload"}
    assert True
    base = _run(Delayed(0, out_rate=44100), only)
    for delay, sign in ((1000, 1), (3000, 1), (300, -1)):
        late = _run(Delayed(delay, sign, out_rate=44100), only)
        a, b = base["metrics"], late["metrics"]
        assert b["impulse"]["filter_type"] == a["impulse"]["filter_type"] == "linear phase", delay
        assert b["impulse"]["pre_ringing_ms"] == pytest.approx(a["impulse"]["pre_ringing_ms"], abs=0.05)
        assert b["step"]["overshoot_percent"] == pytest.approx(a["step"]["overshoot_percent"], abs=0.3)
        assert b["overload_recovery"]["recovery_ms"] == pytest.approx(a["overload_recovery"]["recovery_ms"], abs=5.0)  # the test resolves about 10 ms
        assert b["polarity"] == ("normal" if sign == 1 else "inverted")
        assert b["latency"]["seconds"] == pytest.approx(delay / 44100, abs=2e-5)
        assert b["group_delay_us"]["at_1k"] == pytest.approx(a["group_delay_us"]["at_1k"], abs=2.0)


# ---------------------------------------------------------------- N8: dither

def test_dither_level_in_the_label_is_the_real_one():  # N8: said -162 dBFS
    x = measure.tpdf(2**20, np.random.default_rng(7))
    p = an.power_spectrum(x, 2**16)
    f = an.freqs(2**16, 88200)
    band = (f >= 20) & (f <= 20000)
    level = 10 * np.log10(p[band].sum()) + an.SINE_REF_DB
    assert level == pytest.approx(-194.85, abs=0.3)
    src = open(measure.__file__).read()
    assert "-194.85 dBFS over 20 kHz" in src and "about -162 dBFS over 20 kHz" not in src
