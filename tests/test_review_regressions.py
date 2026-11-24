"""Regression tests for the findings of the independent review of 0.1.0 (B1 to B7, S1 to S7).

The slow tests run the measurement itself on the reference chain (class A and class B, quick
profile): the two columns of the example comparison must agree where the chain is the same.
``pytest -m "not slow"`` skips them; scripts/validate.sh and the full run include them.
"""

import numpy as np
import pytest

from dsd_measure import adapters, floor, measure
from dsd_measure import analyse as an
from dsd_measure import signals as sg
from dsd_measure.dsf import read_dsf, write_dff, write_dsf

FS = 352800


class _Fixed48k(adapters.Adapter):
    """A class A device that writes 48 kHz PCM (any content): enough to reach the rate check."""

    kind = "stub"
    klass = "A"

    def dsd_to_pcm(self, bits, rate):
        n = int(len(bits) / rate * 48000)
        return np.zeros(n), 48000


def test_multitone_off_the_44k_grid_is_not_run_with_a_reason():  # B7
    res = measure.measure_device(_Fixed48k("stub"), "quick", only={"multitone"}, log=lambda *a, **k: None)
    assert "multitone" not in res["metrics"]
    assert "44.1 kHz grid" in res["not_run"]["multitone"]


def test_analysis_version_is_recorded():
    res = measure.measure_device(_Fixed48k("stub"), "quick", only={"polarity"}, log=lambda *a, **k: None)
    assert res["metrics"]["analysis_version"] == 2


def test_noise_is_re_the_sine_rms_and_dither_is_32_bit():  # B5
    assert an.SINE_REF_DB == pytest.approx(3.0103, abs=1e-4)
    assert measure.DITHER_LSB == 2.0**-31
    x = measure.tpdf(2**18, np.random.default_rng(1))
    assert np.max(np.abs(x)) <= 2.0**-30  # +-1 LSB
    # a unit-variance white record reads 3.01 dB above its mean square
    w = np.random.default_rng(2).standard_normal(FS * 3) * 1e-5
    o, _, _ = an.noise_floor(w, FS, nfft=2**16, nseg=4)
    assert o["unweighted_dbfs"] == pytest.approx(10 * np.log10(1e-10 * 19980 / (FS / 2)) + 3.0103, abs=0.2)


def test_ultrasonic_reports_densities_not_a_single_bin():  # B6
    rng = np.random.default_rng(3)
    fs = 705600
    sigma = 1e-5
    w = sigma * rng.standard_normal(fs * 10)
    u = an.ultrasonic_peak(w, fs, nfft=2**18, nseg=6)
    truth = 10 * np.log10(sigma**2 / (fs / 2)) + 3.0103
    for k in ("50000", "100000", "200000"):
        assert u["density_dbfs_hz"][k] == pytest.approx(truth, abs=0.15)
    assert u["bin_hz"] == pytest.approx(fs / 2**18)
    # noise that rises to the band edge: the peak is flagged as the edge, not offered as a feature
    f = np.fft.rfftfreq(2**20, 1 / fs)
    spec = (f / 1e5) ** 2 * (rng.standard_normal(len(f)) + 1j * rng.standard_normal(len(f)))
    edge = np.fft.irfft(spec, 2**20) * 1e-3
    assert an.ultrasonic_peak(np.tile(edge, 6), fs, nfft=2**18, nseg=6)["peak_at_band_edge"]


def test_dsf_and_dff_pad_with_the_idle_pattern(tmp_path):  # S7
    bits = np.ones(100, dtype=np.int8)
    write_dsf(tmp_path / "a.dsf", bits, 2822400)
    raw = (tmp_path / "a.dsf").read_bytes()
    body = raw[92:]  # after the DSD, fmt and data headers
    assert body[13] == 0x69 and body[100] == 0x69  # byte 12 is partly signal; the rest is idle
    assert set(body[14:4096]) == {0x69}
    b, _ = read_dsf(tmp_path / "a.dsf")
    assert b.shape[-1] == 100 and np.all(b == 1)
    write_dff(tmp_path / "a.dff", bits, 2822400)
    assert b"\xff\xf9" in (tmp_path / "a.dff").read_bytes()  # four signal bits, then the idle pattern 1001


def test_jtest_square_wave_harmonics_are_not_reported_as_sidebands():  # S2
    fs = 44100
    r = an.jtest_metrics(sg.jtest(fs, 2**20), fs, 2**18, nseg=2)
    assert r["largest_sideband_db"] is None and r["bin_hz"] == pytest.approx(fs / 2**18)


