"""Conclusions: what a reader can take away from a report, as deterministic rules.

``device_conclusions`` turns the metrics of one device into a short list of plain sentences, and
``comparison_conclusions`` does the same for several devices. Every conclusion carries an ``id``,
a ``verdict``, the metric paths it used (``metrics``), those figures as shown (``evidence``) and
the thresholds it applied (``thresholds``). The thresholds and their sources are in ``THRESHOLDS``
and in docs/conclusions.md; the two are kept identical by a test.

A rule only speaks about figures whose analysis has been validated (``status``). The others are
listed in one "not concluded" line and never contribute to a verdict.
"""

import math
import re

from . import outformat as of
from .floor import MARGIN_DB, flags, limit_for
from .levels import REF_DBFS

# ----------------------------------------------------------------------------- thresholds

#: Every number a rule compares against. ``settled`` is False where the research does not agree or the source has not been read by the authors. These are
#: reference lines taken from the literature: this tool measures, it does not test listening, and a source
#: marked "cited, not checked" is one whose text the authors have not read (it is not in their library).
THRESHOLDS = {
    "range_120_db": {
        "value": 120.0, "unit": "dB below the reference level", "settled": False,
        "meaning": "A reference line of 120 dB, cited from Fielder 1995 as a dynamic range needed only in the most demanding cases (not checked against the paper). "
                   "A reference line only: audibility was not tested.",
        "sources": [("Fielder 1995, JAES 43(5): over 120 dB is needed only in the most demanding cases "
                     "(cited, not checked against the paper)",
                     "https://aes2.org/publications/elibrary-page/?id=7948")]},
    "dither16_db": {
        "value": 87.0, "unit": "dB below the reference level", "settled": False,
        "meaning": "The noise of a correctly dithered 16-bit channel (-93.3 dBFS) seen from the 0 dB SACD "
                   "reference level (-6.02 dBFS): a calculation, not a listening result. Whether such noise is heard "
                   "is not settled: Meyer and Moran 2007 report no detection at normal volume, but detection of "
                   "the loop's noise floor in a brief two-subject test with no input signal at 14 dB of extra gain, and easily above it, and Reiss 2016 finds a small but "
                   "statistically significant ability to discriminate high-resolution content and discusses the "
                   "risk of bias in Meyer and Moran.",
        "sources": [("Meyer and Moran 2007, JAES 55(9)", "https://aes2.org/publications/elibrary-page/?id=14195"),
                    ("Reiss 2016, JAES 64(6), a meta-analysis that finds a small but statistically significant effect",
                     "https://aes2.org/publications/elibrary-page/?id=18296")]},
    "flat_db": {
        "value": 0.1, "unit": "dB", "settled": False,
        "meaning": "A level or response difference this small is treated as none. It is a fifth of the 0.5 dB "
                   "level step below.",
        "sources": [("Jesteadt, Wier and Green 1977, JASA 61(1) (cited, not checked against the paper)",
                     "https://doi.org/10.1121/1.381278")]},
    "level_jnd_db": {
        "value": 0.5, "unit": "dB", "settled": False,
        "meaning": "A level step of 0.5 dB, cited from Jesteadt, Wier and Green as about the smallest level change "
                   "detected on tones (0.5 to 1 dB). A reference line only.",
        "sources": [("Jesteadt, Wier and Green 1977, JASA 61(1) (cited, not checked against the paper)",
                     "https://doi.org/10.1121/1.381278")]},
    "same_db": {
        "value": 1.0, "unit": "dB", "settled": True,
        "meaning": "Two distortion or noise figures closer than this are treated as the same. This is a convention, "
                   "not a measured repeatability: no repeatability interval has been measured yet.",
        "sources": []},
    "floor_margin_db": {
        "value": MARGIN_DB, "unit": "dB", "settled": True,
        "meaning": "A figure this close to the reference floor is limited by the tool. Devices at the floor "
                   "cannot be ranked against each other.",
        "sources": [("The reference floor", "footprint.md#the-reference-floor")]},
    "group_delay_ms": {
        "value": 1.0, "unit": "ms", "settled": False,
        "meaning": "A group delay difference of 1 ms, cited from Blauert and Laws as about the smallest difference "
                   "detected in the midrange on test pulses. A reference line only.",
        "sources": [("Blauert and Laws 1978, JASA 63(5) (cited, not checked against the paper)",
                     "https://doi.org/10.1121/1.381841")]},
    "pre_ringing": {
        "value": None, "unit": "", "settled": False,
        "meaning": "No threshold. The literature does not agree on a limit for the ringing of a linear-phase filter "
                   "before a transient, so the report describes the filter and gives no verdict.",
        "sources": [("Jackson, Capp and Stuart 2014, AES Convention 137: reports effects of filters in listening tests",
                     "https://aes2.org/publications/elibrary-page/?id=17497"),
                    ("Archimago 2015, internet blind test of linear against minimum phase filters: no consistent preference",
                     "https://archimago.blogspot.com/2015/04/internet-blind-test-linear-vs-minimum.html")]},
    "ultrasonic": {
        "value": None, "unit": "", "settled": False,
        "meaning": "No threshold. Noise shaping puts noise above 20 kHz by design and there is no agreed limit for what "
                   "amplifiers and tweeters tolerate, so the report gives the level only.",
        "sources": [("Archimago 2022, notes on DSD and 1-bit measurements of DACs",
                     "https://archimago.blogspot.com/2022/06/notes-on-dac-dsd-1-bit-pdm-measurements.html")]},
    "distortion_music": {
        "value": None, "unit": "", "settled": False,
        "meaning": "No threshold. Above the 16-bit noise level the published thresholds for distortion vary widely "
                   "with its kind, the music and the volume, so the report gives the level and no verdict.",
        "sources": [("de Santis and Henin 2007, Aalborg University (cited, not checked)",
                     "https://projekter.aau.dk/projekter/files/9852082/07gr1061_Thesis.pdf")]},
}

#: Every verdict a conclusion can carry, with its label and one plain meaning.
VERDICTS = {
    "margin-120": ("At least 120 dB down", "Every figure concluded is at least 120 dB below a reference-level tone."),
    "margin-87": ("At least 87 dB down", "Every figure concluded is at least 87 dB below a reference-level tone, the "
                  "noise level of dithered 16-bit on this scale."),
    "margin-low": ("Under 87 dB down", "A figure is less than 87 dB below a reference-level tone, above the noise "
                   "level of dithered 16-bit on this scale."),
    "floor": ("Measurement floor", "The tool measuring itself: the best figures any report can show."),
    "at-floor": ("At the reference floor", "The tool, not the device, limits these figures."),
    "fact": ("Finding", "A measured property."),
    "no-threshold": ("No agreed threshold", "Measured; the literature gives no agreed threshold to compare it with."),
    "same": ("Same within tolerance", "Every difference is below the floor or the stated tolerance."),
    "difference-low": ("Difference between low figures", "A measured difference between figures that are both at least "
                       "87 dB below a reference-level tone."),
    "notable": ("Notable difference", "A measured difference larger than the stated tolerance, or one where a figure "
                "is above the 16-bit noise level."),
    "not-comparable": ("Not comparable", "The devices do different jobs."),
    "not-like-for-like": ("Not like-for-like", "The devices were measured at different output rates or formats, so the "
                          "figures are listed but not compared."),
    "format-limited": ("Not judged: output format", "The file format the tool wrote limits the figures, so they describe the "
                      "format, not the converter."),
    "pending": ("Not concluded", "Measured, but not validated or not used by any rule in this version."),
}

