"""Reports: HTML with inline SVG plots, Markdown, CSV and JSON, one per device plus a comparison."""

import csv
import html
import io
import json
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

PALETTE = ["#0072B2", "#E69F00", "#009E73", "#D55E00", "#CC79A7", "#56B4E9", "#7a7a7a", "#8c564b"]
plt.rcParams.update({
    "svg.hashsalt": "dsd-measure", "svg.fonttype": "none", "figure.figsize": (7.5, 3.9),
    "axes.grid": True, "grid.alpha": 0.3, "axes.spines.top": False, "axes.spines.right": False,
    "font.size": 9, "axes.titlesize": 10, "axes.titleweight": "bold", "figure.facecolor": "white",
    "lines.linewidth": 1.4, "font.family": "sans-serif",
})


def _svg(fig):
    buf = io.StringIO()
    fig.savefig(buf, format="svg", metadata={"Date": None, "Creator": "dsd-measure"}, bbox_inches="tight")
    plt.close(fig)
    s = buf.getvalue()
    s = s[s.index("<svg"):]
    # shorten path coordinates to 0.1 pt: invisible, and about a third smaller
    return re.sub(r' d="([^"]*)"', lambda m: ' d="' + re.sub(r"(\d+\.\d)\d+", r"\1", m.group(1)) + '"', s)


def _fmt_hz(f):
    return f"{f / 1000:g} kHz" if f >= 1000 else f"{f:g} Hz"


def _logx(ax, lo=10, hi=None):
    ax.set_xscale("log")
    ax.set_xlim(lo, hi)
    ax.set_xlabel("Frequency (Hz)")
    ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: _fmt_hz(v).replace(" ", "")))


# ----------------------------------------------------------------------------- plots

def plot_fr(series, zoom=True):
    fig, ax = plt.subplots()
    for name, c, d in series:
        ax.plot(d["f"], d["mag_db"], "-o", ms=3, color=c, label=name)
    _logx(ax, 20, None)
    ax.set_ylabel("Level re 1 kHz (dB)")
    if zoom:
        ax.set_ylim(-3, 1)
    ax.axvline(20000, color="#999", lw=0.8, ls=":")
    ax.set_title("Frequency response")
    if len(series) > 1:
        ax.legend()
    return _svg(fig)


def plot_noise(series, wide=None):
    fig, ax = plt.subplots()
    for name, c, d in series:
        ax.plot(d["f"], d["dbfs_hz"], color=c, label=name, lw=1.0)
    _logx(ax, 20, None)
    ax.set_ylim(-190, -90)
    ax.set_ylabel("Noise (dBFS per Hz)")
    ref = series[0][2].get("ref_24bit_tpdf")
    if ref is not None:
        ax.axhline(ref, color="#999", ls="--", lw=1, label="24-bit dither (PCM reference)")
    ax.axvline(20000, color="#999", lw=0.8, ls=":")
    ax.set_title("Noise floor")
    ax.legend(loc="upper left")
    return _svg(fig)


def plot_levels(series, floor=None):
    fig, ax = plt.subplots()
    for name, c, d in series:
        ax.plot(d["level"], d["thdn_db"], "-o", ms=3, color=c, label=name)
    if floor is not None:  # the floor of the reference chain is a level-dependent curve; its value at 0 dB SACD is shown
        _floor_line(ax, floor, "reference floor at 0 dB SACD")
    ax.set_xlabel("Input level (dBFS; 0 dB SACD is -6.02 dBFS)")
    ax.set_ylabel("THD+N (dB re signal)")
    ax.set_xlim(-130, 0)
    ax.set_ylim(-170, 0)
    if floor is not None:
        ax.legend()
    ax.set_title("THD+N against level, 1 kHz")
    if len(series) > 1:
        ax.legend()
    return _svg(fig)


def plot_thdn_freq(series, floor=None):
    fig, ax = plt.subplots()
    for name, c, d in series:
        ax.plot(d["f"], d["thdn_db"], "-o", ms=3, color=c, label=name)
    _floor_line(ax, floor, "reference floor at 1 kHz")
    _logx(ax, 20, 20000)
    ax.set_ylabel("THD+N (dB re signal)")
    ax.set_ylim(-170, -60)
    if floor is not None:
        ax.legend()
    ax.set_title("THD+N against frequency, 0 dB SACD")
    if len(series) > 1:
        ax.legend()
    return _svg(fig)


def plot_linearity(series):
    fig, ax = plt.subplots()
    for name, c, d in series:
        ax.plot(d["level"], d["error_db"], "-o", ms=3, color=c, label=name)
    ax.set_xlabel("Input level (dBFS)")
    ax.set_ylabel("Level error (dB)")
    ax.set_xlim(-130, 0)
    ax.set_ylim(-3, 3)
    ax.set_title("Linearity, 1 kHz")
    if len(series) > 1:
        ax.legend()
    return _svg(fig)


def plot_spectrum(d, title, fmax=None, tones=None, ylim=(-160, 0), color=None, xlog=False, fmin=0):
    fig, ax = plt.subplots()
    ax.plot(np.array(d["f"]) / 1000, d["db"], color=color or PALETTE[0], lw=0.8)
    if tones:
        ax.plot(np.array(tones[0]) / 1000, tones[1], "o", ms=3, color=PALETTE[3])
    ax.set_xlabel("Frequency (kHz)")
    ax.set_ylabel("Level (dBFS, tone peak; noise per bin)")
    ax.set_ylim(*ylim)
    if fmax:
        ax.set_xlim(fmin / 1000, fmax / 1000)
    ax.set_title(title)
    return _svg(fig)


def plot_impulse(series, step=False):
    fig, ax = plt.subplots()
    for name, c, d in series:
        key = "s" if step else "h"
        v = np.array(d[key])
        fs = d["fs"]
        t = (np.arange(len(v)) - d["center"]) / fs * 1000
        v = v / (np.max(np.abs(v)) or 1) if not step else v
        if len(v) < 700:
            ax.vlines(t, 0, v, color=c, lw=0.8)
            ax.plot(t, v, "o", ms=2.5, color=c, label=name)
        else:
            ax.step(t, v, where="post", color=c, label=name)
    if not step:
        ax.set_xlim(-0.5, 0.5)
    else:
        ax.set_xlim(-0.2, 2)
    ax.set_xlabel("Time (ms)")
    ax.set_ylabel("Amplitude (re peak)" if not step else "Amplitude (re final)")
    ax.set_title("Step response (output samples)" if step else "Impulse response (output samples)")
    if len(series) > 1:
        ax.legend()
    return _svg(fig)


