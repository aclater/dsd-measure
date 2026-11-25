"""Command line: ``dsd-measure run|quick|signals|init|versions``."""

import argparse
import json
import re
import sys
import tempfile
import tomllib
from pathlib import Path

from . import __version__
from .errors import UserError

#: Exit status: 0 everything ran; 1 the report was written but some tests raised an error
#: (see "Not run, and why"); 2 a fatal error (bad suite file, unknown adapter, missing tool,
#: unsafe cache) with no report; 130 interrupted with Ctrl-C.
EXIT_OK, EXIT_TESTS_FAILED, EXIT_FATAL, EXIT_INTERRUPTED = 0, 1, 2, 130


def main(argv=None):
    try:
        return _main(argv)
    except KeyboardInterrupt:
        print("dsd-measure: interrupted", file=sys.stderr)
        return EXIT_INTERRUPTED
    except UserError as e:
        print(f"dsd-measure: error: {e}", file=sys.stderr)
        return EXIT_FATAL
    except (OSError, ValueError, KeyError, RuntimeError, tomllib.TOMLDecodeError) as e:
        print(f"dsd-measure: error: {type(e).__name__}: {e}", file=sys.stderr)
        return EXIT_FATAL


GUIDE = """\
dsd-measure measures DSD to PCM converters and PCM to DSD modulators. What do you want to do?

  dsd-measure quick ffmpeg                  measure a decoder you have installed (ffmpeg, dsd2pcm, sox-dsd)
  dsd-measure null track.dsf ffmpeg         compare it with the reference decoder on your own DSF file
  dsd-measure run suite.toml                run a suite file of several devices side by side

Add --plan to quick, null or run to see what would happen first. More: dsd-measure --help
"""


def _speed_options(p):
    p.add_argument("-j", "--jobs", type=int, metavar="N",
                   help="worker processes (default: all cores up to 4, then half of them, at most 16, fewer when memory is short; "
                        "1 runs the tests one after the other). "
                        "The results do not depend on it")
    p.add_argument("--no-cache", action="store_true",
                   help="do not read or write the cache of encoded test signals (the results are the same, the run is slower)")