# ----------------------------------------------------------------------------- which figures count

#: Metric groups whose analysis is validated in every version.
VALIDATED = frozenset({"floor", "sinad", "thd", "dr", "gain", "linearity", "fr", "imd", "crosstalk"})
#: Groups that are valid from ``metrics["analysis_version"]`` 2 on (corrected definitions).
VALIDATED_FROM_V2 = frozenset({"noise", "ultrasonic", "stopband", "overload"})
#: Groups not yet covered by a check against known answers. Set to True to let the rules use them.
UNREVIEWED = frozenset({"filter", "group_delay", "polarity", "stability"})
UNREVIEWED_VALIDATED = False
#: Plain names for the "not concluded" line, by top-level metric key.
PENDING_NAMES = {
    "impulse": "filter and ringing", "filter_summary": "filter and ringing", "polarity": "polarity",
    "stability": "modulator stability", "noise": "background noise", "ultrasonic": "ultrasonic noise",
    "overload_recovery": "overload recovery", "multitone": "multitone", "jtest": "J-Test",
    "tone_peak": "peak-level SINAD", "alias_tones": "alias images",
}
_GROUP_OF = {"impulse": "filter", "filter_summary": "filter", "group_delay_us": "group_delay", "polarity": "polarity",
             "stability": "stability", "noise": "noise", "ultrasonic": "ultrasonic", "overload_recovery": "overload", "alias_tones": "stopband"}


def status(M):
    """The set of metric groups the rules may use for these metrics."""
    ok = set(VALIDATED)
    if (M.get("analysis_version") or 1) >= 2:
        ok |= VALIDATED_FROM_V2
    if UNREVIEWED_VALIDATED:
        ok |= UNREVIEWED
    if M.get("device_class", "A") == "B":
        ok -= {"filter", "group_delay"}  # for a modulator these rows describe the reference decoder
    return ok


# ----------------------------------------------------------------------------- helpers

def lookup(M, path):
    """``"a.b.c"`` in nested dicts, or None."""
    for p in path.split("."):
        if not isinstance(M, dict) or p not in M:
            return None
        M = M[p]
    return M


def _t(name):
    return THRESHOLDS[name]["value"]


def _down(v):
    """A margin in whole dB, rounded down so the text never overstates it."""
    return f"{math.floor(v + 1e-9):.0f} dB"


def _small(v):
    """A small level difference: 'less than 0.01 dB' or '0.12 dB'."""
    return "less than 0.01 dB" if abs(v) < 0.01 else f"{abs(v):.2f} dB"


def _within(v):
    """For 'within X': the difference rounded up to 0.01 dB, so the statement holds."""
    return f"{max(math.ceil(abs(v) * 100 - 1e-9) / 100, 0.01):.2f} dB"


def _khz(f):
    return f"{f / 1000:.1f} kHz"


def _ev(metric, label, value, device=None):
    e = {"metric": metric, "label": label, "value": value}
    if device is not None:
        e["device"] = device
    return e


def _c(cid, verdict, text, evidence, thresholds=()):
    assert verdict in VERDICTS and all(t in THRESHOLDS for t in thresholds)
    return {"id": cid, "verdict": verdict, "label": VERDICTS[verdict][0], "text": text,
            "metrics": sorted({e["metric"] for e in evidence}), "evidence": evidence, "thresholds": list(thresholds)}


def _join(items):
    items = list(items)
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


#: The figures behind the overall verdict: (group, metric path, plain label, margin from the raw value).
#: A margin is in dB below a reference-level tone (0 dB SACD, -6.02 dBFS); larger is better.
MARGINS = (
    ("sinad", "tone_0dbsacd.sinad_db", "distortion plus noise on a 1 kHz tone (SINAD)", lambda v: v),
    ("dr", "dynamic_range.dr_a_db", "dynamic range, A-weighted", lambda v: v),
    ("imd", "imd_smpte.imd_db", "intermodulation of 60 Hz with 7 kHz", lambda v: -v),
    ("imd", "imd_ccif.imd_db", "intermodulation of 19 kHz with 20 kHz", lambda v: -v),
    ("noise", "noise.a_weighted_dbfs", "background noise, A-weighted", lambda v: REF_DBFS - v),
    ("stopband", "filter_summary.stopband_worst_db", "image rejection (an upper bound on the images)", lambda v: -v),
)
_FLAG_OF = {"tone_0dbsacd.sinad_db": "sinad", "dynamic_range.dr_a_db": "dr", "noise.a_weighted_dbfs": "noise",
            "imd_smpte.imd_db": "imd_smpte", "imd_ccif.imd_db": "imd_ccif"}


def margins(M):
    """[(path, label, margin_db, at_floor)] for the validated figures present in ``M``."""
    ok, fl = status(M), flags(M.get("device_class", "A"), M)
    out = []
    for group, path, label, fn in MARGINS:
        v = lookup(M, path)
        if group in ok and v is not None:
            out.append((path, label, fn(v), _FLAG_OF.get(path) in fl))
    return out


def tier(margin_db):
    """The verdict for a margin below the reference level."""
    if margin_db >= _t("range_120_db"):
        return "margin-120"
    return "margin-87" if margin_db >= _t("dither16_db") else "margin-low"


def is_reference(device):
    return bool(device) and device.get("adapter") == "reference"


def format_limit(M):
    """The output format record when the word length alone may limit this result, else None.

    True for integer output whose measured SINAD lies between 6 dB under the SINAD that rounding with
    dither allows and 6 dB over the SINAD that plain rounding allows (the two bounds of the word length at
    that output rate). A device whose own noise is higher shows its own noise, and one whose rounding noise is
    shaped out of the band is not limited.
    """
    fmt = M.get("output_format")
    if M.get("device_class", "A") != "A" or not of.limits_result(fmt):
        return None
    sinad = lookup(M, "tone_0dbsacd.sinad_db")
    hi, lo = fmt.get("quantisation_sinad_db"), fmt.get("quantisation_sinad_dithered_db")
    if sinad is None or hi is None or lo is None:
        return None
    if sinad > hi + _t("floor_margin_db") or sinad < lo - _t("floor_margin_db"):
        return None
    return fmt


def format_text(fmt):
    """``"24-bit integer: 140.7 dB rounded, 135.9 dB with TPDF dither"``: the SINAD the word length allows."""
    return (f"{fmt['bits']}-bit integer PCM, whose rounding alone limits SINAD to about {fmt['quantisation_sinad_db']:.1f} dB "
            f"(plain rounding) or {fmt['quantisation_sinad_dithered_db']:.1f} dB (TPDF dither) at {fmt['rate'] / 1000:g} kHz")