def plot_filter(series):
    fig, ax = plt.subplots()
    for name, c, d in series:
        ax.plot(d["f"], d["mag_db"], color=c, label=name, lw=1.2)
    _logx(ax, 100, None)
    ax.set_ylim(-140, 6)
    ax.set_ylabel("Magnitude (dB)")
    ax.axvline(20000, color="#999", lw=0.8, ls=":")
    ax.set_title("Filter magnitude from the impulse response")
    if len(series) > 1:
        ax.legend()
    return _svg(fig)


def plot_group_delay(series):
    fig, ax = plt.subplots()
    for name, c, d in series:
        ax.plot(d["f"], d["gd_us"], color=c, label=name)
    _logx(ax, 20, 20000)
    ax.set_ylabel("Group delay (us, latency removed)")
    ax.set_title("Group delay")
    if len(series) > 1:
        ax.legend()
    return _svg(fig)


def plot_density(d):
    fig, ax = plt.subplots()
    ax.fill_between(d["t"], d["min"], d["max"], color=PALETTE[0], alpha=0.3, label="min to max")
    ax.plot(d["t"], d["mean"], color=PALETTE[0], label="mean")
    ax.axhline(71.43, color=PALETTE[3], ls="--", label="71.43 % (peak level)")
    ax.axhline(-71.43, color=PALETTE[3], ls="--")
    ax.set_ylim(-110, 110)
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("28-bit window modulation (%)")
    ax.set_title("Modulation in a 28-bit window at the peak level")
    ax.legend(loc="lower right")
    return _svg(fig)


def _floor_line(ax, y, label="reference floor"):
    if y is not None:
        ax.axhline(y, color="#b3261e", ls=":", lw=1.2, label=label)


def plot_imd_sweep(series):
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(7.5, 3.6))
    for name, c, d in series:
        a1.plot(np.array(d["ccif_centre"]) / 1000, d["ccif_db"], "-o", ms=3, color=c, label=name)
        a2.plot(d["smpte_level"], d["smpte_db"], "-o", ms=3, color=c, label=name)
    a1.set_xlabel("Centre of the 1 kHz-spaced pair (kHz)")
    a1.set_ylabel("CCIF IMD (dB)")
    a1.set_title("CCIF IMD against frequency")
    a2.set_xlabel("Level (dB SACD)")
    a2.set_ylabel("SMPTE IMD (dB)")
    a2.set_title("SMPTE IMD against level")
    for a in (a1, a2):
        a.set_ylim(-170, -60)
    if len(series) > 1:
        a1.legend()
    fig.tight_layout()
    return _svg(fig)


def plot_alias(series):
    fig, ax = plt.subplots()
    for name, c, d in series:
        ax.plot(np.array(d["tone"]) / 1000, d["image_db"], "-o", ms=4, color=c, label=name)
    ax.set_xlabel("Input tone (kHz), all above the output Nyquist frequency")
    ax.set_ylabel("Strongest image (dB re tone)")
    ax.set_ylim(-170, -40)
    ax.set_title("Alias images of out-of-band tones")
    if len(series) > 1:
        ax.legend()
    return _svg(fig)


def plot_overload(series):
    fig, ax = plt.subplots()
    for name, c, d in series:
        ax.plot(d["t_ms"], d["rms_db"], color=c, label=name, lw=1)
        ax.axhline(d["base_db"], color=c, ls=":", lw=0.8)
    ax.set_xlim(-100, 300)
    ax.set_xlabel("Time after the burst ends (ms)")
    ax.set_ylabel("Residual, 5 ms rms (dBFS)")
    ax.set_title("Overload recovery (dotted: level before the burst)")
    if len(series) > 1:
        ax.legend()
    return _svg(fig)


# ----------------------------------------------------------------------------- takeaways

def _g(m, *path, default=None):
    for p in path:
        if not isinstance(m, dict) or p not in m:
            return default
        m = m[p]
    return m


