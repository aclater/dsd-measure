"""Streaming access to DSF and DFF (DSDIFF) files: read any sample range, convert, hash.

The whole-file reader in ``dsf.py`` unpacks every bit at once, which is too much memory for a
full album track (a stereo DSD64 track of five minutes is 1.7 billion bits). ``DsdFile`` maps the
file and unpacks only the range asked for, so memory use is set by the range, not the file.
Compressed DSDIFF (DST) is refused with a clear message: it needs a decoder first.
"""

import hashlib
import struct
from pathlib import Path

import numpy as np

from .dsf import BLOCK


class DsdFile:
    """A DSF or DFF file opened for reading in ranges. ``bits(ch, start, stop)`` gives int8 +1 / -1."""

    def __init__(self, path):
        self.path = Path(path)
        self._mm = np.memmap(self.path, dtype=np.uint8, mode="r")
        head = bytes(self._mm[:4])
        if head == b"DSD ":
            self._open_dsf()
        elif head == b"FRM8":
            self._open_dff()
        else:
            raise ValueError(f"{self.path.name}: not a DSF or DFF file")

    def _open_dsf(self):
        mm = self._mm
        fmt = struct.unpack("<4sQIIIIIIQI", bytes(mm[28:28 + 48]))
        self.kind = "dsf"
        self.channels, self.rate, bps, self.samples, self.block = fmt[5], fmt[6], fmt[7], fmt[8], fmt[9]
        self._bitorder = "little" if bps == 1 else "big"
        pos = 28 + 52
        if bytes(mm[pos:pos + 4]) != b"data":
            raise ValueError("DSF: missing data chunk")
        size = struct.unpack("<Q", bytes(mm[pos + 4:pos + 12]))[0] - 12
        self._data0 = pos + 12
        self._data_bytes = min(size, len(mm) - self._data0)

    def _open_dff(self):
        mm = self._mm
        self.kind = "dff"
        total = struct.unpack(">Q", bytes(mm[4:12]))[0] + 12
        pos, self.channels, self.rate, cmpr, data = 16, None, None, b"DSD ", None
        while pos + 12 <= min(total, len(mm)):
            cid = bytes(mm[pos:pos + 4])
            size = struct.unpack(">Q", bytes(mm[pos + 4:pos + 12]))[0]
            body = pos + 12
            if cid == b"PROP":
                p, end = body + 4, body + size  # skips the "SND " property type
                while p + 12 <= end:
                    sid = bytes(mm[p:p + 4])
                    ssize = struct.unpack(">Q", bytes(mm[p + 4:p + 12]))[0]
                    if sid == b"FS  ":
                        self.rate = struct.unpack(">I", bytes(mm[p + 12:p + 16]))[0]
                    elif sid == b"CHNL":
                        self.channels = struct.unpack(">H", bytes(mm[p + 12:p + 14]))[0]
                    elif sid == b"CMPR":
                        cmpr = bytes(mm[p + 12:p + 16])
                    p += 12 + ssize + (ssize & 1)
            elif cid == b"DSD ":
                data = (body, size)
            pos = body + size + (size & 1)
        if cmpr != b"DSD ":
            raise ValueError("DFF holds DST-compressed audio; decode it to plain DSD first (this tool does not read DST)")
        if data is None or not self.channels or not self.rate:
            raise ValueError("DFF: missing data, channel or rate chunk")
        self._data0, self._data_bytes = data[0], min(data[1], len(mm) - data[0])
        self.samples = self._data_bytes // self.channels * 8
        self._bitorder = "big"

    def bits(self, ch, start, stop):
        """Bits ``start:stop`` of channel ``ch`` as int8 +1 / -1; positions outside the file are 0 (silence is not +-1)."""
        n = max(0, stop - start)
        out = np.zeros(n, dtype=np.int8)
        lo, hi = max(start, 0), min(stop, self.samples)
        if hi <= lo:
            return out
        b0, b1 = lo // 8, (hi + 7) // 8
        if self.kind == "dsf":
            per = self.block
            first, last = b0 // per, (b1 - 1) // per
            parts = []
            for blk in range(first, last + 1):
                off = self._data0 + (blk * self.channels + ch) * per
                parts.append(np.asarray(self._mm[off:off + per]))
            raw = np.concatenate(parts)[b0 - first * per: b1 - first * per]
        else:
            off = self._data0 + b0 * self.channels + ch
            raw = np.asarray(self._mm[off: self._data0 + b1 * self.channels: self.channels])
        bits = np.unpackbits(raw, bitorder=self._bitorder)[lo - b0 * 8: hi - b0 * 8]
        out[lo - start: hi - start] = bits.astype(np.int8) * 2 - 1
        return out

    def sha256(self):
        return sha256_path(self.path)


def sha256_path(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()


def _chunk(cid, body):
    return cid + struct.pack(">Q", len(body)) + body + (b"\x00" if len(body) % 2 else b"")


def convert(src, dst, kind):
    """Write ``src`` (DSF or DFF) as ``kind`` ("dsf" or "dff") without loading it, bit-exactly."""
    f = DsdFile(src)
    ch, n, rate = f.channels, f.samples, f.rate
    step = 1 << 22  # samples per channel per step; a multiple of 8 and of BLOCK * 8
    with open(dst, "wb") as out:
        if kind == "dsf":
            pad = (-n) % (BLOCK * 8)
            nblocks = (n + pad) // 8 // BLOCK
            data_len = nblocks * BLOCK * ch
            out.write(struct.pack("<4sQQQ", b"DSD ", 28, 28 + 52 + 12 + data_len, 0))
            out.write(struct.pack("<4sQIIIIIIQI4x", b"fmt ", 52, 1, 0, ch if ch <= 6 else 7, ch, rate, 1, n, BLOCK))
            out.write(struct.pack("<4sQ", b"data", 12 + data_len))
            for s in range(0, n + pad, step):
                packed = []
                for c in range(ch):
                    b = (f.bits(c, s, min(s + step, n + pad)) > 0).astype(np.uint8)
                    packed.append(np.packbits(b, bitorder="little"))
                m = packed[0].size // BLOCK
                arr = np.stack([p[: m * BLOCK].reshape(m, BLOCK) for p in packed], axis=1)
                out.write(arr.reshape(-1).tobytes())
        elif kind == "dff":
            nbytes = (n + 7) // 8
            data_len = nbytes * ch
            ids = {1: [b"SLFT"], 2: [b"SLFT", b"SRGT"]}.get(ch, [b"C%03d" % i for i in range(ch)])
            prop = (b"SND " + _chunk(b"FS  ", struct.pack(">I", rate))
                    + _chunk(b"CHNL", struct.pack(">H", ch) + b"".join(ids))
                    + _chunk(b"CMPR", b"DSD " + bytes([14]) + b"not compressed\x00"))
            head = b"DSD " + _chunk(b"FVER", struct.pack(">I", 0x01050000)) + _chunk(b"PROP", prop)
            body_len = len(head) + 12 + data_len + (data_len & 1)
            out.write(b"FRM8" + struct.pack(">Q", body_len) + head + b"DSD " + struct.pack(">Q", data_len))
            for s in range(0, n, step):
                packed = [np.packbits((f.bits(c, s, min(s + step, n)) > 0).astype(np.uint8), bitorder="big")
                          for c in range(ch)]
                out.write(np.stack(packed, axis=1).reshape(-1).tobytes())
            if data_len & 1:
                out.write(b"\x00")
        else:
            raise ValueError(kind)
