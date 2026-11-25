"""Adapters: turn a device or tool into DSD -> PCM (class A) or PCM -> DSD (class B).

Every adapter takes and returns arrays, so the runner never cares how the work is done.
File-based adapters write the inputs to a work directory, run the command, read the output and
record the command and the SHA-256 of both files for provenance. Adapters never modify the
signal; the optional ``gain_db`` is applied to the output, recorded, and exists only to undo a
documented level-convention difference (for example a tool that maps WAV full scale to 0 dB SACD).
"""

import hashlib
import os
import re
import shlex
import shutil
import signal
import subprocess
import tempfile
from pathlib import Path

import numpy as np

from . import decode as _decode
from . import encode as _encode
from .dsf import read_dsf, write_dff, write_dsf
from .errors import MissingTool, UserError
from .levels import PEAK_PCT
from .outformat import audio_format
from .wavio import read_wav, write_wav


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def program_identity(command, version_command=None, timeout=20):
    """Who a program is, for the provenance: ``{"program", "path", "sha256", "version"}``.

    ``command`` is the program (or a command line whose first word is the program). The path is resolved the way a run
    resolves it and the file at that path is hashed; the version is the first line the program prints for
    ``--version`` (then ``-version``), or for ``version_command`` when one is given. A field that cannot be found is None:
    a missing version is recorded, never guessed.
    """
    try:
        words = shlex.split(str(command))
    except ValueError:
        words = str(command).split()
    exe = words[0] if words else ""
    rec = {"program": exe, "path": None, "sha256": None, "version": None}
    found = shutil.which(exe) if exe and "/" not in exe else (exe if exe and os.path.isfile(exe) else None)
    if found:
        real = os.path.realpath(found)
        rec["path"] = real
        try:
            rec["sha256"] = sha256_file(real)
        except OSError:
            pass
    tries = [shlex.split(version_command)] if version_command else ([[found or exe, "--version"], [found or exe, "-version"]] if exe else [])
    for cmd in tries:
        try:
            r = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, timeout=timeout, text=True, errors="replace")
        except (OSError, subprocess.TimeoutExpired):
            continue
        line = next((ln.strip() for ln in (r.stdout + "\n" + r.stderr).splitlines() if ln.strip()), "")
        if r.returncode == 0 and line:
            rec["version"] = line[:200]
            break
    return rec


def sha256_array(a):
    return hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest()


def run_checked(cmd, shell=False, timeout=3600):
    """Run a command in its own process group; keep the tool's error text in the exception.

    On a timeout, an error or Ctrl-C the whole group is killed, so a shell's children do not
    outlive the run.
    """
    p = subprocess.Popen(cmd, shell=shell, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.PIPE, start_new_session=True)
    try:
        _, err = p.communicate(timeout=timeout)
    except BaseException as e:  # TimeoutExpired, KeyboardInterrupt, anything else
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        p.communicate()
        if isinstance(e, subprocess.TimeoutExpired):
            raise TimeoutError(f"command timed out after {timeout} s and was killed") from None
        raise
    if p.returncode:
        tail = err.decode(errors="replace").strip().splitlines()[-3:]
        raise RuntimeError(f"command failed ({p.returncode}): {' | '.join(tail)}")


_PLACEHOLDER = re.compile(r"\{\{(input|output)\}\}|\{(input|output)\}")


def substitute(template, **values):
    """Replace ``{input}`` and ``{output}`` in ``template``; every other brace is left alone.

    ``{{input}}`` and ``{{output}}`` give the literal text ``{input}`` and ``{output}``.
    """
    def rep(m):
        if m.group(1):
            return "{" + m.group(1) + "}"
        return values[m.group(2)]
    return _PLACEHOLDER.sub(rep, template)


class _Work:
    """A work folder that removes itself (unless the user named one) when ``close`` is called."""

    def __init__(self, workdir=None):
        self.user = Path(workdir) if workdir else None
        self._tmp = None

    def path(self):
        if self.user:
            self.user.mkdir(parents=True, exist_ok=True)
            return self.user
        if self._tmp is None:
            self._tmp = tempfile.TemporaryDirectory(prefix="dsd-measure-")
        return Path(self._tmp.name)

    def discard(self, *paths):
        """Delete per-call files at once when the folder is ours (a named folder keeps them)."""
        if self.user is None:
            for p in paths:
                Path(p).unlink(missing_ok=True)

    def close(self):
        if self._tmp is not None:
            self._tmp.cleanup()
            self._tmp = None


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
        """Who the device is: its version and, for a program, the SHA-256 of its executable (recorded in the provenance).

        A version the user declares with ``version = "..."`` in the suite file is kept beside what was found.
        """
        d = {"adapter": self.kind}
        if self.opts.get("version"):
            d["declared_version"] = str(self.opts["version"])
        return d

    def output_format(self):
        """The narrowest PCM output format recorded in the provenance log (None if no file was read)."""
        from .outformat import narrowest
        return narrowest(e.get("output_format") for e in self.log)

    def close(self):
        """Remove any temporary files; safe to call more than once."""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


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

    def output_format(self):
        return {"container": "internal", "kind": "float", "bits": 64, "rate": self.out_rate, "channels": 1}

    def tool_versions(self):
        from . import REFERENCE_CHAIN_VERSION, __version__
        return {**super().tool_versions(), "program": "dsd-measure built-in reference chain", "version": __version__,
                "reference_chain": REFERENCE_CHAIN_VERSION}

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


