"""What a run will do, in plain words: the test catalogue, ``--plan`` and the "What was measured" data.

Nothing here runs a measurement. ``TESTS`` is the single list of tests with the signal each one
uses, the level, who it applies to and a plain sentence on why it matters. The run log, ``--plan``,
``signals --list`` and the report header are all written from it.
"""

import datetime
import hashlib
import shlex
import tempfile
import tomllib
from pathlib import Path

from . import REFERENCE_CHAIN_VERSION, __version__
from .adapters import PRESETS, Cli, Import, Reference, ReftoolSox, make_adapter
from .levels import PEAK_DBFS, REF_DBFS
from .measure import PROFILES, rate_name

#: Reference-chain run time in seconds per test, measured for each profile on one CPU core
#: (i9-13900H P-core), for class A and class B devices.
#: The device's own run time is on top of this; each extra DSD rate adds ``RATE_S``.
SECONDS = {
    "quick": {
        "A": {'reference_floor': 5, 'levels': 14, 'thdn_freq': 4, 'frequency_response': 13, 'impulse': 2, 'noise': 3, 'imd': 2, 'multitone': 7, 'tone_15k': 1, 'jtest': 7, 'polarity': 0, 'stability': 0, 'crosstalk': 12, 'imd_sweep': 14, 'alias_tones': 6, 'overload': 1, 'rate_table': 0},
        "B": {'reference_floor': 5, 'levels': 20, 'thdn_freq': 9, 'frequency_response': 25, 'impulse': 4, 'noise': 10, 'imd': 2, 'multitone': 8, 'tone_15k': 1, 'jtest': 7, 'polarity': 0, 'stability': 9, 'crosstalk': 14, 'imd_sweep': 15, 'alias_tones': 0, 'overload': 1, 'rate_table': 0},
    },
    "full": {
        "A": {'reference_floor': 8, 'levels': 72, 'thdn_freq': 12, 'frequency_response': 35, 'impulse': 3, 'noise': 11, 'imd': 6, 'multitone': 22, 'tone_15k': 3, 'jtest': 19, 'polarity': 0, 'stability': 0, 'crosstalk': 28, 'imd_sweep': 38, 'alias_tones': 10, 'overload': 2, 'rate_table': 0},
        "B": {'reference_floor': 8, 'levels': 78, 'thdn_freq': 13, 'frequency_response': 47, 'impulse': 6, 'noise': 35, 'imd': 6, 'multitone': 23, 'tone_15k': 3, 'jtest': 21, 'polarity': 0, 'stability': 143, 'crosstalk': 31, 'imd_sweep': 40, 'alias_tones': 0, 'overload': 2, 'rate_table': 0},
    },
}

RATE_S = {"quick": 40, "full": 45}


def _t(**k):
    return k