def _main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    if not argv:
        print(GUIDE, end="")
        return EXIT_OK
    if Path(argv[0]).suffix.lower() in (".dsf", ".dff") and not argv[0].startswith("-"):
        raise UserError(f"{argv[0]!r} is a DSD file, not a command. To compare decoders on this file: "
                        f"dsd-measure null {argv[0]} ffmpeg")
    ap = argparse.ArgumentParser(prog="dsd-measure", description="Deterministic measurements for DSD and PCM converters.")
    ap.add_argument("--version", action="version", version=__version__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="run a suite file (TOML) and write a report")
    r.add_argument("suite")
    r.add_argument("-o", "--out")
    r.add_argument("--profile", choices=["gate", "quick", "full"],
                   help="gate: the few tests a release check needs; quick: every test, short signals; full: the footprint's durations")
    r.add_argument("--only", nargs="*", help="run only these tests (see docs/options.md)")
    r.add_argument("--plan", action="store_true", help="print what would be measured, against what and with which signals, then exit")
    r.add_argument("-v", "--verbose", action="store_true", help="show device details while running")

    _speed_options(r)

    q = sub.add_parser("quick", help="measure one converter with the quick profile")
    q.add_argument("converter", help="'reference', a tool preset (ffmpeg, dsd2pcm, sox-dsd, sacd_extract) or any name with --command")
    q.add_argument("--command", help="command template with {input} and {output}")
    q.add_argument("--args", help="extra arguments for a preset, put after the program name (for example --args '--filter pysacd'; write --args=--dither when the value starts with a dash)")
    q.add_argument("--class", dest="klass", choices=["A", "B"], default="A", help="A: DSD to PCM, B: PCM to DSD")
    q.add_argument("-o", "--out", default="report")
    q.add_argument("--profile", choices=["gate", "quick", "full"], default="quick")
    q.add_argument("--plan", action="store_true", help="print what would be measured, then exit")
    q.add_argument("-v", "--verbose", action="store_true", help="show device details while running")

    _speed_options(q)

    c = sub.add_parser("cache", help="show or empty the cache of encoded test signals",
                       description="Encoded test signals are kept per user and reused by later runs; see the user guide, Speed.")
    c.add_argument("--clear", action="store_true", help="delete every cached test signal")
    c.add_argument("--key", action="store_true",
                   help="print the name a CI system should save and restore the cache folder under, then exit")

    g = sub.add_parser("gate", help="release gate: fail when a new result is worse than an old one beyond repeatability",
                       description="Compares two device report folders made with the same suite and profile (for example the "
                                   "previous release and the candidate). Judges the measured figures, not the bytes of the output. "
                                   "Exit status 0: no figure is worse; 1: at least one is worse or no longer measured.")
    g.add_argument("old", help="device report folder (or results.json) of the previous version")
    g.add_argument("new", help="device report folder (or results.json) of the new version")
    g.add_argument("--scale", type=float, default=1.0, help="multiply every repeatability by this (default 1)")
    g.add_argument("--json", dest="json_out", help="also write the comparison to this file")

    n = sub.add_parser("null", help="real-music null test: how much does a decoder differ from the reference on your DSD file?",
                       description="Example: dsd-measure null track.dsf ffmpeg compares ffmpeg with the built-in reference decoder on track.dsf.")
    n.add_argument("items", nargs="*", metavar="FILE|DEVICE",
                   help="the DSF or DFF file, then the decoders to compare: a preset (ffmpeg, dsd2pcm, sox-dsd), reference[@RATE], "
                        "NAME=COMMAND or a [[device]] name from --suite. The built-in reference decoder is the baseline unless you name two or more")
    n.add_argument("--source", help="DSF or DFF file (or [null] source in --suite); the same as the first argument")
    n.add_argument("--device", action="append", default=[], help="a decoder, as above; give two or more to choose the baseline (the first)")
    n.add_argument("--suite", help="suite file with [[device]] tables and an optional [null] table")
    n.add_argument("-o", "--out", "--out-dir", dest="out")
    n.add_argument("--trim-start", type=float, help="seconds cut at the start (default 0.5)")
    n.add_argument("--trim-end", type=float, help="seconds cut at the end (default 0.5)")
    n.add_argument("--start", type=float, help="analyse from this time in the file, in seconds")
    n.add_argument("--duration", type=float, help="analyse this many seconds")
    n.add_argument("--rate", type=int, help="common rate in Hz (default: the lower of the two devices' rates)")
    n.add_argument("--max-delay", type=float, help="longest delay searched either way, in seconds (default 0.5)")
    n.add_argument("--polarity", choices=["auto", "keep"], help="auto: detect and undo an inverted device (default)")
    n.add_argument("--gain", choices=["match", "none"], help="match: least-squares level match (default)")
    n.add_argument("--channels", type=int, nargs="+", help="channels to compare (default all)")
    n.add_argument("--diff-wav", action="store_true", help="also write the difference as a WAV file")
    n.add_argument("--diff-gain-db", type=float, help="gain on the difference WAV only (default 0: true level)")
    n.add_argument("--keep-work", action="store_true", help="keep the decoders' output files")

    i = sub.add_parser("init", help="write an example suite file")
    i.add_argument("path", nargs="?", default="suite.toml")

    s = sub.add_parser("signals", help="write every test signal a run feeds a device (to feed a device by hand)")
    s.add_argument("outdir", nargs="?", help="folder for the files (not needed with --list)")
    s.add_argument("--rate", type=int, default=88200, help="PCM rate of the test signals (default 88200)")
    s.add_argument("--class", dest="klass", choices=["A", "B"], default="A",
                   help="A: DSF files for a DSD to PCM converter (default), B: WAV files for a PCM to DSD modulator")
    s.add_argument("--profile", choices=["quick", "full"], default="quick")
    s.add_argument("--only", nargs="+", metavar="TEST", help="write the signals of these tests only (names as for run --only)")
    s.add_argument("--rates", type=int, nargs="*", default=[], help="extra DSD rates for the rate table, for example 5644800 11289600")
    s.add_argument("--list", action="store_true", help="print the catalogue of test signals and what each is for, then exit")

    sub.add_parser("versions", help="print tool versions")
    a = ap.parse_args(argv)

    if a.cmd == "run":
        from .run import run_suite
        _, failed = run_suite(a.suite, a.out, a.profile, a.only, plan=a.plan, verbose=a.verbose, jobs=a.jobs,
                              cache=False if a.no_cache else None)
        return EXIT_TESTS_FAILED if failed else EXIT_OK
    elif a.cmd == "quick":
        from .adapters import PRESETS, unknown_name_message
        from .run import run_suite
        if a.converter == "reference":  # both halves of the reference chain
            devs = [("reference decoder", "A", 'out_rate = 44100'), ("reference modulator", "B", "")]
            spec = ["[suite]", 'name = "quick: reference chain"', f'profile = "{a.profile}"', f"out = {json.dumps(a.out)}"]
            for name, k, extra in devs:
                spec += ["", "[[device]]", f'name = "{name}"', 'adapter = "reference"', f'class = "{k}"']
                spec += [extra] if extra else []
        else:
            if not a.command and a.converter not in PRESETS:
                raise UserError(unknown_name_message(a.converter))
            spec = ["[suite]", f'name = {json.dumps("quick: " + a.converter)}', f'profile = "{a.profile}"', f"out = {json.dumps(a.out)}", "", "[[device]]",
                    f"name = {json.dumps(a.converter)}", f"adapter = {json.dumps('cli' if a.command else a.converter)}",
                    f'class = "{a.klass}"']
            if a.command and a.args:
                raise UserError("--args goes with a preset; with --command, put the arguments in the command itself")
            if a.command:
                spec.append(f"command = {json.dumps(a.command)}")
            elif a.args:
                spec.append(f"args = {json.dumps(a.args)}")
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "suite.toml"
            p.write_text("\n".join(spec) + "\n")
            _, failed = run_suite(p, a.out, a.profile, plan=a.plan, verbose=a.verbose, source=f"dsd-measure quick {a.converter}",
                                  jobs=a.jobs, cache=False if a.no_cache else None)
        return EXIT_TESTS_FAILED if failed else EXIT_OK
    elif a.cmd == "null":
        from .nulltest.run import load_suite, options_from, run_null
        sdev, ncfg = load_suite(a.suite) if a.suite else ([], {})
        cfg = dict(ncfg)
        for k in ("trim_start", "trim_end", "start", "duration", "rate", "max_delay", "polarity", "gain", "channels",
                  "diff_gain_db"):
            if getattr(a, k) is not None:
                cfg[k] = getattr(a, k)
        if a.diff_wav:
            cfg["diff_wav"] = True
        items = list(a.items)
        source = a.source
        if not source and items and (Path(items[0]).suffix.lower() in (".dsf", ".dff") or Path(items[0]).is_file()):
            source = items.pop(0)
        source = source or cfg.get("source")
        devs = a.device + items or cfg.get("devices", [])
        if len(devs) == 1 and not re.fullmatch(r"reference(@\d+)?", devs[0].strip()):
            devs = ["reference"] + devs  # one decoder named: compare it with the built-in reference
        if not source or len(devs) < 2:
            raise UserError("null needs a DSD file and a decoder to compare, for example: dsd-measure null track.dsf ffmpeg "
                            "(the built-in reference decoder is the baseline); see dsd-measure null --help")
        res = run_null(source, devs, options_from(cfg), a.out or cfg.get("out", "null-report"), sdev, a.keep_work)
        if res and res.get("untrustworthy"):
            return EXIT_TESTS_FAILED  # the report is written, but a pair could not be aligned
    elif a.cmd == "init":
        from .run import EXAMPLE_SUITE
        Path(a.path).write_text(EXAMPLE_SUITE)
        print(f"wrote {a.path}")
    elif a.cmd == "signals":
        from . import plan as pl
        if a.list:
            print(pl.list_signals())
            return 0
        if not a.outdir:
            ap.error("signals needs a folder to write to, or --list")
        out = Path(a.outdir)
        out.mkdir(parents=True, exist_ok=True)
        from .adapters import write_signal_set
        m = write_signal_set(out, a.klass, a.profile, a.rate, rates=a.rates, only=a.only)
        print(f"wrote {len(m['files'])} test signals (class {a.klass}, profile {a.profile}) and signals.json to {out}")
    elif a.cmd == "gate":
        from . import gate
        if a.scale <= 0:
            raise UserError("--scale must be above 0")
        return EXIT_OK if gate.run(a.old, a.new, a.scale, a.json_out) else EXIT_TESTS_FAILED
    elif a.cmd == "cache":
        from . import stimcache
        if a.key:
            print(stimcache.gate_key())
            return EXIT_OK
        if a.clear:
            print(f"deleted {stimcache.clear() / 2**20:.1f} MiB of cached test signals")
        u = stimcache.usage()
        print(f"{u['directory']}: {u['entries']} test signals, {u['bytes'] / 2**20:.1f} MiB (limit {u['limit_bytes'] / 2**20:.0f} MiB)"
              + ("" if stimcache.enabled() else "; the cache is switched off (DSD_MEASURE_NO_CACHE)"))
    elif a.cmd == "versions":
        from .run import versions
        print(json.dumps(versions(), indent=1))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
