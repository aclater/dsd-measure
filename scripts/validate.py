#!/usr/bin/env python3
"""Full accuracy validation of the dsd-measure analysers (see docs/accuracy.md).

Sections (run one, or ``all``):

known      every known-answer case, with the long records (also run, shorter, by pytest)
stats      Monte Carlo: bias and scatter of the noise and THD+N estimators
chain      the reference chain's own output, analysed by the main and the independent analyser
tools      the same files measured by SoX and ffmpeg (needs the pinned containers)
archimago  the SoX-DSD test conditions of the 2021-10 and 2022-06 posts (needs the containers)

``python3 scripts/validate.py all --out DIR`` writes ``DIR/validation.json`` and ``DIR/validation.md``
(the tables docs/accuracy.md quotes). Sections that need containers are skipped, and say so, when
``tools/reftool.sh`` cannot run them. Set REFTOOL_PREFIX / REFTOOL_RELABEL as for reftool.sh.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

import accuracy_cases as ac  # noqa: E402
import refanalyser as ra  # noqa: E402
from dsd_measure import analyse as an  # noqa: E402
from dsd_measure import decode as dec  # noqa: E402
from dsd_measure import encode as enc  # noqa: E402
from dsd_measure import signals as sg  # noqa: E402
from dsd_measure.adapters import ReftoolSox  # noqa: E402
from dsd_measure.dsf import write_dff  # noqa: E402
from dsd_measure.levels import REF_DBFS  # noqa: E402
from dsd_measure.wavio import read_wav, write_wav  # noqa: E402

REFTOOL = ROOT / "tools" / "reftool.sh"
FS = 352800
NFFT = 2**18
NOTE = []


def log(*a):
    print(*a, file=sys.stderr, flush=True)


# ---------------------------------------------------------------------------- tables

def table(headers, rows):
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" if i == 0 else "---:" for i in range(len(headers))) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(c) for c in r) + " |")
    return "\n".join(out)


def f2(v, n=2):
    return "n/a" if v is None else f"{v:.{n}f}"


# ---------------------------------------------------------------------------- known answers

def section_known(out):
    t0 = time.time()
    rows = ac.all_rows(quick=False)
    fails = [m for r in rows for m in ac.check(r)]
    groups = {}
    for r in rows:
        g = groups.setdefault(r["metric"], {"n": 0, "dt": 0.0, "dr": 0.0, "tol_t": 0.0, "tol_r": 0.0, "ref": 0})
        g["n"] += 1
        g["dt"] = max(g["dt"], abs(r["ours"] - r["truth"]))
        g["tol_t"] = max(g["tol_t"], r["tol_truth"])
        if r["ref"] is not None:
            g["ref"] += 1
            g["dr"] = max(g["dr"], abs(r["ours"] - r["ref"]))
            g["tol_r"] = max(g["tol_r"], r["tol_ref"])
    tbl = table(["Metric", "Cases", "Worst error vs truth", "Tolerance", "Cases vs 2nd analyser", "Worst difference", "Tolerance"],
                [[k, g["n"], f2(g["dt"], 4), "limit" if "floor" in k else f"{g['tol_t']:g}", g["ref"] or "", f2(g["dr"], 4) if g["ref"] else "",
                  f"{g['tol_r']:g}" if g["ref"] else ""] for k, g in sorted(groups.items())])
    log(f"known: {len(rows)} rows, {len(fails)} failures, {time.time() - t0:.0f} s")
    for m in fails:
        log("  FAIL", m)
    return {"rows": rows, "failures": fails, "table": tbl, "seconds": round(time.time() - t0)}


# ---------------------------------------------------------------------------- Monte Carlo

def section_stats(out, trials=40):
    rng = np.random.default_rng(ac.SEED + 99)
    res = []
    for fs, nf, secs, label in ((352800, 2**18, 14, "2^18 x 8 at 352.8 kHz"), (352800, 2**20, 24, "2^20 x 8 at 352.8 kHz"),
                                (44100, 2**15, 14, "2^15 x 8 at 44.1 kHz")):
        sigma = 3e-6
        truth = ac._db(ac._band_noise_power(sigma, fs)) + ac.SR  # dBFS re a full-scale sine's rms
        err, dens = [], []
        for _ in range(trials):
            x = sigma * rng.standard_normal(int(fs * secs))
            o, _, _ = an.noise_floor(x, fs, nfft=nf, nseg=8)
            err.append(o["unweighted_dbfs"] - truth)
            dens.append(o["density_1k_dbfs_hz"] - (ac._db(sigma**2 / (fs / 2)) + ac.SR))
        res.append(["noise 20 Hz-20 kHz", label, f"{np.mean(err):+.3f}", f"{np.std(err):.3f}", f"{np.max(np.abs(err)):.3f}"])
        res.append(["noise density at 1 kHz", label, f"{np.mean(dens):+.3f}", f"{np.std(dens):.3f}", f"{np.max(np.abs(dens)):.3f}"])
    f0 = sg.coherent_freq(1000, FS, NFFT)
    t = np.arange(NFFT) / FS
    for rel in (-100.0, -140.0):
        sigma = np.sqrt(10 ** (rel / 10) * 10 ** (-6 / 10) / 2 / (19980 / (FS / 2)))
        err = []
        for _ in range(trials):
            x = 10 ** (-6 / 20) * np.sin(2 * np.pi * f0 * t) + sigma * rng.standard_normal(NFFT)
            err.append(an.tone_metrics(x, FS, f0, NFFT)["thdn_db"] - rel)
        res.append(["THD+N, one 2^18 record", f"noise only at {rel:g} dB", f"{np.mean(err):+.3f}", f"{np.std(err):.3f}", f"{np.max(np.abs(err)):.3f}"])
    tbl = table(["Estimate", "Setting", "Mean error (dB)", "Std (dB)", "Worst (dB)"], res)
    log("stats done")
    return {"table": tbl, "rows": res}


# ---------------------------------------------------------------------------- containers

def have_tools():
    try:
        work = Path(os.environ.get("TMPDIR", "/tmp")) / "dsdm-validate-probe"
        work.mkdir(parents=True, exist_ok=True)
        for name in ("sox", "ffmpeg"):
            r = subprocess.run([str(REFTOOL), name, str(work), str(work), "-version" if name == "ffmpeg" else "--version"],
                               capture_output=True, text=True, timeout=300)
            if r.returncode:
                return False
        r = subprocess.run([str(REFTOOL), "sox-dsd", str(work), str(work), "--version"], capture_output=True, text=True, timeout=300)
        return r.returncode == 0
    except Exception:
        return False


def tool(name, indir, outdir, args, timeout=3600):
    Path(outdir).mkdir(parents=True, exist_ok=True)
    r = subprocess.run([str(REFTOOL), name, str(indir), str(outdir), *args], capture_output=True, text=True, timeout=timeout)
    if r.returncode:
        raise RuntimeError(f"{name} failed: {r.stderr.strip()[-300:]}")
    return r.stdout + r.stderr


_RMS = re.compile(r"RMS lev dB\s+(-?[\d.]+)")


def sox_rms(indir, wav, effects, start=1.5, dur=3.0):
    """RMS level (dB re full scale) of a mono WAV after the SoX effects, over a steady stretch."""
    text = tool("sox", indir, indir.parent / "sox-out",
                ["-D", f"/in/{wav}", "-n", "rate", "-v", "96000", *effects, "trim", str(start), str(dur), "stats"])
    return float(_RMS.search(text).group(1))


def sox_thdn(indir, wav, f0, fs_in=FS):
    """THD+N in dB by SoX: band-limit to 20 Hz-20 kHz, reject 940-1060 Hz style band round the tone."""
    lo, hi = f0 - 40.0, f0 + 40.0
    band = ["sinc", "-a", "140", "-t", "25", "20", "sinc", "-a", "160", "-t", "150", "-20000"]
    rej = ["sinc", "-a", "120", "-t", "25", f"{hi:.2f}-{lo:.2f}"] * 2
    sig = sox_rms(indir, wav, ["sinc", "-a", "160", "-t", "100", f"{f0 - 200:.1f}-{f0 + 200:.1f}"])
    noise = sox_rms(indir, wav, band + rej)
    return noise - sig, noise, sig


def sox_noise(indir, wav):
    return sox_rms(indir, wav, ["sinc", "-a", "140", "-t", "25", "20", "sinc", "-a", "160", "-t", "150", "-20000"])


_FF = re.compile(r"(RMS level dB|Peak level dB|DC offset): (-?[\d.inf-]+)")


def ffmpeg_astats(indir, wav):
    text = tool("ffmpeg", indir, indir.parent / "ff-out",
                ["-nostats", "-i", f"/in/{wav}", "-af", "astats=metadata=0:reset=0", "-f", "null", "-"])
    tail = text[text.rfind("Overall"):] if "Overall" in text else text
    return {k: float(v) for k, v in _FF.findall(tail)}


# ---------------------------------------------------------------------------- the reference chain

CHAIN_CASES = [(2822400, REF_DBFS, "DSD64, 0 dB SACD"), (2822400, REF_DBFS - 20, "DSD64, -20 dB SACD"),
               (2822400, REF_DBFS - 60, "DSD64, -60 dB SACD"), (5644800, REF_DBFS, "DSD128, 0 dB SACD")]


def chain_files(work):
    """Run the reference modulator and decoder; write one float64 WAV per case at 352.8 kHz."""
    work.mkdir(parents=True, exist_ok=True)
    out = []
    f0 = sg.coherent_freq(1000, FS, NFFT)
    for rate, lvl, label in CHAIN_CASES:
        x = sg.sine(f0, lvl, 88200, int(88200 * 9))
        bits, info = enc.encode(x, 88200, rate)
        y = dec.decode(bits, rate, FS)
        name = re.sub(r"[^A-Za-z0-9_.]", "_", f"chain_{rate // 44100}_{lvl:.1f}.wav")
        write_wav(work / name, y, FS, "float64")
        out.append({"label": label, "rate": rate, "level": lvl, "wav": name, "f0": f0, "bits": bits, "ntf": info["ntf"]})
    return out


def section_chain(out, with_tools):
    work = out / "work-chain"
    cases = chain_files(work)
    rows = []
    for c in cases:
        y, fs = read_wav(work / c["wav"])
        y = y[0]
        seg = y[int(0.5 * FS) : int(0.5 * FS) + NFFT]
        f0 = c["f0"]
        m = an.tone_metrics(seg, FS, f0, NFFT)
        fit = ra.thdn_sinefit(seg, FS, f0, refine=False)  # the stimulus frequency is exact
        nt = ra.thdn_notch(seg, FS, f0)
        th = ra.thd_harmonics(seg, FS, f0, fixed=True)
        row = {"case": c["label"], "ours_thdn": m["thdn_db"], "fit_thdn": fit["thdn_db"], "notch_thdn": nt["thdn_db"],
               "ours_thd": m["thd_db"], "ref_thd": th["thd_db"], "ours_fund": m["fundamental_dbfs"], "ref_fund": fit["fund_dbfs"],
               "ours_aw": m["thdn_a_db"], "ref_aw": ra.thdn_sinefit(seg, FS, f0, weighted=True, refine=False)["thdn_db"], "ntf": c["ntf"]}
        if with_tools:
            try:
                row["sox_thdn"], _, _ = sox_thdn(work, c["wav"], f0)
            except Exception as e:  # keep going
                NOTE.append(f"chain SoX failed for {c['label']}: {e}")
        rows.append(row)
        log("chain", c["label"], f"ours {m['thdn_db']:.2f} fit {fit['thdn_db']:.2f} notch {nt['thdn_db']:.2f}")
    # the same bits through ffmpeg's own DSD decoder at several output rates
    ffrows = []
    if with_tools:
        c = cases[0]
        write_dff(work / "x.dff", c["bits"], c["rate"])
        for ar in (352800, 176400, 88200, 44100):
            try:
                tool("ffmpeg", work, work / "ff-dec", ["-v", "error", "-y", "-i", "/in/x.dff", "-ar", str(ar), "-c:a", "pcm_f64le", "/out/ff.wav"])
                y, fs = read_wav(work / "ff-dec" / "ff.wav")
                n = max(int(round(2**18 * fs / FS)), 2**12)
                seg = y[0][int(0.5 * fs) : int(0.5 * fs) + n]
                m = an.tone_metrics(seg, fs, c["f0"], n)
                ffrows.append({"rate": fs, "ours_thdn": m["thdn_db"], "fit_thdn": ra.thdn_sinefit(seg, fs, c["f0"], refine=False)["thdn_db"]})
            except Exception as e:
                NOTE.append(f"ffmpeg decode at {ar} failed: {e}")
    t = table(["Case", "THD+N main", "THD+N sine fit", "THD+N notch", "THD+N SoX", "THD main", "THD harmonic fit", "A-weighted main", "A-weighted fit"],
              [[r["case"], f2(r["ours_thdn"]), f2(r["fit_thdn"]), f2(r["notch_thdn"]), f2(r.get("sox_thdn")), f2(r["ours_thd"]),
                f2(r["ref_thd"]), f2(r["ours_aw"]), f2(r["ref_aw"])] for r in rows])
    ft = table(["ffmpeg output rate (Hz)", "SINAD main (dB)", "SINAD sine fit (dB)"],
               [[r["rate"], f2(-r["ours_thdn"]), f2(-r["fit_thdn"])] for r in ffrows]) if ffrows else ""
    return {"rows": rows, "ffmpeg": ffrows, "table": t, "ffmpeg_table": ft}


# ---------------------------------------------------------------------------- tools on synthetic files

def section_tools(out):
    work = out / "work-tools"
    work.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(ac.SEED + 11)
    n = FS * 8
    f0 = sg.coherent_freq(1000, FS, NFFT)
    t = np.arange(n) / FS
    rows = []
    # (1) tone, 3rd harmonic and white noise with a known THD+N
    for lvl, rel in ((-6.0, -100.0), (-6.0, -120.0), (-60.0, -90.0), (-6.0, -140.0)):
        a = 10 ** (lvl / 20)
        p1 = a**2 / 2
        hp = p1 * 10 ** (rel / 10)
        sigma = np.sqrt(0.1 * hp / (19980 / (FS / 2)))
        x = a * np.sin(2 * np.pi * f0 * t) + np.sqrt(2 * hp) * np.sin(2 * np.pi * 3 * f0 * t + 0.7) + sigma * rng.standard_normal(n)
        name = f"tone_{lvl:.0f}_{rel:.0f}.wav".replace("-", "m")
        write_wav(work / name, x, FS, "float64")
        truth = ac._db(10 ** (rel / 10) * 1.1)
        seg = x[FS : FS + NFFT]
        s_thdn, _, s_sig = sox_thdn(work, name, f0)
        ff = ffmpeg_astats(work, name)
        rows.append({"metric": "THD+N, dB", "case": f"{lvl:g} dBFS tone, harmonic {rel:g} dB", "truth": truth,
                     "ours": an.tone_metrics(seg, FS, f0, NFFT)["thdn_db"], "fit": ra.thdn_sinefit(x[FS:], FS, f0)["thdn_db"], "sox": s_thdn})
        rows.append({"metric": "tone level, dBFS rms", "case": f"{lvl:g} dBFS tone", "truth": ac._db(p1),
                     "ours": an.tone_metrics(seg, FS, f0, NFFT)["fundamental_dbfs"], "fit": ra.thdn_sinefit(x[FS:], FS, f0)["fund_dbfs"],
                     "sox": s_sig, "ffmpeg": ff.get("RMS level dB")})
        log("tools", name, f"truth {truth:.3f} sox {s_thdn:.3f}")
    # (2) white noise at several levels
    for sigma in (1e-4, 3e-6, 1e-7):
        x = sigma * rng.standard_normal(n)
        name = f"white_{-int(np.log10(sigma) * 10)}.wav".replace("-", "m")
        write_wav(work / name, x, FS, "float64")
        truth = ac._db(ac._band_noise_power(sigma, FS)) + ac.SR  # dBFS re a full-scale sine's rms
        o, _, _ = an.noise_floor(x[FS:], FS, nfft=2**18, nseg=8)
        ff = ffmpeg_astats(work, name)
        rows.append({"metric": "noise 20 Hz-20 kHz, dBFS", "case": f"white, sigma {sigma:g}", "truth": truth, "ours": o["unweighted_dbfs"],
                     "fit": ra.noise_dbfs(x[FS:], FS), "sox": sox_noise(work, name) + ac.SR})  # SoX reads the mean square
        rows.append({"metric": "noise full band, dBFS rms (no filter)", "case": f"white, sigma {sigma:g}", "truth": ac._db(sigma**2),
                     "ours": ac._db(np.mean(x**2)), "fit": None, "sox": None, "ffmpeg": ff.get("RMS level dB")})
    # (3) DC and peak conventions
    x = 0.3 * np.sin(2 * np.pi * f0 * t) + 1e-3
    write_wav(work / "dc.wav", x, FS, "float64")
    ff = ffmpeg_astats(work, "dc.wav")
    rows.append({"metric": "DC offset (linear)", "case": "1e-3 on a 0.3 sine", "truth": 1e-3, "ours": an.dc_offset(x[: FS * 8 // 1000 * 1000])["dc"],
                 "fit": ra.fit_sine(x[:2**16], FS, f0)["offset"], "sox": None, "ffmpeg": ff.get("DC offset")})
    return {"rows": rows}


def tools_table(res):
    lines = []
    for r in res["rows"]:
        lines.append([r["metric"], r["case"], f2(r["truth"], 3)] + [
            f2(None if r.get(k) is None else r[k] - r["truth"], 3) for k in ("ours", "fit", "sox", "ffmpeg")])
    return table(["Metric", "Case", "Truth", "dsd-measure", "Sine-fit analyser", "SoX", "ffmpeg"], lines)


# ---------------------------------------------------------------------------- Archimago's conditions

def modulate_and_measure(job, work):
    """PCM tone -> SoX-DSD modulator (through the adapter) -> reference decoder -> measurements."""
    name, mod, rate, lvl, trellis, secs = job
    f0 = sg.coherent_freq(1000, FS, NFFT)
    src = 192000
    x = sg.sine(f0, lvl, src, int(src * secs))
    ad = ReftoolSox(name, REFTOOL, klass="B", dsd_rate=rate, modulator=mod, trellis=trellis, workdir=work / name)
    bits, r = ad.pcm_to_dsd(x, src)
    y = dec.decode(bits, r, FS)
    seg = y[int(0.5 * FS) : int(0.5 * FS) + NFFT]
    m = an.tone_metrics(seg, FS, f0, NFFT)
    ur = 705600
    yu = dec.decode(bits, r, ur)[int(0.5 * ur) :]
    u = an.ultrasonic_peak(yu, ur, nfft=2**18, nseg=6, f_lo=20000.0, f_hi=0.4 * ur)
    return {"name": name, "mod": mod, "rate": rate, "level": lvl, "trellis": trellis, "thdn": m["thdn_db"], "thd": m["thd_db"],
            "aw": m["thdn_a_db"], "fund": m["fundamental_dbfs"], "noise": m["noise_dbfs"], "us_hz": u["peak_hz"],
            "us_dens": u["peak_density_dbfs_hz"], "us_50": u["density_dbfs_hz"].get("50000"),
            "us_100": u["density_dbfs_hz"].get("100000"), "us_40_96": u["integrated_dbfs"].get("40000-96000"),
            "us_20_40": u["integrated_dbfs"].get("20000-40000")}


def section_archimago(out, secs=12.0, workers=8):
    work = out / "work-archimago"
    work.mkdir(parents=True, exist_ok=True)
    jobs = []
    # 2021-10: DSD64, the six modulators of the comparison, 1 kHz at -0.1 dBFS, SoX's own trellis settings
    for mod in ("clans-4", "clans-6", "clans-8", "sdm-4", "sdm-6", "sdm-8"):
        jobs.append((f"a21-{mod}", mod, 2822400, -0.1, "default", secs))
    jobs.append(("a21-sdm-8-dsd128", "sdm-8", 5644800, -0.1, "default", secs))
    # 2022-06: CLANS-8 / -7 / -6 for DSD64 / 128 / 256 with -t 32 -n 32, 1 kHz at -2.9 dBFS
    for mod, rate in (("clans-8", 2822400), ("clans-7", 5644800), ("clans-6", 11289600)):
        jobs.append((f"a22-{mod}", mod, rate, -2.9, "32x32", secs))
    # the -60 dBFS dynamic-range tone
    for mod in ("sdm-8", "clans-8"):
        jobs.append((f"dr-{mod}", mod, 2822400, -60.0, "default", secs))
    res = []
    with ThreadPoolExecutor(workers) as ex:
        futs = [ex.submit(modulate_and_measure, j, work) for j in jobs]
        for j, fu in zip(jobs, futs, strict=True):
            try:
                r = fu.result()
                res.append(r)
                log("archimago", j[0], f"thdn {r['thdn']:.2f} a-weighted {r['aw']:.2f}")
            except Exception as e:
                NOTE.append(f"archimago {j[0]} failed: {e}")
    # the 21.4 kHz tone of the multitone: level through SoX-DSD's own filter, from 44.1 and 96 kHz sources
    tone_rows = []
    for src in (44100, 96000):
        for fq in (1000.0, 20000.0, 21400.0):
            f = sg.coherent_freq(fq, FS, NFFT)
            ad = ReftoolSox(f"t{src}-{fq:g}", REFTOOL, klass="B", dsd_rate=2822400, modulator="sdm-8", workdir=work / f"t{src}-{fq:g}")
            bits, r = ad.pcm_to_dsd(sg.sine(f, -6.0206, src, int(src * 6)), src)
            y = dec.decode(bits, r, FS)
            seg = y[int(0.5 * FS) : int(0.5 * FS) + NFFT]
            lvl = an.tone_level_db(seg, FS, f, NFFT)
            tone_rows.append({"source": src, "freq": f, "level": lvl})
    for s in (44100, 96000):
        ref = [t for t in tone_rows if t["source"] == s and t["freq"] < 1100][0]["level"]
        for t in tone_rows:
            if t["source"] == s:
                t["rel"] = t["level"] - ref
    return {"rows": res, "tones": tone_rows}


def archimago_tables(res):
    r = res["rows"]
    t1 = table(["Run", "Modulator", "DSD rate", "Input (dBFS)", "Trellis", "SINAD (dB)", "THD+N A-weighted (dB)", "THD (dB)"],
               [[x["name"], x["mod"], f"DSD{x['rate'] // 44100}", x["level"], x["trellis"], f2(-x["thdn"], 1), f2(x["aw"], 1), f2(x["thd"], 1)] for x in r])
    t2 = table(["Run", "50 kHz (dBFS/Hz)", "100 kHz (dBFS/Hz)", "Highest 1/3 octave (kHz)", "20-40 kHz (dBFS)", "40-96 kHz (dBFS)"],
               [[x["name"], f2(x["us_50"], 1), f2(x["us_100"], 1), f2(x["us_hz"] / 1000, 0), f2(x["us_20_40"], 1), f2(x["us_40_96"], 1)]
                for x in r])
    t3 = table(["PCM source rate", "Tone (Hz)", "Level re 1 kHz (dB)"],
               [[t["source"], f"{t['freq']:.0f}", f2(t["rel"], 2)] for t in res["tones"]])
    return t1, t2, t3


# ---------------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("section", nargs="?", default="all", choices=["known", "stats", "chain", "tools", "archimago", "all"])
    ap.add_argument("--out", default="validation", help="output folder (default ./validation)")
    a = ap.parse_args()
    out = Path(a.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    want = {"known", "stats", "chain", "tools", "archimago"} if a.section == "all" else {a.section}
    containers = bool(want & {"chain", "tools", "archimago"}) and have_tools()
    if want & {"chain", "tools", "archimago"} and not containers:
        NOTE.append("containers unavailable: the SoX and ffmpeg parts and the archimago section are skipped "
                    "(build the images with tools/reftool.sh build)")
    res, md = {}, ["# Validation results", ""]
    if "known" in want:
        res["known"] = section_known(out)
        md += ["## Known answers", "", res["known"]["table"], "", f"{len(res['known']['rows'])} cases, {len(res['known']['failures'])} failures.", ""]
    if "stats" in want:
        res["stats"] = section_stats(out)
        md += ["## Estimator statistics", "", res["stats"]["table"], ""]
    if "chain" in want:
        res["chain"] = section_chain(out, containers)
        md += ["## Reference chain output", "", res["chain"]["table"], ""]
        if res["chain"]["ffmpeg_table"]:
            md += ["### Same bits decoded by ffmpeg", "", res["chain"]["ffmpeg_table"], ""]
    if "tools" in want and containers:
        res["tools"] = section_tools(out)
        md += ["## SoX and ffmpeg on synthetic files (error against truth, dB)", "", tools_table(res["tools"]), ""]
    if "archimago" in want and containers:
        res["archimago"] = section_archimago(out)
        t1, t2, t3 = archimago_tables(res["archimago"])
        md += ["## SoX-DSD conditions of the 2021-10 and 2022-06 posts", "", t1, "", t2, "", t3, ""]
    if NOTE:
        md += ["## Notes", ""] + [f"- {n}" for n in NOTE] + [""]
    (out / "validation.json").write_text(json.dumps(res, indent=1, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o)))
    (out / "validation.md").write_text("\n".join(md))
    log(f"written {out}/validation.md")
    failed = bool(res.get("known", {}).get("failures"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