#: Tests in run order. ``sig`` and ``level`` are the short forms for the run log; ``detail`` is the
#: long form for the plan (a function of the profile settings ``p`` and the PCM rate ``r``).
TESTS = {
    "reference_floor": _t(
        klass="AB", sig="reference chain alone", level="1 kHz 0 dB SACD, -60 dB SACD, silence",
        detail=lambda p, r: "1 kHz tone at 0 dB SACD, a -60 dB SACD tone and 32-bit-level dithered silence through the reference chain only, with no device in it",
        what="Measures the reference chain itself: the least distortion and noise this tool can see.",
        why="A device figure close to this floor is limited by the measurement, not by the device, so the report marks it."),
    "levels": _t(
        klass="AB", sig="1 kHz tones", level="+3.1 to -120 dB SACD",
        detail=lambda p, r: (f"1 kHz tones, {p['seg_s']} s each, from 0 dB SACD ({REF_DBFS:.2f} dBFS) down to -120 dB SACD in "
                             f"{p['step_db']:g} dB steps, plus one at +3.1 dB SACD ({PEAK_DBFS:.2f} dBFS)"),
        what="A 1 kHz sine wave at 0 dB SACD (half of full modulation), then the same tone ever quieter, plus one at the loudest level SACD allows.",
        why="It gives the headline SINAD, THD+N, dynamic range and linearity figures that reviewers quote."),
    "thdn_freq": _t(
        klass="AB", sig="tones 20 Hz to 20 kHz", level="0 dB SACD",
        detail=lambda p, r: f"tones at 20 Hz, 100 Hz, 1, 5, 10, 15 and 20 kHz, {p['seg_s']} s each, 0 dB SACD",
        what="The same loud tone at several pitches from bass to the top of the audio band.",
        why="Distortion often rises towards high frequencies; one 1 kHz figure hides that."),
    "frequency_response": _t(
        klass="AB", sig="third-octave tones to 40 kHz", level="0 dB SACD",
        detail=lambda p, r: (f"tones at third-octave steps from 20 Hz to 20 kHz (every {p['fr_every']}"
                             f"{'nd' if p['fr_every'] == 2 else 'st'} one) and at 20.5 to 40 kHz where the rate allows, {p['seg_s']} s each, 0 dB SACD"),
        what="A series of single tones from the lowest bass to beyond the audible band.",
        why="It shows how flat the response is and where the converter's filter starts to roll off."),
    "impulse": _t(
        klass="AB", sig="impulses and a step", level="0 dB SACD",
        detail=lambda p, r: "single-sample impulses (several phases) and a step, 0 dB SACD",
        what="A single click and a sudden step, with silence around them.",
        why="They show the filter's ringing before and after the click, the \"pre-ringing\" that audiophiles argue about, and the group delay."),
    "noise": _t(
        klass="AB", sig="32-bit-level dithered silence", level="below -160 dBFS",
        detail=lambda p, r: f"{p['noise_s']:g} s of 32-bit-level dithered silence, plus (class A) the DSD idle pattern and (class B) zero input",
        what="Silence, with only a trace of dither (32-bit level, far below what a 24-bit recording carries, so the device's own noise is what is measured).",
        why="It shows the noise floor in the audible band and, for a modulator, the shaped noise above 20 kHz."),
    "imd": _t(
        klass="AB", sig="two-tone pairs (SMPTE, CCIF)", level="0 dB SACD",
        detail=lambda p, r: f"60 Hz + 7 kHz (4:1, SMPTE) and 19 kHz + 20 kHz (CCIF), {p['imd_s']:g} s each, 0 dB SACD",
        what="Two tones played together.",
        why="Distortion that only appears when two sounds meet (intermodulation) is more audible than plain harmonic distortion."),
    "multitone": _t(
        klass="AB", sig="32-tone multitone", level="0 dB SACD overall",
        detail=lambda p, r: f"32 tones from 17.6 Hz to 21.4 kHz, {p['mt_periods']} periods, 13.3 dB crest factor",
        what="32 tones at once, spread over the audio band, loud like dense music.",
        why="The gaps between the tones show how clean the device stays under a complex load."),
    "tone_15k": _t(
        klass="AB", sig="15 kHz tone", level="-12 dBFS",
        detail=lambda p, r: f"15 kHz tone, {p['tone_s']:g} s, -12 dBFS",
        what="A high 15 kHz tone at moderate level.",
        why="Stereophile's standard check for ultrasonic images and filter leakage."),
    "jtest": _t(
        klass="AB", sig="J-Test (44.1 kHz)", level="-3 dBFS",
        detail=lambda p, r: f"J-Test at 44.1 kHz, {p['jtest_s']:g} s",
        what="A tone at a quarter of the sample rate with a tiny low-frequency square wave underneath.",
        why="It reveals jitter and data-dependent timing errors as sidebands around the tone."),
    "polarity": _t(
        klass="AB", sig="asymmetric pulse", level="small",
        detail=lambda p, r: "one asymmetric pulse, 8192 samples",
        what="A lopsided pulse that looks different upside down.",
        why="It tells whether the device inverts the signal."),
    "stability": _t(
        klass="B", sig="long loud tones", level="0 dB SACD, +3.1 dB SACD",
        detail=lambda p, r: f"1 kHz at 0 dB SACD, 1 kHz at the peak level and 20 kHz at the peak level, each held {p['hold_s']:g} s",
        what="Loud tones held for a long time.",
        why="A modulator that is unstable at high levels produces bursts of noise or goes silent."),
    "crosstalk": _t(
        klass="AB", sig="stereo: tone left, silence right", level="0 dB SACD",
        detail=lambda p, r: "tone in one channel and dithered silence in the other, at 1 kHz and 10 kHz, both directions",
        what="A tone in one channel and silence in the other.",
        why="Any signal that leaks into the silent channel is crosstalk; it also checks that both channels match."),
    "imd_sweep": _t(
        klass="AB", sig="two-tone sweep", level="0 dB SACD and below",
        detail=lambda p, r: ("CCIF pairs centred at 10 to 19.5 kHz, and SMPTE 60 Hz + 7 kHz at -60 to 0 dB SACD relative level, "
                             f"{p['imd_s'] + 0.8:g} s each"),
        what="The two-tone test repeated at many pitches and levels.",
        why="It shows where intermodulation is worst, not only at one favourable setting."),
    "alias_tones": _t(
        klass="A", sig="tones above the output Nyquist", level="0 dB SACD",
        detail=lambda p, r: "tones 2 to 10 kHz above half the device's output rate (skipped at 352.8 kHz or more), 0 dB SACD",
        what="Tones too high for the device's output rate to carry.",
        why="A good filter removes them; a poor one lets them fold back into the audible band as false tones."),
    "overload": _t(
        klass="AB", sig="quiet tone with a loud burst", level="-60 dB SACD, burst at the peak",
        detail=lambda p, r: "1 kHz at -60 dB SACD with a 50 ms burst at the peak level (class B: digital full scale)",
        what="A quiet tone interrupted by a short, very loud burst.",
        why="It shows how quickly the device recovers after being overloaded."),
    "rate_table": _t(
        klass="AB", sig="1 kHz tones at other DSD rates", level="0 and -60 dB SACD",
        detail=lambda p, r: "1 kHz at 0 dB SACD and -60 dB SACD at each extra DSD rate named by rates = [...] in the suite file",
        what="The main tone test repeated at DSD128 and DSD256.",
        why="Many devices behave differently at higher DSD rates."),
}