def takeaway(key, M):
    """One plain-language line per plot, filled from the real numbers."""
    if key == "fr":
        fr = M.get("frequency_response")
        if not fr:
            return ""
        r = fr["ripple_pp_db"]
        a20 = fr["at_hz"].get("20000")
        word = "flat" if r < 0.1 else ("slightly uneven" if r < 0.5 else "uneven")
        return (f"The treble is {word}: the response varies by {r:.2f} dB from 20 Hz to 20 kHz"
                f" and is {a20:+.2f} dB at 20 kHz.")
    if key == "impulse":
        i = M.get("impulse")
        if not i:
            return ""
        if not i.get("measurable", True):
            return ("The filter cannot be read at this output rate: the noise of the DSD stream in the record is above the "
                    "-60 dB threshold of the ringing and cut-off figures.")
        t = i["filter_type"]
        pre = i["pre_ringing_ms"]
        return (f"The filter is {t}. Ringing before the main pulse lasts {pre:.2f} ms "
                f"(more than 0 means a 'pre-echo'), after it {i['post_ringing_ms']:.2f} ms.")
    if key == "noise":
        n = M.get("noise")
        if not n:
            return ""
        return (f"Background noise is {n['a_weighted_dbfs']:.0f} dBFS weighted for hearing "
                f"({n['unweighted_dbfs']:.0f} dBFS unweighted); quieter is better.")
    if key == "levels":
        t = M.get("tone_0dbsacd")
        if not t:
            return ""
        s = t["sinad_db"]
        word = "excellent" if s > 100 else ("very good" if s > 90 else ("good" if s > 80 else "audible in a quiet room"))
        return f"At reference level distortion plus noise is {t['thdn_db']:.0f} dB ({word}); higher SINAD ({s:.0f} dB) is better."
    if key == "multitone":
        m = _g(M, "multitone", "headline")
        if not m:
            return ""
        return (f"With 32 tones playing at once the cleanest range is {m['distortion_free_range_db']:.0f} dB "
                f"below the quietest tone; this shows how the device copes with music-like signals.")
    if key == "spectrum_1k":
        t = M.get("tone_0dbsacd")
        if not t:
            return ""
        h = t["largest_harmonic"]
        return (f"A 1 kHz tone with total harmonic distortion {t['thd_db']:.0f} dB; the biggest unwanted "
                f"tone is harmonic {h['order']} at {h['db']:.0f} dB." if h else "")
    if key == "filter":
        return "How the filter treats frequencies above the audio band, from the impulse response; the dotted line marks 20 kHz."
    if key == "step":
        s = M.get("step")
        return f"The step overshoots by {s['overshoot_percent']:.1f} percent and settles within 1 percent in {s['settle_1pct_ms']:.2f} ms." if s else ""
    if key == "group_delay":
        g = M.get("group_delay_us")
        return f"Frequencies arrive {abs(g['at_20k'] - g['at_1k']):.0f} microseconds apart between 1 kHz and 20 kHz." if g else ""
    if key == "linearity":
        l = M.get("linearity")
        lo = l and l["lowest_level_within_0p5_db"]
        return f"Quiet sounds keep their level down to {lo:.0f} dBFS within 0.5 dB." if lo is not None else ""
    if key == "thdn_freq":
        t = M.get("thdn_vs_frequency")
        return (f"Distortion plus noise is {t['1000']:.0f} dB at 1 kHz and {t['20000']:.0f} dB at 20 kHz, "
                f"so within the 20 kHz band the treble is {'as clean as' if t['20000'] < t['1000'] + 6 else 'less clean than'} the midrange "
                "(harmonics of a tone above 10 kHz fall outside that band).") if t else ""
    if key == "imd_smpte":
        i = M.get("imd_smpte")
        return f"Mixing bass and treble creates {pct(i['imd_percent'])[:-2]} percent unwanted tones (SMPTE test)." if i else ""
    if key == "imd_ccif":
        i = M.get("imd_ccif")
        return f"Two very high tones leave {pct(i['imd_percent'])[:-2]} percent unwanted tones in the audible band (CCIF test)." if i else ""
    if key == "tone_15k":
        t = M.get("tone_15k")
        return (f"A 15 kHz tone: the strongest unwanted tone below 20 kHz is {t['audio_band']['db']:.0f} dB "
                f"down at {t['audio_band']['hz'] / 1000:.1f} kHz.") if t else ""
    if key == "jtest":
        j = M.get("jtest")
        if not j:
            return ""
        if j.get("largest_sideband_db") is None:
            return (f"File-level J-Test: no sideband stands above the noise (noise {j['noise_floor_db']:.0f} dB re the carrier "
                    f"in {j['bin_hz']:.2f} Hz bins; arithmetic only, not a clock test).")
        return (f"File-level J-Test: the largest sideband is {j['largest_sideband_db']:.0f} dB down, "
                f"{j['sidebands_detected']} above the noise (arithmetic only, not a clock test).")
    if key == "density":
        s = _g(M, "stability", "levels")
        if not s:
            return ""
        pk = [v for k, v in s.items() if "peak" in k]
        mx = max(v["max_modulation_pct"] for v in pk) if pk else None
        return f"At the loudest allowed level the 28-bit window reaches {mx:.1f} percent modulation; it never saturates." if mx and mx < 100 else "The modulator saturated at the peak level."
    if key == "imd_sweep":
        i = M.get("imd_sweep")
        return (f"Across the sweep the worst CCIF figure is {i['ccif_worst_db']:.0f} dB (pair centred on "
                f"{i['ccif_worst_centre_hz'] / 1000:g} kHz) and the worst SMPTE figure {i['smpte_worst_db']:.0f} dB; "
                "SMPTE rises at low level because the signal gets small.") if i else ""
    if key == "alias":
        a = M.get("alias_tones")
        return (f"Tones above the output's own limit leave images no louder than {a['worst_image_db']:.0f} dB "
                f"relative to the tone (worst at {a['worst_image_hz'] / 1000:.1f} kHz); lower is better.") if a else ""
    if key == "overload":
        o = M.get("overload_recovery")
        if not o:
            return ""
        rec = "within about 10 ms" if o["recovery_ms"] < 12 else f"after {o['recovery_ms']:.0f} ms"
        return f"After a 50 ms burst above the working range a quiet tone is back to its normal noise level {rec}."
    if key == "noise_wide":
        u = M.get("ultrasonic")
        if not u:
            return ""
        d = u.get("density_dbfs_hz", {})
        dens = ", ".join(f"{v:.0f} dBFS/Hz at {int(k) // 1000} kHz" for k, v in d.items())
        edge = " (the band edge, not a feature of the noise)" if u.get("peak_at_band_edge") else ""
        return (f"Ultrasonic noise density: {dens}. The highest 1/3-octave band is {u['peak_density_dbfs_hz']:.0f} dBFS/Hz "
                f"at {u['peak_hz'] / 1000:.0f} kHz{edge}.")
    return ""


# ----------------------------------------------------------------------------- tables

def _row(section, label, value, num=None, better=None, flag=False, hint=""):
    return {"section": section, "label": label, "value": value, "num": num, "better": better,
            "flag": flag, "hint": hint}


def _hz(f):
    return "not reached" if f is None else (f"{f / 1000:.2f} kHz" if f >= 1000 else f"{f:.0f} Hz")


