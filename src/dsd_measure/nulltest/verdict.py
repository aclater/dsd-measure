"""Plain-language verdicts from the null depth, with the thresholds and why they are what they are.

Audibility cannot be read off one number: it depends on the playback level, the listener, and what
masks what. The tiers below are conservative rules of thumb, stated as such in every report, with the
sources they rest on. They say how far below the music the difference is, nothing more; the only
test of "can I hear it?" is a blind listening test, which the lower tiers point to.
"""

import numpy as np

SOURCES = [
    ("ISO 226, normal equal-loudness-level contours (hearing in quiet)", "https://www.iso.org/standard/34222.html"),
    ("Zwicker and Fastl, Psychoacoustics: Facts and Models (simultaneous masking)",
     "https://link.springer.com/book/10.1007/978-3-662-09562-1"),
    ("Clark, High-resolution subjective testing using a double-blind comparator, JAES 30(5), 1982 (match levels first)",
     "https://aes2.org/publications/elibrary-page/?id=3839"),
    ("Meyer and Moran, Audibility of a CD-standard A/D/A loop inserted into high-resolution audio playback, "
     "JAES 55(9), 2007 (a blind test of a 16-bit loop)",
     "https://www.aes.org/e-lib/browse.cfm?elib=14195"),
    ("ITU-R BS.1116, methods for the subjective assessment of small impairments in audio systems",
     "https://www.itu.int/rec/R-REC-BS.1116"),
]

#: (minimum null depth in dB, tier id, wording)
TIERS = [
    (300.0, "identical", "identical after alignment: the two outputs match to floating-point rounding"),
    (100.0, "far-below", "far below audibility"),
    (80.0, "well-below", "well below audibility"),
    (60.0, "below", "below audibility in normal listening; it could matter only at extreme playback levels"),
    (40.0, "borderline", "a shallow null: a difference this size can be heard on revealing music, but a null test cannot say whether it can; "
                         "listen with a blind test (ABX)"),
    (20.0, "possibly", "a deep difference: a null this shallow usually means different filters or phase (see the bands); "
                       "a null test cannot say whether that is audible, so listen with a blind test (ABX)"),
    (-1e9, "audible", "a large difference: check the alignment and the level match, then listen with a blind test (ABX)"),
]

BASIS = ("Rules of thumb, not a psychoacoustic model. A difference 100 dB or more under the music is, for music peaking "
         "near 100 dB SPL at the ear, at or under the threshold of hearing in quiet (ISO 226) and under the masking "
         "of the music itself (Zwicker and Fastl). Meyer and Moran's blind tests of a 16-bit loop, whose added noise lies roughly "
         "60 to 80 dB under typical music, found no audible difference at normal levels, which is why 60 dB is the lower edge of "
         "the 'below audibility' tier. Below 40 dB the difference can be masked in places and heard in others, "
         "so only a blind test can say.")


def tier(depth_db):
    for lo, tid, text in TIERS:
        if depth_db >= lo:
            return tid, text


def audible_band_depth(ch):
    """Null depth over the bands up to 20 kHz (the verdict ignores ultrasonic energy)."""
    bands = [b for b in ch["bands"] if not b["ultrasonic"]]
    if not bands:
        return ch["null_depth_db"]
    pm = sum(10 ** (b["music_dbfs"] / 10) for b in bands)
    pd = sum(10 ** (b["diff_dbfs"] / 10) for b in bands)
    return 400.0 if pd <= 0 else float(10 * np.log10(pm / pd))


def verdict(channels):
    """Verdict for the worst channel: a dict with ``tier``, ``headline``, ``details`` and the depth used."""
    depths = [audible_band_depth(c) for c in channels]
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
    for c in channels:
        if c["polarity_inverted"]:
            details.append(f"Channel {c['channel']}: device B has inverted polarity; it was flipped before subtracting.")
        if abs(c["gain_db"]) >= 0.095:
            louder = "above" if c["gain_db"] < 0 else "below"
            details.append(f"Channel {c['channel']}: the fitted gain of device B is {abs(c['gain_db']):.2f} dB {louder} that of device A "
                           "(with different responses this is the best-fit gain, not a level difference). A level difference of this "
                           "size alone can be heard; match levels before any listening test (Clark 1982).")
    weak = [b for b in ch["bands"] if not b["ultrasonic"] and b["depth_db"] < 40 and b["diff_dbfs"] > -100 and tid != "identical"]
    if weak and depth >= 40:
        w = min(weak, key=lambda b: b["depth_db"])
        details.append(f"The difference is concentrated around {w['centre_hz']:.0f} Hz, where it is only {w['depth_db']:.0f} dB "
                       "below the music in that band.")
    us = [b for b in ch["bands"] if b["ultrasonic"]]
    if us and tid != "identical":
        worst = min(us, key=lambda b: b["depth_db"])
        if worst["depth_db"] < 40:
            details.append(f"From 20 kHz up the outputs differ more (down to {worst['depth_db']:.0f} dB at {worst['centre_hz'] / 1000:.0f} kHz). "
                           "That is outside the verdict because it lies above hearing, but it matters to amplifiers and to anyone listening to "
                           "the content itself.")
    return {"tier": tid, "headline": head, "details": details, "depth_db": depth, "channel": ch["channel"]}