#: The five signals ``dsd-measure signals`` writes for hand-fed devices, with the file names.
#: The reference signal files whose hashes the report lists under "What was measured".
HAND_SIGNALS = ("tone_1k_0dbsacd", "tone_1k_peak", "tone_15k_m12", "multitone", "jtest_44100")


def label(test):
    t = TESTS[test]
    return f"{t['sig']}, {t['level']}"


def applies(test, klass):
    return klass in TESTS[test]["klass"]


def tests_for(klass, only=None):
    return [t for t in TESTS if applies(t, klass) and (not only or t in only)]


def list_signals():
    """The catalogue for ``dsd-measure signals --list``."""
    out = ["Test signals made by dsd-measure. All are synthetic and deterministic; none is music.",
           "0 dB SACD is half of full modulation (-6.02 dBFS); +3.1 dB SACD is the loudest level (-2.92 dBFS).", ""]
    for name, t in TESTS.items():
        who = {"AB": "both classes", "A": "class A only", "B": "class B only"}[t["klass"]]
        out.append(f"{name} ({who}): {t['sig']}, {t['level']}")
        out.append(f"    {t['what']} {t['why']}")
    out += ["", "'dsd-measure signals DIR [--class A|B]' writes every one of these as the file a run feeds the device "
            "(a DSF per test for class A, a WAV per test for class B) with a signals.json list, so a device run by hand "
            "gets exactly the same stimuli."]
    return "\n".join(out)


