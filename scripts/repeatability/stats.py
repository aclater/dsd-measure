"""Statistics of the repeatability ensemble made by run.sh.

usage: stats.py DIR      (DIR holds direct-N/ and fft-N/ report folders)

Prints, for the headline figures, the mean and standard deviation of each ensemble and Welch's
t-test between them, and for all figures the number of small p-values against the number
expected by chance. Writes every figure's statistics to DIR/stats.json.
"""

import json
import sys
from pathlib import Path

import numpy as np
from scipy import stats

HEAD = ["tone_0dbsacd/sinad_db", "tone_0dbsacd/thd_db", "tone_0dbsacd/thdn_a_db", "tone_peak/sinad_db",
        "dynamic_range/dr_a_db", "noise/a_weighted_dbfs", "noise/unweighted_dbfs", "imd_smpte/imd_db", "imd_ccif/imd_db",
        "multitone/headline/distortion_free_range_db", "alias_tones/worst_image_db", "jtest/noise_floor_db",
        "crosstalk/1000/left_to_right_db", "reference_floor/chain/thdn_db", "reference_floor/chain/dr_a_db",
        "reference_floor/chain/noise_a_dbfs", "reference_floor/decoder_alone/thdn_db"]


def leaves(d, path=""):
    if isinstance(d, dict):
        for k, v in d.items():
            yield from leaves(v, f"{path}/{k}")
    elif isinstance(d, list):
        for i, v in enumerate(d):
            yield from leaves(v, f"{path}[{i}]")
    elif isinstance(d, (int, float)) and not isinstance(d, bool):
        yield path, float(d)


def load(run):
    out = {}
    for res in sorted(run.glob("*/results.json")):
        if res.parent.name == "comparison":
            continue
        for p, v in leaves(json.loads(res.read_text())["metrics"]):
            out[f"{res.parent.name}{p}"] = v
    return out


def main(root):
    dirs = {m: [p for p in sorted(root.glob(f"{m}-[0-9]*")) if p.is_dir()] for m in ("direct", "fft")}
    for m, ds in dirs.items():
        empty = [p.name for p in ds if not any(c.name != "comparison" for c in p.glob("*/results.json"))]
        if empty:
            sys.exit(f"the {m} ensemble has members without any results.json: {', '.join(empty)}")
    ens = {m: [load(p) for p in ds] for m, ds in dirs.items()}
    print(f"members: direct {len(ens['direct'])}, fft {len(ens['fft'])}")
    if len(ens["direct"]) != len(ens["fft"]):
        sys.exit(f"the two ensembles differ in size: direct {len(ens['direct'])}, fft {len(ens['fft'])} members")
    if len(ens["direct"]) < 2:
        sys.exit(f"each ensemble needs at least 2 members (found {len(ens['direct'])}): a spread cannot be read from fewer")
    for m, runs in ens.items():  # an ensemble whose members are all one run was not perturbed: no proof
        if len(runs) > 1 and all(r == runs[0] for r in runs[1:]):
            sys.exit(f"the {m} ensemble has {len(runs)} identical members: the perturbation did not reach its interpolator")
    keys = [k for k in ens["direct"][0] if all(k in r for rs in ens.values() for r in rs)]
    rows = {}
    fixed = 0
    for k in keys:
        a = np.array([r[k] for r in ens["direct"]])
        b = np.array([r[k] for r in ens["fft"]])
        if not (np.all(np.isfinite(a)) and np.all(np.isfinite(b))):
            continue
        if a.std() == 0 and b.std() == 0 and a[0] == b[0]:
            fixed += 1
            continue
        if np.array_equal(np.sort(a), np.sort(b)):
            t, p = 0.0, 1.0  # the same values in both ensembles (signals the perturbation swamps)
        else:
            t, p = stats.ttest_ind(a, b, equal_var=False)
        rows[k] = {"direct_mean": a.mean(), "direct_sd": a.std(ddof=1), "fft_mean": b.mean(), "fft_sd": b.std(ddof=1),
                   "t": abs(float(t)), "p": float(p)}
    ps = np.array([r["p"] for r in rows.values()])
    print(f"numeric results: {len(keys)}; the same in every run: {fixed}; varying with the noise realisation: {len(rows)}")
    for th in (0.05, 0.01, 0.001):
        print(f"  p < {th}: {int(np.sum(ps < th))} figures (about {th * len(ps):.1f} expected by chance)")
    print(f"\n{'figure':64s} {'direct':>10s} {'sd':>6s} {'fft':>10s} {'sd':>6s} {'|t|':>5s} {'p':>6s}")
    devices = sorted({k.split("/")[0] for k in keys})
    for dev in devices:
        for h in HEAD:
            k = f"{dev}/{h}"
            if k in rows:
                r = rows[k]
                print(f"{k:64s} {r['direct_mean']:10.3f} {r['direct_sd']:6.3f} {r['fft_mean']:10.3f} {r['fft_sd']:6.3f} "
                      f"{r['t']:5.2f} {r['p']:6.3f}")
            elif k in ens["direct"][0]:
                print(f"{k:64s} {ens['direct'][0][k]:10.3f}  the same in every run of both ensembles")
    (root / "stats.json").write_text(json.dumps(rows, indent=1) + "\n")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