def _format_conclusion(M, fmt, name=None):
    hi, lo = fmt["quantisation_sinad_db"], fmt["quantisation_sinad_dithered_db"]
    ev = [_ev("output_format.bits", "word length of the output file", f"{fmt['bits']} bits"),
          _ev("output_format.rate", "output rate", f"{fmt['rate'] / 1000:g} kHz"),
          _ev("output_format.quantisation_sinad_db", f"SINAD that {fmt['bits']}-bit plain rounding allows", f"{hi:.1f} dB"),
          _ev("output_format.quantisation_sinad_dithered_db", f"SINAD that {fmt['bits']}-bit rounding with TPDF dither allows", f"{lo:.1f} dB"),
          _ev("tone_0dbsacd.sinad_db", "SINAD measured", f"{M['tone_0dbsacd']['sinad_db']:.1f} dB")]
    who = f"{name} wrote" if name else "The tool wrote"
    text = (f"Not judged: {who} {format_text(fmt)} (measured {M['tone_0dbsacd']['sinad_db']:.1f} dB), so these figures cannot "
            "be told from the file format, and a converter noisier than the format would read about the same. "
            "Ask the tool for floating-point output and measure again.")
    return _c("overall", "format-limited", text, ev, ["floor_margin_db"])


# ----------------------------------------------------------------------------- device rules

def _overall(M):
    fmt = format_limit(M)
    if fmt:
        return _format_conclusion(M, fmt)
    ms = margins(M)
    if not ms:
        return None
    path, label, worst, at_floor = min(ms, key=lambda m: m[2])
    ev = [_ev(p, lab, _down(v) + " below the reference level" + (", at the reference floor" if f else ""))
          for p, lab, v, f in ms]
    v, w = tier(worst), _down(worst)
    least = " This figure is at the tool's own floor, so the tool cannot show more." if at_floor else ""
    rng, cd = f"{_t('range_120_db'):.0f} dB", f"{_t('dither16_db'):.0f} dB"
    what = "distortion, noise and images" if any(p.startswith("filter_summary.") for p, *_ in ms) else "distortion and noise"
    if v == "margin-120":
        text = (f"In every test concluded here, {what} stay at least {w} below a reference-level tone (the weakest is "
                f"{label}), above the {rng} reference line (docs/conclusions.md gives its source and status). This is a measurement, not a listening test.{least}")
        th = ["range_120_db"]
    elif v == "margin-87":
        text = (f"In every test concluded here, {what} stay at least {w} below a reference-level tone (the weakest is "
                f"{label}). That is below the noise level of dithered 16-bit ({cd} on this scale) and short of {rng}. "
                f"This is a measurement, not a listening test.{least}")
        th = ["dither16_db", "range_120_db"]
    else:
        text = (f"{label[:1].upper() + label[1:]} is {w} below a reference-level tone, less than the {cd} of dithered 16-bit noise on "
                "this scale. This is a measurement, not a listening test, and there is no single agreed threshold.")
        th = ["dither16_db", "distortion_music"]
    return _c("overall", v, text, ev, th)


def _floor(M):
    f, t = M.get("reference_floor"), M.get("tone_0dbsacd")
    if not f:
        return None
    ch, m = f["chain"], f["margin_db"]
    rate = f"DSD{int(f['dsd_rate']) // 44100}"
    ev = [_ev("reference_floor.chain.sinad_db", f"SINAD of the reference chain at {rate}", f"{ch['sinad_db']:.1f} dB"),
          _ev("reference_floor.chain.dr_a_db", "dynamic range of the reference chain, A-weighted", f"{ch['dr_a_db']:.1f} dB"),
          _ev("reference_floor.margin_db", "margin", f"{m:.0f} dB")]
    if t:
        ev.append(_ev("tone_0dbsacd.sinad_db", "SINAD of this device", f"{t['sinad_db']:.1f} dB"))
    text = (f"This is the measurement floor, not a result for a product: the built-in reference chain reads SINAD "
            f"{ch['sinad_db']:.1f} dB and dynamic range {ch['dr_a_db']:.1f} dB (A-weighted) at {rate}. A DSD to PCM "
            f"converter within {m:.0f} dB of these figures (SINAD above {ch['sinad_db'] - m:.1f} dB) cannot be "
            f"ranked by this tool.")
    ev.append(_ev("reference_floor.chain.sinad_db", "SINAD above which a converter cannot be ranked",
                  f"{ch['sinad_db'] - m:.1f} dB"))
    return _c("floor", "floor", text, ev, ["floor_margin_db"])


def _response(M):
    fr = M.get("frequency_response")
    if not fr or "fr" not in status(M):
        return None
    r, a20 = fr["ripple_pp_db"], fr["at_hz"].get("20000")
    ev = [_ev("frequency_response.ripple_pp_db", "response variation, 20 Hz to 20 kHz", _small(r))]
    tail = ""
    if a20 is not None:
        ev.append(_ev("frequency_response.at_hz.20000", "response at 20 kHz against 1 kHz", _small(a20)))
        tail = f" and is {'down' if a20 < 0 else 'up'} by {_small(a20)} at 20 kHz"
    if r <= _t("flat_db"):
        return _c("response", "fact", f"Flat response: the level varies by {_small(r)} from 20 Hz to 20 kHz (read at the tones measured){tail}.",
                  ev, ["flat_db"])
    if r <= _t("level_jnd_db"):
        return _c("response", "fact", f"Nearly flat response: the level varies by {_small(r)} from 20 Hz to 20 kHz{tail}. "
                  f"That is under the {_t('level_jnd_db'):.1f} dB level step used as a reference line here.",
                  ev, ["flat_db", "level_jnd_db"])
    return _c("response", "notable", f"Uneven response: the level varies by {_small(r)} from 20 Hz to 20 kHz{tail}. "
              f"That is more than the {_t('level_jnd_db'):.1f} dB level step used as a reference line here.",
              ev, ["level_jnd_db"])