def hand_signals(rate):
    """The WAV test signals written by ``dsd-measure signals`` as ``{name: (array, rate)}``."""
    from . import signals as sg
    from .levels import PEAK_DBFS, REF_DBFS
    n = rate * 6
    f = sg.coherent_freq(1000, 352800, 2**18)
    return {"tone_1k_0dbsacd": (sg.sine(f, REF_DBFS, rate, n), rate),
            "tone_1k_peak": (sg.sine(f, PEAK_DBFS, rate, n), rate),
            "tone_15k_m12": (sg.sine(sg.coherent_freq(15000, 352800, 2**18), -12.0, rate, n), rate),
            "multitone": (sg.multitone_standard(fs=rate)[0], rate),
            "jtest_44100": (sg.jtest(44100, 44100 * 12), 44100)}


def source_hashes(rate):
    """SHA-256 of each reference test-signal file as ``dsd-measure signals`` writes it."""
    from .wavio import write_wav
    out = {}
    with tempfile.TemporaryDirectory() as d:
        for name, (x, r) in hand_signals(rate).items():
            p = Path(d) / f"{name}.wav"
            write_wav(p, x, r, "pcm32")
            out[f"{name}.wav"] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


EXAMPLE_DIR = "/tmp/dsd-measure-example"


def device_facts(adapter):
    """Plain facts about a device: how it is run, what it is fed, what it outputs."""
    a = adapter
    A = a.klass == "A"
    f = {"name": a.name, "class": a.klass,
         "kind": "DSD to PCM converter" if A else "PCM to DSD modulator",
         "adapter": a.kind, "gain_db": a.gain_db, "dsd_rate": a.dsd_rate, "dsd_rate_name": rate_name(a.dsd_rate)}
    if isinstance(a, Reference):
        f["command"] = "built-in (no external command)"
        f["output"] = f"PCM at {a.out_rate} Hz" if A else f"DSD ({rate_name(a.dsd_rate)}) made by the built-in modulator"
        f["output_rate"] = a.out_rate if A else a.dsd_rate
    elif isinstance(a, Cli):
        i = f"{EXAMPLE_DIR}/in1.{a.input_ext if A else 'wav'}"
        o = f"{EXAMPLE_DIR}/out1.{a.output_ext}"
        f["command"] = a.command.format(input=shlex.quote(i), output=shlex.quote(o))
        f["command_template"] = a.command
        f["output"] = f"{'WAV' if a.output_ext == 'wav' else a.output_ext.upper()} file read back" if A else "DSF file read back"
    elif isinstance(a, ReftoolSox):
        mod = "" if A else f" with modulator {a.modulator}"
        f["command"] = (f"{a.reftool} sox-dsd (pinned container) {'to PCM at ' + str(a.out_rate) + ' Hz' if A else 'to DSD' + mod}")
        f["output"] = f"PCM at {a.out_rate} Hz" if A else "DSF file read back"
    elif isinstance(a, Import):
        f["command"] = f"none: reads results already made in {a.dir}"
        f["output"] = "files made elsewhere"
    else:
        f["command"] = a.kind
        f["output"] = ""
    return f


def io_text(facts, in_rate):
    """One line each for what the device is fed and what it returns."""
    if facts["class"] == "A":
        fed = f"DSD ({facts['dsd_rate_name']}, 1 bit, {facts['dsd_rate']} Hz) made from the test signals by the built-in reference modulator"
        ret = f"{facts['output']}; analysed by the reference analyser in 64-bit float"
    else:
        fed = f"PCM at {in_rate} Hz, 32-bit integer WAV, made from the test signals"
        ret = f"{facts['output']}; decoded to PCM by the built-in reference decoder, then analysed"
    return fed, ret


def estimate_s(profile, klass, tests, extra_rates=0):
    tbl = SECONDS.get(profile, {}).get(klass, {})
    return sum(tbl.get(t, 0.0) for t in tests) + (extra_rates * RATE_S[profile] if "rate_table" in tests else 0)


def _mins(s):
    return "under a minute" if s < 45 else f"about {max(1, round(s / 60))} min"


def build_adapters(spec_cfg):
    out = []
    for spec in spec_cfg.get("device", []):
        try:
            out.append((make_adapter(spec), None))
        except FileNotFoundError as e:
            s = dict(spec)
            kind = s.pop("adapter", "reference")
            name = s.pop("name", kind)
            klass = s.pop("class", "A")
            cmd = s.pop("command", PRESETS.get(kind, kind))
            out.append((Cli(name, cmd, klass=klass, **s), f"warning: {e}"))
    return out