class Recorder(Reference):
    """The reference chain that also writes what it is fed, one file per call tag.

    ``dsd-measure signals`` runs the whole measurement through it, so the files are exactly what a
    run feeds a device: a DSF per tag for class A (the DSD the reference modulator makes), a WAV per
    tag for class B. A device run by hand reads these files and writes ``<tag>.wav`` (class A) or
    ``<tag>.dsf`` (class B) for the ``import`` adapter. ``entries`` lists what was written.
    """

    kind = "recorder"

    def __init__(self, directory, klass="A", dsd_rate=2822400, out_rate=44100, **opts):
        super().__init__("signals", klass=klass, out_rate=out_rate, dsd_rate=dsd_rate, **opts)
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.current = None
        self.entries = []

    def _name(self, ext, data_hash):
        tag = self.current or "call"
        for e in self.entries:
            if e["tag"] == tag and e["samples_sha256"] == data_hash:
                return None  # the same stimulus again (a second analysis of one run)
        n = sum(1 for e in self.entries if e["tag"] == tag)
        return tag if n == 0 else f"{tag}_{n + 1}"

    def dsd_to_pcm(self, bits, rate):
        h = sha256_array(bits)
        name = self._name("dsf", h)
        if name:
            write_dsf(self.dir / f"{name}.dsf", bits, rate)
            self.entries.append({"tag": self.current or "call", "file": f"{name}.dsf", "sha256": sha256_file(self.dir / f"{name}.dsf"),
                                 "samples_sha256": h, "rate": int(rate),
                                 "channels": 1 if np.ndim(bits) == 1 else len(bits),
                                 "seconds": round(np.shape(bits)[-1] / rate, 3), "feeds": "DSD, to a class A device"})
        return super().dsd_to_pcm(bits, rate)

    def pcm_to_dsd(self, x, fs):
        h = sha256_array(np.asarray(x))
        name = self._name("wav", h)
        if name:
            write_wav(self.dir / f"{name}.wav", np.asarray(x, dtype=np.float64), fs, "pcm32")
            self.entries.append({"tag": self.current or "call", "file": f"{name}.wav", "sha256": sha256_file(self.dir / f"{name}.wav"),
                                 "samples_sha256": h, "rate": int(fs),
                                 "channels": 1 if np.ndim(x) == 1 else len(x),
                                 "seconds": round(np.shape(x)[-1] / fs, 3), "feeds": "PCM, to a class B device"})
        return super().pcm_to_dsd(x, fs)