def summary_rows(M):
    """The one-screen dashboard as a list of rows (see ``_row``); a ``flag`` marks a figure
    within 6 dB of the reference floor."""
    from .floor import flags
    fl = flags(M.get("device_class", "A"), M)
    r = []
    H, F, U, O = "Headline", "Filter", "Ultrasonic", "Other tests"
    t = M.get("tone_0dbsacd")
    if t:
        r += [_row(H, "SINAD, 1 kHz at 0 dB SACD (-6.02 dBFS)", f"{t['sinad_db']:.1f} dB", t["sinad_db"], "higher",
                   "sinad" in fl, "ASR-style: the tone over everything else, 20 Hz to 20 kHz, unweighted"),
              _row(H, "THD+N, 1 kHz", f"{t['thdn_db']:.1f} dB ({pct(t['thdn_percent'])})", -t["thdn_db"], "higher", "thdn" in fl),
              _row(H, "THD, 1 kHz", f"{t['thd_db']:.1f} dB ({pct(t['thd_percent'])})", -t["thd_db"], "higher", "thd" in fl,
                   "harmonics 2 to 9 only")]
    if "dynamic_range" in M:
        r.append(_row(H, "Dynamic range, A-weighted", f"{M['dynamic_range']['dr_a_db']:.1f} dB", M["dynamic_range"]["dr_a_db"],
                      "higher", "dr" in fl, "-60 dB tone method; unweighted figure in the CSV"))
    n = M.get("noise")
    if n:
        r.append(_row(H, "Noise 20 Hz-20 kHz, A-weighted", f"{n['a_weighted_dbfs']:.1f} dBFS", -n["a_weighted_dbfs"], "higher",
                      "noise" in fl, "32-bit-level dithered silence in; dBFS re the rms of a full-scale sine"))
    pk = M.get("tone_peak")
    if pk:
        df = pk.get("design_floor")
        # Class A: the reference modulator's design at this level has its own, higher, floor; say so in the value
        # so that every format (HTML, Markdown, CSV) carries it.
        extra = f" (reference modulator {df['ntf']}: floor {df['sinad_db']:.1f} dB)" if df else ""
        r.append(_row(H, "SINAD at the peak level (+3.1 dB SACD, -2.9 dBFS)", f"{pk['sinad_db']:.1f} dB{extra}", pk["sinad_db"],
                      "higher", "peak_sinad" in fl,
                      "the reference modulator is less accurate at this level than at 0 dB SACD" if df else ""))
    # filter
    im, fs_ = M.get("impulse"), M.get("filter_summary") or {}
    meas = bool(im.get("measurable", True)) if im else True
    if im and not meas:
        r.append(_row(F, "Filter type, ringing and cut-off", "not measurable at this output rate", None, None, False,
                      im.get("not_measurable_reason", "the noise of the DSD stream is above the -60 dB threshold")))
    elif im:
        r.append(_row(F, "Filter type", im["filter_type"]))
        r.append(_row(F, "Ringing before / after the pulse", f"{im['pre_ringing_ms']:.2f} / {im['post_ringing_ms']:.2f} ms",
                      im["pre_ringing_ms"], "lower", False, "samples above -60 dB of the peak"))
    if fs_ and meas:
        r.append(_row(F, "-0.1 dB / -3 dB frequency", f"{_hz(fs_.get('minus_0p1_db_hz'))} / {_hz(fs_.get('minus_3_db_hz'))}"))
    if fs_ and fs_.get("stopband_worst_db") is not None:
        rng = fs_.get("stopband_tested_hz")
        span = f"{rng[0] / 1000:.1f} to {rng[1] / 1000:.1f} kHz" if rng else f"from {_hz(fs_['stopband_edge_hz'])}"
        r.append(_row(F, "Stopband (upper bound)",
                      f"{fs_['stopband_worst_db']:.0f} dB or deeper, tones {span}", -fs_["stopband_worst_db"], "higher", False,
                      "worst image of the tones tested, read in the 20 Hz-20 kHz band; includes the device's own noise, "
                      "so the true stopband is this or deeper"))
    fr = M.get("frequency_response")
    if fr:
        r += [_row(F, "Passband ripple 20 Hz-20 kHz", f"{fr['ripple_pp_db']:.3f} dB peak to peak", fr["ripple_pp_db"], "lower"),
              _row(F, "Response at 20 kHz re 1 kHz", f"{fr['at_hz']['20000']:+.3f} dB")]
    gd = M.get("group_delay_us")
    if gd and gd.get("measurable", True):
        r.append(_row(F, "Group delay 20 kHz re 1 kHz", f"{gd['at_20k'] - gd['at_1k']:+.1f} microseconds"))
    # ultrasonic
    u = M.get("ultrasonic")
    if u:
        dd = u.get("density_dbfs_hz", {})
        if dd:
            r.append(_row(U, "Ultrasonic density at 50 / 100 / 200 kHz",
                          " / ".join(f"{dd[k]:.0f}" if k in dd else "n/a" for k in ("50000", "100000", "200000")) + " dBFS/Hz",
                          -dd.get("100000", dd.get("50000", 0.0)), "higher", False,
                          "power per Hz in a third of an octave, dBFS re a full-scale sine; lower is quieter"))
        r.append(_row(U, "Ultrasonic noise, highest 1/3 octave",
                      f"{u['peak_density_dbfs_hz']:.0f} dBFS/Hz at {u['peak_hz'] / 1000:.0f} kHz"
                      + (" (band edge)" if u.get("peak_at_band_edge") else ""), None, None, False,
                      "a single noisy bin is never reported; at the band edge the noise still rises"))
        ig = u["integrated_dbfs"]
        r.append(_row(U, "Integrated 20-40 / 40-96 kHz", f"{ig['20000-40000']:.0f} / {ig['40000-96000']:.0f} dBFS", -ig["40000-96000"], "higher"))
    elif n and n.get("bands", {}).get("20000-40000") is not None:
        r.append(_row(U, "Noise 20-40 kHz (device output)", f"{n['bands']['20000-40000']:.0f} dBFS", -n["bands"]["20000-40000"], "higher"))
    # other
    if "imd_smpte" in M:
        r.append(_row(O, "IMD SMPTE 60 Hz + 7 kHz, 0 dB SACD", f"{M['imd_smpte']['imd_db']:.1f} dB", -M["imd_smpte"]["imd_db"], "higher", "imd_smpte" in fl,
                      "sideband power re the 7 kHz tone; includes noise in the lobes"))
    if "imd_ccif" in M:
        r.append(_row(O, "IMD CCIF 19 + 20 kHz", f"{M['imd_ccif']['imd_db']:.1f} dB", -M["imd_ccif"]["imd_db"], "higher", "imd_ccif" in fl,
                      "products re the power sum of the two tones (3.01 dB higher than the IEC 60268-3 amplitude-sum value)"))
    sw = M.get("imd_sweep")
    if sw:
        r.append(_row(O, "IMD sweep, worst CCIF / SMPTE", f"{sw['ccif_worst_db']:.1f} / {sw['smpte_worst_db']:.1f} dB",
                      -sw["ccif_worst_db"], "higher", False, "CCIF pairs 10-19.5 kHz; SMPTE -60 to 0 dB SACD"))
    mt = _g(M, "multitone", "headline")
    if mt:
        r.append(_row(O, "Multitone distortion-free range", f"{mt['distortion_free_range_db']:.1f} dB", mt["distortion_free_range_db"], "higher", "multitone" in fl,
                      "tones and residual up to 20 kHz"))
    ct = M.get("crosstalk")
    if ct:
        worst = max(max(v["left_to_right_db"], v["right_to_left_db"]) for v in ct.values())
        r.append(_row(O, "Crosstalk, worst of 1 and 10 kHz", f"{worst:.0f} dB", -worst, "higher", "crosstalk" in fl,
                      "software paths show only the dither floor; a recorded analogue path shows real crosstalk"))
        r.append(_row(O, "Channel gain difference", f"{ct['1000']['gain_diff_db']:+.4f} dB, phase {ct['1000']['phase_diff_deg']:+.3f} deg"))
    al = M.get("alias_tones")
    if al:
        r.append(_row(O, "Worst alias image, tones above Nyquist", f"{al['worst_image_db']:.0f} dB re tone", -al["worst_image_db"], "higher", "alias" in fl))
    ov = M.get("overload_recovery")
    if ov:
        rec = ov["recovery_ms"]
        r.append(_row(O, "Overload recovery (50 ms burst)", "under 10 ms" if rec < 12 else f"{rec:.0f} ms", rec, "lower"))
    if "gain_error_db" in M:
        r.append(_row(O, "Gain error at 0 dB SACD", f"{M['gain_error_db']:+.3f} dB", abs(M["gain_error_db"]), "lower",
                      False, "output tone level minus the level expected for the input; 0 means unity gain"))
    if "polarity" in M:
        r.append(_row(O, "Polarity", M["polarity"]))
    if "dc" in M:
        r.append(_row(O, "DC offset", f"{M['dc']['dc_dbfs']:.0f} dBFS"))
    s = _g(M, "stability", "levels")
    if s:
        r.append(_row(O, "Stable at +3.1 dB SACD peak", "yes" if not any(v["saturated"] for v in s.values()) else "NO"))
    rt = M.get("rates")
    if rt:
        for k, v in rt.items():
            ex = f"SINAD {v['sinad_db']:.0f} dB, DR(A) {v['dr_a_db']:.0f} dB"
            if "ultrasonic" in v:
                dd = v["ultrasonic"].get("density_dbfs_hz", {})
                if "100000" in dd:
                    ex += f", ultrasonic {dd['100000']:.0f} dBFS/Hz at 100 kHz"
            r.append(_row(O, f"{k} (1 kHz, 0 dB SACD)", ex, v["sinad_db"], "higher"))
    f = M.get("reference_floor")
    if f:
        lim = f["chain"] if M.get("device_class", "A") == "A" else f["decoder_alone"]
        who = "reference modulator + decoder" if M.get("device_class", "A") == "A" else "reference decoder alone"
        r.append(_row("Reference floor", f"Reference floor ({who}, {rate_label(f['dsd_rate'])})",
                      f"THD+N {lim['thdn_db']:.1f} dB, DR(A) {lim['dr_a_db']:.0f} dB",
                      None, None, False,
                      f"modulator: {f['ntf']}. A device figure within {f['margin_db']:.0f} dB of this is marked and is limited by the measurement, not the device."))
    return r


