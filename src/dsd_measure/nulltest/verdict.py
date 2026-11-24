"""Depth bands for the null depth, with what each band does and does not say.

A null depth says how far below the music the difference between two outputs is. It does not say whether
the difference is heard: that depends on the playback level, the listener and what masks what, and the only
test is a blind listening test, which the lower bands point to. The bands below are plain ranges of depth,
shown with the sources a reader may want, and carry no claim about hearing.
"""

import numpy as np

SOURCES = [
    ("ISO 226:2023, normal equal-loudness-level contours (hearing in quiet)", "https://www.iso.org/standard/83117.html"),
    ("Zwicker and Fastl, Psychoacoustics: Facts and Models (simultaneous masking; cited, not checked: the authors have not read it)",
     "https://link.springer.com/book/10.1007/978-3-662-09562-1"),
    ("Clark, High-resolution subjective testing using a double-blind comparator, JAES 30(5), 1982 (match levels first)",
     "https://aes2.org/publications/elibrary-page/?id=3839"),
    ("Meyer and Moran, Audibility of a CD-standard A/D/A loop inserted into high-resolution audio playback, "
     "JAES 55(9), 2007 (a blind test of a 16-bit loop)",
     "https://www.aes.org/e-lib/browse.cfm?elib=14195"),
    ("ITU-R BS.1116, methods for the subjective assessment of small impairments in audio systems (cited, not checked)",
     "https://www.itu.int/rec/R-REC-BS.1116"),
]

#: (minimum null depth in dB, band id, wording)
TIERS = [
    (300.0, "identical", "identical after alignment: the two outputs match to floating-point rounding"),
    (100.0, "d100", "depth band 100 dB or more"),
    (80.0, "d80", "depth band 80 to 100 dB"),
    (60.0, "d60", "depth band 60 to 80 dB"),
    (40.0, "d40", "depth band 40 to 60 dB"),
    (20.0, "d20", "depth band 20 to 40 dB, which usually means different filters or phase (see the bands)"),
    (-1e9, "d0", "depth band under 20 dB: check the alignment and the level match first"),
]

BASIS = ("Depth bands, not a psychoacoustic model: they say how far below the music the difference is and make no statement "
         "about hearing, which was not tested, for any band; a null test cannot say whether a difference is heard. Whether a difference is heard depends on the playback level, the listener and "
         "masking (see the sources below); the test for that is a blind listening test. The band edges are round numbers, "
         "not thresholds from a source.")


def tier(depth_db):
    for lo, tid, text in TIERS:
        if depth_db >= lo:
            return tid, text


def inband_depth(ch):
    """Null depth over the bands up to 20 kHz (the band depth ignores ultrasonic energy)."""
    bands = [b for b in ch["bands"] if not b["ultrasonic"]]
    if not bands:
        return ch["null_depth_db"]
    pm = sum(10 ** (b["music_dbfs"] / 10) for b in bands)
    pd = sum(10 ** (b["diff_dbfs"] / 10) for b in bands)
    return 400.0 if pd <= 0 else float(10 * np.log10(pm / pd))


def _khz(hz):
    return f"{hz / 1000:.1f} kHz"


def _band_text(ch):
    lo, hi = ch.get("null_band_hz", (20.0, 20000.0))
    return f"{lo:g} Hz to {hi / 1000:g} kHz"


