"""Suite runner: a TOML suite file (devices x tests) -> a full report folder."""

import hashlib
import platform
import sys
import tomllib
from pathlib import Path

import matplotlib
import numpy
import scipy

from . import REFERENCE_CHAIN_VERSION, __version__
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


def run_suite(path, out=None, profile=None, only=None, log=print):
    path = Path(path)
    raw = path.read_bytes()
    cfg = tomllib.loads(raw.decode())
    suite = cfg.get("suite", {})
    profile = profile or suite.get("profile", "quick")
    in_rate = int(suite.get("in_rate", 88200))
    outdir = Path(out or suite.get("out", "report"))
    outdir.mkdir(parents=True, exist_ok=True)
    results = []
    for spec in cfg.get("device", []):
        adapter = make_adapter(spec)
        log(f"measuring {adapter.name} (class {adapter.klass}, profile {profile})")
        res = measure_device(adapter, profile, in_rate, log=log, only=only)
        meta = {"device": adapter.describe(), "profile": profile, "in_rate": in_rate,
                "reference_chain": REFERENCE_CHAIN_VERSION, "versions": versions(),
                "suite_sha256": hashlib.sha256(raw).hexdigest(), "adapter_calls": adapter.log[:50],
                "command": " ".join(["dsd-measure"] + sys.argv[1:]), "timing_s": res["timing_s"],
                "profile_settings": PROFILES[profile], "reference_modulator_designs": res.get("reference_chain_ntf", {})}
        safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in adapter.name)
        write_device_report(outdir / safe, adapter.name, res, meta)
        results.append((safe, res))
    if len(results) > 1:
        write_comparison(outdir / "comparison", results, {"profile": profile})
    log(f"report written to {outdir}/")
    return outdir
