"""Run the null test end to end: decode with each device, compare each to the first, write the report."""

import dataclasses
import re
import shutil
import sys
import tomllib
from pathlib import Path

from ..dsdstream import DsdFile
from .analyse import Options, compare, source_info
from .devices import parse_device
from .report import write_report
from .verdict import verdict


def options_from(cfg):
    """An ``Options`` from the keys of a suite file's ``[null]`` table (unknown keys are an error)."""
    names = {f.name for f in dataclasses.fields(Options)}
    bad = set(cfg) - names - {"source", "devices", "out", "suite"}
    if bad:
        raise ValueError(f"unknown [null] keys: {', '.join(sorted(bad))}")
    kw = {k: v for k, v in cfg.items() if k in names}
    if "channels" in kw:
        kw["channels"] = tuple(kw["channels"])
    return Options(**kw)


def load_suite(path):
    cfg = tomllib.loads(Path(path).read_text())
    return cfg.get("device", []), cfg.get("null", {})


def run_null(source, device_args, opts, out, suite_devices=None, keep_work=False, log=print):
    from ..run import versions
    if len(device_args) < 2:
        raise ValueError("the null test needs at least two devices (--device A --device B)")
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    work = out / ".work"
    src = DsdFile(source)
    log(f"source {src.path.name}: {src.kind.upper()}, {src.channels} channels, {src.samples / src.rate:.1f} s; hashing")
    run = {"source": source_info(source), "options": dataclasses.asdict(opts), "versions": versions(),
           "command": " ".join(["dsd-measure"] + sys.argv[1:]), "devices": [], "pairs": []}
    tracks = []
    try:
        for text in device_args:
            dev = parse_device(text, suite_devices)
            if any(dev.name == d.name for d, _ in tracks):  # the same decoder twice: tell them apart
                dev.name += f" ({sum(d.name.split(' (')[0] == dev.name for d, _ in tracks) + 1})"
            log(f"decoding with {dev.name}")
            track, info = dev.prepare(src, work)
            tracks.append((dev, track))
            run["devices"].append({"describe": dev.describe(), "info": info, "rate": track.rate,
                                   "channels": track.channels, "samples": track.length})
        for dev, track in tracks[1:]:
            log(f"comparing {dev.name} with {tracks[0][0].name}")
            safe = re.sub(r"[^A-Za-z0-9_-]+", "-", dev.name).strip("-")
            wav = f"difference-{safe}.wav" if opts.diff_wav else None
            res = compare(tracks[0][1], track, opts, out / wav if wav else None, log=log)
            run["pairs"].append({"a": tracks[0][0].name, "b": dev.name, "result": res,
                                 "verdict": verdict(res["channels"]), "diff_wav": wav})
    finally:
        if not keep_work:
            shutil.rmtree(work, ignore_errors=True)
    write_report(out, run)
    for p in run["pairs"]:
        log(f"{p['b']} against {p['a']}: {p['verdict']['headline']}")
    log(f"report written to {out}/")
    return run
