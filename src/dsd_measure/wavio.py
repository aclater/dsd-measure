"""Minimal WAV reader/writer: 16/24/32-bit integer and 32-bit float, any channel count."""

import struct

import numpy as np


def write_wav(path, data, fs, subtype="float32"):
    """Write ``data`` (channels x samples, or 1-D mono) as WAV. subtype: pcm16, pcm24, pcm32, float32."""
    x = np.atleast_2d(np.asarray(data, dtype=np.float64))
    ch, n = x.shape
    if subtype == "float32":
        raw = x.T.astype("<f4").tobytes()
        fmt, bits = 3, 32
    elif subtype in ("pcm16", "pcm24", "pcm32"):
        bits = int(subtype[3:])
        scale = 2 ** (bits - 1)
        q = np.clip(np.round(x.T * scale), -scale, scale - 1).astype(np.int64)
        if bits == 16:
            raw = q.astype("<i2").tobytes()
        elif bits == 32:
            raw = q.astype("<i4").tobytes()
        else:
            b = q.astype("<i4").view(np.uint8).reshape(-1, 4)[:, :3]
            raw = b.tobytes()
        fmt = 1
    else:
        raise ValueError(f"unknown subtype {subtype}")
    block = ch * bits // 8
    hdr = b"RIFF" + struct.pack("<I", 36 + len(raw)) + b"WAVE"
    hdr += b"fmt " + struct.pack("<IHHIIHH", 16, fmt, ch, int(fs), int(fs) * block, block, bits)
    hdr += b"data" + struct.pack("<I", len(raw))
    with open(path, "wb") as f:
        f.write(hdr + raw)


def read_wav(path):
    """Return (data[channels, samples] float64 in -1..1, fs)."""
    with open(path, "rb") as f:
        buf = f.read()
    if buf[:4] != b"RIFF" or buf[8:12] != b"WAVE":
        raise ValueError("not a WAV file")
    pos, fmt, data = 12, None, None
    while pos + 8 <= len(buf):
        cid, size = buf[pos : pos + 4], struct.unpack("<I", buf[pos + 4 : pos + 8])[0]
        body = buf[pos + 8 : pos + 8 + size]
        if cid == b"fmt ":
            fmt = struct.unpack("<HHIIHH", body[:16])
            if fmt[0] == 0xFFFE and len(body) >= 26:  # WAVE_FORMAT_EXTENSIBLE
                fmt = (struct.unpack("<H", body[24:26])[0],) + fmt[1:]
        elif cid == b"data":
            data = body
        pos += 8 + size + (size & 1)
    if fmt is None or data is None:
        raise ValueError("missing fmt or data chunk")
    tag, ch, fs, _, _, bits = fmt
    if tag == 3 and bits == 32:
        x = np.frombuffer(data, "<f4").astype(np.float64)
    elif tag == 3 and bits == 64:
        x = np.frombuffer(data, "<f8")
    elif tag == 1 and bits == 16:
        x = np.frombuffer(data, "<i2") / 32768.0
    elif tag == 1 and bits == 24:
        b = np.frombuffer(data, np.uint8)[: len(data) // 3 * 3].reshape(-1, 3)
        v = (b[:, 0].astype(np.int32) | (b[:, 1].astype(np.int32) << 8) | (b[:, 2].astype(np.int32) << 16))
        v = np.where(v & 0x800000, v - 0x1000000, v)
        x = v / 8388608.0
    elif tag == 1 and bits == 32:
        x = np.frombuffer(data, "<i4") / 2147483648.0
    else:
        raise ValueError(f"unsupported WAV format tag={tag} bits={bits}")
    n = len(x) // ch
    return x[: n * ch].reshape(n, ch).T.copy(), fs
