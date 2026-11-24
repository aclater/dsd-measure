"""Minimal DSF (DSD Stream File) reader and writer. Bits are int8 +1 / -1 arrays."""

import struct

import numpy as np

BLOCK = 4096


def write_dsf(path, bits, rate):
    """Write ``bits`` (channels x samples, or 1-D mono; +1 / -1) as DSF, LSB first."""
    b = np.atleast_2d(np.asarray(bits))
    ch, n = b.shape
    pad = (-n) % (BLOCK * 8)
    bb = np.concatenate([(b > 0).astype(np.uint8), np.zeros((ch, pad), np.uint8)], axis=1)
    packed = np.packbits(bb.reshape(ch, -1, 8), axis=2, bitorder="little").reshape(ch, -1)
    nblocks = packed.shape[1] // BLOCK
    blocks = packed.reshape(ch, nblocks, BLOCK).transpose(1, 0, 2).reshape(-1)
    data = blocks.tobytes()
    fmt = struct.pack("<4sQIIIIIIQI4x", b"fmt ", 52, 1, 0, ch if ch <= 6 else 7, ch, rate, 1, n, BLOCK)
    dsd = struct.pack("<4sQQQ", b"DSD ", 28, 28 + 52 + 12 + len(data), 0)
    dat = struct.pack("<4sQ", b"data", 12 + len(data))
    with open(path, "wb") as f:
        f.write(dsd + fmt + dat + data)


def read_dsf(path):
    """Return (bits[channels, samples] int8 +-1, rate)."""
    with open(path, "rb") as f:
        buf = f.read()
    if buf[:4] != b"DSD ":
        raise ValueError("not a DSF file")
    fmt = struct.unpack("<4sQIIIIIIQI", buf[28:28 + 52 - 4])
    ch, rate, bps, n, block = fmt[5], fmt[6], fmt[7], fmt[8], fmt[9]
    pos = 28 + 52
    if buf[pos : pos + 4] != b"data":
        raise ValueError("missing data chunk")
    size = struct.unpack("<Q", buf[pos + 4 : pos + 12])[0] - 12
    raw = np.frombuffer(buf, np.uint8, count=size, offset=pos + 12)
    per = block * ch
    nblocks = len(raw) // per
    raw = raw[: nblocks * per].reshape(nblocks, ch, block).transpose(1, 0, 2).reshape(ch, -1)
    bitorder = "little" if bps == 1 else "big"
    bits = np.unpackbits(raw, axis=1, bitorder=bitorder)[:, :n].astype(np.int8) * 2 - 1
    return bits, rate


def _chunk(cid, body):
    pad = b"\x00" if len(body) % 2 else b""
    return cid + struct.pack(">Q", len(body)) + body + pad


def write_dff(path, bits, rate):
    """Write ``bits`` (channels x samples, or 1-D mono; +1 / -1) as uncompressed DSDIFF (DFF), MSB first."""
    b = np.atleast_2d(np.asarray(bits))
    ch, n = b.shape
    pad = (-n) % 8
    bb = np.concatenate([(b > 0).astype(np.uint8), np.zeros((ch, pad), np.uint8)], axis=1)
    packed = np.packbits(bb.reshape(ch, -1, 8), axis=2, bitorder="big").reshape(ch, -1)
    data = packed.T.reshape(-1).tobytes()  # one byte per channel in turn
    ids = {1: [b"SLFT"], 2: [b"SLFT", b"SRGT"]}.get(ch, [b"C%03d" % i for i in range(ch)])
    prop = (b"SND " + _chunk(b"FS  ", struct.pack(">I", rate))
            + _chunk(b"CHNL", struct.pack(">H", ch) + b"".join(ids))
            + _chunk(b"CMPR", b"DSD " + bytes([14]) + b"not compressed\x00"))
    body = b"DSD " + _chunk(b"FVER", struct.pack(">I", 0x01050000)) + _chunk(b"PROP", prop) + _chunk(b"DSD ", data)
    with open(path, "wb") as f:
        f.write(b"FRM8" + struct.pack(">Q", len(body)) + body)