def _level(M):
    ok, parts, ev, verdict = status(M), [], [], "fact"
    g = M.get("gain_error_db")
    if g is not None:
        ev.append(_ev("gain_error_db", "gain error at 0 dB SACD", _within(g) if abs(g) <= _t("flat_db") else _small(g)))
        if abs(g) <= _t("flat_db"):
            parts.append(f"unity gain within {_within(g)}")
        else:
            parts.append(f"the output is {_small(g)} {'higher' if g > 0 else 'lower'} than unity gain, so match "
                         "levels before any listening comparison with another device")
            verdict = "notable"
    ct = M.get("crosstalk")
    if ct and "1000" in ct:
        d = ct["1000"]["gain_diff_db"]
        ev.append(_ev("crosstalk.1000.gain_diff_db", "channel gain difference at 1 kHz", _within(d) if abs(d) <= _t("flat_db") else _small(d)))
        if abs(d) <= _t("flat_db"):
            parts.append(f"channels matched within {_within(d)}")
        else:
            parts.append(f"the channels differ by {_small(d)}")
            verdict = "notable" if abs(d) > _t("level_jnd_db") else verdict
    lo = lookup(M, "linearity.lowest_level_within_0p5_db")
    if lo is not None:
        ev.append(_ev("linearity.lowest_level_within_0p5_db", "lowest level reproduced within 0.5 dB", f"{lo:.0f} dBFS"))
        parts.append(f"quiet signals keep their level down to {lo:.0f} dBFS")
    if M.get("polarity") is not None and "polarity" in ok:
        ev.append(_ev("polarity", "polarity", str(M["polarity"])))
        parts.append("polarity is correct" if M["polarity"] == "normal" else "polarity is inverted")
    if not parts:
        return None
    text = "Level: " + _join(parts) + "."
    return _c("level", verdict, text, ev, ["flat_db"] + (["level_jnd_db"] if ct else []))


def _limits(M):
    f = M.get("reference_floor")
    if not f:
        return None
    k = M.get("device_class", "A")
    lim, fl, ok = limit_for(k, f), flags(k, M), status(M)
    rows = (("sinad", "sinad", "SINAD", "tone_0dbsacd.sinad_db", "sinad_db", "dB"),
            ("thd", "thd", "THD", "tone_0dbsacd.thd_db", "thd_db", "dB"),
            ("dr", "dr", "dynamic range", "dynamic_range.dr_a_db", "dr_a_db", "dB"),
            ("noise", "noise", "background noise", "noise.a_weighted_dbfs", "noise_a_dbfs", "dBFS"))
    names, ev = [], []
    for flag, group, name, path, fkey, unit in rows:
        if flag in fl and group in ok:
            names.append(name)
            ev.append(_ev(path, f"{name}, this device", f"{lookup(M, path):.1f} {unit}"))
            ev.append(_ev(f"reference_floor.{'chain' if k == 'A' else 'decoder_alone'}.{fkey}", f"{name}, reference floor",
                          f"{lim[fkey]:.1f} {unit}"))
    if not names:
        return None
    n = len(names)
    text = (f"At the reference floor in {n} figure{'s' if n > 1 else ''} ({_join(names)}): "
            f"{'they are' if n > 1 else 'it is'} within {f['margin_db']:.0f} dB of the tool's own limit, so "
            f"{'they show' if n > 1 else 'it shows'} the tool's limit, not the device's. The tool cannot show more.")
    ev.append(_ev("reference_floor.margin_db", "margin", f"{f['margin_db']:.0f} dB"))
    ev.append(_ev("reference_floor.margin_db", "figures within the margin", str(n)))
    return _c("limits", "at-floor", text, ev, ["floor_margin_db"])


def _tested(fs_):
    """" (tones from 24.1 to 34.1 kHz)" for the stopband sentences, or an empty string."""
    rng = fs_.get("stopband_tested_hz")
    return f" (tones from {rng[0] / 1000:.1f} to {rng[1] / 1000:.1f} kHz)" if rng else ""


def _filter(M):
    im, fs_ = M.get("impulse"), M.get("filter_summary") or {}
    if not im or "filter" not in status(M) or not im.get("measurable", True):
        return None
    kind, pre, post = im["filter_type"], im["pre_ringing_ms"], im["post_ringing_ms"]
    ev = [_ev("impulse.filter_type", "filter type", kind),
          _ev("impulse.pre_ringing_ms", "ringing before a transient", f"{pre:.2f} ms"),
          _ev("impulse.post_ringing_ms", "ringing after a transient", f"{post:.2f} ms")]
    flat = ""
    f01, f3 = fs_.get("minus_0p1_db_hz"), fs_.get("minus_3_db_hz")
    if f01:
        ev.append(_ev("filter_summary.minus_0p1_db_hz", "flat within 0.1 dB up to", _khz(f01)))
        flat = f", flat within 0.1 dB up to {_khz(f01)}"
    if f3:
        ev.append(_ev("filter_summary.minus_3_db_hz", "cut-off (-3 dB)", _khz(f3)))
    sb = fs_.get("stopband_worst_db")
    rej = ""
    if sb is not None and "stopband" in status(M):
        ev.append(_ev("filter_summary.stopband_worst_db", "image rejection", f"{-sb:.0f} dB"))
        rej = f" It rejects images by at least {-sb:.0f} dB{_tested(fs_)}."
        if fs_.get("stopband_tested_hz"):
            r_ = fs_["stopband_tested_hz"]
            ev.append(_ev("filter_summary.stopband_tested_hz", "tones tested", f"{r_[0] / 1000:.1f} to {r_[1] / 1000:.1f} kHz"))
    where = f", near its {_khz(f3)} cut-off" if f3 else ""
    if kind == "linear phase":
        text = (f"{kind.capitalize()} filter{flat}. It rings for {pre:.2f} ms before and {post:.2f} ms after a "
                f"transient{where}.{rej} The literature does not agree on a limit for this ringing, so no "
                "verdict is given.")
        return _c("filter", "no-threshold", text, ev, ["pre_ringing"])
    gd = M.get("group_delay_us")
    late = ""
    th = ["pre_ringing"]
    if gd and "group_delay" in status(M) and gd.get("measurable", True):
        d = abs(gd["at_20k"] - gd["at_1k"]) / 1000
        ev.append(_ev("group_delay_us.at_20k", "delay of 20 kHz against 1 kHz", f"{d:.2f} ms"))
        late = (f" It delays 20 kHz by {d:.2f} ms against 1 kHz, "
                f"{'below' if d < _t('group_delay_ms') else 'above'} the {_t('group_delay_ms'):.0f} ms reference line (docs/conclusions.md).")
        th.append("group_delay_ms")
    text = (f"{kind.capitalize()} filter{flat}. It rings for {pre:.2f} ms before and {post:.2f} ms after a "
            f"transient{where}.{late}{rej} The literature does not agree on a limit for this ringing, so no "
            "verdict is given.")
    return _c("filter", "no-threshold", text, ev, th)


def ultrasonic_level(M):
    """(dBFS, low Hz, high Hz, metric paths, bands) of the noise between 20 and 96 kHz, summed over the bands present.

    ``bands`` is a list of ``(low Hz, high Hz, dBFS, metric path)``; use it, not the path text, for the band edges
    (a key such as ``20000-22050.0`` holds a dot).
    """
    for base in ("ultrasonic.integrated_dbfs", "noise.bands"):
        bands = lookup(M, base) or {}
        use = []
        for k, v in bands.items():
            lo, hi = (float(x) for x in k.split("-"))
            if lo >= 20000 and hi <= 96000 and v is not None:
                use.append((lo, hi, v, f"{base}.{k}"))
        if use and max(u[1] for u in use) < 40000:
            use = []  # only the filter's own transition band (a 44.1 kHz decode): not ultrasonic noise
        if use:
            p = sum(10 ** (v / 10) for _, _, v, _ in use)
            use.sort()
            return 10 * math.log10(p), min(u[0] for u in use), max(u[1] for u in use), [u[3] for u in use], use
    return None


