"""Command line: ``dsd-measure run|quick|signals|init|versions``."""

import argparse
import json
import sys
import tempfile
from pathlib import Path

from . import __version__


def main(argv=None):
    ap = argparse.ArgumentParser(prog="dsd-measure", description="Reproducible measurements for DSD and PCM converters.")
    ap.add_argument("--version", action="version", version=__version__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="run a suite file (TOML) and write a report")
    r.add_argument("suite")
    r.add_argument("-o", "--out")
    r.add_argument("--profile", choices=["quick", "full"])
    r.add_argument("--only", nargs="*", help="run only these tests (see docs/options.md)")

    q = sub.add_parser("quick", help="measure one converter with the quick profile")
    q.add_argument("converter", help="'reference' or a tool preset (dsd2pcm, sox-dsd, sacd_extract) or any name with --command")
    q.add_argument("--command", help="command template with {input} and {output}")
    q.add_argument("--class", dest="klass", choices=["A", "B"], default="A", help="A: DSD to PCM, B: PCM to DSD")
    q.add_argument("-o", "--out", default="report")
    q.add_argument("--profile", choices=["quick", "full"], default="quick")

    i = sub.add_parser("init", help="write an example suite file")
    i.add_argument("path", nargs="?", default="suite.toml")

    s = sub.add_parser("signals", help="write the test signals as WAV files (to feed a device by hand)")
    s.add_argument("outdir")
    s.add_argument("--rate", type=int, default=88200)

    sub.add_parser("versions", help="print tool versions")
    a = ap.parse_args(argv)

    if a.cmd == "run":
        from .run import run_suite
        run_suite(a.suite, a.out, a.profile, a.only)
    elif a.cmd == "quick":
        from .run import run_suite
        if a.converter == "reference":  # both halves of the reference chain
            devs = [("reference decoder", "A", 'out_rate = 44100'), ("reference modulator", "B", "")]
            spec = ["[suite]", f'profile = "{a.profile}"', f'out = "{a.out}"']
            for name, k, extra in devs:
                spec += ["", "[[device]]", f'name = "{name}"', 'adapter = "reference"', f'class = "{k}"']
                spec += [extra] if extra else []
        else:
            spec = ["[suite]", f'profile = "{a.profile}"', f'out = "{a.out}"', "", "[[device]]",
                    f'name = "{a.converter}"', f'adapter = "{"cli" if a.command else a.converter}"',
                    f'class = "{a.klass}"']
            if a.command:
                spec.append(f"command = {json.dumps(a.command)}")
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "suite.toml"
            p.write_text("\n".join(spec) + "\n")
            run_suite(p, a.out, a.profile)
    elif a.cmd == "init":
        from .run import EXAMPLE_SUITE
        Path(a.path).write_text(EXAMPLE_SUITE)
        print(f"wrote {a.path}")
    elif a.cmd == "signals":
        from . import signals as sg
        from .levels import PEAK_DBFS, REF_DBFS
        from .wavio import write_wav
        out = Path(a.outdir)
        out.mkdir(parents=True, exist_ok=True)
        n = a.rate * 6
        f = sg.coherent_freq(1000, 352800, 2**18)
        for name, x in (("tone_1k_0dbsacd", sg.sine(f, REF_DBFS, a.rate, n)),
                        ("tone_1k_peak", sg.sine(f, PEAK_DBFS, a.rate, n)),
                        ("tone_15k_m12", sg.sine(sg.coherent_freq(15000, 352800, 2**18), -12.0, a.rate, n)),
                        ("multitone", sg.multitone_standard(fs=a.rate)[0]),
                        ("jtest_44100", sg.jtest(44100, 44100 * 12))):
            write_wav(out / f"{name}.wav", x, 44100 if name.startswith("jtest") else a.rate, "pcm32")
        print(f"wrote test signals to {out}")
    elif a.cmd == "versions":
        from .run import versions
        print(json.dumps(versions(), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
