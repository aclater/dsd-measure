"""Suite runner: a TOML suite file (devices x tests) -> a full report folder."""

import hashlib
import platform
import re
import sys
import time
import tomllib
from pathlib import Path

import matplotlib
import numpy
import scipy

from . import REFERENCE_CHAIN_VERSION, __version__, preflight
from .adapters import make_adapter
from .measure import PROFILES, measure_device
from .report import write_comparison, write_device_report

EXAMPLE_SUITE = """\
# dsd-measure suite: devices x tests -> a report folder.
[suite]
name = "reference chain"
profile = "quick"      # "quick" (minutes) or "full" (the footprint's durations)
in_rate = 88200        # PCM rate fed to the device or modulator
out = "report"

[[device]]
name = "reference decoder"      # class A: DSD to PCM
adapter = "reference"
class = "A"
out_rate = 44100

[[device]]
name = "reference modulator"    # class B: PCM to DSD
adapter = "reference"
class = "B"
"""


def versions():
    return {"dsd_measure": __version__, "reference_chain": REFERENCE_CHAIN_VERSION,
            "python": platform.python_version(), "numpy": numpy.__version__, "scipy": scipy.__version__,
            "matplotlib": matplotlib.__version__}


def _say(msg="", end="\n"):
    print(msg, end=end, flush=True)


def summary_line(name, res):
    """One line per device for the end of a run: SINAD, dynamic range and the reference-floor flag."""
    from .report import summary_rows
    rows = summary_rows(res["metrics"])

    def pick(pre):
        return next((r for r in rows if r["label"].startswith(pre)), None)

    bits = []
    for lab, pre in (("SINAD", "SINAD, 1 kHz"), ("DR(A)", "Dynamic range")):
        r = pick(pre)
        bits.append(f"{lab} {r['value']}" if r else f"{lab} not measured")
    from .conclusions import format_limit
    fmt = format_limit(res["metrics"])
    if fmt:
        bits.append(f"limited by its {fmt['bits']}-bit output file, not judged")
    elif pick("SINAD, 1 kHz") or pick("Dynamic range"):
        # each row is judged against its own floor (the peak-level row has a higher one); say which rows are at it
        at = [re.split(r"[,(]", r["label"])[0].strip() for r in rows if r["flag"]]
        bits.append("at its reference floor (limited by the measurement) in: " + ", ".join(at) if at else "clear of the reference floor")
    return f"  {name}: " + ", ".join(bits)


def run_suite(path, out=None, profile=None, only=None, log=None, plan=False, verbose=False, source=None):
    """Run a suite file; returns ``(report folder, {device: [tests that raised]})``.

    ``plan=True`` prints what would run and returns ``(None, {})`` without measuring.
    """
    from . import plan as pl
    log = log or _say
    path = Path(path)
    if plan:
        log(pl.plan_text(path, out, profile, only, source=source))
        return None, {}
    raw = path.read_bytes()
    cfg = tomllib.loads(raw.decode())
    suite = cfg.get("suite", {})
    profile = profile or suite.get("profile", "quick")
    in_rate = int(suite.get("in_rate", 88200))
    outdir = Path(out or suite.get("out", "report"))
    null_only = only == ["null"]
    specs = [] if null_only else cfg.get("device", [])
    t_start = time.time()
    log(f"dsd-measure {__version__}: suite {suite.get('name', 'unnamed')!r}, profile {profile}, {len(specs)} device(s). "
        f"Source data: synthetic test signals made by the tool (not music). Report folder: {outdir}/")
    seen = {}
    for spec in specs:  # two names that sanitise to one folder would overwrite each other's report
        key = pl.safe_name(str(spec.get("name", spec.get("adapter", "reference"))))
        if key in seen:
            raise ValueError(f"devices {seen[key]!r} and {spec.get('name')!r} would both write the report folder {key!r}: "
                             "give them names that differ in letters, digits, - or _")
        seen[key] = spec.get("name")
    adapters = [make_adapter(spec) for spec in specs]
    results, metas, failed, heads = [], [], {}, []
    try:
        # pre-flight: every device converts one short signal before anything is measured or written
        pre = [preflight.run(a, in_rate, log) for a in adapters]
        outdir.mkdir(parents=True, exist_ok=True)
        for n, (adapter, pf) in enumerate(zip(adapters, pre, strict=True), 1):
            fa = pl.device_facts(adapter)
            log("")
            log(f"Device {n} of {len(specs)}: {adapter.name} (class {adapter.klass}, {fa['kind']}, adapter {adapter.kind})")
            if verbose:
                fed, ret = pl.io_text(fa, in_rate)
                log(f"  command (example): {fa['command']}")
                log(f"  fed with: {fed}")
                log(f"  returns: {ret}")
                if adapter.gain_db:
                    log(f"  gain applied to its output: {adapter.gain_db:+g} dB")
            res = measure_device(adapter, profile, in_rate, log=log, only=only)
            if res["errors"]:
                failed[adapter.name] = list(res["errors"])
            meta = {"device": adapter.describe(), "profile": profile, "in_rate": in_rate,
                    "reference_chain": REFERENCE_CHAIN_VERSION, "versions": versions(),
                    "suite_sha256": hashlib.sha256(raw).hexdigest(), "adapter_calls": adapter.log[:50],
                    "command": " ".join(["dsd-measure"] + sys.argv[1:]), "timing_s": res["timing_s"],
                    "preflight": pf,
                    "profile_settings": PROFILES[profile], "reference_modulator_designs": res.get("reference_chain_ntf", {})}
            meta["measured"] = pl.measured(adapter, profile, in_rate, res["metrics"].get("reference_floor"), suite.get("name"))
            meta["measured"]["versions"] = meta["versions"]
            safe = pl.safe_name(adapter.name)
            heads.append(write_device_report(outdir / safe, adapter.name, res, meta))
            results.append((adapter.name, safe, res))
            metas.append(meta["measured"])
    finally:
        for a in adapters:
            a.close()  # temporary files go on success, failure and Ctrl-C
    if len(results) > 1:
        heads = [write_comparison(outdir / "comparison", [(s_, r) for _, s_, r in results], {"profile": profile, "measured": metas})]
    if "null" in cfg and (only is None or "null" in only):
        from .nulltest.run import options_from, run_null
        ncfg = dict(cfg["null"])
        run_null(ncfg["source"], ncfg["devices"], options_from(ncfg), ncfg.get("out", outdir / "null"),
                 cfg.get("device", []), log=log)
    top = outdir / ("comparison" if len(results) > 1 else results[0][1] if results else "") / "index.html"
    secs = time.time() - t_start
    log("")
    log(f"Finished in {secs / 60:.1f} min. Report: {top}")
    for name, _, res in results:
        log(summary_line(name, res))
    for name, tests in failed.items():
        log(f"{name}: {len(tests)} test(s) failed: {', '.join(tests)}")
    if heads:
        log(heads[0])
    return outdir, failed
