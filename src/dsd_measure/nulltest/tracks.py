"""Audio tracks read in ranges, so a long file never has to fit in memory.

A track has a ``rate``, a number of ``channels``, a ``length`` in samples and ``read(ch, start, stop)``,
which returns float64 samples and zeros for positions outside the track. Memory use is set by
the range asked for.
"""

import struct
from math import gcd

import numpy as np
from scipy import signal


class ArrayTrack:
    """A track held in memory (used for tests and short signals)."""

    def __init__(self, data, rate):
        self.data = np.atleast_2d(np.asarray(data, dtype=np.float64))
        self.rate = int(rate)
        self.channels, self.length = self.data.shape

    def read(self, ch, start, stop):
        out = np.zeros(max(0, stop - start))
        lo, hi = max(start, 0), min(stop, self.length)
        if hi > lo:
            out[lo - start: hi - start] = self.data[ch, lo:hi]
        return out


class WavTrack:
    """A WAV file mapped from disk: 16, 24 or 32-bit integer or 32 or 64-bit float, any channel count."""

    def __init__(self, path, scale=1.0):
        self.path, self.scale = str(path), float(scale)
        mm = np.memmap(path, dtype=np.uint8, mode="r")
        if bytes(mm[:4]) != b"RIFF" or bytes(mm[8:12]) != b"WAVE":
            raise ValueError("not a WAV file")
        pos, fmt, data = 12, None, None
        while pos + 8 <= len(mm):
            cid, size = bytes(mm[pos:pos + 4]), struct.unpack("<I", bytes(mm[pos + 4:pos + 8]))[0]
            if cid == b"fmt ":
                body = bytes(mm[pos + 8:pos + 8 + size])
                fmt = struct.unpack("<HHIIHH", body[:16])
                if fmt[0] == 0xFFFE and len(body) >= 26:
                    fmt = (struct.unpack("<H", body[24:26])[0],) + fmt[1:]
            elif cid == b"data":
                data = (pos + 8, min(size, len(mm) - pos - 8))
                break
            pos += 8 + size + (size & 1)
        if fmt is None or data is None:
            raise ValueError("WAV: missing fmt or data chunk")
        tag, self.channels, rate, _, _, bits = fmt
        self.rate = int(rate)
        self._bits, self._tag = bits, tag
        self._mm, self._off = mm, data[0]
        self.length = data[1] // (self.channels * bits // 8)
        if not ((tag == 3 and bits in (32, 64)) or (tag == 1 and bits in (16, 24, 32))):
            raise ValueError(f"unsupported WAV format tag={tag} bits={bits}")

    def read(self, ch, start, stop):
        out = np.zeros(max(0, stop - start))
        lo, hi = max(start, 0), min(stop, self.length)
        if hi <= lo:
            return out
        w, c = self._bits // 8, self.channels
        raw = np.asarray(self._mm[self._off + lo * c * w: self._off + hi * c * w]).reshape(-1, c * w)
        raw = np.ascontiguousarray(raw[:, ch * w:(ch + 1) * w])
        if self._tag == 3:
            x = raw.view("<f4" if w == 4 else "<f8").reshape(-1).astype(np.float64)
        elif w == 2:
            x = raw.view("<i2").reshape(-1) / 32768.0
        elif w == 4:
            x = raw.view("<i4").reshape(-1) / 2147483648.0
        else:
            v = raw[:, 0].astype(np.int32) | (raw[:, 1].astype(np.int32) << 8) | (raw[:, 2].astype(np.int32) << 16)
            x = np.where(v & 0x800000, v - 0x1000000, v) / 8388608.0
        out[lo - start: hi - start] = x * self.scale
        return out


def resample_taps(p, q, rate_out, edge=0.45, atten=160.0):
    """Kaiser low-pass for a rational ``p/q`` resampler (design rate: ``p`` x the input rate).

    The pass edge is ``edge`` x the lower of the two rates (0.45 x 44.1 kHz is 19.8 kHz) and the
    stop edge is half the lower rate, so nothing that aliases lands below the pass edge. ``atten``
    is the stopband in dB.
    """
    lo_rate = min(rate_out, rate_out * q / p)
    fs_design = rate_out * q  # = p x input rate
    width = (0.5 - edge) * lo_rate
    ntaps = int(np.ceil((atten - 8) / (2.285 * 2 * np.pi * width / fs_design))) | 1
    beta = 0.1102 * (atten - 8.7)
    cutoff = (edge + 0.5) / 2 * lo_rate
    return signal.firwin(ntaps, cutoff / (fs_design / 2), window=("kaiser", beta)) * p


class ResampledTrack:
    """``track`` at another rate by an exact rational ratio, computed range by range.

    The filter is the Kaiser design of ``resample_taps`` (160 dB stopband, flat to 0.45 x the lower
    rate). A range is computed with real neighbours on both sides, so a ranged read equals the
    whole-file result and no seams show.
    """

    def __init__(self, track, rate_out, max_ratio=4000):
        self.src, self.rate = track, int(rate_out)
        g = gcd(self.rate, track.rate)
        self.p, self.q = self.rate // g, track.rate // g
        if max(self.p, self.q) > max_ratio:
            raise ValueError(f"resampling {track.rate} Hz to {self.rate} Hz needs the ratio {self.p}/{self.q}, which is "
                             f"too awkward; pick a common rate with --rate that is a simple multiple of both")
        self.channels = track.channels
        self.length = -(-track.length * self.p // self.q)
        self.taps = resample_taps(self.p, self.q, self.rate)
        self.half = (len(self.taps) - 1) // 2

    def read(self, ch, start, stop):
        n = stop - start
        if n <= 0:
            return np.zeros(0)
        pad = self.half // self.p + 4  # input samples of context each side
        i0 = (start * self.q) // self.p - pad
        i1 = -(-stop * self.q // self.p) + pad
        # align the block so that the output phase of its first sample is zero
        i0 -= i0 % self.q
        x = self.src.read(ch, i0, i1)
        y = signal.resample_poly(x, self.p, self.q, window=self.taps)
        o0 = i0 * self.p // self.q
        out = np.zeros(n)
        lo, hi = max(start, o0), min(stop, o0 + len(y))
        if hi > lo:
            out[lo - start: hi - start] = y[lo - o0: hi - o0]
        return out