def pct(v):
    return "under 0.0001 %" if v < 1e-4 else f"{v:.4f} %" if v < 0.1 else f"{v:.2f} %"


def rate_label(r):
    return f"DSD{int(r) // 44100}" if int(r) % 44100 == 0 else f"{r} Hz"


def summary_pairs(M):
    return [(x["label"], x["value"] + ("  (at the reference floor)" if x["flag"] else "")) for x in summary_rows(M)]


def flatten(d, prefix=""):
    out = []
    if isinstance(d, dict):
        for k, v in d.items():
            out += flatten(v, f"{prefix}{k}." if prefix or True else k)
    elif isinstance(d, (list, tuple)):
        if all(isinstance(x, (int, float)) for x in d) and len(d) <= 64:
            out.append((prefix[:-1], json.dumps(list(d))))
    else:
        out.append((prefix[:-1], d))
    return out


# ----------------------------------------------------------------------------- pages

CSS = """
:root{--bg:#fff;--fg:#1c2330;--mut:#5b6573;--card:#f5f7fa;--line:#dde2e8;--acc:#0072B2}
@media (prefers-color-scheme:dark){:root{--bg:#14181f;--fg:#e6e9ee;--mut:#9aa4b2;--card:#1d232d;--line:#2c3441;--acc:#56B4E9}}
body{background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif;max-width:980px;margin:0 auto;padding:16px}
h1{font-size:1.6rem;margin:.3em 0}h2{font-size:1.15rem;margin:1.4em 0 .4em}
.lead{color:var(--mut)}table{border-collapse:collapse;width:100%}
td,th{padding:.35em .6em;border-bottom:1px solid var(--line);text-align:left}td.v,th.v{text-align:right;font-variant-numeric:tabular-nums}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(420px,1fr));gap:14px}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:10px}
.card svg{width:100%;height:auto;background:#fff;border-radius:4px}
.take{margin:.4em 0 0;font-size:.95em}.det{color:var(--mut);font-size:.8em}
details{margin:.6em 0}summary{cursor:pointer;font-weight:600}.warn{color:#b3261e}
.hero{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:10px;margin:.8em 0}
.hero div{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:8px 10px}
.hero b{display:block;font-size:1.35rem;font-variant-numeric:tabular-nums}.hero span{color:var(--mut);font-size:.8em}
.hero .fl{border-color:#b3261e}.fl-tag{color:#b3261e;font-weight:600;font-size:.8em}
tr.sec td{background:var(--card);font-weight:600;color:var(--mut);font-size:.85em;text-transform:uppercase;letter-spacing:.04em}
td.h{color:var(--mut);font-size:.8em}.best{font-weight:700}
.legend{font-size:.88em;color:var(--mut);border-left:3px solid var(--line);padding-left:10px}
td{word-break:break-word}.card ul{margin:.3em 0;padding-left:1.2em}.card h2{margin-top:.2em}
.concl{border-left:4px solid var(--acc)}.concl li{margin:.35em 0}.concl li.c-pending{color:var(--mut)}
a{color:var(--acc)}footer{margin-top:2em;color:var(--mut);font-size:.85em}
"""


def _card(svg, take, detail=""):
    return (f'<div class="card">{svg}<p class="take">{html.escape(take)}</p>'
            f'{f"<p class=det>{html.escape(detail)}</p>" if detail else ""}</div>')


def _page(title, body, sub=""):
    return (f"<!doctype html><html lang=en-GB><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
            f"<title>{html.escape(title)}</title><style>{CSS}</style><body><h1>{html.escape(title)}</h1>"
            f"<p class=lead>{sub}</p>{body}<footer>Made with dsd-measure. Part of the "
            f"<a href='https://github.com/aclater/dsd-toolbox'>DSD Toolbox</a>.</footer></body></html>")