def _ultrasonic(M):
    if "ultrasonic" not in status(M):
        return None
    u = ultrasonic_level(M)
    if not u:
        return None
    lvl, lo, hi, paths, bands = u
    val = f"{lvl:.0f} dBFS"
    ev = [_ev(p, f"noise from {b_lo / 1000:g} to {b_hi / 1000:g} kHz", f"{v:.0f} dBFS") for b_lo, b_hi, v, p in bands]
    ev.append(_ev(paths[0], f"sum from {lo / 1000:g} to {hi / 1000:g} kHz", val))
    text = (f"Ultrasonic noise: {val} between {lo / 1000:g} and {hi / 1000:g} kHz. Noise shaping puts noise there by design. "
            "There is no agreed limit, so no verdict is given.")
    return _c("ultrasonic", "no-threshold", text, ev, ["ultrasonic"])


def _stability(M):
    s = lookup(M, "stability.levels")
    if not s or "stability" not in status(M):
        return None
    bad = [k for k, v in s.items() if v["saturated"]]
    drift = max(abs(v["thdn_drift_db"]) for v in s.values())
    hold = lookup(M, "stability.hold_s")
    ev = [_ev(f"stability.levels.{k}.saturated", f"saturated at {k}", "yes" if v["saturated"] else "no") for k, v in s.items()]
    ev.append(_ev("stability.hold_s", "length of each hold", f"{hold:.0f} s"))
    if bad:
        return _c("stability", "notable", f"Unstable: the modulator saturated at {_join(bad)} during a {hold:.0f} s "
                  "hold.", ev)
    k0 = max(s, key=lambda k: abs(s[k]["thdn_drift_db"]))
    ev.append(_ev(f"stability.levels.{k0}.thdn_drift_db", "largest drift of THD+N during a hold", _small(drift)))
    text = (f"Stable: the modulator did not saturate in {hold:.0f} s holds at {_join(list(s))}, and its "
            f"distortion drifted by {_small(drift)}.")
    return _c("stability", "fact", text, ev)


def _stopband(M):
    """Image rejection from the alias tones (class A). Stands alone when the filter description is not used."""
    sb = lookup(M, "filter_summary.stopband_worst_db")
    if sb is None or "stopband" not in status(M) or "filter" in status(M):
        return None  # with the filter rule on, the figure is part of its sentence
    fs_ = lookup(M, "filter_summary") or {}
    rng = fs_.get("stopband_tested_hz")
    ev = [_ev("filter_summary.stopband_worst_db", "worst image of the tones tested", f"{-sb:.0f} dB below the tone")]
    if rng:
        ev.append(_ev("filter_summary.stopband_tested_hz", "tones tested", f"{rng[0] / 1000:.1f} to {rng[1] / 1000:.1f} kHz"))
    which = f"tones from {rng[0] / 1000:.1f} to {rng[1] / 1000:.1f} kHz" if rng else "the tones tested"
    text = (f"Image rejection: {which} come back as images at least {-sb:.0f} dB below the tone. The figure "
            "includes the device's own noise, so it is an upper bound on the images.")
    return _c("stopband", "fact", text, ev)


def _overload(M):
    ov = lookup(M, "overload_recovery.recovery_ms")
    if ov is None or "overload" not in status(M):
        return None
    ev = [_ev("overload_recovery.recovery_ms", "recovery after an overload burst", f"{ov:.0f} ms")]
    lvl, ms = lookup(M, "overload_recovery.burst_level_dbfs"), lookup(M, "overload_recovery.burst_ms")
    from .levels import PEAK_DBFS
    kind = "a loud burst (the peak level SACD allows)" if lvl is not None and abs(lvl - PEAK_DBFS) < 0.1 else "a burst"
    burst = f"{kind} of {ms:.0f} ms at {lvl:.1f} dBFS" if lvl is not None and ms else "a loud burst"
    ev.append(_ev("overload_recovery.recovery_ms", "resolution of the test", "about 10 ms"))
    if ov <= 10:
        back = "back to normal within 10 ms, the resolution of the test"
    else:
        back = f"back to normal within {ov:.0f} ms (the test resolves about 10 ms)"
    return _c("overload", "fact", f"Overload: after {burst} the output is {back}.", ev)


def _rates(M):
    rt, t = M.get("rates"), M.get("tone_0dbsacd")
    if not rt or "sinad" not in status(M):
        return None
    ev, bits = [], []
    if t:
        base = f"DSD{int(M.get('dsd_rate', 2822400)) // 44100}"
        ev.append(_ev("tone_0dbsacd.sinad_db", f"SINAD at {base}", f"{t['sinad_db']:.0f} dB"))
        bits.append(f"{t['sinad_db']:.0f} dB at {base}")
    for k, v in rt.items():
        ev.append(_ev(f"rates.{k}.sinad_db", f"SINAD at {k}", f"{v['sinad_db']:.0f} dB"))
        bits.append(f"{v['sinad_db']:.0f} dB at {k}")
    text = f"By rate: SINAD is {_join(bits)}."
    if "ultrasonic" in status(M):
        us = []
        for k, v in rt.items():
            u = ultrasonic_level(v)
            if u:
                ev.append(_ev(u[3][0].replace("ultrasonic.", f"rates.{k}.ultrasonic.", 1), f"ultrasonic noise at {k}, "
                              f"{u[1] / 1000:g} to {u[2] / 1000:g} kHz", f"{u[0]:.0f} dBFS"))
                us.append(f"{u[0]:.0f} dBFS at {k}")
        if us:
            text += f" Ultrasonic noise from 20 to 96 kHz is {_join(us)}."
    return _c("rates", "fact", text, ev)


def _pending(M):
    ok = status(M)
    keys = [k for k in PENDING_NAMES if M.get(k) is not None and _GROUP_OF.get(k, "never") not in ok]
    if not keys:
        return None
    ev = [_ev(k, PENDING_NAMES[k], "measured, not concluded") for k in keys]
    text = (f"Not concluded in this version: {_join(list(dict.fromkeys(PENDING_NAMES[k] for k in keys)))}. These figures are "
            "either not validated yet or not used by any rule in this version, so they are in the table for reference "
            "only and are not part of any verdict here.")
    if "tone_peak" in keys:
        text += " The peak-level SINAD is shown with the floor of the reference modulator at that level."
    return _c("pending", "pending", text, ev)


def device_conclusions(M, device=None):
    """The conclusions for one device, most important first. ``device`` is its description
    (``{"adapter": ..., "class": ...}``); the built-in reference chain gets the floor conclusion."""
    ref = is_reference(device)
    rules = [_floor if ref else _overall, _response, _filter, _stopband, _ultrasonic, _level, _stability, _overload, _rates,
             None if ref else _limits, _pending]
    return [c for c in (r(M) for r in rules if r) if c]


# ----------------------------------------------------------------------------- comparison rules

