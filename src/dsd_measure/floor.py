"""The floor of the reference chain: what the measurement itself cannot see below.

Two numbers are measured and shown in every report:

* **Reference modulator and decoder together** (limits class A devices, which are fed DSD made by
  the reference modulator): a 1 kHz tone at 0 dB SACD, a -60 dB SACD tone and 32-bit-level dithered
  silence go through the modulator and the decoder.
* **Decoder alone** (limits class B devices, whose DSD the reference decoder reads): the same tone
  as an ideal 64-bit sine at the DSD rate, with no modulator. Whatever this reads is the decoder's
  and the analyser's own distortion and noise.
"""

from functools import lru_cache

import numpy as np

from . import analyse as an
from . import decode as dec
from . import encode as enc
from . import signals as sg
from .levels import PEAK_DBFS, REF_DBFS

REF_FS = 352800
NFFT = 2**18
#: Goal for the reference chain's in-band distortion plus noise (dB, unweighted, 1 kHz at 0 dB SACD).
TARGET_DB = -140.0
#: A device figure this close to the floor (dB) is flagged as limited by the reference.
MARGIN_DB = 6.0


def _tone_row(y, f0):
    m = an.tone_metrics(y[-NFFT - 3000 : -3000], REF_FS, f0, NFFT)
    return {k: round(float(m[k]), 2) for k in ("thdn_db", "thd_db", "thdn_a_db", "sinad_db")}


def _imd_floors(run, in_rate, secs=2.4, f_imd=(60.0, 7000.0, 19000.0, 20000.0)):
    """IMD floors of a chain: ``run(x)`` takes a signal at ``in_rate`` and returns PCM at 352.8 kHz."""
    n_in = int(secs * in_rate)
    t = np.arange(n_in) / in_rate
    f1, f2 = (sg.coherent_freq(f, REF_FS, NFFT) for f in f_imd[:2])
    g1, g2 = (sg.coherent_freq(f, REF_FS, NFFT) for f in f_imd[2:])
    amp = 10 ** (REF_DBFS / 20)
    ys = run((4 * np.sin(2 * np.pi * f1 * t) + np.sin(2 * np.pi * f2 * t)) / 5 * amp)[-NFFT - 3000 : -3000]
    yc = run((np.sin(2 * np.pi * g1 * t) + np.sin(2 * np.pi * g2 * t)) / 2 * amp)[-NFFT - 3000 : -3000]
    return {"imd_smpte_db": round(an.imd_smpte(ys, REF_FS, NFFT, f1, f2)["imd_db"], 2),
            "imd_ccif_db": round(an.imd_ccif(yc, REF_FS, NFFT, g1, g2)["imd_db"], 2)}


def _multitone_floor(run44, in_rate, periods=3):
    x1, _, bins = sg.multitone_standard(REF_DBFS, fs=in_rate)
    x = np.concatenate([np.zeros(in_rate), np.tile(x1, periods + 2)])
    y = run44(x)
    n = 2**17  # one period at 44.1 kHz
    r = an.multitone_metrics(y[n + 44100 :], 44100, n, bins, nseg=periods)
    return round(r["averaged"]["distortion_free_range_db"], 1)


def _silence(in_rate, secs=4.2):
    """The 32-bit-level dithered silence that the noise test feeds a device."""
    rng = np.random.default_rng(7)
    n = int(secs * in_rate)
    return (rng.random(n) - rng.random(n)) * 2.0**-31


@lru_cache(maxsize=16)
def design_floor(dsd_rate, order, hinf, in_rate=88200):
    """The floor of the reference chain with one modulator design at the peak level.

    The stability guard falls back to a lower-order design when the loop overloads, and every
    such design has its own floor. This measures a 1 kHz tone at the peak level (+3.1 dB SACD)
    and 32-bit-level dithered silence through the modulator design ``(order, hinf)`` and the
    reference decoder. A report attaches it to every row that ran on that design.
    """
    f0 = sg.coherent_freq(1000, REF_FS, NFFT)
    x = sg.sine(f0, PEAK_DBFS, in_rate, int(2.2 * in_rate))
    bits, info = enc.encode(x, in_rate, dsd_rate, order=order, hinf=hinf)
    row = _tone_row(dec.decode(bits, dsd_rate, REF_FS), f0)
    bitsn, _ = enc.encode(_silence(in_rate), in_rate, dsd_rate, order=order, hinf=hinf)
    yn = dec.decode(bitsn, dsd_rate, REF_FS)[int(0.5 * REF_FS) : -3000]
    pn = an.power_spectrum(yn[-NFFT - 3000 : -3000], NFFT)
    lobe = float(an.db(an.lobe_power(pn, an.tone_bin(f0, NFFT, REF_FS))) - (REF_DBFS - 3.0103))
    return {"order": order, "hinf": hinf, "ntf": f"order {order}, max gain {hinf}", "stable": info["overload_samples"] == 0,
            "level_dbfs": PEAK_DBFS, "thdn_db": row["thdn_db"], "thd_db": row["thd_db"], "sinad_db": row["sinad_db"],
            "lobe_noise_db": round(lobe, 1)}