def device_plots(results, keyset="key"):
    """results: list of (name, result). Returns list of (key, svg, takeaway, detail) in display order."""
    names = [r[0] for r in results]
    fl0 = results[0][1]["metrics"].get("reference_floor")
    floor_db = None
    if fl0:
        k0 = results[0][1]["metrics"].get("device_class", "A")
        floor_db = (fl0["chain"] if k0 == "A" else fl0["decoder_alone"])["thdn_db"]
    col = {n: PALETTE[i % len(PALETTE)] for i, n in enumerate(names)}

    def ser(key):
        return [(n, col[n], r["plots"][key]) for n, r in results if key in r["plots"]]

    M0 = results[0][1]["metrics"]
    tk = lambda k: takeaway(k, M0) if len(results) == 1 else ""  # noqa: E731
    detail = {"fr": "31 stepped coherent tones at 0 dB SACD, relative to 1 kHz.",
              "noise": "Welch 8 averages, BH7 window, dBFS per Hz; plotted in 1/48-octave power buckets.",
              "levels": "Coherent 1 kHz, BH7 window, notch method 20 Hz-20 kHz.",
              "multitone": "32 tones, 17.6 Hz-21.4 kHz, crest 13.3 dB, peak at 0 dB SACD.",
              "spectrum_1k": "Coherent 1 kHz at 0 dB SACD (-6.02 dBFS), BH7 window; the tone reads at its level, noise per 1.35 Hz bin.",
              "impulse": "Averaged response to 8 impulses at 0 dB SACD, raw output samples."}
    items = []
    if ser("fr"):
        items.append(("key", "fr", plot_fr(ser("fr")), tk("fr")))
    if ser("impulse"):
        items.append(("key", "impulse", plot_impulse(ser("impulse")), tk("impulse")))
    if ser("noise"):
        items.append(("key", "noise", plot_noise(ser("noise")), tk("noise")))
    if ser("levels"):
        items.append(("key", "levels", plot_levels(ser("levels"), floor_db), tk("levels")))
    if len(results) == 1:
        r = results[0][1]["plots"]
        if "multitone" in r:
            items.append(("key", "multitone", plot_spectrum(r["multitone"], "32-tone multitone", 22050,
                                                            (r["multitone"]["tone_f"], r["multitone"]["tone_db"]), (-150, -20)),
                          tk("multitone")))
        if "spectrum_1k" in r:
            items.append(("key", "spectrum_1k", plot_spectrum(r["spectrum_1k"], "1 kHz tone, 0 dB SACD", None), tk("spectrum_1k")))
    if ser("filter"):
        items.append(("key", "filter", plot_filter(ser("filter")), tk("filter")))
    # details
    if ser("step"):
        items.append(("detail", "step", plot_impulse(ser("step"), step=True), tk("step")))
    if ser("group_delay"):
        items.append(("detail", "group_delay", plot_group_delay(ser("group_delay")), tk("group_delay")))
    if ser("thdn_freq"):
        items.append(("detail", "thdn_freq", plot_thdn_freq(ser("thdn_freq"), floor_db), tk("thdn_freq")))
    if ser("levels"):
        items.append(("detail", "linearity", plot_linearity(ser("levels")), tk("linearity")))
    if ser("imd_sweep"):
        items.append(("detail", "imd_sweep", plot_imd_sweep(ser("imd_sweep")), tk("imd_sweep")))
    if ser("alias"):
        items.append(("detail", "alias", plot_alias(ser("alias")), tk("alias")))
    if ser("overload"):
        items.append(("detail", "overload", plot_overload(ser("overload")), tk("overload")))
    if len(results) == 1:
        r = results[0][1]["plots"]
        for k, ttl in (("imd_smpte", "SMPTE IMD: 60 Hz + 7 kHz"), ("imd_ccif", "CCIF IMD: 19 + 20 kHz"),
                       ("tone_15k", "15 kHz tone at -12 dBFS")):
            if k in r:
                items.append(("detail", k, plot_spectrum(r[k], ttl, None, ylim=(-160, 0)), tk(k)))
        if "jtest" in r:
            items.append(("detail", "jtest", plot_spectrum(r["jtest"], "J-Test, 9 to 13 kHz", 13000, ylim=(-160, -40), fmin=9000), tk("jtest")))
        if "noise_wide" in r:
            fig, ax = plt.subplots()
            d = r["noise_wide"]
            ax.plot(d["f"], d["dbfs_hz"], color=PALETTE[0], lw=1)
            _logx(ax, 1000, None)
            ax.set_ylim(-190, -40)
            ax.set_ylabel("dBFS per Hz")
            ax.set_title(f"Ultrasonic noise ({d.get('decode_rate', 705600) / 1000:g} kHz decode)")
            items.append(("detail", "noise_wide", _svg(fig), tk("noise_wide")))
        if "density" in r:
            items.append(("detail", "density", plot_density(r["density"]), tk("density")))
    return [(k, key, svg, take, detail.get(key, "")) for k, key, svg, take in items]


LEGEND = ("Levels: dBFS is relative to PCM full scale. 0 dB SACD is the reference tone level, 50 % modulation, "
          "-6.02 dBFS; noise in dBFS is referred to the rms of a full-scale sine (AES17, ASR). Distortion and noise figures "
          "are in dB below the 1 kHz tone unless they say dBFS. Bandwidth "
          "20 Hz to 20 kHz, unweighted unless marked A-weighted. SINAD is THD+N turned positive. Because the tone is "
          "6 dB below full scale, a noise-limited device would read about 6 dB better at full scale; compare reports "
          "made at the same level.")


def _hero(M):
    rows = {x["label"]: x for x in summary_rows(M)}

    def pick(prefix):
        return next((v for k, v in rows.items() if k.startswith(prefix)), None)

    cards = []
    for lab, pre in (("SINAD", "SINAD, 1 kHz"), ("Dynamic range (A)", "Dynamic range"), ("Noise (A)", "Noise 20 Hz")):
        x = pick(pre)
        if x:
            cards.append((lab, x["value"], x["flag"]))
    ft, fs_ = M.get("impulse"), M.get("filter_summary") or {}
    if ft and ft.get("measurable", True):
        cards.append(("Filter", f"{ft['filter_type']}, -3 dB at {_hz(fs_.get('minus_3_db_hz'))}", False))
    x = pick("Ultrasonic noise peak")
    if x:
        cards.append(("Ultrasonic noise peak", x["value"], False))
    elif pick("Noise 20-40"):
        cards.append(("Noise 20-40 kHz", pick("Noise 20-40")["value"], False))
    return "".join(f'<div class="{"fl" if fl else ""}"><span>{html.escape(lab)}</span><b>{html.escape(v)}</b>'
                   f'{"<span class=fl-tag>at the reference floor</span>" if fl else ""}</div>' for lab, v, fl in cards)


def _table(M):
    out, sec = [], None
    for x in summary_rows(M):
        if x["section"] != sec:
            sec = x["section"]
            out.append(f'<tr class=sec><td colspan=2>{html.escape(sec)}</td></tr>')
        tag = ' <span class=fl-tag>at the reference floor</span>' if x["flag"] else ""
        hint = f'<br><span class=h>{html.escape(x["hint"])}</span>' if x["hint"] else ""
        out.append(f'<tr><td>{html.escape(x["label"])}{hint}</td><td class=v>{html.escape(x["value"])}{tag}</td></tr>')
    return "".join(out)