_RANK = {"same": 0, "technical": 1, "material": 2}

#: The tolerance sentence every comparison carries until a repeatability interval is measured.
NO_INTERVAL = "No repeatability interval has been measured yet, so a difference is reported, not ranked."


def conditions(M):
    """What a figure was measured under: the DSD rate, and for a converter the output rate and format.

    Two devices that differ here are not like-for-like: the output rate sets the noise bandwidth and the
    floor, and the word length can set a floor of its own.
    """
    c = {"class": M.get("device_class", "A"), "dsd_rate": M.get("dsd_rate")}
    fmt = M.get("output_format")
    if c["class"] == "A" and fmt:
        # every floating-point format is one format here (its rounding is far below the reference floor); integers differ by width
        c.update(out_rate=fmt.get("rate"), kind=fmt.get("kind"), bits=fmt.get("bits") if fmt.get("kind") == "int" else None)
    return c


def _rate_text(r):
    return f"{r / 1000:g} kHz" if r else "an unknown rate"


def condition_text(M):
    """The conditions of one device as a short phrase: ``DSD64 in, 32-bit float out at 352.8 kHz``."""
    c = conditions(M)
    base = f"DSD{int(c['dsd_rate']) // 44100}" if c.get("dsd_rate") else "DSD"
    if "out_rate" in c:
        word = f"{c['bits']}-bit integer" if c["kind"] == "int" else "floating-point"
        return f"{base} in, {word} out at {_rate_text(c['out_rate'])}"
    return f"{base} out"


def like_for_like(entries):
    """``(True, "")`` when every device of a class was measured under the same conditions, else ``(False, reason)``.

    ``entries`` is a list of ``(name, metrics)``. Only devices of the same class are compared.
    """
    for k in sorted({conditions(M)["class"] for _, M in entries}):
        group = [(n, M) for n, M in entries if conditions(M)["class"] == k]
        base = conditions(group[0][1])
        if any(conditions(M) != base for _, M in group[1:]):
            return False, _join([f"{n}: {condition_text(M)}" for n, M in group])
    return True, ""


def _pair_margins(a, b):
    """Compare the overall-verdict figures of two devices: [(class, path, label, margin_a, margin_b)]."""
    ma = {p: (lab, v, f) for p, lab, v, f in margins(a)}
    mb = {p: (lab, v, f) for p, lab, v, f in margins(b)}
    out = []
    for p in ma:
        if p not in mb:
            continue
        (lab, va, fa), (_, vb, fb) = ma[p], mb[p]
        if (fa and fb) or abs(va - vb) < _t("same_db"):
            cls = "same"
        elif min(va, vb) >= _t("dither16_db"):
            cls = "technical"
        else:
            cls = "material"
        out.append((cls, p, lab, va, vb))
    return out


def _cmp_distortion(na, a, nb, b):
    rows = _pair_margins(a, b)
    if not rows:
        return "same", None
    ev = []
    for _, p, lab, va, vb in rows:
        ev += [_ev(p, lab, _down(va) + " below the reference level", na), _ev(p, lab, _down(vb) + " below the reference level", nb)]
    worst = max(rows, key=lambda r: (_RANK[r[0]], abs(r[3] - r[4])))
    cls, _, lab, va, vb = worst
    if cls == "same":
        return cls, _c("cmp-distortion", "same",
                       f"Distortion and noise: no difference that can be ranked. Every figure is either at the reference "
                       f"floor for both or within {_t('same_db'):.0f} dB (a convention).", ev, ["same_db", "floor_margin_db"])
    (lo_n, lo), (hi_n, hi) = sorted(((na, va), (nb, vb)), key=lambda x: x[1])
    d = f"{math.floor(hi - lo + 1e-9):.0f} dB"
    ev.append(_ev(worst[1], f"difference in {lab}", d))
    if cls == "technical":
        both = min(lo, hi) >= _t("range_120_db")
        why = (f"both are at least {_t('range_120_db'):.0f} dB below it" if both else
               f"both are below the {_t('dither16_db'):.0f} dB noise level of dithered 16-bit on this scale")
        text = (f"Distortion and noise: in {lab}, {hi_n} reads {_down(hi)} and {lo_n} {_down(lo)} below a "
                f"reference-level tone, a difference of {d}; {why}. {NO_INTERVAL}")
        return cls, _c("cmp-distortion", "difference-low", text, ev, ["range_120_db" if both else "dither16_db", "same_db"])
    text = (f"Distortion and noise: {lo_n} is {_down(lo)} below a reference-level tone in {lab}, less than the "
            f"{_t('dither16_db'):.0f} dB noise level of dithered 16-bit on this scale; {hi_n} is at {_down(hi)}. "
            f"{NO_INTERVAL}")
    return cls, _c("cmp-distortion", "notable", text, ev, ["dither16_db", "distortion_music", "same_db"])


def _cmp_response(na, a, nb, b):
    fa, fb = a.get("frequency_response"), b.get("frequency_response")
    if not fa or not fb:
        return "same", None
    keys = [k for k in fa["at_hz"] if k in fb["at_hz"] and fa["at_hz"][k] is not None and fb["at_hz"][k] is not None]
    if not keys:
        return "same", None
    k = max(keys, key=lambda x: abs(fa["at_hz"][x] - fb["at_hz"][x]))
    d = abs(fa["at_hz"][k] - fb["at_hz"][k])
    f = _khz(float(k)) if float(k) >= 1000 else f"{float(k):.0f} Hz"
    p = f"frequency_response.at_hz.{k}"
    ev = [_ev(p, f"response at {f} against 1 kHz", f"{fa['at_hz'][k]:+.2f} dB", na),
          _ev(p, f"response at {f} against 1 kHz", f"{fb['at_hz'][k]:+.2f} dB", nb),
          _ev(p, "largest difference in response, 20 Hz to 20 kHz", _within(d) if d <= _t("flat_db") else _small(d))]
    if d <= _t("flat_db"):
        return "same", _c("cmp-response", "same", f"Frequency response: the same within {_within(d)} from "
                          "20 Hz to 20 kHz.", ev, ["flat_db"])
    if d <= _t("level_jnd_db"):
        return "technical", _c("cmp-response", "difference-low", f"Frequency response: they differ by up to {_small(d)} (at {f}), "
                               f"under the {_t('level_jnd_db'):.1f} dB level step used as a reference line here.", ev,
                               ["flat_db", "level_jnd_db"])
    return "material", _c("cmp-response", "notable", f"Frequency response: they differ by up to {_small(d)} (at {f}), more "
                          f"than the {_t('level_jnd_db'):.1f} dB level step used as a reference line here.", ev, ["level_jnd_db"])


