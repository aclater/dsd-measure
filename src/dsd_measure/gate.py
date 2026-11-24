"""Release gate: is a new version of a converter worse than the previous one?

``dsd-measure gate OLD NEW`` compares two device report folders (or two ``results.json`` files)
made by the same dsd-measure version, suite and profile, figure by figure. It judges the
measured figures, not the bytes of the output: a converter may change its output and pass, as
long as no figure is worse than before by more than the repeatability of the measurement.

Repeatability. A figure read at or near the noise floor moves a little from one noise
realisation to the next. ``GATE_METRICS`` carries, for each figure, the largest difference
between two runs that noise alone explains (three standard deviations of a difference, from the
ensemble in docs/accuracy.md, "Repeatability"). A change inside it is "same"; outside it the
figure is "better" or "worse". Any "worse" (or a figure that is no longer measured) fails.
"""

import json
import math
from pathlib import Path

#: (label, path in ``metrics``, which way is better, repeatability in dB)
#: "higher" / "lower": more / less is better; "abs": closer to zero is better.
GATE_METRICS = (
    ("SINAD, 1 kHz at 0 dB SACD", ("tone_0dbsacd", "sinad_db"), "higher", 0.6),
    ("THD, 1 kHz at 0 dB SACD", ("tone_0dbsacd", "thd_db"), "lower", 1.5),
    ("THD+N A-weighted, 1 kHz at 0 dB SACD", ("tone_0dbsacd", "thdn_a_db"), "lower", 0.6),
    ("SINAD at the peak level", ("tone_peak", "sinad_db"), "higher", 0.6),
    ("Dynamic range, A-weighted", ("dynamic_range", "dr_a_db"), "higher", 0.5),
    ("Noise 20 Hz-20 kHz, A-weighted", ("noise", "a_weighted_dbfs"), "lower", 0.2),
    ("Noise 20 Hz-20 kHz", ("noise", "unweighted_dbfs"), "lower", 0.2),
    ("Gain error at 1 kHz", ("gain_error_db",), "abs", 0.001),
    # one step of the level ladder (6 dB at the quick and gate profiles)
    ("Lowest level within 0.5 dB", ("linearity", "lowest_level_within_0p5_db"), "lower", 6.1),
    ("Worst alias image", ("alias_tones", "worst_image_db"), "lower", 6.0),
)


def load_metrics(path):
    """The ``metrics`` table of a device report folder or of a ``results.json`` file."""
    p = Path(path)
    if p.is_dir():
        p = p / "results.json"
    if not p.is_file():
        raise FileNotFoundError(f"{p}: no results.json here (give a device report folder, for example report/NAME)")
    data = json.loads(p.read_text())
    if "metrics" not in data:
        raise ValueError(f"{p} is not a device results file (a comparison folder has no single device: give report/NAME)")
    return data["metrics"]


def _get(m, path):
    for k in path:
        if not isinstance(m, dict) or k not in m:
            return None
        m = m[k]
    if not isinstance(m, (int, float)) or isinstance(m, bool) or not math.isfinite(m):
        return None  # NaN and infinity are "not measured"
    return float(m)


def compare(old, new, scale=1.0):
    """Rows ``{"label", "old", "new", "change", "repeatability", "verdict"}`` for two ``metrics`` tables.

    ``verdict`` is "same", "better", "worse", "not measured" (in neither), "new" (only in the new
    one) or "missing" (measured before, not now). A value that is not a finite number (NaN,
    infinity) counts as not measured. ``scale`` multiplies every repeatability.
    """
    rows = []
    for label, path, better, rep in GATE_METRICS:
        a, b = _get(old, path), _get(new, path)
        tol = rep * scale
        row = {"label": label, "key": ".".join(path), "old": a, "new": b, "change": None, "repeatability": tol}
        if a is None and b is None:
            row["verdict"] = "not measured"
        elif a is None:
            row["verdict"] = "new"
        elif b is None:
            row["verdict"] = "missing"
        else:
            row["change"] = b - a
            gain = {"higher": b - a, "lower": a - b, "abs": abs(a) - abs(b)}[better]  # > 0: the new one is better
            row["verdict"] = "better" if gain > tol else "worse" if gain < -tol else "same"
        rows.append(row)
    return rows


def compared(rows):
    """True when at least one figure was measured in both results."""
    return any(r["verdict"] in ("better", "same", "worse") for r in rows)


