"""Command line: ``dsd-measure run|quick|signals|init|versions``."""

import argparse
import json
import sys
import tempfile
import tomllib
from pathlib import Path

from . import __version__

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
    except (OSError, ValueError, KeyError, RuntimeError, tomllib.TOMLDecodeError) as e:
        print(f"dsd-measure: error: {type(e).__name__}: {e}", file=sys.stderr)
        return EXIT_FATAL


def _main(argv=None):
    ap = argparse.ArgumentParser(prog="dsd-measure", description="Reproducible measurements for DSD and PCM converters.")
    ap.add_argument("--version", action="version", version=__version__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="run a suite file (TOML) and write a report")
    r.add_argument("suite")
    r.add_argument("-o", "--out")
    r.add_argument("--profile", choices=["quick", "full"])
    r.add_argument("--only", nargs="*", help="run only these tests (see docs/options.md)")
    r.add_argument("--plan", action="store_true", help="print what would be measured, against what and with which signals, then exit")
    r.add_argument("-v", "--verbose", action="store_true", help="show device details while running")

    q = sub.add_parser("quick", help="measure one converter with the quick profile")
    q.add_argument("converter", help="'reference' or a tool preset (dsd2pcm, sox-dsd, sacd_extract) or any name with --command")
    q.add_argument("--command", help="command template with {input} and {output}")
    q.add_argument("--class", dest="klass", choices=["A", "B"], default="A", help="A: DSD to PCM, B: PCM to DSD")
    q.add_argument("-o", "--out", default="report")
    q.add_argument("--profile", choices=["quick", "full"], default="quick")
    q.add_argument("--plan", action="store_true", help="print what would be measured, then exit")
    q.add_argument("-v", "--verbose", action="store_true", help="show device details while running")

    n = sub.add_parser("null", help="real-music null test: how much do two decoders differ on your DSD file?")
    n.add_argument("--source", help="DSF or DFF file (or [null] source in --suite)")
    n.add_argument("--device", action="append", default=[], help="reference[@RATE], NAME=COMMAND with {input} and {output}, "
                   "or a [[device]] name from --suite; give two or more (the first is the baseline)")
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
        _, failed = run_suite(a.suite, a.out, a.profile, a.only, plan=a.plan, verbose=a.verbose)
        return EXIT_TESTS_FAILED if failed else EXIT_OK
    elif a.cmd == "quick":
        from .run import run_suite
        if a.converter == "reference":  # both halves of the reference chain
            devs = [("reference decoder", "A", 'out_rate = 44100'), ("reference modulator", "B", "")]
            spec = ["[suite]", 'name = "quick: reference chain"', f'profile = "{a.profile}"', f"out = {json.dumps(a.out)}"]
            for name, k, extra in devs:
                spec += ["", "[[device]]", f'name = "{name}"', 'adapter = "reference"', f'class = "{k}"']
                spec += [extra] if extra else []
        else:
            spec = ["[suite]", f'name = {json.dumps("quick: " + a.converter)}', f'profile = "{a.profile}"', f"out = {json.dumps(a.out)}", "", "[[device]]",
                    f"name = {json.dumps(a.converter)}", f"adapter = {json.dumps('cli' if a.command else a.converter)}",
                    f'class = "{a.klass}"']
            if a.command:
                spec.append(f"command = {json.dumps(a.command)}")
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "suite.toml"
            p.write_text("\n".join(spec) + "\n")
            _, failed = run_suite(p, a.out, a.profile, plan=a.plan, verbose=a.verbose, source=f"dsd-measure quick {a.converter}")
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
        source = a.source or cfg.get("source")
        devs = a.device or cfg.get("devices", [])
        if not source or not devs:
            ap.error("null needs --source and two or more --device (or a [null] table with source and devices)")
        run_null(source, devs, options_from(cfg), a.out or cfg.get("out", "null-report"), sdev, a.keep_work)
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
    elif a.cmd == "versions":
        from .run import versions
        print(json.dumps(versions(), indent=1))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