def _cmp_level(na, a, nb, b):
    ga, gb = a.get("gain_error_db"), b.get("gain_error_db")
    if ga is None or gb is None:
        return "same", None
    d = abs(ga - gb)
    ev = [_ev("gain_error_db", "gain error at 0 dB SACD", f"{ga:+.2f} dB", na),
          _ev("gain_error_db", "gain error at 0 dB SACD", f"{gb:+.2f} dB", nb),
          _ev("gain_error_db", "difference in output level", _within(d) if d <= _t("flat_db") else _small(d))]
    if d <= _t("flat_db"):
        return "same", _c("cmp-level", "same", f"Level: the same within {_within(d)}.", ev, ["flat_db"])
    loud = na if ga > gb else nb
    return "material", _c("cmp-level", "notable", f"Level: {loud} reads {_small(d)} higher in output level. Match the "
                          "levels before any listening comparison.", ev, ["flat_db", "level_jnd_db"])


def _cmp_filter(na, a, nb, b):
    ia, ib = a.get("impulse"), b.get("impulse")
    if not ia or not ib or "filter" not in status(a) or "filter" not in status(b):
        return "same", None
    ev = [_ev("impulse.filter_type", "filter type", ia["filter_type"], na), _ev("impulse.filter_type", "filter type", ib["filter_type"], nb),
          _ev("impulse.pre_ringing_ms", "ringing before a transient", f"{ia['pre_ringing_ms']:.2f} ms", na),
          _ev("impulse.pre_ringing_ms", "ringing before a transient", f"{ib['pre_ringing_ms']:.2f} ms", nb)]
    if ia["filter_type"] == ib["filter_type"] and abs(ia["pre_ringing_ms"] - ib["pre_ringing_ms"]) < 0.05:
        return "same", None
    text = (f"Filters: {na} is {ia['filter_type']} and rings {ia['pre_ringing_ms']:.2f} ms before a transient; {nb} is "
            f"{ib['filter_type']} and rings {ib['pre_ringing_ms']:.2f} ms. The literature does not agree on a limit for this "
            "ringing, so no verdict is given.")
    return "unsettled", _c("cmp-filter", "no-threshold", text, ev, ["pre_ringing"])


def _cmp_ultrasonic(na, a, nb, b):
    if "ultrasonic" not in status(a) or "ultrasonic" not in status(b):
        return "same", None
    ua, ub = ultrasonic_level(a), ultrasonic_level(b)
    if not ua or not ub or (ua[1], ua[2]) != (ub[1], ub[2]) or abs(ua[0] - ub[0]) < _t("same_db"):
        return "same", None
    band = f"{ua[1] / 1000:g} to {ua[2] / 1000:g} kHz"
    ev = [_ev(ua[3][0], f"noise, {band}", f"{ua[0]:.0f} dBFS", na), _ev(ub[3][0], f"noise, {band}", f"{ub[0]:.0f} dBFS", nb)]
    (lo_n, lo), (hi_n, hi) = sorted(((na, ua[0]), (nb, ub[0])), key=lambda x: x[1])
    text = (f"Ultrasonic noise: {hi_n} passes {hi:.0f} dBFS and {lo_n} {lo:.0f} dBFS between {band.replace(' to ', ' and ')}. "
            "There is no agreed limit, so no verdict is given.")
    return "unsettled", _c("cmp-ultrasonic", "no-threshold", text, ev, ["ultrasonic"])


def _format_head(limited):
    ev = [e for n, f in limited for e in (_ev("output_format.bits", "word length of the output file", f"{f['bits']} bits", n),
                                          _ev("output_format.rate", "output rate", f"{f['rate'] / 1000:g} kHz", n),
                                          _ev("output_format.quantisation_sinad_db", f"SINAD that {f['bits']}-bit plain rounding allows", f"{f['quantisation_sinad_db']:.1f} dB", n),
                                          _ev("output_format.quantisation_sinad_dithered_db", f"SINAD that {f['bits']}-bit rounding with TPDF dither allows", f"{f['quantisation_sinad_dithered_db']:.1f} dB", n))]
    who = _join([f"{n} wrote {format_text(f)}" for n, f in limited])
    return _c("cmp-format", "format-limited", f"Distortion and noise were not compared: {who}. "
              "Ask the tool for floating-point output and measure again.", ev)


def _pair(na, a, nb, b, suffix=""):
    same_conditions, _ = like_for_like([(na, a), (nb, b)])
    limited = [(n, format_limit(M)) for n, M in ((na, a), (nb, b)) if format_limit(M)]
    if not same_conditions:  # a different output rate or format: the distortion and noise figures would compare settings
        found = [fn(na, a, nb, b) for fn in (_cmp_response, _cmp_level, _cmp_filter)]
        ev = [_ev("output_format.rate", "output rate and format", condition_text(M), n) for n, M in ((na, a), (nb, b))]
        head = _c("cmp-conditions", "not-like-for-like",
                  f"Not like-for-like: {na} was measured as {condition_text(a)} and {nb} as {condition_text(b)}. The output rate "
                  "sets the noise bandwidth and the floor, and the word length can set a floor of its own, so distortion and "
                  "noise were not compared. Measure both at the same output rate and format.", ev)
        out = [head] + [c for _, c in found if c]
        if limited:
            out.insert(1, _format_head(limited))
    elif limited:  # a word length that caps the figures: the distortion rows would compare file formats
        found = [fn(na, a, nb, b) for fn in (_cmp_response, _cmp_level, _cmp_filter, _cmp_ultrasonic)]
        out = [_format_head(limited)] + [c for _, c in found if c]
    else:
        found = [fn(na, a, nb, b) for fn in (_cmp_distortion, _cmp_response, _cmp_level, _cmp_filter, _cmp_ultrasonic)]
        out = [c for _, c in found if c]
        classes = [cls for cls, c in found if c]
        if not out:
            return []
        ev = [e for c in out for e in c["evidence"]]
        names = f"{na} and {nb}"
        where = [c["text"].split(":")[0].lower() for (cls, c) in found if c and cls == "material"]
        if "material" in classes:
            head = _c("cmp-overall", "notable", f"{names} differ by more than the tolerance used here in {_join(where)}. See below. "
                      f"This names the difference; it is not a ranking. {NO_INTERVAL}", ev)
        elif "technical" in classes:
            head = _c("cmp-overall", "difference-low", f"{names} measure differently on the tests concluded here, but no difference "
                      f"reaches the thresholds used here. This describes the measurements and ranks nothing. {NO_INTERVAL}", ev)
        else:
            head = _c("cmp-overall", "same", f"{names} measure the same in the audio band on the tests concluded here: every "
                      f"difference is below the reference floor or the {_t('same_db'):.0f} dB tolerance, which is a convention "
                      "and not a measured repeatability.", ev, ["same_db"])
        if "unsettled" in classes:
            head["text"] += " One difference has no agreed threshold (see below)."
        out = [head] + out
    for c in out:
        c["id"] += suffix
    return out


