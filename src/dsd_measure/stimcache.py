"""Per-user cache of the reference modulator's output (the encoded test stimuli).

The reference encoder is deterministic: the same PCM samples, rates and design always give the
same DSD bits on the same software. Encoding is most of a run's work, so the bits are kept in a
private folder and read back on the next run and for every further device of a suite.

Key. An entry is named by the SHA-256 of everything the bits depend on: the PCM samples (their
bytes, dtype and length), both rates, the requested design and headroom, the dsd-measure and
reference-chain versions, the source of the encoder (``encode.py``, ``csrc/dsm.c`` and the
compiler flags), the NumPy and SciPy versions and the machine type. Any change to one of them
gives a new name, so a stale entry is never read; old entries age out by size.

Integrity. The file holds the SHA-256 of its payload and is checked on every read. A file that
is short, altered or made by another format version is deleted and the stimulus is encoded
again. The folder must be private to the user (the rules of the compiled-core cache).

Pieces. The encoder works in pieces and carries its state across them, so the bits do not depend on how a long signal is cut; an entry is always the whole signal, and a read back needs one byte per bit.

Size. The bits are stored packed (one bit per sample, 353 kB per second of DSD64). When the
folder grows beyond the limit (4 GiB unless ``DSD_MEASURE_CACHE_MAX_MB`` says otherwise) the
entries read longest ago are deleted first.

Switches. ``dsd-measure run --no-cache`` or ``DSD_MEASURE_NO_CACHE=1`` turns the cache off;
``DSD_MEASURE_CACHE_DIR`` moves the whole dsd-measure cache; ``dsd-measure cache`` shows it and
``dsd-measure cache --clear`` empties it.
"""

import hashlib
import json
import os
import platform
import struct
import tempfile
import time
from pathlib import Path

import numpy as np

MAGIC = b"DSDMSTIM1\n"
DEFAULT_MAX_MB = 4096
#: Evict down to this fraction of the limit, so a run does not evict after every write.
LOW_WATER = 0.9

_state = {"enabled": None, "hits": 0, "misses": 0, "written": 0, "since_evict": 0}


def enabled():
    if _state["enabled"] is not None:
        return _state["enabled"]
    return os.environ.get("DSD_MEASURE_NO_CACHE", "") in ("", "0")


def set_enabled(on):
    """Switch the cache for this process and, through the environment, for its worker processes."""
    _state["enabled"] = bool(on)
    if on:
        os.environ.pop("DSD_MEASURE_NO_CACHE", None)
    else:
        os.environ["DSD_MEASURE_NO_CACHE"] = "1"


def stats():
    return {k: _state[k] for k in ("hits", "misses", "written")}


def reset_stats():
    for k in ("hits", "misses", "written"):
        _state[k] = 0


def add_stats(other):
    for k in ("hits", "misses", "written"):
        _state[k] += int(other.get(k, 0))


def max_bytes():
    try:
        return int(float(os.environ.get("DSD_MEASURE_CACHE_MAX_MB", DEFAULT_MAX_MB)) * 2**20)
    except ValueError:
        return DEFAULT_MAX_MB * 2**20


def directory(create=True):
    """The private folder for stimuli (``<cache>/stimuli``); checked on every use."""
    from .encode import _cache_dir, _private_dir
    root = _cache_dir()
    if not create:
        return root / "stimuli"
    return _private_dir(_private_dir(root) / "stimuli")


def _source_tag():
    import scipy

    from . import REFERENCE_CHAIN_VERSION, __version__
    from . import encode as enc
    here = Path(enc.__file__).parent
    h = hashlib.sha256()
    for part in (MAGIC, __version__.encode(), REFERENCE_CHAIN_VERSION.encode(),
                 (here / "encode.py").read_bytes(), (here / "csrc" / "dsm.c").read_bytes(),
                 " ".join(enc.CFLAGS).encode(), np.__version__.encode(), scipy.__version__.encode(),
                 platform.machine().encode()):
        h.update(struct.pack("<Q", len(part)))
        h.update(part)
    return h.digest()


_TAG = None


def key(x, fs, dsd_rate, order, hinf, headroom, interpolator="fft"):
    """The name of the entry for one ``encode`` call (hex SHA-256 of every input)."""
    global _TAG
    if _TAG is None:
        _TAG = _source_tag()
    x = np.ascontiguousarray(x)
    h = hashlib.sha256(_TAG)
    h.update(json.dumps([int(fs), int(dsd_rate), order, hinf, float(headroom), interpolator, str(x.dtype), list(x.shape)]).encode())
    h.update(x.tobytes())
    return h.hexdigest()


