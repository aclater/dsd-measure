"""Decoders as devices for the null test: the reference decoder, or any command-line tool.

A device turns the one source file into a track. The command devices work like the ``cli`` adapter:
a template with ``{input}`` and ``{output}`` that is run once on the whole file, so a tool sees the
same file it would see from a user. The source is passed untouched when it is already in the format
the device wants, and converted bit-exactly otherwise.
"""

import re
import shlex
import shutil
from math import ceil
from pathlib import Path

import numpy as np

from .. import decode as _decode
from ..adapters import run_checked, substitute
from ..dsdstream import convert, sha256_path
from .tracks import WavTrack

PRESETS = {
    "dsd2pcm": "dsd2pcm {input} -o {output}",
    "sox-dsd": "sox {input} -b 32 -e floating-point {output} rate -v 352800",
    "sacd_extract": "sacd_extract -i {input} -p -o {output}",
}


class RefDecoderTrack:
    """The reference decoder as a lazy track: only the range asked for is decoded.

    A range is decoded from the DSD bits with enough real neighbouring bits on both sides to cover
    the whole filter chain, so the result equals decoding the whole file in one go.
    """

    def __init__(self, dsd, out_rate, passband=20000.0):
        self.dsd, self.rate, self.passband = dsd, int(out_rate), passband
        if dsd.rate % self.rate:
            raise ValueError(f"the reference decoder needs an output rate that divides {dsd.rate} Hz, not {self.rate} Hz")
        self.m = dsd.rate // self.rate
        self.channels = dsd.channels
        self.length = -(-dsd.samples // self.m)
        keep, fs, span, scale = _decode.keep_edge(self.rate, passband), dsd.rate, 0.0, 1
        for q in _decode.stage_plan(dsd.rate, self.rate):
            taps, fs_out = _decode.decimator(fs, q, keep)
            span += (len(taps) - 1) / 2 * scale
            fs, scale = fs_out, scale * q
        self.pad = int(ceil(span / self.m) + 2) * self.m  # input bits of context each side

    def read(self, ch, start, stop):
        n = stop - start
        if n <= 0:
            return np.zeros(0)
        a = start * self.m - self.pad
        bits = self.dsd.bits(ch, a, stop * self.m + self.pad)
        y = _decode.decode(bits.astype(np.float64), self.dsd.rate, self.rate, self.passband)
        k = self.pad // self.m
        return y[k: k + n]


class ReferenceDevice:
    """The built-in long linear-phase decoder at ``out_rate`` (it must divide the DSD rate)."""

    kind = "reference"

    def __init__(self, name=None, out_rate=352800, passband=20000.0, gain_db=0.0, **_):
        self.out_rate, self.passband, self.gain_db = int(out_rate), float(passband), float(gain_db)
        self.name = name or f"reference {self.out_rate / 1000:g} kHz"

    def describe(self):
        return {"name": self.name, "adapter": "reference", "out_rate": self.out_rate, "passband_hz": self.passband,
                "gain_db": self.gain_db}

    def prepare(self, source, work):
        t = RefDecoderTrack(source, self.out_rate, self.passband)
        info = {"filter": _decode.total_taps_report(source.rate, self.out_rate)}
        return _Scaled(t, 10 ** (self.gain_db / 20)), info


class _Scaled:
    def __init__(self, track, g):
        self.t, self.g = track, g
        self.rate, self.channels, self.length = track.rate, track.channels, track.length

    def read(self, ch, start, stop):
        x = self.t.read(ch, start, stop)
        return x * self.g if self.g != 1.0 else x


class FileDevice:
    """A command template run once on the source file; ``{input}`` and ``{output}`` are file paths.

    As for the ``cli`` adapter, the template is split into words and run without a shell; set
    ``shell = true`` (suite file) to run it with ``/bin/sh -c``.
    """

    kind = "cli"

    def __init__(self, name, command, input_ext="dsf", output_ext="wav", gain_db=0.0, timeout=7200, shell=False, **_):
        self.shell = bool(shell)
        self.name, self.command, self.gain_db, self.timeout = name, command, float(gain_db), timeout
        self.input_ext, self.output_ext = input_ext.lower().lstrip("."), output_ext.lower().lstrip(".")
        if self.input_ext not in ("dsf", "dff"):
            raise ValueError(f"{name}: input_ext must be dsf or dff")

    def describe(self):
        return {"name": self.name, "adapter": "cli", "command": self.command, "shell": self.shell,
                "input_ext": self.input_ext, "gain_db": self.gain_db}

    def prepare(self, source, work):
        work = Path(work)
        work.mkdir(parents=True, exist_ok=True)
        safe = re.sub(r"[^A-Za-z0-9_-]+", "-", self.name).strip("-") or "device"
        if source.kind == self.input_ext:
            inp = source.path
        else:
            inp = work / f"{safe}-input.{self.input_ext}"
            convert(source.path, inp, self.input_ext)
        out = work / f"{safe}-output.{self.output_ext}"
        if self.shell:
            cmd = substitute(self.command, input=shlex.quote(str(inp)), output=shlex.quote(str(out)))
        else:
            cmd = [substitute(w, input=str(inp), output=str(out)) for w in shlex.split(self.command)]
        run_checked(cmd, shell=self.shell, timeout=self.timeout)
        if not out.exists():
            raise RuntimeError(f"{self.name}: the command ran but wrote no file at the {{output}} path")
        info = {"output_sha256": sha256_path(out)}
        if inp != source.path:
            info["converted_input_sha256"] = sha256_path(inp)
            info["input_conversion"] = f"{source.kind} to {self.input_ext}, bit-exact"
            inp.unlink()
        if out.suffix.lower() == ".flac":
            wav = out.with_suffix(".wav")
            run_checked(["ffmpeg", "-v", "error", "-y", "-i", str(out), "-c:a", "pcm_f32le", str(wav)], timeout=self.timeout)
            out.unlink()
            out = wav
        elif out.suffix.lower() != ".wav":
            raise ValueError(f"{self.name}: output_ext must be wav or flac")
        return WavTrack(out, 10 ** (self.gain_db / 20)), info


def from_suite_spec(spec):
    """A device from a suite-file ``[[device]]`` table."""
    spec = dict(spec)
    kind = spec.pop("adapter", "reference")
    name = spec.pop("name", kind)
    spec.pop("class", None)
    if kind == "reference":
        return ReferenceDevice(name, **spec)
    if kind == "cli":
        return FileDevice(name, **spec)
    if kind in PRESETS and "reftool" not in spec:
        cmd = spec.pop("command", PRESETS[kind])
        exe = shlex.split(cmd)[0]
        if "/" not in exe and shutil.which(exe) is None:
            raise FileNotFoundError(f"device {name}: {exe} not found on PATH (set command = ...)")
        return FileDevice(name, cmd, **spec)
    raise ValueError(f"device {name}: the null test runs the reference decoder and command-line tools "
                     f"(adapter 'reference', 'cli' or a preset); for a container tool use a cli device with "
                     f"tools/reftool-file.sh")


def parse_device(text, suite_devices=None):
    """A device from a ``--device`` value.

    ``reference`` or ``reference@RATE``: the built-in decoder (default 352800 Hz).
    ``NAME=COMMAND``: a command template with ``{input}`` and ``{output}``; start the command with
    ``dff:`` to give the tool a DFF file instead of a DSF file.
    Anything else is looked up by name among the suite file's ``[[device]]`` tables.
    """
    t = text.strip()
    m = re.fullmatch(r"reference(?:@(\d+))?", t)
    if m:
        return ReferenceDevice(out_rate=int(m.group(1) or 352800))
    if "=" in t and "{input}" in t:
        name, cmd = t.split("=", 1)
        ext = "dsf"
        if cmd.lstrip().startswith("dff:"):
            ext, cmd = "dff", cmd.lstrip()[4:].lstrip()
        return FileDevice(name.strip(), cmd.strip(), input_ext=ext)
    for spec in suite_devices or []:
        if spec.get("name") == t:
            return from_suite_spec(spec)
    raise ValueError(f"unknown device {text!r}: use reference, reference@RATE, NAME=COMMAND (with {{input}} "
                     f"and {{output}}), or the name of a [[device]] in --suite")
