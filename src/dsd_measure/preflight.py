"""Pre-flight: run each device once on a short test signal before any measuring starts.

A missing program, a bad flag or a tool that writes nothing then fails in about a second, with the
tool's own error printed once, instead of after a minute of identical errors and an empty report.
"""

import os
import shlex
import shutil
import time

import numpy as np

from . import outformat as of
from . import signals as sg
from .errors import MissingTool, UserError
from .levels import REF_DBFS

#: Length of the test signal (seconds at the PCM source rate).
SECS = 0.5
#: The most a pre-flight conversion may take (seconds); a real conversion of 0.5 s takes about one.
TIMEOUT = 120


def exe_of(command, shell=False):
    """The program a command template starts, or None when it cannot be told."""
    try:
        words = shlex.split(command)
    except ValueError:
        return None
    return words[0] if words else None


def check_program(command, shell=False, what="the command"):
    """Raise ``UserError`` when the program a command starts is not installed."""
    exe = exe_of(command, shell)
    if exe is None or shell:
        return exe
    if "/" in exe:
        if not (os.path.isfile(exe) and os.access(exe, os.X_OK)):
            raise UserError(f"{what}: {exe} is not an executable file. Check the path.")
    elif shutil.which(exe) is None:
        raise MissingTool(f"{what}: {exe} is not on PATH. Install it, or give its full path in the command.")
    return exe


def _one_line(text):
    return " ".join(str(text).split())


def run(adapter, in_rate, log):
    """Run ``adapter`` once on a short tone. Returns a record for the report's provenance.

    Raises ``UserError`` with the tool's own error when the device fails or returns nothing usable.
    The adapter's provenance log is left as it was.
    """
    from .adapters import Cli, Import, Recorder, ReftoolSox
    if isinstance(adapter, Import):
        if not adapter.dir.is_dir():
            raise UserError(f"{adapter.name}: the folder {adapter.dir} does not exist")
        return {"checked": "folder exists"}
    if isinstance(adapter, Cli):
        check_program(adapter.command, adapter.shell, f"{adapter.name}")
    if isinstance(adapter, ReftoolSox) and not os.access(adapter.reftool, os.X_OK):
        raise UserError(f"{adapter.name}: {adapter.reftool} is not an executable file")
    if isinstance(adapter, Recorder) or adapter.kind == "reference":
        return {"checked": "built-in"}
    from .measure import Chain
    n = int(SECS * in_rate)
    x = np.sin(2 * np.pi * sg.coherent_freq(1000, 352800, 2**18) * np.arange(n) / in_rate) * 10 ** (REF_DBFS / 20)
    mark = len(adapter.log)
    t0 = time.time()
    full_timeout = getattr(adapter, "timeout", None)
    if full_timeout is not None:
        adapter.timeout = min(full_timeout, TIMEOUT)
    try:
        try:
            y, fs, _ = Chain(adapter, in_rate).run(x, "preflight")
        except UserError:
            raise
        except Exception as e:
            alt = getattr(adapter, "input_ext_fallback", None)
            if not alt or alt == adapter.input_ext:
                raise UserError(f"{adapter.name}: could not convert a {SECS:g} s test signal: {_one_line(e)}") from None
            # some builds of a tool read DSD from DFF but not from DSF (distribution ffmpeg): try the other file type
            first, adapter.input_ext = adapter.input_ext, alt
            try:
                y, fs, _ = Chain(adapter, in_rate).run(x, "preflight")
            except Exception:
                adapter.input_ext = first
                raise UserError(f"{adapter.name}: could not convert a {SECS:g} s test signal "
                                f"(tried {first.upper()} and {alt.upper()} files): {_one_line(e)}") from None
            log(f"Pre-flight: {adapter.name} could not read DSF files here; it reads {alt.upper()}, so it is given {alt.upper()} files.")
    finally:
        if full_timeout is not None:
            adapter.timeout = full_timeout
        fmt = adapter.output_format() if hasattr(adapter, "output_format") and len(adapter.log) > mark else None
        del adapter.log[mark:]
    y = np.asarray(y)
    if y.size == 0 or not np.all(np.isfinite(y)):
        raise UserError(f"{adapter.name}: the test signal came back empty or not a number; check the command writes the whole file")
    if adapter.klass == "A":
        if float(np.max(np.abs(y))) < 1e-6:
            raise UserError(f"{adapter.name}: the test signal came back silent; check the command and its level options")
        if abs(y.shape[-1] / fs - SECS) > 0.25:
            raise UserError(f"{adapter.name}: a {SECS:g} s test signal came back {y.shape[-1] / fs:.2f} s long; "
                            "check the command converts the whole file")
    rec = {"checked": "converted a short test signal", "seconds": round(time.time() - t0, 2), "rate": int(fs)}
    if fmt:
        rec["output_format"] = of.summary(fmt)
        log(f"Pre-flight: {adapter.name} converted a {SECS:g} s test signal: {of.name_of(fmt)}, {fmt['rate'] / 1000:g} kHz. OK")
        warn = of.warning(fmt, getattr(adapter, "command", ""))
        if warn:
            rec["warning"] = warn
            log(f"  warning: {warn}")
    else:
        log(f"Pre-flight: {adapter.name} converted a {SECS:g} s test signal. OK")
    return rec