def _path(k):
    return directory() / f"{k}.stim"


def load(k):
    """Return ``(bits, info)`` for key ``k``, or None when there is no valid entry."""
    from .encode import _check_private
    p = _path(k)
    try:
        _check_private(p, "cached stimulus")
        raw = p.read_bytes()
    except FileNotFoundError:
        _state["misses"] += 1
        return None
    out = _parse(raw)
    if out is None:  # damaged or foreign: drop it and encode again
        p.unlink(missing_ok=True)
        _state["misses"] += 1
        return None
    try:
        os.utime(p)  # read time for the oldest-first eviction
    except OSError:
        pass
    _state["hits"] += 1
    return out


def _parse(raw):
    if not raw.startswith(MAGIC) or len(raw) < len(MAGIC) + 8 + 32:
        return None
    o = len(MAGIC)
    (hlen,) = struct.unpack("<Q", raw[o : o + 8])
    o += 8
    digest, body = raw[o : o + 32], memoryview(raw)[o + 32 :]  # a view: a long entry is not copied
    if hlen > len(body) or hashlib.sha256(body).digest() != digest:
        return None
    try:
        head = json.loads(bytes(body[:hlen]).decode())
        n = int(head["n"])
        info = head["info"]
    except (ValueError, KeyError, TypeError):
        return None
    packed = np.frombuffer(body, dtype=np.uint8, offset=hlen)
    if n < 0 or len(packed) != (n + 7) // 8 or not isinstance(info, dict):
        return None
    bits = np.unpackbits(packed, count=n).view(np.int8)  # 0 / 1 in place, then -1 / +1: one byte per bit
    bits *= 2
    bits -= 1
    return bits, info


def store(k, bits, info):
    """Write an entry (private file, atomic rename). A full disk only loses the cache, not the run."""
    bits = np.asarray(bits)
    head = json.dumps({"n": int(len(bits)), "info": info}).encode()
    body = head + np.packbits(bits > 0).tobytes()
    blob = MAGIC + struct.pack("<Q", len(head)) + hashlib.sha256(body).digest() + body
    d = directory()
    try:
        fd, tmp = tempfile.mkstemp(prefix=".w-", suffix=".tmp", dir=d)  # 0600
    except OSError:
        return False
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(blob)
        os.replace(tmp, _path(k))
    except OSError:
        return False
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    _state["written"] += 1
    _state["since_evict"] += len(blob)
    if _state["since_evict"] > max_bytes() * (1 - LOW_WATER) / 2:
        _state["since_evict"] = 0
        evict()
    return True


def _entries(d):
    out = []
    try:
        names = os.listdir(d)
    except FileNotFoundError:
        return out
    for name in names:
        if not (name.endswith(".stim") or name.endswith(".tmp")):
            continue
        p = Path(d) / name
        try:
            st = os.lstat(p)
        except FileNotFoundError:
            continue
        if name.endswith(".tmp") and time.time() - st.st_mtime < 3600:
            continue  # another process is writing it
        out.append((st.st_mtime, st.st_size, p))
    return out


def usage():
    """``{"directory", "entries", "bytes", "limit_bytes"}`` without creating anything."""
    d = directory(create=False)
    ent = [e for e in _entries(d) if e[2].suffix == ".stim"]
    return {"directory": str(d), "entries": len(ent), "bytes": sum(e[1] for e in ent), "limit_bytes": max_bytes()}


def evict(limit=None):
    """Delete the entries read longest ago until the folder is under the limit. Returns bytes freed."""
    limit = max_bytes() if limit is None else limit
    d = directory(create=False)
    ent = sorted(_entries(d))
    total = sum(e[1] for e in ent)
    if total <= limit:
        return 0
    freed = 0
    for _, size, p in ent:
        if total - freed <= limit * LOW_WATER:
            break
        try:
            p.unlink()
            freed += size
        except OSError:
            pass
    return freed


def gate_key():
    """A short name for everything but the signals that an entry's name depends on.

    Two installations print the same value exactly when one can read the other's entries, so it
    is the key under which a CI system should save and restore the folder.
    """
    global _TAG
    if _TAG is None:
        _TAG = _source_tag()
    return "dsd-measure-stimuli-" + hashlib.sha256(_TAG).hexdigest()[:20]


def clear():
    """Delete every cached stimulus. Returns the number of bytes freed."""
    d = directory(create=False)
    freed = 0
    for _, size, p in _entries(d):
        try:
            p.unlink()
            freed += size
        except OSError:
            pass
    return freed