class Cli(Adapter):
    """A command template with ``{input}`` and ``{output}``; works for any tool.

    The template is split into words with ``shlex.split`` and run without a shell, so pipes,
    redirects and globs do not work; set ``shell = true`` to run it with ``/bin/sh -c`` instead.
    Either way it runs as the current user: only use commands you trust.

    Class A: ``{input}`` is a DSF file (a DFF file if ``input_ext = "dff"``), ``{output}`` a WAV
    (or FLAC if ``output_ext = "flac"``).
    Class B: ``{input}`` is a WAV, ``{output}`` a DSF.
    """

    kind = "cli"

    def __init__(self, name, command, klass="A", output_ext=None, input_ext="dsf", workdir=None,
                 timeout=3600, shell=False, input_ext_fallback=None, version_command=None, **opts):
        super().__init__(name, **opts)
        #: a command that prints the tool's version, for a command that starts a wrapper script (``--version`` would not reach the tool)
        self.version_command = version_command
        #: another file type to try in the pre-flight when the tool cannot read ``input_ext`` (see ``preflight``)
        self.input_ext_fallback = input_ext_fallback
        self.shell = bool(shell)
        self.input_ext = input_ext
        self.command = command
        self.klass = klass
        self.output_ext = output_ext or ("wav" if klass == "A" else "dsf")
        self.timeout = timeout
        self._work = _Work(workdir)
        self._n = 0

    def describe(self):
        d = super().describe()
        d["command"] = self.command
        d["shell"] = self.shell
        if self.klass == "A":
            d["input_ext"] = self.input_ext
        return d

    def tool_versions(self):
        return {**super().tool_versions(), **program_identity(self.command, self.version_command)}

    def close(self):
        self._work.close()

    def _run(self, in_path, out_path):
        i, o = str(in_path), str(out_path)
        if self.shell:
            cmd = substitute(self.command, input=shlex.quote(i), output=shlex.quote(o))
        else:
            cmd = [substitute(w, input=i, output=o) for w in shlex.split(self.command)]
        run_checked(cmd, shell=self.shell, timeout=self.timeout)

    def _tmp(self):
        self._n += 1
        return self._work.path(), self._n

    def dsd_to_pcm(self, bits, rate):
        d, n = self._tmp()
        i, o = d / f"in{n}.{self.input_ext}", d / f"out{n}.{self.output_ext}"
        (write_dff if self.input_ext == "dff" else write_dsf)(i, bits, rate)
        self._run(i, o)
        fmt = audio_format(o)  # what the tool wrote, before any conversion
        if o.suffix == ".flac":
            w = d / f"out{n}.wav"
            run_checked(["ffmpeg", "-v", "error", "-y", "-i", str(o), "-c:a", "pcm_f32le", str(w)],
                        timeout=self.timeout)
            o = w
        y, fs = read_wav(o)
        self.log.append({"input_sha256": sha256_file(i), "output_sha256": sha256_file(o), "rate": fs, "output_format": fmt})
        self._work.discard(i, o, d / f"out{n}.wav")
        return _pick(y, bits) * 10 ** (self.gain_db / 20), fs

    def pcm_to_dsd(self, x, fs):
        d, n = self._tmp()
        i, o = d / f"in{n}.wav", d / f"out{n}.{self.output_ext}"
        write_wav(i, x, fs, "pcm32")
        self._run(i, o)
        bits, rate = read_dsf(o)
        self.log.append({"input_sha256": sha256_file(i), "output_sha256": sha256_file(o), "rate": rate})
        self._work.discard(i, o)
        return _pick(bits, x), rate


#: ``modulator = "auto"``: the SoX-DSD filter per DSD rate used in Archimago's 2022 DSD tests
#: (CLANS-8, -7 and -6), also used by the dsd2pcm quality tools (credited in docs/reference-tools.md).
AUTO_SDM = {64: "clans-8", 128: "clans-7", 256: "clans-6"}


