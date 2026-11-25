"""Minimal DSF (DSD Stream File) reader and writer. Bits are int8 +1 / -1 arrays."""

import struct

import numpy as np

BLOCK = 4096


#: Blocks of ``BLOCK`` bytes per channel written or read in one step, so the working memory is a
#: few megabytes whatever the length of the file.
GROUP = 256


def write_dsf(path, bits, rate):
    """Write ``bits`` (channels x samples, or 1-D mono; +1 / -1) as DSF, LSB first."""
    b = np.atleast_2d(np.asarray(bits))
    ch, n = b.shape
    pad = (-n) % (BLOCK * 8)
    nblocks = (n + pad) // 8 // BLOCK
    size = nblocks * BLOCK * ch
    fmt = struct.pack("<4sQIIIIIIQI4x", b"fmt ", 52, 1, 0, ch if ch <= 6 else 7, ch, rate, 1, n, BLOCK)
    dsd = struct.pack("<4sQQQ", b"DSD ", 28, 28 + 52 + 12 + size, 0)
    dat = struct.pack("<4sQ", b"data", 12 + size)
    # Pad with the DSD idle pattern (0x69, a repeating 01101001), not zero bits: zero bits are
    # a burst of -100 % modulation that a decoder converting whole blocks turns into a transient
    # at the end of the file.
    idle = np.unpackbits(np.array([0x69], np.uint8), bitorder="little")
    with open(path, "wb") as f:
        f.write(dsd + fmt + dat)
        for k0 in range(0, nblocks, GROUP):
            k1 = min(nblocks, k0 + GROUP)
            lo, hi = k0 * BLOCK * 8, k1 * BLOCK * 8
            packed = np.empty((k1 - k0, ch, BLOCK), np.uint8)
            for c in range(ch):
                seg = np.empty(hi - lo, np.uint8)
                m = max(0, min(hi, n) - lo)
                seg[:m] = b[c, lo : lo + m] > 0
                seg[m:] = idle[(lo + m + np.arange(hi - lo - m)) % 8]
                packed[:, c, :] = np.packbits(seg, bitorder="little").reshape(k1 - k0, BLOCK)
            f.write(packed.tobytes())


def read_dsf(path):
    """Return (bits[channels, samples] int8 +-1, rate)."""
    mm = np.memmap(path, dtype=np.uint8, mode="r")
    buf = bytes(mm[: 28 + 52 + 12])
    if buf[:4] != b"DSD ":
        raise ValueError("not a DSF file")
    fmt = struct.unpack("<4sQIIIIIIQI", buf[28:28 + 52 - 4])
    ch, rate, bps, n, block = fmt[5], fmt[6], fmt[7], fmt[8], fmt[9]
    pos = 28 + 52
    if buf[pos : pos + 4] != b"data":
        raise ValueError("missing data chunk")
    size = struct.unpack("<Q", buf[pos + 4 : pos + 12])[0] - 12
    raw = mm[pos + 12 : pos + 12 + size]
    per = block * ch
    nblocks = len(raw) // per
    n = min(n, nblocks * block * 8)
    bitorder = "little" if bps == 1 else "big"
    bits = np.empty((ch, n), np.int8)
    for k0 in range(0, nblocks, GROUP):
        k1 = min(nblocks, k0 + GROUP)
        lo, hi = k0 * block * 8, min(n, k1 * block * 8)
        if hi <= lo:
            break
        grp = np.asarray(raw[k0 * per : k1 * per]).reshape(k1 - k0, ch, block)
        for c in range(ch):
            u = np.unpackbits(grp[:, c, :].reshape(-1), bitorder=bitorder)[: hi - lo]
            bits[c, lo:hi] = u.astype(np.int8) * 2 - 1
    del raw, mm
    return bits, rate


def _chunk(cid, body):
    pad = b"\x00" if len(body) % 2 else b""
    return cid + struct.pack(">Q", len(body)) + body + pad


def write_dff(path, bits, rate):
    """Write ``bits`` (channels x samples, or 1-D mono; +1 / -1) as uncompressed DSDIFF (DFF), MSB first."""
    b = np.atleast_2d(np.asarray(bits))
    ch, n = b.shape
    pad = (-n) % 8
    idle = np.unpackbits(np.array([0x69], np.uint8))  # DSDIFF is MSB first
    bb = np.concatenate([(b > 0).astype(np.uint8), np.tile(idle[(n + np.arange(pad)) % 8], (ch, 1))], axis=1)
    packed = np.packbits(bb.reshape(ch, -1, 8), axis=2, bitorder="big").reshape(ch, -1)
    data = packed.T.reshape(-1).tobytes()  # one byte per channel in turn
    ids = {1: [b"SLFT"], 2: [b"SLFT", b"SRGT"]}.get(ch, [f"C{i:03d}".encode() for i in range(ch)])
    prop = (b"SND " + _chunk(b"FS  ", struct.pack(">I", rate))
            + _chunk(b"CHNL", struct.pack(">H", ch) + b"".join(ids))
            + _chunk(b"CMPR", b"DSD " + bytes([14]) + b"not compressed\x00"))
    body = b"DSD " + _chunk(b"FVER", struct.pack(">I", 0x01050000)) + _chunk(b"PROP", prop) + _chunk(b"DSD ", data)
    with open(path, "wb") as f:
        f.write(b"FRM8" + struct.pack(">Q", len(body)) + body)
