"""The null-test report: one screen of numbers and a verdict, three plots, and what was compared."""

import csv
import html
import json
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from ..report import PALETTE, _card, _logx, _page, _svg  # noqa: E402
from .verdict import BASIS, SOURCES, TIERS, inband_depth, verdict  # noqa: E402

_TIER_NOTE = re.compile(r"^depth band [^;:,]*[;:,]?\s*")


def _worst(res):
    chs = res["channels"]
    return min(chs, key=lambda c: c["null_depth_db"])


def plot_spectrum(ch, fc):
    fig, ax = plt.subplots()
    f = [b["centre_hz"] for b in ch["bands"]]
    ax.plot(f, [b["music_dbfs"] for b in ch["bands"]], "-o", ms=3, color=PALETTE[0], label="music (device A)")
    ax.plot(f, [max(b["diff_dbfs"], -250) for b in ch["bands"]], "-o", ms=3, color=PALETTE[3], label="difference (A minus B)")
    ax.axvline(20000, color="#999", lw=0.8, ls=":")
    _logx(ax, 20, None)
    ax.set_ylabel("Level in third-octave band (dBFS)")
    lo = min(-200, min(max(b["diff_dbfs"], -250) for b in ch["bands"]) - 5)
    ax.set_ylim(max(lo, -250), 0)
    ax.set_title("Music and difference by frequency")
    ax.legend(loc="upper right")
    return _svg(fig)


def plot_time(ch):
    fig, ax = plt.subplots()
    t = [s["t_s"] for s in ch["seconds"]]
    ax.plot(t, [s["music_dbfs"] for s in ch["seconds"]], color=PALETTE[0], label="music (device A)")
    ax.plot(t, [max(s["diff_dbfs"], -250) for s in ch["seconds"]], color=PALETTE[3], label="difference (A minus B)")
    ax.set_xlabel("Time from the start of the analysed range (s)")
    ax.set_ylabel("RMS level per second (dBFS)")
    ax.set_title("Music and difference over time")
    ax.legend(loc="upper right")
    return _svg(fig)


def plot_depth(ch):
    fig, ax = plt.subplots()
    f = [b["centre_hz"] for b in ch["bands"]]
    d = [min(b["depth_db"], 300) for b in ch["bands"]]
    ax.plot(f, d, "-o", ms=3, color=PALETTE[2])
    for y, lab in ((100, "100 dB"), (60, "60 dB"), (40, "40 dB")):
        ax.axhline(y, color="#999", lw=0.8, ls="--")
        ax.text(21, y + 1.5, lab, fontsize=7, color="#666")
    ax.axvline(20000, color="#999", lw=0.8, ls=":")
    _logx(ax, 20, None)
    ax.set_ylabel("Null depth (dB below the music in the band)")
    ax.set_ylim(0, max(120, min(max(d) + 5, 320)))
    ax.set_title("How far below the music, by frequency")
    return _svg(fig)


def _fmt(x, nd=1):
    return "n/a" if x is None else f"{x:.{nd}f}"


def _depth_txt(d):
    return "identical" if d >= 300 else f"{d:.1f} dB"


def _summary_rows(ch, v):
    gain = -ch["gain_db"]
    return [
        ("Null depth, 20 Hz to 20 kHz (music RMS minus difference RMS)", _depth_txt(v["depth_db"])),
        ("Null depth, full analysed band", _depth_txt(ch["null_depth_db"])),
        ("Difference RMS, 20 Hz to 20 kHz", f"{_fmt(ch['diff_rms_audio_dbfs'])} dBFS"),
        ("Difference RMS, full analysed band", f"{_fmt(ch['diff_rms_dbfs'])} dBFS"),
        ("Difference peak", f"{_fmt(ch['diff_peak_dbfs'])} dBFS"),
        ("Music RMS (20 Hz to 20 kHz), peak", f"{_fmt(ch['music_rms_audio_dbfs'])} dBFS, {_fmt(ch['music_peak_dbfs'])} dBFS"),
        ("Correlation, 20 Hz to 20 kHz (1 minus r)", f"{ch['correlation']:.10f} ({ch['one_minus_correlation']:.2e})"),
        ("Delay of B behind A", f"{ch['delay_samples']:.4f} samples ({ch['delay_us']:.2f} µs); spread over segments {ch['delay_spread_samples']:.1e}"),
        ("Level of B relative to A", f"{gain:+.4f} dB"),
        ("Polarity of B", "inverted (flipped for the subtraction)" if ch["polarity_inverted"] else "same as A"),
    ]


def _table(rows):
    return "<table>" + "".join(f"<tr><td>{html.escape(a)}</td><td class=v>{html.escape(b)}</td></tr>" for a, b in rows) + "</table>"