def plan_text(suite_path, out=None, profile=None, only=None, source=None):
    """The ``--plan`` text for a suite file. Runs nothing."""
    cfg = tomllib.loads(Path(suite_path).read_text())
    suite = cfg.get("suite", {})
    profile = profile or suite.get("profile", "quick")
    in_rate = int(suite.get("in_rate", 88200))
    outdir = Path(out or suite.get("out", "report"))
    devs = build_adapters(cfg)
    p = PROFILES[profile]
    L = [f"Plan for {source or suite_path} (nothing has been run)", "",
         f"Suite: {suite.get('name', 'unnamed')}   profile: {profile}   PCM source rate: {in_rate} Hz   devices: {len(devs)}", "",
         "Source data: synthetic, deterministic test signals generated by dsd-measure "
         f"{__version__} (tones, two-tone pairs, multitone, J-Test, impulses; no music).",
         "Every device below is measured with the same signals. The built-in reference chain "
         f"(version {REFERENCE_CHAIN_VERSION}) is the floor: the least distortion and noise the tool itself can see.", ""]
    total = 0.0
    shown = set()
    for n, (a, warn) in enumerate(devs, 1):
        fa = device_facts(a)
        fed, ret = io_text(fa, in_rate)
        tl = tests_for(a.klass, only)
        t_est = estimate_s(profile, a.klass, tl, len(a.rates))
        total += t_est
        L += [f"Device {n}: {a.name}",
              f"  class {a.klass}: {fa['kind']}",
              f"  adapter: {a.kind}" + (f", gain applied to its output: {a.gain_db:+g} dB" if a.gain_db else ", no gain applied"),
              f"  command (example for the 1 kHz tone; the file names are made up here, the run makes its own): {fa['command']}",
              f"  fed with: {fed}",
              f"  returns: {ret}"]
        if warn:
            L.append(f"  {warn}")
        if a.rates:
            L.append("  extra DSD rates: " + ", ".join(rate_name(r) for r in a.rates))
        L.append(f"  tests: {len(tl)}, reference-chain time {_mins(t_est)} (the device's own run time is extra)")
        L.append("")
        shown.update(tl)
    L += ["Signals generated (profile " + profile + "):"]
    w = max((len(t) for t in shown), default=10)
    for t in TESTS:
        if t in shown:
            T = TESTS[t]
            who = "" if T["klass"] == "AB" else f" [class {T['klass']} only]"
            L.append(f"  {t:<{w}}  {T['detail'](p, in_rate)}{who}")
    rates = sorted({rate for a, _ in devs for rate in [a.dsd_rate] + list(a.rates)})
    L += ["", "DSD rates: " + ", ".join(rate_name(r) for r in rates) + ".",
          f"Profile {profile}: " + ", ".join(f"{k} {v}" for k, v in p.items()) + ".",
          f"Estimated time: {_mins(total)} for the reference chain, plus the run time of any external tools.", ""]
    L += ["Report:"] + [f"  {outdir}/{safe_name(a.name)}/index.html   ({a.name})" for a, _ in devs]
    if len(devs) > 1:
        L.append(f"  {outdir}/comparison/index.html   (all {len(devs)} side by side, reference chain as the floor)")
    L += [
          "Run it for real by taking --plan off the same command."]
    return "\n".join(L)


def _out_word(adapter):
    """The output word length line: what the device wrote, when a file has been read."""
    from .outformat import name_of
    fmt = getattr(adapter, "output_format", lambda: None)()
    if not fmt or fmt["container"] == "internal":
        return "as written by the device, read and analysed in 64-bit float"
    return f"{name_of(fmt)} as written by the device ({fmt['container'].upper()}), read and analysed in 64-bit float"