def comparison_conclusions(entries):
    """Conclusions for a comparison. ``entries`` is a list of ``(name, metrics, device)``."""
    out = []
    if entries and all(is_reference(d) for _, _, d in entries):
        fl = next((_floor(M) for _, M, _ in entries if M.get("reference_floor")), None)
        if fl:
            fl["text"] = ("Every device here is the built-in reference chain. " + fl["text"])
            out.append(fl)
        s = [(n, lookup(M, "tone_0dbsacd.sinad_db")) for n, M, _ in entries]
        s = [(n, v) for n, v in s if v is not None]
        if len(s) > 1:
            d = max(v for _, v in s) - min(v for _, v in s)
            ev = [_ev("tone_0dbsacd.sinad_db", "SINAD", f"{v:.1f} dB", n) for n, v in s]
            ev.append(_ev("tone_0dbsacd.sinad_db", "spread of SINAD", _small(d)))
            agree = d < _t("same_db")
            out.append(_c("floor-agreement", "fact" if agree else "notable",
                          f"The parts of the chain {'agree' if agree else 'do not agree'}: SINAD is "
                          f"{_join([f'{v:.1f} dB for {n}' for n, v in s])}, a spread of {_small(d)}."
                          + ("" if agree else " They should read the same; treat this run with care."), ev, ["same_db"]))
    else:
        groups = {}
        for n, M, d in entries:
            groups.setdefault(M.get("device_class", (d or {}).get("class", "A")), []).append((n, M))
        if len(groups) > 1:
            kinds = {"A": "DSD to PCM converter", "B": "PCM to DSD modulator"}
            ev = [_ev("device_class", "class", k, n) for k, g in groups.items() for n, _ in g]
            desc = _join([f"{n} is a {kinds.get(k, k)}" for k, g in groups.items() for n, _ in g])
            out.append(_c("cmp-classes", "not-comparable", f"Different jobs: {desc}. Converters and modulators are not "
                          "rivals; their columns are side by side for reference only.", ev))
        many = sum(len(g) > 1 for g in groups.values()) > 1
        for k, g in groups.items():
            pairs = [(g[i], g[j]) for i in range(len(g)) for j in range(i + 1, len(g))]
            for n, ((na, a), (nb, b)) in enumerate(pairs):
                suffix = (f"-{k}" if many else "") + (f"-{n + 1}" if len(pairs) > 1 else "")
                out += _pair(na, a, nb, b, suffix)
    seen = {}
    for _, M, _ in entries:
        p = _pending(M)
        for e in (p["evidence"] if p else []):
            seen.setdefault(e["metric"], e)
    if seen:
        names = _join(list(dict.fromkeys(e["label"] for e in seen.values())))
        out.append(_c("pending", "pending", f"Not compared in this version: {names}. These figures are not "
                      "validated yet or not used by any rule, and converters often differ most in their filters and ultrasonic noise, so "
                      "this comparison is not the whole picture.", list(seen.values())))
    return out


# ----------------------------------------------------------------------------- rendering helpers

SCOPE = ("Conclusions cover the synthetic test signals and the software path measured here. They are not a listening "
         "test and say nothing about a DAC, an amplifier or a recording.")
DOC_URL = "https://github.com/dsd-toolbox/dsd-measure/blob/main/docs/conclusions.md"


def numbers(text):
    """The numbers in a sentence, as strings (used by the tests to check that each one is backed by evidence)."""
    return re.findall(r"(?<![\w.])-?\d+(?:\.\d+)?(?!\d|\.\d|-bit)", text)


# ----------------------------------------------------------------------------- the one-sentence result

#: Measured but not concluded, named in the headline because converters often differ most there.
_HEADLINE_PENDING = ("filter and ringing", "ultrasonic noise")


def _not_judged(Ms):
    """" Filters and ultrasonic noise are not judged in this version." when that is so for any of ``Ms``."""
    names = []
    for M in Ms:
        p = _pending(M)
        names += [e["label"] for e in (p["evidence"] if p else []) if e["label"] in _HEADLINE_PENDING]
    names = [n for n in _HEADLINE_PENDING if n in names]
    return f" Not judged in this version: {_join(names)}." if names else ""


def device_headline(M, device=None, name=None):
    """One sentence that starts "Result:" for a single device's report."""
    who = name or (device or {}).get("name") or "this device"
    if is_reference(device):
        f = M.get("reference_floor")
        sinad = f"SINAD {f['chain']['sinad_db']:.1f} dB, " if f else ""
        return (f"Result: this is the measurement floor of the built-in reference chain ({sinad}the highest figure the tool can show), "
                "not a result for a product.")
    fmt = format_limit(M)
    if fmt:
        return (f"Result: not judged. {who} wrote {format_text(fmt)}, "
                "so the figures describe the file format, not the converter; ask the tool for floating-point output and measure again.")
    ms = margins(M)
    if not ms:
        return f"Result: {who} was measured, but no figure here is validated for a verdict; see the table."
    path, label, worst, at_floor = min(ms, key=lambda m: m[2])
    v, w = tier(worst), _down(worst)
    least = ", at the tool's own floor, so the tool cannot show more" if at_floor else ""
    cd, rng = f"{_t('dither16_db'):.0f} dB", f"{_t('range_120_db'):.0f} dB"
    where = {"margin-120": f"every concluded figure is at least {rng} down",
             "margin-87": f"every concluded figure is at least {cd} down, the noise level of dithered 16-bit on this scale",
             "margin-low": f"less than {cd} down, the noise level of dithered 16-bit on this scale"}[v]
    head = (f"Result: {who} measures {w} below a reference-level tone in its weakest figure in the audio band, {label}{least}; "
            f"{where}.")
    return head + _not_judged([M])


def comparison_headline(entries, conclusions):
    """One sentence that starts "Result:" for a comparison; ``entries`` as for ``comparison_conclusions``."""
    names = [n for n, _, _ in entries]
    if entries and all(is_reference(d) for _, _, d in entries):
        return ("Result: every device here is the built-in reference chain, so this is the measurement floor of the tool, "
                "not a result for a product.")
    heads = [c for c in conclusions if c["id"].startswith(("cmp-overall", "cmp-format", "cmp-conditions"))]
    if not heads:
        return f"Result: {_join(names)} were measured side by side; see the table."
    unlike = [c for c in heads if c["verdict"] == "not-like-for-like"]
    if unlike:
        return ("Result: not like-for-like. " + unlike[0]["text"].split(": ", 1)[1].split(" Measure both")[0]
                + " Figures are listed but not compared.")
    fmt = [c for c in heads if c["verdict"] == "format-limited"]
    if fmt:
        return ("Result: not compared in distortion and noise. " + fmt[0]["text"].split(": ", 1)[1])
    rank = {"same": 0, "difference-low": 1, "notable": 2}
    worst = max(heads, key=lambda c: rank[c["verdict"]])
    tail = _not_judged([M for _, M, _ in entries]).replace("Not judged in this version", "Not compared in this version")
    if worst["verdict"] == "same":
        return f"Result: in the audio band, {_join(names)} measure the same within the tolerance used here.{tail}"
    if worst["verdict"] == "difference-low":
        return (f"Result: {_join(names)} measure differently, but no difference reaches the thresholds used here; "
                f"nothing is ranked.{tail}")
    return "Result: " + worst["text"].split(" See below.")[0].rstrip(".") + "; nothing is ranked." + tail