@lru_cache(maxsize=8)
def reference_floor(dsd_rate=2822400, in_rate=88200):
    f0 = sg.coherent_freq(1000, REF_FS, NFFT)
    secs = 2.2
    n_in = int(secs * in_rate)
    out = {"dsd_rate": dsd_rate, "target_db": TARGET_DB, "margin_db": MARGIN_DB}
    # modulator + decoder
    bits, info = enc.encode(sg.sine(f0, REF_DBFS, in_rate, n_in), in_rate, dsd_rate)
    ch = _tone_row(dec.decode(bits, dsd_rate, REF_FS), f0)
    out["ntf"] = info["ntf"]
    out["ntf_fallbacks"] = info["fallbacks"]
    # dynamic range: tone at -60 dB SACD
    bits60, _ = enc.encode(sg.sine(f0, REF_DBFS - 60, in_rate, n_in), in_rate, dsd_rate)
    y60 = dec.decode(bits60, dsd_rate, REF_FS)
    dr = an.dynamic_range(y60[-NFFT - 3000 : -3000], REF_FS, f0, NFFT)
    # in-band noise with 32-bit-level dithered silence (the same input as the noise test)
    bitsn, _ = enc.encode(_silence(in_rate), in_rate, dsd_rate)
    yn = dec.decode(bitsn, dsd_rate, REF_FS)[int(0.5 * REF_FS) : -3000]
    nz, _, _ = an.noise_floor(yn, REF_FS, nfft=NFFT, nseg=8)
    ch.update({"noise_dbfs": round(nz["unweighted_dbfs"], 2), "noise_a_dbfs": round(nz["a_weighted_dbfs"], 2),
               "dr_db": round(dr["dr_db"], 2), "dr_a_db": round(dr["dr_a_db"], 2)})
    # figures that are floor-limited besides THD+N: the noise in the lobe of a 1 kHz tone (the floor
    # of crosstalk, J-Test sidebands and alias images), IMD, and the multitone range
    pn = an.power_spectrum(yn[-NFFT - 3000 : -3000], NFFT)
    k0 = an.tone_bin(f0, NFFT, REF_FS)
    lobe_noise = float(an.db(an.lobe_power(pn, k0)) - (REF_DBFS - 3.0103))
    mf = {"lobe_noise_db": round(lobe_noise, 1)}
    mf.update(_imd_floors(lambda x: dec.decode(enc.encode(x, in_rate, dsd_rate)[0], dsd_rate, REF_FS), in_rate))
    mf["multitone_dfr_db"] = _multitone_floor(
        lambda x: dec.decode(enc.encode(x, in_rate, dsd_rate)[0], dsd_rate, 44100, passband=21500.0), in_rate)
    ch["metric_floors"] = mf
    out["chain"] = ch
    # decoder alone: an ideal sine at the DSD rate, no modulator
    ideal = sg.sine(f0, REF_DBFS, dsd_rate, int(1.6 * dsd_rate))
    alone = _tone_row(dec.decode(ideal, dsd_rate, REF_FS), f0)
    alone["peak"] = _tone_row(dec.decode(sg.sine(f0, PEAK_DBFS, dsd_rate, int(1.6 * dsd_rate)), dsd_rate, REF_FS), f0)
    ideal60 = sg.sine(f0, REF_DBFS - 60, dsd_rate, int(1.6 * dsd_rate))
    d60 = an.dynamic_range(dec.decode(ideal60, dsd_rate, REF_FS)[-NFFT - 3000 : -3000], REF_FS, f0, NFFT)
    alone.update({"noise_dbfs": round(d60["noise_dbfs"], 2), "noise_a_dbfs": round(d60["noise_a_dbfs"], 2),
                  "dr_db": round(d60["dr_db"], 2), "dr_a_db": round(d60["dr_a_db"], 2)})
    # decoder alias rejection: loud tones just above multiples of the output rate must not fold in band
    t = np.arange(int(1.6 * dsd_rate)) / dsd_rate
    ups = np.zeros(len(t))
    srcs = []
    for k in (1, 2, 3):
        for d in (-5000.0, 5000.0):
            fk = k * REF_FS + d
            ups += 0.1 * np.sin(2 * np.pi * fk * t)
            srcs.append(fk)
    yu = dec.decode(ups, dsd_rate, REF_FS)[-NFFT - 3000 : -3000]
    pu = an.power_spectrum(yu, NFFT)
    inband = an.band_mask(NFFT, REF_FS, 20.0, 20000.0)
    rms_in = float(np.sum(pu[inband]))
    alone["alias_rejection_db"] = round(float(an.db(rms_in / (0.1**2 / 2))), 1)
    # the decoder alone: IMD of ideal tones at the DSD rate, and its own noise in the tone's lobe
    # (a limit of the analysis arithmetic, far below anything a modulator reaches); no multitone
    # floor (it would need minutes of ideal 64-bit samples at the DSD rate)
    nbins = int(np.sum(an.band_mask(NFFT, REF_FS, 20.0, 20000.0)))
    amf = {"lobe_noise_db": round(float(d60["noise_dbfs"] - an.SINE_REF_DB + an.db((2 * an.LOBE + 1) / nbins)
                                        - (REF_DBFS - 3.0103)), 1)}
    amf.update(_imd_floors(lambda x: dec.decode(x, dsd_rate, REF_FS), dsd_rate, secs=1.6))
    alone["metric_floors"] = amf
    out["decoder_alone"] = alone
    out["meets_target"] = bool(ch["thdn_db"] <= TARGET_DB)
    return out


