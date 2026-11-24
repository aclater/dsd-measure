"""The floor of the reference chain: what the measurement itself cannot see below.

Two numbers are measured and shown in every report:

* **Reference modulator and decoder together** (limits class A devices, which are fed DSD made by
  the reference modulator): a 1 kHz tone at 0 dB SACD, a -60 dB SACD tone and 24-bit dithered
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
from .levels import REF_DBFS

REF_FS = 352800
NFFT = 2**18
#: Goal for the reference chain's in-band distortion plus noise (dB, unweighted, 1 kHz at 0 dB SACD).
TARGET_DB = -140.0
#: A device figure this close to the floor (dB) is flagged as limited by the reference.
MARGIN_DB = 6.0


def _tone_row(y, f0):
    m = an.tone_metrics(y[-NFFT - 3000 : -3000], REF_FS, f0, NFFT)
    return {k: round(float(m[k]), 2) for k in ("thdn_db", "thd_db", "thdn_a_db", "sinad_db")}


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
    # in-band noise with 24-bit dithered silence
    rng = np.random.default_rng(7)
    n_n = int(4.2 * in_rate)
    xs = (rng.random(n_n) - rng.random(n_n)) * 2.0**-23
    bitsn, _ = enc.encode(xs, in_rate, dsd_rate)
    yn = dec.decode(bitsn, dsd_rate, REF_FS)[int(0.5 * REF_FS) : -3000]
    nz, _, _ = an.noise_floor(yn, REF_FS, nfft=NFFT, nseg=8)
    ch.update({"noise_dbfs": round(nz["unweighted_dbfs"], 2), "noise_a_dbfs": round(nz["a_weighted_dbfs"], 2),
               "dr_db": round(dr["dr_db"], 2), "dr_a_db": round(dr["dr_a_db"], 2)})
    out["chain"] = ch
    # decoder alone: an ideal sine at the DSD rate, no modulator
    ideal = sg.sine(f0, REF_DBFS, dsd_rate, int(1.6 * dsd_rate))
    alone = _tone_row(dec.decode(ideal, dsd_rate, REF_FS), f0)
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
    return out