def _methods(meta):
    ps = meta.get("profile_settings", {})
    rows = [("Profile", f"{meta['profile']}: " + ", ".join(f"{k} {v}" for k, v in ps.items())),
            ("Analysis", "64-bit float; 2^18-point FFT at 352.8 kHz bin spacing, 7-term Blackman-Harris window, coherent tones, "
                         "notch method for THD+N, 20 Hz to 20 kHz, A-weighting per IEC 61672"),
            ("Reference chain", f"version {meta['reference_chain']}: the stability-guarded single-bit modulator, then a long linear-phase FIR decoder (160 dB stopband)"),
            ("Reference modulator designs used", json.dumps(meta.get("reference_modulator_designs", {}))),
            ("Full definitions", "docs/footprint.md in the dsd-measure repository")]
    return "<table>" + "".join(f"<tr><td>{html.escape(a)}</td><td>{html.escape(b)}</td></tr>" for a, b in rows) + "</table>"


def _notes_html(notes):
    if not notes:
        return ""
    return "<h2>Notes</h2><div class=card><ul>" + "".join(f"<li>{html.escape(n)}</li>" for n in notes) + "</ul></div>"


def _notes_md(notes):
    return ["", "## Notes", ""] + [f"- {n}" for n in notes] if notes else []


def _measured_html(ms):
    """The "What was measured" block: ``ms`` is a list of ``meta["measured"]`` (one device, or all in a comparison)."""
    from .plan import measured_details, measured_summary
    if len(ms) == 1:
        lines = measured_summary(ms[0])
    else:
        m0 = ms[0]
        lines = [("Devices", "; ".join(f"{m['device']['name']} (class {m['device']['class']}, {m['device']['adapter']})" for m in ms)
                  + ". Every device was fed the identical signals."),
                 ("Source signals", "Synthetic and deterministic test signals made by the toolkit (not music), the same for every device."),
                 ("Reference chain", measured_summary(m0)[2][1]),
                 ("Profile and date", measured_summary(m0)[3][1])]
    body = "".join(f"<li><b>{html.escape(a)}:</b> {html.escape(b)}</li>" for a, b in lines)
    det = ""
    for m in ms:
        rows = "".join(f"<tr><td>{html.escape(a)}</td><td>{html.escape(str(b))}</td></tr>" for a, b in measured_details(m))
        head = f"<p><b>{html.escape(m['device']['name'])}</b></p>" if len(ms) > 1 else ""
        det += head + f"<table>{rows}</table>"
    return (f"<div class=card><h2>What was measured</h2><ul>{body}</ul>"
            f"<details><summary>Details: rates, word lengths, signal file hashes, versions</summary>{det}</details></div>")


def _measured_md(ms):
    from .plan import measured_summary
    lines = measured_summary(ms[0]) if len(ms) == 1 else [
        ("Devices", "; ".join(m["device"]["name"] for m in ms) + ". Every device was fed the identical signals."),
        measured_summary(ms[0])[1], measured_summary(ms[0])[2], measured_summary(ms[0])[3]]
    return ["## What was measured", ""] + [f"- **{a}:** {b}" for a, b in lines] + [""]


# ----------------------------------------------------------------------------- conclusions

def _conclusions_html(cs):
    """The "Conclusions" card: one bullet per conclusion, then the evidence and thresholds, collapsed."""
    from .conclusions import DOC_URL, SCOPE, THRESHOLDS
    if not cs:
        return ""
    lis = "".join(f"<li class='c-{html.escape(c['verdict'])}'>{html.escape(c['text'])}</li>" for c in cs)
    rows = ""
    for c in cs:
        for e in c["evidence"]:
            who = f"{html.escape(e['device'])}: " if e.get("device") else ""
            rows += (f"<tr><td>{html.escape(c['label'])}</td><td>{who}{html.escape(e['label'])}</td>"
                     f"<td class=v>{html.escape(e['value'])}</td><td class=h>{html.escape(e['metric'])}</td></tr>")
    used = sorted({t for c in cs for t in c["thresholds"]})
    th = ""
    for t in used:
        d = THRESHOLDS[t]
        val = "" if d["value"] is None else f" = {d['value']:g} {html.escape(d['unit'])}"
        th += f"<li><b>{html.escape(t)}</b>{val}: {html.escape(d['meaning'])}</li>"
    return (f"<div class='card concl'><h2>Conclusions</h2><ul>{lis}</ul><p class=det>{html.escape(SCOPE)} "
            f"<a href='{DOC_URL}'>How the conclusions are drawn, with thresholds and sources</a>.</p>"
            f"<details><summary>Evidence: the figures and thresholds behind each conclusion</summary>"
            f"<table><tr><th>Conclusion</th><th>Figure</th><th class=v>Value</th><th>Key in results.json</th></tr>{rows}</table>"
            f"<ul>{th}</ul></details></div>")


def _conclusions_md(cs):
    from .conclusions import DOC_URL, SCOPE
    if not cs:
        return []
    return ["## Conclusions", ""] + [f"- {c['text']}" for c in cs] + ["", f"{SCOPE} [How the conclusions are drawn]({DOC_URL}).", ""]


