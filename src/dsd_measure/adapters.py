"""Adapters: turn a device or tool into DSD -> PCM (class A) or PCM -> DSD (class B).

Every adapter takes and returns arrays, so the runner never cares how the work is done.
File-based adapters write the inputs to a work directory, run the command, read the output and
record the command and the SHA-256 of both files for provenance. Adapters never modify the
signal; the optional ``gain_db`` is applied to the output, recorded, and exists only to undo a
documented level-convention difference (for example a tool that maps WAV full scale to 0 dB SACD).
"""

import hashlib
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np

from . import decode as _decode
from . import encode as _encode
from .dsf import read_dsf, write_dff, write_dsf
from .levels import PEAK_PCT
from .wavio import read_wav, write_wav


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_array(a):
    return hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest()


def _run_checked(cmd, **kw):
    """subprocess.run that keeps the tool's own error text in the exception."""
    r = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, **kw)
    if r.returncode:
        tail = r.stderr.decode(errors="replace").strip().splitlines()[-3:]
        raise RuntimeError(f"command failed ({r.returncode}): {' | '.join(tail)}")


def _pick(out, inp):
    """Mono in, mono out; stereo in, stereo out (files always hold a channel axis)."""
    return out if np.ndim(inp) == 2 else out[0]


class Adapter:
    """Base: a device. ``klass`` is "A" (DSD to PCM) or "B" (PCM to DSD)."""

    klass = "A"
    kind = "base"
    #: DSD rate fed to a class A device, or requested from a class B modulator (samples per second)
    dsd_rate = 2822400
    #: extra DSD rates measured in the rate table (a list of rates), see ``measure``
    rates = ()

    def __init__(self, name, gain_db=0.0, dsd_rate=2822400, rates=(), **opts):
        self.name = name
        self.gain_db = float(gain_db)
        self.dsd_rate = int(dsd_rate)
        self.rates = tuple(int(r) for r in rates)
        self.opts = opts
        self.log = []  # provenance records, one per call

    def describe(self):
        return {"name": self.name, "class": self.klass, "adapter": self.kind, "gain_db": self.gain_db,
                "dsd_rate": self.dsd_rate}

    def dsd_to_pcm(self, bits, rate):  # pragma: no cover - interface
        raise NotImplementedError

    def pcm_to_dsd(self, x, fs):  # pragma: no cover - interface
        raise NotImplementedError

    def tool_versions(self):
        return {}


class Reference(Adapter):
    """The reference chain: the long-FIR decoder (class A) or the reference modulator (class B)."""

    kind = "reference"

    def __init__(self, name="reference", klass="A", out_rate=352800, **opts):
        super().__init__(name, **opts)
        self.klass = klass
        self.out_rate = int(out_rate)

    def describe(self):
        d = super().describe()
        d["detail"] = {"out_rate": self.out_rate,
                       "decoder": _decode.total_taps_report(self.dsd_rate, self.out_rate),
                       "modulator": "order 8 down to 5 by the stability guard (see design)"}
        return d

    def dsd_to_pcm(self, bits, rate):
        g = 10 ** (self.gain_db / 20)
        if np.ndim(bits) == 2:
            return np.array([_decode.decode(b, rate, self.out_rate) for b in bits]) * g, self.out_rate
        return _decode.decode(bits, rate, self.out_rate) * g, self.out_rate

    def pcm_to_dsd(self, x, fs):
        # A real encoder protects itself from input above its peak level: the reference clips
        # the input at the 71.43 % peak level and says so (``clipped`` in the adapter log).
        lim = PEAK_PCT / 100 * 1.0005  # a hair of tolerance for the peak-level test signal itself
        x = np.asarray(x, dtype=np.float64)
        clipped = bool(np.max(np.abs(x)) > lim)
        x = np.clip(x, -lim, lim)
        chans = x if x.ndim == 2 else x[None]
        out = []
        for c in chans:
            bits, info = _encode.encode(c, fs, self.dsd_rate)
            out.append(bits)
        self.log.append({"clipped_to_peak_level": clipped, "ntf": info["ntf"], "fallbacks": info["fallbacks"]})
        return (np.array(out) if x.ndim == 2 else out[0]), self.dsd_rate