def _compared(run):
    s = run["source"]
    rows = [("Source file", f"{s['name']} ({s['format']}, DSD{s['dsd_rate'] // 44100}, {s['channels']} channels, {s['seconds']:.1f} s)"),
            ("Source SHA-256", s["sha256"])]
    for i, d in enumerate(run["devices"]):
        role = "A (reference for the subtraction)" if i == 0 else f"B{i if len(run['devices']) > 2 else ''}"
        dd = d["describe"]
        cmd = dd.get("command") or f"built-in reference decoder, {dd.get('out_rate')} Hz output"
        rows.append((f"Device {role}", f"{dd['name']}: {cmd}"))
        rows.append((f"  output of {dd['name']}", f"{d['rate']} Hz" + (f"; output SHA-256 {d['info']['output_sha256']}" if "output_sha256" in d["info"] else "")
                     + (f"; {d['info']['filter']}" if "filter" in d["info"] else "")))
    p0 = run["pairs"][0]["result"]
    o = run["options"]
    rows.append(("Common rate", f"{p0['common_rate']} Hz" + ("; resampled: " + ", ".join(f"{k} from {a} Hz" for k, (a, _) in p0["resampled"].items())
                 if p0["resampled"] else "; no resampling")))
    rows.append(("Resampler", "Kaiser polyphase, 160 dB stopband, flat to 0.45 x the lower rate" if p0["resampled"] else "not used"))
    rows.append(("Analysed range", f"{p0['range_s'][0]:.2f} s to {p0['range_s'][1]:.2f} s (trim {o['trim_start']} s at the start, {o['trim_end']} s at the end)"))
    rows.append(("Alignment", f"delay: cross-correlation then sub-sample refinement; polarity: {o['polarity']}; gain: {o['gain']} (least squares)"))
    rows.append(("Analysis", f"third-octave bands up to {p0['analysis_band_hz'] / 1000:.1f} kHz from a {p0['nfft']}-point Hann spectrum ({p0['bin_hz']:.2f} Hz bins)"))
    rows.append(("Command", run["command"]))
    return _table(rows)