class ReftoolSox(Adapter):
    """SoX-DSD run as a black box through the pinned container wrapper (``tools/reftool.sh``).

    Class A: DSD to 32-bit float PCM at ``out_rate``. Class B: PCM to DSD with the ``sdm`` or
    ``clans`` modulator. The default modulator is ``sdm-8``, the highest order of the ``sdm`` family, which read lower noise than
    ``clans-8`` in our checks (docs/accuracy.md: 140.8 dB against 119.5 dB on the same input) and in Archimago's 2022 notes it
    is described as the lower-noise filter; ``clans-8`` and the per-rate ``auto`` choice are still available by name.

    Level convention. SoX-DSD maps PCM full scale (0 dBFS) to 50 % modulation, which is 0 dB SACD
    in this toolkit, so a -6.02 dBFS test tone reaches the modulator at 25 % and SoX writes its
    output 6.02 dB below the input level. Two options deal with it, both recorded in the report:

    ``input_gain_db`` (default 0) raises the PCM before the modulator. Set it to 6.0206 so the
    modulator sees the test level the footprint defines (0 dB SACD at -6.02 dBFS). Samples that
    would exceed full scale are clipped and logged: the +3.1 dB SACD peak test cannot be
    reached through SoX, whose input range ends at 50 %.

    ``gain_db`` is applied to the output so that the whole chain has unity gain. Unless given,
    it is ``6.0206 - input_gain_db`` (6.0206 with no input gain, 0 with 6.0206 of input gain).

    ``trellis`` is ``"default"`` (the default: SoX's own trellis settings, no ``-t``/``-n``) or ``"32x32"``
    (``-t 32 -n 32``: trellis depth and number of paths both 32). Before 0.1.3 the default was ``"32x32"``; with
    ``sdm-8`` at +6.0206 dB input SoX's own settings read SINAD 140.8 dB and A-weighted noise -156.5 dBFS against
    138.6 dB and -147.5 dBFS (DSD64, built-in stimulus, 2026-11-24). Which is better depends on the modulator and
    the figure (with ``clans-8`` they trade places), so say which one was used when comparing.
    """

    kind = "sox-dsd"
    TRELLIS = {"32x32": ["-t", "32", "-n", "32"], "default": []}

    def __init__(self, name, reftool, klass="A", out_rate=352800, modulator="sdm-8", workdir=None,
                 gain_db=None, input_gain_db=0.0, trellis="default", timeout=3600, **opts):
        input_gain_db = float(input_gain_db) if klass == "B" else 0.0  # input gain is a class B option
        if gain_db is None:
            gain_db = 6.0206 - input_gain_db
        if trellis not in self.TRELLIS:
            raise ValueError(f"trellis must be one of {sorted(self.TRELLIS)}, not {trellis!r}")
        super().__init__(name, gain_db=gain_db, **opts)
        self.reftool, self.klass, self.out_rate, self.modulator = str(reftool), klass, int(out_rate), modulator
        self.input_gain_db, self.trellis = input_gain_db, trellis
        self._work = _Work(workdir)
        self._n = 0
        self.timeout = timeout

    def describe(self):
        d = super().describe()
        d["detail"] = {"reftool": "container wrapper", "modulator": self.modulator, "out_rate": self.out_rate,
                       "input_gain_db": self.input_gain_db, "trellis": self.trellis,
                       "level_mapping": self.level_mapping()}
        return d

    def level_mapping(self):
        """What the modulator's input level is, in words (class B only): the test tone enters at 25 % or 50 % modulation."""
        if self.klass != "B":
            return "not applicable (class A)"
        pct = 25.0 * 10 ** (self.input_gain_db / 20)
        return (f"the 0 dB SACD test tone (-6.02 dBFS) enters the modulator at {pct:.0f} % modulation "
                f"(SoX-DSD maps PCM full scale to 50 %; input gain {self.input_gain_db:g} dB); the output is raised by {self.gain_db:g} dB")

    def tool_versions(self):
        import json
        d = {**super().tool_versions(), "program": "SoX-DSD in the pinned container", "wrapper": program_identity(self.reftool, version_command="true")}
        try:
            r = subprocess.run([self.reftool, "versions"], stdin=subprocess.DEVNULL, capture_output=True, timeout=300, text=True)
            info = json.loads(r.stdout)["sox-dsd"] if r.returncode == 0 else None
        except (OSError, subprocess.TimeoutExpired, ValueError, KeyError):
            info = None
        d.update(info or {"version": None})
        if self.klass == "B":
            d.update(modulator=self.modulator, level_mapping=self.level_mapping())
        return d

    def close(self):
        self._work.close()

    def _call(self, args):
        run_checked([self.reftool, "sox-dsd", str(self._in), str(self._out)] + args, timeout=self.timeout)

    def _dirs(self):
        self._n += 1
        base = self._work.path() / f"c{self._n}"
        self._in, self._out = base / "in", base / "out"
        self._in.mkdir(parents=True, exist_ok=True)
        self._out.mkdir(parents=True, exist_ok=True)

    def dsd_to_pcm(self, bits, rate):
        self._dirs()
        write_dsf(self._out / "x.dsf", bits, rate)  # the wrapper reads the DSD from the output folder
        self._call(["/out/x.dsf", "-e", "floating-point", "-b", "32", "/out/x.wav", "rate", "-v", str(self.out_rate)])
        y, fs = read_wav(self._out / "x.wav")
        self.log.append({"input_sha256": sha256_file(self._out / "x.dsf"),
                         "output_sha256": sha256_file(self._out / "x.wav"), "rate": fs,
                         "output_format": audio_format(self._out / "x.wav")})
        return _pick(y, bits) * 10 ** (self.gain_db / 20), fs

    def pcm_to_dsd(self, x, fs):
        self._dirs()
        x = np.asarray(x, dtype=np.float64) * 10 ** (self.input_gain_db / 20)
        clipped = bool(np.max(np.abs(x)) > 1.0)
        write_wav(self._in / "x.wav", np.clip(x, -1.0, 1.0), fs, "pcm32")
        mod = AUTO_SDM.get(self.dsd_rate // 44100, "clans-8") if self.modulator == "auto" else self.modulator
        self._call(["/in/x.wav", "/out/x.dsf", "rate", "-v", str(self.dsd_rate), "sdm", "-f", mod]
                   + self.TRELLIS[self.trellis])
        bits, rate = read_dsf(self._out / "x.dsf")
        self.log.append({"input_sha256": sha256_file(self._in / "x.wav"),
                         "output_sha256": sha256_file(self._out / "x.dsf"), "rate": rate,
                         "input_gain_db": self.input_gain_db, "clipped_at_full_scale": clipped})
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

    def tool_versions(self):
        return {**super().tool_versions(), "program": "produced elsewhere", "directory": str(self.dir),
                "version": None, "note": "dsd-measure cannot know the tool or version behind these files; each file's SHA-256 is in the provenance"}

    def dsd_to_pcm(self, bits, rate):
        p = self.dir / f"{self.current}.wav"
        if not p.exists():
            raise FileNotFoundError(p)
        y, fs = read_wav(p)
        self.log.append({"output_sha256": sha256_file(p), "rate": fs, "output_format": audio_format(p)})
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
    # float output on purpose: ffmpeg writes 16-bit WAV by default, which would measure the file format, not the decoder
    "ffmpeg": "ffmpeg -v error -y -i {input} -c:a pcm_f32le {output}",
    "dsd2pcm": "dsd2pcm {input} {output}",
    "sox-dsd": "sox {input} -b 32 -e floating-point {output} rate -v 352800",
    "sacd_extract": "sacd_extract -i {input} -p -o {output}",
}