class Cli(Adapter):
    """A command template with ``{input}`` and ``{output}``; works for any tool.

    Class A: ``{input}`` is a DSF file (a DFF file if ``input_ext = "dff"``), ``{output}`` a WAV
    (or FLAC if ``output_ext = "flac"``).
    Class B: ``{input}`` is a WAV, ``{output}`` a DSF.
    """

    kind = "cli"

    def __init__(self, name, command, klass="A", output_ext=None, input_ext="dsf", workdir=None,
                 timeout=3600, **opts):
        super().__init__(name, **opts)
        self.input_ext = input_ext
        self.command = command
        self.klass = klass
        self.output_ext = output_ext or ("wav" if klass == "A" else "dsf")
        self.timeout = timeout
        self.workdir = Path(workdir) if workdir else None
        self._n = 0

    def describe(self):
        d = super().describe()
        d["command"] = self.command
        return d

    def _run(self, in_path, out_path):
        cmd = self.command.format(input=shlex.quote(str(in_path)), output=shlex.quote(str(out_path)))
        _run_checked(cmd, shell=True, timeout=self.timeout)

    def _tmp(self):
        d = self.workdir or Path(tempfile.mkdtemp(prefix="dsd-measure-"))
        d.mkdir(parents=True, exist_ok=True)
        self._n += 1
        return d, self._n

    def dsd_to_pcm(self, bits, rate):
        d, n = self._tmp()
        i, o = d / f"in{n}.{self.input_ext}", d / f"out{n}.{self.output_ext}"
        (write_dff if self.input_ext == "dff" else write_dsf)(i, bits, rate)
        self._run(i, o)
        if o.suffix == ".flac":
            w = d / f"out{n}.wav"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(o), "-c:a", "pcm_f32le", str(w)], check=True)
            o = w
        y, fs = read_wav(o)
        self.log.append({"input_sha256": sha256_file(i), "output_sha256": sha256_file(o), "rate": fs})
        return _pick(y, bits) * 10 ** (self.gain_db / 20), fs

    def pcm_to_dsd(self, x, fs):
        d, n = self._tmp()
        i, o = d / f"in{n}.wav", d / f"out{n}.{self.output_ext}"
        write_wav(i, x, fs, "pcm32")
        self._run(i, o)
        bits, rate = read_dsf(o)
        self.log.append({"input_sha256": sha256_file(i), "output_sha256": sha256_file(o), "rate": rate})
        return _pick(bits, x), rate


#: ``modulator = "auto"``: the SoX-DSD filter per DSD rate used in Archimago's 2022 DSD tests
#: (CLANS-8, -7 and -6), also used by the dsd2pcm quality tools (credited in docs/reference-tools.md).
AUTO_SDM = {64: "clans-8", 128: "clans-7", 256: "clans-6"}


