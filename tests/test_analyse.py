"""Known-answer tests for the analysers (synthetic signals with a known truth)."""

import numpy as np
import pytest
from scipy import signal

from dsd_measure import analyse as an
from dsd_measure import signals as sg
from dsd_measure.levels import PEAK_DBFS, REF_DBFS, dbfs_to_sacd

FS = 352800
NFFT = 2**18


def tone(level=-6.0, f=1000.0, n=NFFT):
    f0 = sg.coherent_freq(f, FS, NFFT)
    return sg.sine(f0, level, FS, n), f0


def test_levels_convention():
    assert REF_DBFS == pytest.approx(-6.0206, abs=1e-3)
    assert PEAK_DBFS == pytest.approx(-2.9, abs=0.03)
    assert dbfs_to_sacd(PEAK_DBFS) == pytest.approx(3.1, abs=0.01)


def test_window_is_flat_zero_at_edge():
    w = an.bh7(1024)
    assert abs(w[0]) < 1e-6 and w.max() == pytest.approx(1.0, abs=1e-3)


def test_coherent_freq_is_bin_centred_and_odd():
    f = sg.coherent_freq(1000, FS, NFFT)
    k = f * NFFT / FS
    assert k == pytest.approx(round(k)) and int(round(k)) % 2 == 1
    assert abs(f - 1000) < 2 * FS / NFFT


def test_pure_sine_thd_floor():
    x, f0 = tone()
    m = an.tone_metrics(x, FS, f0, NFFT)
    assert m["fundamental_dbfs"] == pytest.approx(-6.0 - 3.0103, abs=0.001)
    assert m["thdn_db"] < -200


def test_known_second_harmonic():
    x, f0 = tone(-6.0)
    x = x + 0.01 * 10 ** (-6 / 20) * np.sin(2 * np.pi * 2 * f0 * np.arange(NFFT) / FS)
    m = an.tone_metrics(x, FS, f0, NFFT)
    assert m["thd_db"] == pytest.approx(-40.0, abs=0.01)
    assert m["thd_percent"] == pytest.approx(1.0, abs=0.01)
    assert m["largest_harmonic"]["order"] == 2


def test_known_noise_thdn():
    rng = np.random.default_rng(1)
    x, f0 = tone(-6.0)
    sigma = 1e-4
    x = x + sigma * rng.standard_normal(NFFT)
    m = an.tone_metrics(x, FS, f0, NFFT)
    n_band = sigma**2 * (20000 - 20) / (FS / 2)
    expect = 10 * np.log10(n_band / (10 ** (-6 / 10) / 2))
    assert m["thdn_db"] == pytest.approx(expect, abs=0.3)


def test_a_weighting_curve():
    assert an.a_weight_db(1000.0) == pytest.approx(0.0, abs=0.01)
    assert an.a_weight_db(100.0) == pytest.approx(-19.1, abs=0.1)
    assert an.a_weight_db(10000.0) == pytest.approx(-2.5, abs=0.1)


def test_noise_floor_white():
    rng = np.random.default_rng(2)
    sigma = 1e-5
    x = sigma * rng.standard_normal(FS * 12)
    out, _, _ = an.noise_floor(x, FS, nfft=2**16)
    expect = 10 * np.log10(sigma**2 * 19980 / (FS / 2)) + an.SINE_REF_DB  # dBFS re a full-scale sine's rms
    assert out["unweighted_dbfs"] == pytest.approx(expect, abs=0.2)
    assert out["a_weighted_dbfs"] < out["unweighted_dbfs"]


def test_dynamic_range_of_known_noise():
    rng = np.random.default_rng(3)
    f0 = sg.coherent_freq(1000, FS, NFFT)
    sigma = 1e-5
    x = sg.sine(f0, -66.0206, FS, NFFT) + sigma * rng.standard_normal(NFFT)
    r = an.dynamic_range(x, FS, f0, NFFT)
    noise_rms = 10 * np.log10(sigma**2 * 19980 / (FS / 2))
    assert r["noise_dbfs"] == pytest.approx(noise_rms + an.SINE_REF_DB, abs=0.3)
    assert r["dr_db"] == pytest.approx(REF_DBFS - 3.0103 - noise_rms, abs=0.3)