def with_args(command, args):
    """Put extra arguments right after the program name: ``dsd2pcm --filter pysacd {input} {output}``."""
    args = (args or "").strip()
    if not args:
        return command
    command = command.lstrip()
    if command[:1] in ("'", '"') and command.find(command[0], 1) > 0:  # a quoted program path may hold spaces
        end = command.find(command[0], 1) + 1
        head, rest = command[:end], command[end:].lstrip()
    else:
        head, _, rest = command.partition(" ")
    return f"{head} {args} {rest}".rstrip()


#: Extra options a preset passes to its adapter. A distribution ffmpeg may read DSD from DFF files but not DSF files.
PRESET_OPTS = {"ffmpeg": {"input_ext_fallback": "dff"}}


def unknown_name_message(name):
    """What to tell a user who typed a tool name that is not a preset."""
    names = ", ".join(sorted(PRESETS))
    msg = f"unknown converter {name!r}. Built-in presets: reference, {names}."
    if Path(name).suffix.lower() in (".dsf", ".dff"):
        return (f"{name!r} is a DSD file, not a converter. To compare decoders on this file: "
                f"dsd-measure null {name} ffmpeg")
    return msg + (f" To measure any other tool, give its command: dsd-measure quick {name} --command "
                  f"\"{name} {{input}} {{output}}\" ({{input}} is a DSF file, {{output}} the WAV the tool writes).")


def write_signal_set(outdir, klass="A", profile="quick", in_rate=88200, dsd_rate=2822400, rates=(), only=None, log=None):
    """Write every stimulus a run of ``profile`` feeds a ``klass`` device, plus ``signals.json``.

    The set is recorded from the real measurement (``Recorder``), so it cannot drift from what
    ``run`` feeds. Returns the manifest (a dict).
    """
    import json

    from . import __version__
    from .measure import measure_device
    # out_rate 44100 so that the alias-tone stimuli (they need an output Nyquist frequency below 24 kHz) are made too
    rec = Recorder(outdir, klass=klass, dsd_rate=dsd_rate, out_rate=44100, rates=rates)
    res = measure_device(rec, profile, in_rate, log=log or (lambda *a, **k: None), only=only)
    manifest = {"dsd_measure": __version__, "class": klass, "profile": profile, "pcm_input_rate": in_rate,
                "dsd_rate": dsd_rate, "files": rec.entries,
                "how": ("Feed each file to the device and save its output as <tag>.wav (class A) or <tag>.dsf (class B) in one "
                        "folder; then run a suite with adapter = \"import\" and directory = that folder.")}
    (Path(outdir) / "signals.json").write_text(json.dumps(manifest, indent=1) + "\n")
    manifest["errors"] = res["errors"]
    return manifest


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
        cmd = with_args(spec.pop("command", PRESETS[kind]), spec.pop("args", ""))
        if "input_ext" not in spec:
            spec = {**PRESET_OPTS.get(kind, {}), **spec}
        if shutil.which(cmd.split()[0]) is None and "/" not in cmd.split()[0]:
            raise MissingTool(f"{cmd.split()[0]} is not on PATH (needed by {name!r}). Install it, or set command = ... to its full path")
        return Cli(name, cmd, klass=klass, **spec)
    if kind == "import":
        return Import(name, klass=klass, **spec)
    raise UserError(f"unknown adapter {kind!r} (adapters: reference, cli, import, sox-dsd, and the presets "
                    f"{', '.join(sorted(PRESETS))}; a [[device]] with adapter = \"cli\" takes any command)")