class ReftoolSox(Adapter):
    """SoX-DSD run as a black box through the pinned container wrapper (``tools/reftool.sh``).

    Class A: DSD to 32-bit float PCM at ``out_rate``. Class B: PCM to DSD64 with the ``sdm`` or
    ``clans`` modulator. SoX-DSD writes output 6.02 dB below the input level, so ``gain_db``
    defaults to +6.0206 to bring the output back to the input level (recorded in the report).
    """

    kind = "sox-dsd"

    def __init__(self, name, reftool, klass="A", out_rate=352800, modulator="clans-8", workdir=None,
                 gain_db=6.0206, **opts):
        super().__init__(name, gain_db=gain_db, **opts)
        self.reftool, self.klass, self.out_rate, self.modulator = str(reftool), klass, int(out_rate), modulator
        self.workdir = Path(workdir) if workdir else Path(tempfile.mkdtemp(prefix="dsd-measure-"))
        self._n = 0

    def describe(self):
        d = super().describe()
        d["detail"] = {"reftool": "container wrapper", "modulator": self.modulator, "out_rate": self.out_rate}
        return d

    def _call(self, args):
        _run_checked([self.reftool, "sox-dsd", str(self._in), str(self._out)] + args)

    def _dirs(self):
        self._n += 1
        base = self.workdir / f"c{self._n}"
        self._in, self._out = base / "in", base / "out"
        self._in.mkdir(parents=True, exist_ok=True)
        self._out.mkdir(parents=True, exist_ok=True)

    def dsd_to_pcm(self, bits, rate):
        self._dirs()
        write_dsf(self._out / "x.dsf", bits, rate)  # the wrapper reads the DSD from the output folder
        self._call(["/out/x.dsf", "-e", "floating-point", "-b", "32", "/out/x.wav", "rate", "-v", str(self.out_rate)])
        y, fs = read_wav(self._out / "x.wav")
        self.log.append({"input_sha256": sha256_file(self._out / "x.dsf"),
                         "output_sha256": sha256_file(self._out / "x.wav"), "rate": fs})
        return _pick(y, bits) * 10 ** (self.gain_db / 20), fs

    def pcm_to_dsd(self, x, fs):
        self._dirs()
        write_wav(self._in / "x.wav", x, fs, "pcm32")
        mod = AUTO_SDM.get(self.dsd_rate // 44100, "clans-8") if self.modulator == "auto" else self.modulator
        self._call(["/in/x.wav", "/out/x.dsf", "rate", "-v", str(self.dsd_rate), "sdm", "-f", mod,
                    "-t", "32", "-n", "32"])
        bits, rate = read_dsf(self._out / "x.dsf")
        self.log.append({"input_sha256": sha256_file(self._in / "x.wav"),
                         "output_sha256": sha256_file(self._out / "x.dsf"), "rate": rate})
        return _pick(bits, x), rate


class Import(Adapter):
    """Results produced elsewhere: reads ``<dir>/<signal id>.wav`` (class A) or ``.dsf`` (class B).

    Used for the foobar2000 SACD plug-in and for recordings. The signals to feed the device are
    written with ``dsd-measure signals``; the outputs go back in the same folder under the same name.
    """

    kind = "import"

    def __init__(self, name, directory, klass="A", **opts):
        super().__init__(name, **opts)
        self.dir = Path(directory)
        self.klass = klass
        self.current = None  # set by the runner before each call

    def dsd_to_pcm(self, bits, rate):
        p = self.dir / f"{self.current}.wav"
        if not p.exists():
            raise FileNotFoundError(p)
        y, fs = read_wav(p)
        self.log.append({"output_sha256": sha256_file(p), "rate": fs})
        return _pick(y, bits) * 10 ** (self.gain_db / 20), fs

    def pcm_to_dsd(self, x, fs):
        p = self.dir / f"{self.current}.dsf"
        if not p.exists():
            raise FileNotFoundError(p)
        bits, rate = read_dsf(p)
        self.log.append({"output_sha256": sha256_file(p), "rate": rate})
        return _pick(bits, x), rate


#: Command presets for tools run as black boxes. Edit paths through the suite file.
PRESETS = {
    "dsd2pcm": "dsd2pcm {input} -o {output}",
    "sox-dsd": "sox {input} -b 32 -e floating-point {output} rate -v 352800",
    "sacd_extract": "sacd_extract -i {input} -p -o {output}",
}


def make_adapter(spec):
    """Build an adapter from a suite-file table."""
    spec = dict(spec)
    kind = spec.pop("adapter", "reference")
    name = spec.pop("name", kind)
    klass = spec.pop("class", "A")
    if kind == "reference":
        return Reference(name, klass=klass, **spec)
    if kind == "cli":
        return Cli(name, klass=klass, **spec)
    if kind == "sox-dsd" and "reftool" in spec:
        return ReftoolSox(name, klass=klass, **spec)
    if kind in PRESETS:
        cmd = spec.pop("command", PRESETS[kind])
        if shutil.which(cmd.split()[0]) is None and "/" not in cmd.split()[0]:
            raise FileNotFoundError(f"adapter {kind}: {cmd.split()[0]} not found on PATH (set command = ...)")
        return Cli(name, cmd, klass=klass, **spec)
    if kind == "import":
        return Import(name, klass=klass, **spec)
    raise ValueError(f"unknown adapter {kind}")