def test_imd_ccif_known_product():
    x, (g1, g2) = sg.ccif(FS, NFFT, NFFT)
    amp = 10 ** (REF_DBFS / 20) / 2
    prod = 0.001 * amp  # product at -60 dB re each tone
    t = np.arange(NFFT) / FS
    x = x + prod * np.sin(2 * np.pi * (g2 - g1) * t)
    r = an.imd_ccif(x, FS, NFFT, g1, g2)
    expect = 10 * np.log10(prod**2 / (2 * amp**2))
    assert r["imd_db"] == pytest.approx(expect, abs=0.05)


def test_imd_smpte_known_sideband():
    x, (f1, f2) = sg.smpte(FS, NFFT, NFFT)
    a2 = 10 ** (REF_DBFS / 20) / 5
    t = np.arange(NFFT) / FS
    x = x + 0.01 * a2 * np.sin(2 * np.pi * (f2 + f1) * t) + 0.01 * a2 * np.sin(2 * np.pi * (f2 - f1) * t)
    r = an.imd_smpte(x, FS, NFFT, f1, f2)
    assert r["imd_percent"] == pytest.approx(100 * 0.01 * np.sqrt(2), abs=0.02)


def test_multitone_crest_and_peak():
    x, freqs, ph = sg.multitone(FS, NFFT)
    crest = 20 * np.log10(np.max(np.abs(x)) / np.sqrt(np.mean(x**2)))
    assert crest == pytest.approx(13.3, abs=0.1)
    assert 20 * np.log10(np.max(np.abs(x))) == pytest.approx(REF_DBFS, abs=1e-6)
    assert len(freqs) == 32 and freqs[0] == pytest.approx(17.6, rel=0.1)
    assert freqs[-1] == pytest.approx(21400, rel=0.01)


def test_multitone_residual_of_clean_signal_is_tiny():
    x, freqs, _ = sg.multitone(FS, NFFT)
    bins = np.round(freqs * NFFT / FS).astype(int)
    r = an.multitone_metrics(np.tile(x, 8), FS, NFFT, bins)
    assert r["headline"]["distortion_free_range_db"] > 200


def test_multitone_detects_injected_distortion():
    x, freqs, _ = sg.multitone(FS, NFFT)
    bins = np.round(freqs * NFFT / FS).astype(int)
    t = np.arange(NFFT) / FS
    # a spur one bin off the tone lattice at -100 dB re the peak
    spur = 10 ** (-100 / 20) * 10 ** (REF_DBFS / 20) * np.sin(2 * np.pi * (bins[10] + 1) * FS / NFFT * t)
    r = an.multitone_metrics(np.tile(x + spur, 8), FS, NFFT, bins)
    assert r["headline"]["residual_max_dbfs"] == pytest.approx(-100 + REF_DBFS - 3.0103, abs=0.5)


def test_fir_response_ripple_and_phase():
    h = signal.firwin(1001, 30000, fs=FS, window=("kaiser", 14))
    f, mag, _ = an.response_from_impulse(h, FS)
    r = an.response_metrics(f, mag)
    assert r["ripple_pp_db"] < 0.001
    assert 29000 < r["minus_3p0_db_hz"] < 31000
    im = an.impulse_metrics(h, FS)
    assert im["filter_type"] == "linear phase"
    f, gd = an.group_delay_us(h, FS)
    sel = (f > 100) & (f < 15000)
    assert np.max(np.abs(gd[sel])) < 0.5  # linear phase: flat group delay


def test_min_phase_filter_is_detected():
    h = signal.firwin(255, 21000, fs=FS)
    from scipy.signal import minimum_phase
    hm = minimum_phase(h, method="homomorphic")
    assert an.impulse_metrics(hm, FS)["filter_type"] == "minimum phase"
    assert an.impulse_metrics(h, FS)["filter_type"] == "linear phase"


