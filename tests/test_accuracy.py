"""Accuracy tests: every analyser against signals with a known answer, and against an
independent second implementation (``refanalyser.py``). See docs/accuracy.md.

The cases live in ``accuracy_cases.py``; ``scripts/validate.sh`` runs the same cases with the
longer records and prints the table that docs/accuracy.md quotes.
"""

import numpy as np
import pytest

import accuracy_cases as ac
import refanalyser as ra
from dsd_measure import adapters
from dsd_measure import analyse as an
from dsd_measure import signals as sg
from dsd_measure.dsf import read_dsf, write_dsf
from dsd_measure.wavio import read_wav, write_wav

GROUPS = [ac.tone_rows, ac.tone_edge_rows, ac.quantisation_rows, ac.noise_rows, ac.band_edge_rows, ac.dynamic_range_rows,
          ac.imd_rows, ac.stereo_rows, ac.response_rows, ac.impulse_step_rows, ac.dc_polarity_rows,
          ac.multitone_rows, ac.spur_rows, ac.jtest_rows, ac.a_weighting_rows]


@pytest.fixture(scope="module")
def rows():
    out = []
    for g in GROUPS:
        out += g(quick=True) if "quick" in g.__code__.co_varnames[: g.__code__.co_argcount] else g()
    return out


def test_every_known_answer_row_passes(rows):
    failures = [m for r in rows for m in ac.check(r)]
    assert not failures, "\n".join(failures)
    assert len(rows) > 200  # the table is not silently shrinking


# ---------------------------------------------------------------- regressions

def test_thd_at_low_fundamental_does_not_count_the_fundamental_skirt():
    """Below ~27 Hz the 2nd-harmonic lobe overlapped the fundamental's lobe and the skirt was
    counted as distortion (a 20 Hz tone with a -80 dB 2nd harmonic read -61 dB)."""
    fs, n = 352800, 2**18
    t = np.arange(n) / fs
    for f in (20.0, 22.0, 26.0):
        f0 = sg.coherent_freq(f, fs, n)
        a = 10 ** (-6 / 20)
        x = a * np.sin(2 * np.pi * f0 * t) + a * 1e-4 * np.sin(2 * np.pi * 2 * f0 * t)
        assert an.tone_metrics(x, fs, f0, n)["thd_db"] == pytest.approx(-80.0, abs=0.01)


def test_harmonic_lobes_never_count_a_bin_twice():
    fs, n = 352800, 2**18
    f0 = sg.coherent_freq(20, fs, n)
    t = np.arange(n) / fs
    x = np.sin(2 * np.pi * f0 * t) + 1e-5 * np.sin(2 * np.pi * 3 * f0 * t)
    assert an.tone_metrics(x, fs, f0, n)["thd_db"] == pytest.approx(-100.0, abs=0.01)


# ---------------------------------------------------------------- the reference analyser itself

def test_reference_analyser_a_weighting_is_the_iec_curve():
    got = ra.a_weight_db(np.array(list(ac.IEC_A)))
    assert np.max(np.abs(got - np.array(list(ac.IEC_A.values())))) < 0.06  # table is rounded to 0.1 dB


def test_reference_sine_fit_finds_an_off_bin_tone():
    fs, n = 96000, 2**15
    f = 1000.37
    x = 0.3 * np.sin(2 * np.pi * f * np.arange(n) / fs + 0.4) + 0.001
    fit = ra.fit_sine(x, fs, 1000.0)
    assert fit["freq"] == pytest.approx(f, abs=1e-6)
    assert fit["amp"] == pytest.approx(0.3, abs=1e-9)
    assert fit["offset"] == pytest.approx(0.001, abs=1e-9)


@pytest.mark.parametrize("fs, n", [(96000, 2**16), (48000, 2**15)])
def test_noncoherent_tone_agrees_with_the_fit(fs, n):
    """Off-bin tone, white noise: the windowed analyser and the time-domain fit agree."""
    rng = np.random.default_rng(3)
    f0 = 1234.567
    x = 0.4 * np.sin(2 * np.pi * f0 * np.arange(n) / fs) + 2e-6 * rng.standard_normal(n)
    a = an.tone_metrics(x, fs, f0, n)["thdn_db"]
    b = ra.thdn_sinefit(x, fs, f0)["thdn_db"]
    assert a == pytest.approx(b, abs=0.08)


# ---------------------------------------------------------------- file formats and adapters