def write_device_report(outdir, name, result, meta):
    out = Path(outdir)
    (out / "plots").mkdir(parents=True, exist_ok=True)
    M = result["metrics"]
    plots = device_plots([(name, result)])
    key = "".join(_card(s, t, d) for kind, _, s, t, d in plots if kind == "key")
    det = "".join(_card(s, t, d) for kind, _, s, t, d in plots if kind == "detail")
    nr = "".join(f"<li><b>{html.escape(k)}</b>: {html.escape(v)}</li>" for k, v in result["not_run"].items())
    mm = [meta["measured"]] if meta.get("measured") else []
    from .conclusions import device_conclusions
    concl = device_conclusions(M, meta.get("device"))
    body = (f"{_conclusions_html(concl)}{_measured_html(mm) if mm else ''}<div class=hero>{_hero(M)}</div><p class=legend>{html.escape(LEGEND)}</p>"
            f"<h2>Summary</h2><div class=card><table>{_table(M)}</table></div>"
            f"{_notes_html(result.get('notes'))}"
            f"<h2>Key plots</h2><div class=grid>{key}</div>"
            f"<details><summary>More plots</summary><div class=grid>{det}</div></details>"
            f"<details><summary>Method and settings</summary>{_methods(meta)}</details>"
            f"<details><summary>Not run, and why</summary><ul>{nr or '<li>Everything ran.</li>'}</ul></details>"
            f"<details><summary>Provenance</summary><pre>{html.escape(json.dumps(meta, indent=1, default=str))}</pre></details>"
            f"<p>Raw numbers: <a href=results.csv>results.csv</a>, <a href=results.json>results.json</a>, "
            f"<a href=provenance.json>provenance.json</a>. Plots as files are in <code>plots/</code>.</p>")
    sub = (f"Class {meta['device']['class']} ({'DSD to PCM converter' if meta['device']['class'] == 'A' else 'PCM to DSD modulator'}); "
           f"{rate_label(meta['device'].get('dsd_rate', 2822400))}; profile {meta['profile']}; reference chain {meta['reference_chain']}.")
    (out / "index.html").write_text(_page(f"{name}: measurement report", body, sub))
    for _kind, key_, svg, *_ in plots:
        (out / "plots" / f"{key_}.svg").write_text(svg)
    (out / "results.json").write_text(json.dumps({"conclusions": concl, "metrics": M, "not_run": result["not_run"], "notes": result["notes"]}, indent=1, default=str))
    (out / "provenance.json").write_text(json.dumps(meta, indent=1, default=str))
    with open(out / "results.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["metric", "value"])
        for k, v in flatten(M):
            w.writerow([k, v])
    md = [f"# {name}: measurement report", "", sub, ""] + _conclusions_md(concl) + (_measured_md(mm) if mm else []) + [f"> {LEGEND}", "", "| Metric | Value |", "|---|---|"]
    md += [f"| {a} | {b} |" for a, b in summary_pairs(M)]
    md += _notes_md(result.get("notes"))
    md += ["", "Plots: see `plots/`. Raw numbers: `results.csv`, `results.json`.", ""]
    for _kind, key_, _, take, _ in plots:
        if take:
            md.append(f"- **{key_}**: {take}")
    (out / "index.md").write_text("\n".join(md) + "\n")


_FILTER_LABELS = ("Filter type", "Ringing before", "-0.1 dB", "Stopband", "Group delay", "Worst alias image")


def _absent(klass, label):
    """What a comparison cell says when a device has no such row: a modulator's filter rows are the reference decoder's."""
    return "not shown (a modulator's filter is the reference decoder's)" if klass == "B" and label.startswith(_FILTER_LABELS) else "not run"


def write_comparison(outdir, results, meta):
    out = Path(outdir)
    klass = {n: r["metrics"].get("device_class", "A") for n, r in results}
    (out / "plots").mkdir(parents=True, exist_ok=True)
    names = [n for n, _ in results]
    rows_by = {n: {x["label"]: x for x in summary_rows(r["metrics"])} for n, r in results}
    labels, secs = [], {}
    for n in names:
        for k, x in rows_by[n].items():
            if k not in secs:
                labels.append(k)
                secs[k] = x["section"]
    trs, sec = [], None
    for k in labels:
        if secs[k] != sec:
            sec = secs[k]
            trs.append(f"<tr class=sec><td colspan={len(names) + 1}>{html.escape(sec)}</td></tr>")
        nums = [rows_by[n][k]["num"] for n in names if k in rows_by[n] and rows_by[n][k]["num"] is not None]
        better = next((rows_by[n][k]["better"] for n in names if k in rows_by[n]), None)
        best = (max(nums) if better == "higher" else min(nums)) if nums and better and len(nums) > 1 else None
        cells = []
        for n in names:
            x = rows_by[n].get(k)
            if not x:
                cells.append(f"<td class=v>{html.escape(_absent(klass[n], k))}</td>")
                continue
            cls = "v best" if best is not None and x["num"] == best else "v"
            tag = ' <span class=fl-tag>floor</span>' if x["flag"] else ""
            cells.append(f"<td class='{cls}'>{html.escape(x['value'])}{tag}</td>")
        trs.append(f"<tr><td>{html.escape(k)}</td>{''.join(cells)}</tr>")
    head = "".join(f"<th class=v>{html.escape(n)}</th>" for n in names)
    plots = device_plots(results)
    cards = "".join(_card(s, "", d) for kind, _, s, t, d in plots if kind == "key")
    det = "".join(_card(s, "", d) for kind, _, s, t, d in plots if kind == "detail")
    mm = meta.get("measured") or []
    from .conclusions import comparison_conclusions
    devs = [m.get("device") for m in mm] if len(mm) == len(results) else [None] * len(results)
    concl = comparison_conclusions([((d or {}).get("name") or n, r["metrics"], d) for (n, r), d in zip(results, devs, strict=True)])
    (out / "results.json").write_text(json.dumps({"devices": names, "conclusions": concl}, indent=1, default=str))
    body = (f"{_conclusions_html(concl)}{_measured_html(mm) if mm else ''}<p class=legend>{html.escape(LEGEND)} Bold marks the better figure in a row; 'floor' marks a figure within 6 dB of that "
            f"device's reference floor, so it may be limited by the measurement.</p>"
            f"<h2>Summary</h2><div class=card><table><tr><th>Metric</th>{head}</tr>{''.join(trs)}</table></div>"
            f"<h2>Overlays</h2><div class=grid>{cards}</div>"
            f"{_notes_html([f'{n}: {t}' for n, r in results for t in r.get('notes', [])])}"
            f"<details><summary>More overlays</summary><div class=grid>{det}</div></details>"
            f"<p>Per-device reports: " + ", ".join(f"<a href='../{html.escape(n)}/index.html'>{html.escape(n)}</a>" for n in names)
            + ". Raw numbers: <a href=results.csv>results.csv</a>; conclusions as data: <a href=results.json>results.json</a>.</p>")
    (out / "index.html").write_text(_page("Comparison report", body, f"{len(names)} devices; profile {meta['profile']}."))
    for _kind, key_, svg, *_ in plots:
        (out / "plots" / f"{key_}.svg").write_text(svg)
    with open(out / "results.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["device", "metric", "value"])
        for n, r in results:
            for k, v in flatten(r["metrics"]):
                w.writerow([n, k, v])
    md = ["# Comparison report", ""] + _conclusions_md(concl) + (_measured_md(mm) if mm else []) + [f"> {LEGEND}", "", "| Metric | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]
    for k in labels:
        md.append(f"| {k} | " + " | ".join((rows_by[n][k]["value"] + (" (floor)" if rows_by[n][k]["flag"] else "")) if k in rows_by[n] else _absent(klass[n], k) for n in names) + " |")
    md += _notes_md([f"{n}: {t}" for n, r in results for t in r.get("notes", [])])
    (out / "index.md").write_text("\n".join(md) + "\n")