def limit_for(klass, floor):
    """The floor that limits a device of this class."""
    return floor["chain"] if klass == "A" else floor["decoder_alone"]


def flags(klass, M):
    """Names of device figures within MARGIN_DB of the reference floor."""
    f = M.get("reference_floor")
    if not f:
        return set()
    lim = limit_for(klass, f)
    out = set()
    t = M.get("tone_0dbsacd")
    if t:
        if t["thdn_db"] <= lim["thdn_db"] + MARGIN_DB:
            out |= {"thdn", "sinad"}
        if t["thd_db"] <= lim["thd_db"] + MARGIN_DB:
            out.add("thd")
        if t["thdn_a_db"] <= lim["thdn_a_db"] + MARGIN_DB:
            out.add("thdn_a")
    d = M.get("dynamic_range")
    if d and d["dr_a_db"] >= lim["dr_a_db"] - MARGIN_DB:
        out.add("dr")
    n = M.get("noise")
    if n and n["a_weighted_dbfs"] <= lim["noise_a_dbfs"] + MARGIN_DB:
        out.add("noise")
    pk = M.get("tone_peak")
    if pk:
        fl_pk = pk.get("design_floor") if klass == "A" else lim.get("peak")
        if fl_pk and pk["sinad_db"] >= fl_pk["sinad_db"] - MARGIN_DB:
            out.add("peak_sinad")
    mf = lim.get("metric_floors") or {}
    if "imd_smpte" in M and "imd_smpte_db" in mf and M["imd_smpte"]["imd_db"] <= mf["imd_smpte_db"] + MARGIN_DB:
        out.add("imd_smpte")
    if "imd_ccif" in M and "imd_ccif_db" in mf and M["imd_ccif"]["imd_db"] <= mf["imd_ccif_db"] + MARGIN_DB:
        out.add("imd_ccif")
    mt = (M.get("multitone") or {}).get("headline")
    if mt and mf.get("multitone_dfr_db") is not None and mt["distortion_free_range_db"] >= mf["multitone_dfr_db"] - MARGIN_DB:
        out.add("multitone")
    ln = mf.get("lobe_noise_db")
    ln_peak = (M.get("jtest") or {}).get("design_floor", {}).get("lobe_noise_db", ln)
    ct = M.get("crosstalk")
    if ct and ln is not None and max(max(v["left_to_right_db"], v["right_to_left_db"]) for v in ct.values()) <= ln + MARGIN_DB:
        out.add("crosstalk")
    j = M.get("jtest")
    if j and ln_peak is not None and j["noise_floor_db"] <= ln_peak - 3.0 + MARGIN_DB:
        out.add("jtest")
    al = M.get("alias_tones")
    if al and ln is not None and al["worst_image_db"] <= ln + MARGIN_DB:
        out.add("alias")
    return out