def write_report(outdir, run):
    out = Path(outdir)
    (out / "plots").mkdir(parents=True, exist_ok=True)
    fc = run["pairs"][0]["result"]["common_rate"]
    a_name = run["devices"][0]["describe"]["name"]
    sections, md = [], [f"# Null test: {run['source']['name']}", ""]
    md += [f"**Result: {(p['b'] + ' against ' + a_name + ': ') if len(run['pairs']) > 1 else ''}{p['verdict']['headline']}**" for p in run["pairs"]] + [""]
    srows = []
    for i, p in enumerate(run["pairs"]):
        res, v = p["result"], p["verdict"]
        ch = _worst(res)
        tag = f"{i + 1}"
        for name, svg in (("spectrum", plot_spectrum(ch, fc)), ("time", plot_time(ch)), ("depth", plot_depth(ch))):
            (out / "plots" / f"{name}-{tag}.svg").write_text(svg)
        cards = "".join([
            _card(plot_spectrum(ch, fc), "Where the difference sits against the music. The dotted line marks 20 kHz; bands above it are ultrasonic and are not part of the verdict."),
            _card(plot_time(ch), "Whether the difference follows the music or is steady. A difference that rises in loud passages scales with the music; a flat one is a noise floor."),
            _card(plot_depth(ch), "The same two lines as a ratio. Dashed lines mark the depth band edges."),
        ])
        per_ch = "<table><tr><th>Channel</th><th class=v>Null depth, 20 Hz to 20 kHz</th><th class=v>Null depth, full analysed band</th><th class=v>Diff RMS (dBFS)</th><th class=v>Diff peak (dBFS)</th><th class=v>Delay (samples)</th><th class=v>Level B vs A (dB)</th></tr>" + "".join(
            f"<tr><td>{c['channel']}</td><td class=v>{_depth_txt(inband_depth(c))}</td><td class=v>{_depth_txt(c['null_depth_db'])}</td><td class=v>{c['diff_rms_dbfs']:.1f}</td><td class=v>{c['diff_peak_dbfs']:.1f}</td>"
            f"<td class=v>{c['delay_samples']:.4f}</td><td class=v>{-c['gain_db']:+.4f}</td></tr>" for c in res["channels"]) + "</table>"
        det = "".join(f"<li>{html.escape(x)}</li>" for x in v["details"])
        wav = f"<p>Difference signal: <a href='{html.escape(p['diff_wav'])}'>{html.escape(p['diff_wav'])}</a> (32-bit float WAV at {fc} Hz; the level is {run['options']['diff_gain_db']:+g} dB from true, so turn the volume down before playing it).</p>" if p.get("diff_wav") else ""
        sections.append(f"<h2>{html.escape(p['b'])} against {html.escape(a_name)}</h2><p><b>{html.escape(v['headline'])}</b></p>"
                        f"{f'<ul>{det}</ul>' if det else ''}<div class=card>{_table(_summary_rows(ch, v))}</div>"
                        f"<div class=card>{per_ch}</div><div class=grid>{cards}</div>{wav}")
        srows.append((p["b"], v, ch))
        md += [f"## {p['b']} against {a_name}", "", f"**{v['headline']}**", ""] + [f"- {x}" for x in v["details"]] + ["", "| Measure | Value |", "|---|---|"]
        md += [f"| {a} | {b} |" for a, b in _summary_rows(ch, v)] + [""]
    hero = "".join(f"<div><span>{html.escape(b)} vs {html.escape(a_name)}</span><b>{_depth_txt(v['depth_db'])}</b><span>null depth</span></div>" for b, v, _ in srows)
    results = [(f"{p['b']} against {a_name}: " if len(srows) > 1 else "") + p["verdict"]["headline"] for p in run["pairs"]]
    head = "".join(f"<p class=result>Result: {html.escape(r)}</p>" for r in results)
    tiers = "".join(f"<tr><td>{'identical' if lo >= 300 else (f'{lo:g} dB or more' if lo > -1e8 else 'under 20 dB')}</td><td>{html.escape(_TIER_NOTE.sub('', t))}</td></tr>" for lo, _, t in TIERS)
    src = "".join(f"<li><a href='{u}'>{html.escape(n)}</a></li>" for n, u in SOURCES)
    body = (f"<div class=hero>{hero}</div>{head}{''.join(sections)}"
            f"<h2>What was compared</h2><div class=card>{_compared(run)}</div>"
            f"<details><summary>How to read the depth band</summary><p>Null depth is how far below the music the difference is: the music's RMS level minus the RMS level of "
            f"A minus B after alignment and level matching.</p><table>{tiers}</table><p>{html.escape(BASIS)}</p><ul>{src}</ul></details>"
            f"<p class=legend>This is a test on your own music, separate from the synthetic measurements of the footprint: it says how much two decoders differ on this recording; it does not say which is right or whether the difference is heard. "
            f"A difference may be a filter, a level or a delay choice rather than an error.</p>"
            f"<p>Raw numbers: <a href=results.json>results.json</a>, <a href=bands.csv>bands.csv</a>, <a href=seconds.csv>seconds.csv</a>, <a href=provenance.json>provenance.json</a>.</p>")
    sub = f"Null test of {len(run['devices'])} decoders on {html.escape(run['source']['name'])}; common rate {fc} Hz."
    (out / "index.html").write_text(_page("Null test report", body, sub))
    md += ["## What was compared", ""] + [f"- {k}: {v}" for k, v in _rows_plain(run)] + ["", "Depth bands and sources: see `index.html`.", ""]
    (out / "index.md").write_text("\n".join(md) + "\n")
    (out / "results.json").write_text(json.dumps(run, indent=1, default=float))
    (out / "provenance.json").write_text(json.dumps({k: run[k] for k in ("source", "devices", "options", "command", "versions")}, indent=1, default=float))
    with open(out / "bands.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["device_b", "channel", "centre_hz", "low_hz", "high_hz", "music_dbfs", "diff_dbfs", "depth_db", "ultrasonic"])
        for p in run["pairs"]:
            for c in p["result"]["channels"]:
                for b in c["bands"]:
                    w.writerow([p["b"], c["channel"], b["centre_hz"], b["low_hz"], b["high_hz"], f"{b['music_dbfs']:.3f}", f"{b['diff_dbfs']:.3f}", f"{b['depth_db']:.3f}", b["ultrasonic"]])
    with open(out / "seconds.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["device_b", "channel", "t_s", "music_dbfs", "diff_dbfs", "depth_db"])
        for p in run["pairs"]:
            for c in p["result"]["channels"]:
                for s in c["seconds"]:
                    w.writerow([p["b"], c["channel"], s["t_s"], f"{s['music_dbfs']:.3f}", f"{s['diff_dbfs']:.3f}", f"{s['depth_db']:.3f}"])


def _rows_plain(run):
    s = run["source"]
    rows = [("Source", f"{s['name']}, SHA-256 {s['sha256']}")]
    for d in run["devices"]:
        dd = d["describe"]
        rows.append((f"Device {dd['name']}", f"{dd.get('command') or 'reference decoder'}; output {d['rate']} Hz"))
    rows.append(("Command", run["command"]))
    return rows


__all__ = ["write_report", "verdict"]