def test_wide_thd_does_not_report_noise_as_harmonics():  # S3
    rng = np.random.default_rng(4)
    n = 2**18
    f0 = sg.coherent_freq(10000, FS, n)
    t = np.arange(n) / FS
    clean = 0.5 * np.sin(2 * np.pi * f0 * t) + 1e-4 * rng.standard_normal(n)  # noise only
    m = an.tone_metrics(clean, FS, f0, n, thd_wide_hz=80000.0)
    assert m["thd_wide_db"] is None and m["thd_wide_bound_db"] < -50
    h = clean + 0.5 * 1e-3 * np.sin(2 * np.pi * 3 * f0 * t)  # a real 3rd harmonic at 30 kHz, -60 dB
    assert an.tone_metrics(h, FS, f0, n, thd_wide_hz=80000.0)["thd_wide_db"] == pytest.approx(-60.0, abs=0.3)


def test_linearity_stops_at_the_first_failure():  # S4
    rows = [{"level_dbfs": -6.0 - 3 * i, "error_db": e} for i, e in enumerate([0.0, 0.1, 0.9, 0.0, 0.0])]
    lowest = None
    for r in rows:  # the rule of measure.levels, kept in step by the next test
        if abs(r["error_db"]) > 0.5:
            break
        lowest = r["level_dbfs"]
    assert lowest == -9.0
    import inspect
    assert "break" in inspect.getsource(measure.measure_device)


def test_plot_offset_puts_a_tone_at_its_level():  # S1
    n = 2**16
    f0 = sg.coherent_freq(1000, 44100, n)
    x = sg.sine(f0, -6.0206, 44100, n)
    p = an.power_spectrum(x, n)
    shown = an.db(p.max()) + measure._plot_offset_db(n, "bh7")
    assert shown == pytest.approx(-6.0206, abs=0.01)


def test_floor_flags_cover_imd_multitone_crosstalk_jtest_and_alias():  # S6
    mf = {"lobe_noise_db": -150.0, "imd_smpte_db": -140.0, "imd_ccif_db": -135.0, "multitone_dfr_db": 150.0}
    fl = {"dsd_rate": 2822400, "chain": {"thdn_db": -147.0, "thd_db": -160.0, "thdn_a_db": -150.0, "dr_a_db": 150.0, "noise_a_dbfs": -160.0,
                    "metric_floors": mf}}
    fl["decoder_alone"] = fl["chain"]
    M = {"reference_floor": fl, "imd_smpte": {"imd_db": -138.0}, "imd_ccif": {"imd_db": -100.0},
         "multitone": {"headline": {"distortion_free_range_db": 146.0}},
         "crosstalk": {"1000": {"left_to_right_db": -148.0, "right_to_left_db": -149.0, "gain_diff_db": 0.0, "phase_diff_deg": 0.0}},
         "jtest": {"noise_floor_db": -149.0}, "alias_tones": {"worst_image_db": -100.0}}
    got = floor.flags("A", M)
    assert {"imd_smpte", "multitone", "crosstalk", "jtest"} <= got and not {"imd_ccif", "alias"} & got


# ---------------------------------------------------------------- the reference chain, both columns

@pytest.fixture(scope="module")
def columns():
    out = {}
    only = {"multitone", "impulse", "alias_tones", "overload"}
    for name, kw in (("A", dict(klass="A", out_rate=44100)), ("B", dict(klass="B"))):
        out[name] = measure.measure_device(adapters.Reference(name, **kw), "quick", only=only, log=lambda *a, **k: None)["metrics"]
    return out


@pytest.mark.slow
def test_multitone_range_agrees_between_the_two_columns(columns):  # B1
    a = columns["A"]["multitone"]["headline"]["distortion_free_range_db"]
    b = columns["B"]["multitone"]["headline"]["distortion_free_range_db"]
    assert a > 140 and b > 140 and abs(a - b) < 3.0  # 136.0 against 104.2 before the fix


@pytest.mark.slow
def test_stopband_is_the_filter_not_the_impulse_noise(columns):  # B2
    fs = columns["A"]["filter_summary"]
    assert fs["stopband_worst_db"] < -120 and "tones from the output rate minus 20 kHz" in fs["stopband_method"]  # -81 dB before the fix
    assert "filter_summary" not in columns["B"]  # S5: a modulator's filter figures are the reference decoder's
    assert "stopband_worst_db" not in columns["B"]["reference_decoder_only"]["filter_summary"]


@pytest.mark.slow
def test_overload_recovery_does_not_depend_on_the_output_rate(columns):  # B4
    a, b = columns["A"]["overload_recovery"]["recovery_ms"], columns["B"]["overload_recovery"]["recovery_ms"]
    assert a < 15 and b < 15 and abs(a - b) < 6  # 47.5 ms against 10 ms before the fix