@pytest.mark.parametrize("subtype, tol", [("float64", 0.0), ("float32", 1e-7), ("pcm24", 2**-23), ("pcm16", 2**-15)])
def test_wav_round_trip(tmp_path, subtype, tol):
    x = 0.9 * np.sin(np.arange(4096) * 0.01)
    write_wav(tmp_path / "a.wav", x, 48000, subtype)
    y, fs = read_wav(tmp_path / "a.wav")
    assert fs == 48000 and np.max(np.abs(y[0] - x)) <= tol


class _FakeSox(adapters.ReftoolSox):
    """ReftoolSox with the container call replaced: records the arguments and the input WAV."""

    def _call(self, args):
        self.args = args
        self.wav, _ = read_wav(self._in / "x.wav")
        write_dsf(self._out / "x.dsf", np.ones(2822400 // 8 * 8, dtype=np.int8), 2822400)


def test_sox_adapter_levels_and_trellis(tmp_path):
    x = sg.sine(1000.0, -6.0206, 88200, 4096)
    a = _FakeSox("s", "unused", klass="B", workdir=tmp_path)
    assert a.gain_db == pytest.approx(6.0206) and a.input_gain_db == 0.0
    a.pcm_to_dsd(x, 88200)
    assert a.args[-4:] == ["-t", "32", "-n", "32"]
    assert np.max(np.abs(a.wav)) == pytest.approx(np.max(np.abs(x)), abs=1e-6)
    b = _FakeSox("s", "unused", klass="B", workdir=tmp_path, input_gain_db=6.0206, trellis="default")
    assert b.gain_db == pytest.approx(0.0, abs=1e-9)  # unity overall: 6.02 in, SoX -6.02, 0 out
    b.pcm_to_dsd(x, 88200)
    assert "-t" not in b.args and b.args[-2:] == ["-f", "sdm-8"]
    assert np.max(np.abs(b.wav)) == pytest.approx(1.0, abs=1e-3)  # the modulator now sees 0 dB SACD
    assert b.log[-1]["clipped_at_full_scale"] is False
    b.pcm_to_dsd(sg.sine(1000.0, -2.9, 88200, 4096), 88200)  # the +3.1 dB SACD peak cannot be reached
    assert b.log[-1]["clipped_at_full_scale"] is True
    with pytest.raises(ValueError):
        _FakeSox("s", "unused", klass="B", workdir=tmp_path, trellis="64x64")


def test_sox_adapter_class_a_ignores_input_gain(tmp_path):
    a = _FakeSox("s", "unused", klass="A", workdir=tmp_path, input_gain_db=6.0206)
    assert a.input_gain_db == 0.0 and a.gain_db == pytest.approx(6.0206)


def test_dsf_round_trip_is_bit_exact(tmp_path):
    rng = np.random.default_rng(1)
    bits = np.where(rng.random(2822400) > 0.5, 1, -1).astype(np.int8)
    write_dsf(tmp_path / "x.dsf", bits, 2822400)
    b, r = read_dsf(tmp_path / "x.dsf")
    assert r == 2822400 and np.array_equal(b[0] if b.ndim == 2 else b, bits)


# ---------------------------------------------------------------- the reference chain itself

def test_reference_chain_output_agrees_with_the_second_analyser():
    """Real decoder output (delta-sigma noise up to 141 kHz, about -50 dBFS) read by both analysers.

    The chain's published floor is about -147 dB THD+N (DSD64, 0 dB SACD). The sine-fit residual
    and the time-domain notch method must read the same within 0.1 dB.
    """
    from dsd_measure import decode as dec
    from dsd_measure import encode as enc

    fs, n = 352800, 2**18
    f0 = sg.coherent_freq(1000, fs, n)
    bits, _ = enc.encode(sg.sine(f0, -6.0206, 88200, int(88200 * 1.6)), 88200, 2822400)
    y = dec.decode(bits, 2822400, fs)
    seg = y[int(0.6 * fs) : int(0.6 * fs) + n]
    ours = an.tone_metrics(seg, fs, f0, n)
    assert ours["thdn_db"] < -140
    assert ra.thdn_sinefit(seg, fs, f0, refine=False)["thdn_db"] == pytest.approx(ours["thdn_db"], abs=0.1)
    assert ra.thdn_notch(seg, fs, f0)["thdn_db"] == pytest.approx(ours["thdn_db"], abs=0.1)
    assert ra.thdn_sinefit(seg, fs, f0, refine=False, weighted=True)["thdn_db"] == pytest.approx(ours["thdn_a_db"], abs=0.1)