def test_step_overshoot_known():
    h = signal.firwin(255, 21000, fs=FS)
    s = np.cumsum(np.concatenate([np.zeros(100), h, np.zeros(2000)]))
    m = an.step_metrics(s, FS)
    assert 5 < m["overshoot_percent"] < 12  # Gibbs overshoot of a sharp low-pass


def test_crosstalk_and_match():
    x, f0 = tone()
    leak = 1e-5 * x
    assert an.crosstalk(x, leak, FS, f0, NFFT) == pytest.approx(-100, abs=0.01)
    m = an.channel_match(x, x * 10 ** (0.5 / 20), FS, f0, NFFT)
    assert m["gain_diff_db"] == pytest.approx(0.5, abs=0.01)
    assert abs(m["phase_diff_deg"]) < 0.01


def test_polarity_dc_gain():
    p = sg.polarity_pulse()
    assert an.polarity(p, p) == "normal"
    assert an.polarity(-p, p) == "inverted"
    assert an.dc_offset(np.full(1000, 0.001))["dc_dbfs"] == pytest.approx(-60, abs=0.001)
    x, f0 = tone(-6.0206, n=FS * 3)
    assert an.gain_error_db(x, FS, REF_DBFS) == pytest.approx(0, abs=0.01)
    assert an.gain_error_db(x * 10 ** (1 / 20), FS, REF_DBFS) == pytest.approx(1, abs=0.01)


def test_linearity_known_error():
    n = 2**15
    fs = 44100
    f0 = sg.coherent_freq(1000, fs, n)
    marks, parts, pos = [], [], 0
    for lv in (-6.0, -60.0, -120.0):
        g = 1.0 if lv > -100 else 10 ** (1 / 20)  # +1 dB error at the lowest step
        parts.append(sg.sine(f0, lv, fs, n) * g)
        marks.append((lv, pos, pos + n))
        pos += n
    res = an.linearity(np.concatenate(parts), marks, fs, f0, n)
    assert [round(r["error_db"], 2) for r in res] == [0.0, 0.0, 1.0]


def test_jtest_runs_and_marks_carrier():
    x = sg.jtest(44100, 2**20)
    r = an.jtest_metrics(x, 44100, 2**18, nseg=2)
    assert r["carrier_dbfs"] == pytest.approx(-3 - 3.0103, abs=0.1)


def test_spur_report_finds_injected_spur():
    x, f0 = sg.tone_15k(FS, NFFT, NFFT)
    t = np.arange(NFFT) / FS
    fsp = sg.coherent_freq(7000, FS, NFFT)
    amp = 10 ** (-12 / 20)
    x = x + amp * 1e-4 * np.sin(2 * np.pi * fsp * t)
    r = an.spur_report(x, FS, f0, NFFT)
    assert r["audio_band"]["db"] == pytest.approx(-80, abs=0.2)
    assert r["audio_band"]["hz"] == pytest.approx(fsp, abs=FS / NFFT)


def test_bit_density_and_runs():
    bits = np.where(np.arange(1000) % 4 == 0, -1, 1)
    d = an.bit_density(bits, 28)
    assert d.max() == pytest.approx(0.75, abs=0.001)
    assert an.longest_run(np.array([1, 1, 1, -1, 1, 1])) == 3
    s = an.stability_report(np.ones(100), 2822400)
    assert s["saturated"]


def test_standard_multitone_matches_definition():
    x, f, bins = sg.multitone_standard()
    crest = 20 * np.log10(np.max(np.abs(x)) / np.sqrt(np.mean(x**2)))
    assert crest == pytest.approx(13.3, abs=0.02)
    assert len(f) == 32 and f[0] == pytest.approx(17.5, abs=0.2) and f[-1] == pytest.approx(21400, abs=1)
    assert 20 * np.log10(np.max(np.abs(x))) == pytest.approx(REF_DBFS, abs=1e-6)
    r = an.multitone_metrics(np.tile(x, 2), 352800, 2**20, bins, nseg=2)
    assert r["headline"]["distortion_free_range_db"] > 200