def measured(adapter, profile, in_rate, floor, suite_name=None):
    """The data behind the report's "What was measured" block."""
    fa = device_facts(adapter)
    fed, ret = io_text(fa, in_rate)
    log = adapter.log[0] if adapter.log else {}
    if adapter.klass == "A":
        out_rate = getattr(adapter, "out_rate", None) or log.get("rate")
    else:
        out_rate = log.get("rate") or adapter.dsd_rate
    return {"device": fa, "fed_with": fed, "returns": ret, "in_rate_hz": in_rate,
            "in_word": "32-bit integer WAV" if adapter.klass == "B" else "1-bit DSD",
            "out_rate_hz": out_rate,
            "out_word": _out_word(adapter) if adapter.klass == "A"
            else "1-bit DSD, decoded to PCM by the reference decoder and analysed in 64-bit float",
            "gain_db": adapter.gain_db, "profile": profile,
            "date": datetime.date.today().isoformat(),
            "generator": f"dsd-measure {__version__}, reference chain {REFERENCE_CHAIN_VERSION}",
            "source_signal_sha256": source_hashes(in_rate),
            "floor": floor, "suite": suite_name}


def _floor_text(m):
    f = m.get("floor")
    if not f:
        return "not measured in this run"
    lim = f["chain"] if m["device"]["class"] == "A" else f["decoder_alone"]
    who = "reference modulator and decoder" if m["device"]["class"] == "A" else "reference decoder alone"
    return (f"{who} at {rate_name(f['dsd_rate'])}: THD+N {lim['thdn_db']:.1f} dB, dynamic range (A) {lim['dr_a_db']:.1f} dB. "
            f"A device figure within {f['margin_db']:.0f} dB of it is marked as limited by the measurement.")


def measured_summary(m):
    """The few visible lines of "What was measured": (label, text) pairs."""
    d = m["device"]
    out_rate = f"{m['out_rate_hz']} Hz" if m.get("out_rate_hz") else "its own rate"
    if d["class"] == "A":
        io = f"in: DSD {d['dsd_rate']} Hz, 1 bit; out: PCM at {out_rate}"
    else:
        io = f"in: PCM {m['in_rate_hz']} Hz, 32-bit integer WAV; out: DSD at {out_rate}, 1 bit"
    files = ""
    if d.get("command_template"):
        files = (" ({input} is the DSD file made for each test signal, {output} the WAV the tool writes)" if d["class"] == "A"
                 else " ({input} is the WAV made for each test signal, {output} the DSF the tool writes)")
    gain = f"gain applied to its output: {m['gain_db']:+g} dB" if m["gain_db"] else "no gain applied"
    return [
        ("Device", f"{d['name']}: class {d['class']}, {d['kind']}, adapter {d['adapter']}. Run as: {d.get('command_template') or d['command']}{files}. {io}; {gain}."),
        ("Source signals", "Synthetic and deterministic test signals made by the toolkit (tones, two-tone pairs, multitone, J-Test, impulses; "
                           + ("no music), encoded to DSD by the built-in reference modulator." if d["class"] == "A"
                              else "no music), fed to the device as PCM.")),
        ("Reference chain", _floor_text(m)),
        ("Profile and date", f"{m['profile']}, {m['date']}, {m['generator']}."),
    ]


def measured_details(m):
    d = m["device"]
    rows = [("Fed with", m["fed_with"]), ("Returns", m["returns"]), ("Output word length", m["out_word"]),
            ("Suite", m.get("suite") or "")]
    rows += [("Tool versions", ", ".join(f"{k} {v}" for k, v in (m.get("versions") or {}).items()))]
    rows += [(f"SHA-256 {k}", v) for k, v in m["source_signal_sha256"].items()]
    rows += [("Hash note", f"Hashes are of five reference signals (32-bit WAV at {m['in_rate_hz']} Hz) made by the signal generator: a "
                           "fingerprint of the generator. Every run regenerates the same signals bit for bit; 'dsd-measure "
                           "signals DIR' lists the files a run feeds a device, with their hashes, in signals.json.")]
    if d.get("command_template"):
        rows.insert(0, ("Command template", d["command_template"]))
    return rows


def safe_name(name):
    return "".join(c if c.isalnum() or c in "-_" else "-" for c in name)