def verdict(channels, trust=None):
    """Verdict for the worst channel: a dict with ``tier``, ``headline``, ``details`` and the depth used.

    ``trust`` is the ``trust`` record of the comparison. When the alignment cannot be trusted the verdict says so
    and gives no depth band; a pair that is not like-for-like in band gets a detail line.
    """
    trust = trust or {}
    if trust.get("untrustworthy"):
        head = f"The alignment could not be trusted, so no depth band is given: {trust['reason']}."
        details = ["Check that both devices decoded the same source and channels, and that the delay search (--max-delay) covers the delay."]
        if trust.get("not_like_for_like"):
            details.append(_nlfl_text(trust, channels[0]))
        return {"tier": "untrustworthy", "headline": head, "details": details, "depth_db": None, "channel": channels[0]["channel"]}
    depths = [inband_depth(c) for c in channels]
    k = int(np.argmin(depths))
    ch, depth = channels[k], depths[k]
    tid, text = tier(depth)
    which = f" (channel {ch['channel']}, the worse of {len(channels)})" if len(channels) > 1 else ""
    louder_b = [c for c in channels if abs(c["gain_db"]) >= 0.095]
    if tid == "identical":
        lv = ""
        if louder_b:
            g = louder_b[0]["gain_db"]
            lv = f" and level matching (device B is {abs(g):.2f} dB {'louder' if g < 0 else 'quieter'} than device A)"
        head = f"Identical after alignment{lv}: the difference is zero to floating-point rounding{which}."
    else:
        head = f"Difference {-depth:.0f} dB relative to the music (null depth {depth:.0f} dB): {text}{which}."
    details = []
    if trust.get("not_like_for_like"):
        details.append(_nlfl_text(trust, ch))
    for c in channels:
        if c["polarity_inverted"]:
            details.append(f"Channel {c['channel']}: device B has inverted polarity; it was flipped before subtracting.")
        if abs(c["gain_db"]) >= 0.095:
            louder = "above" if c["gain_db"] < 0 else "below"
            details.append(f"Channel {c['channel']}: the fitted gain of device B is {abs(c['gain_db']):.2f} dB {louder} that of device A "
                           "(with different responses this is the best-fit gain, not a level difference). Match levels before any "
                           "listening test (Clark 1982).")
    weak = [b for b in ch["bands"] if not b["ultrasonic"] and b["depth_db"] < 40 and b["diff_dbfs"] > -100 and tid != "identical"]
    if weak and depth >= 40:
        w = min(weak, key=lambda b: b["depth_db"])
        details.append(f"The difference is concentrated around {w['centre_hz']:.0f} Hz, where it is only {w['depth_db']:.0f} dB "
                       "below the music in that band.")
    top = ch.get("null_band_hz", (20.0, 20000.0))[1]
    us = [b for b in ch["bands"] if b["ultrasonic"]]
    if us and tid != "identical":
        worst = min(us, key=lambda b: b["depth_db"])
        if worst["depth_db"] < 40:
            details.append(f"From {top / 1000:g} kHz up the outputs differ more (down to {worst['depth_db']:.0f} dB at {worst['centre_hz'] / 1000:.0f} kHz). "
                           f"That is outside the depth above, which covers {_band_text(ch)}; the level up there is reported as measured.")
    return {"tier": tid, "headline": head, "details": details, "depth_db": depth, "channel": ch["channel"]}


def _nlfl_text(trust, ch):
    bw = trust["bandwidth_hz"]
    seen = f"device A passes to about {_khz(bw['A'])} and device B to about {_khz(bw['B'])} (each estimated from its own spectrum against the other's)"
    if not trust.get("null_band_affected", True):
        return f"The passbands differ: {seen}. The null band, {_band_text(ch)}, is not affected."
    return f"Not like-for-like in band: {seen}. Alignment and the null depth use {_band_text(ch)}, the band both devices share."


def apply_format_limit(v, ch, formats):
    """Say so when an integer output (any width below 32 bits), not the decoder, sets the null depth.

    ``formats`` is a list of ``(device name, format record)`` or ``(device name, format record, gain_db)``, where
    ``gain_db`` is the gain applied to that device's output before the difference is taken (its own ``gain_db`` plus the
    level match), so that its rounding noise is compared in the same units as the difference. Rounding to ``bits`` adds white noise of
    power (LSB squared) / 12, or 4.77 dB more with TPDF dither; when the difference in 20 Hz to 20 kHz is within 6 dB of
    that noise (plain or dithered), the depth is a statement about the file format and ``v`` says so
    (``v["format_limited"]`` lists the devices). Whether a file was dithered is not detected.
    """
    from .. import outformat as of
    hit = []
    for item in formats:
        name, fmt = item[0], item[1]
        if not of.limits_result(fmt):
            continue
        lsb = 2.0 ** (1 - fmt["bits"])
        band_hz = min(of.BAND_HZ, ch.get("null_band_hz", (0, of.BAND_HZ))[1])
        noise = 10 * np.log10(lsb * lsb / 12 * min(band_hz / (fmt["rate"] / 2), 1.0)) + (item[2] if len(item) > 2 else 0.0)
        if noise - 6.0 <= ch["diff_rms_audio_dbfs"] <= noise + of.TPDF_COST_DB + 6.0:
            hit.append((name, fmt["bits"], noise))
    if not hit:
        return v
    name, bits, noise = max(hit, key=lambda h: h[2])
    if len(hit) > 1:  # both files are rounded: the two noises add
        noise = float(10 * np.log10(sum(10 ** (h[2] / 10) for h in hit)))
        name = " and ".join(h[0] for h in hit)
    ceiling = ch["music_rms_audio_dbfs"] - noise
    v["format_limited"] = [h[0] for h in hit]
    v["details"].append(f"{name} wrote {bits}-bit integer PCM. The rounding noise alone is about {noise:.0f} dBFS from {_band_text(ch)} "
                        f"(about {of.TPDF_COST_DB:.0f} dB more with dither), "
                        f"which caps the null depth at about {ceiling:.0f} dB on this music, so the figure above describes the file format, "
                        "not the decoder. Ask the tool for floating-point output and run again.")
    v["headline"] += f" Limited by the {bits}-bit output of {name}: ask it for floating-point output to see the decoder."
    return v