def passed(rows):
    return compared(rows) and not any(r["verdict"] in ("worse", "missing") for r in rows)


def _num(v):
    return "-" if v is None else f"{v:.3f}"


def text(rows, old_name="old", new_name="new"):
    """The comparison as a plain table with a one-line verdict."""
    head = ("Figure", old_name, new_name, "change", "repeatability", "verdict")
    body = [(r["label"], _num(r["old"]), _num(r["new"]), "-" if r["change"] is None else f"{r['change']:+.3f}",
             f"{r['repeatability']:g}", r["verdict"]) for r in rows]
    w = [max(len(str(x[i])) for x in [head] + body) for i in range(len(head))]
    lines = ["  ".join(str(c).ljust(w[i]) if i == 0 else str(c).rjust(w[i]) for i, c in enumerate(row)) for row in [head] + body]
    worse = [r["label"] for r in rows if r["verdict"] == "worse"]
    gone = [r["label"] for r in rows if r["verdict"] == "missing"]
    better = [r["label"] for r in rows if r["verdict"] == "better"]
    if not compared(rows) and not gone:
        end = "NOTHING COMPARED: no figure was measured in both results"
    elif worse or gone:
        end = "FAIL: " + ". ".join((["worse beyond repeatability: " + "; ".join(worse)] if worse else [])
                                   + (["no longer measured: " + "; ".join(gone)] if gone else []))
    else:
        end = "PASS: no figure is worse beyond repeatability" + (" (better: " + "; ".join(better) + ")" if better else "")
    return "\n".join(lines + ["", end])


def check_same_conditions(old, new):
    """Reasons why two results cannot be compared (an empty list when they can)."""
    out = []
    for k, what in (("analysis_version", "analysis version"), ("device_class", "device class"), ("dsd_rate", "DSD rate")):
        missing = [n for n, m in (("the old result", old), ("the new result", new)) if m.get(k) is None]
        if missing:
            out.append(f"{what} is not recorded in {' and '.join(missing)}")
        elif old[k] != new[k]:
            out.append(f"{what} differs ({old[k]!r} and {new[k]!r})")
    return out


def _provenance(path):
    p = Path(path)
    p = p / "provenance.json" if p.is_dir() else None
    return json.loads(p.read_text()) if p and p.is_file() else None


def check_same_run(old, new, mo, mn):
    """Reasons why two report folders were not measured the same way (input rate, output rate, profile).

    Needs ``provenance.json`` in both folders; without it nothing is checked here. The gate profile
    uses the quick profile's signals, so those two are comparable; full is comparable with neither.
    """
    po, pn = _provenance(old), _provenance(new)
    if po is None or pn is None:
        return []
    out = []
    same = {"gate": "quick"}
    prof = [same.get(p.get("profile"), p.get("profile")) for p in (po, pn)]
    if prof[0] != prof[1]:
        out.append(f"profile differs ({po.get('profile')!r} and {pn.get('profile')!r})")
    if po.get("in_rate") != pn.get("in_rate"):
        out.append(f"input rate differs ({po.get('in_rate')!r} and {pn.get('in_rate')!r})")
    ro, rn = ((m.get("output_format") or {}).get("rate") for m in (mo, mn))
    if ro is not None and rn is not None and ro != rn:
        out.append(f"output rate differs ({ro!r} and {rn!r})")
    return out


def run(old, new, scale=1.0, json_out=None, log=print):
    """Compare two results and print the table. Returns True when the gate passes.

    Raises ValueError (exit status 2) when the two cannot be compared or nothing was measured in both.
    """
    mo, mn = load_metrics(old), load_metrics(new)
    bad = check_same_conditions(mo, mn) + check_same_run(old, new, mo, mn)
    if bad:
        raise ValueError("these two results cannot be compared: " + "; ".join(bad))
    rows = compare(mo, mn, scale)
    log(text(rows, Path(old).name or "old", Path(new).name or "new"))
    if not compared(rows) and not any(r["verdict"] == "missing" for r in rows):
        raise ValueError("could not compare: no gate figure was measured in both results")
    ok = passed(rows)
    if json_out:
        Path(json_out).write_text(json.dumps({"pass": ok, "old": str(old), "new": str(new), "rows": rows}, indent=1) + "\n")
    return ok
