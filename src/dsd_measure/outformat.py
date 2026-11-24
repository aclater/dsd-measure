"""Output word length: what a converter wrote, and what that format alone can hide.

A converter that writes 16-bit PCM adds rounding noise of about -98 dBFS (in the whole band; 92.5 dB SINAD at 44.1 kHz output, 101.5 dB at 352.8 kHz), whatever its decoder
does. Read as a verdict on the decoder, that noise would be wrong, so every measured file's format
is recorded and a result that the format limits is reported as such.
"""

import math
import struct
from pathlib import Path

#: The analysis band of SINAD, THD+N and dynamic range (Hz).
BAND_HZ = 20000.0
#: The test tone's RMS (0 dB SACD = -6.02 dBFS, amplitude 0.5).
TONE_RMS = 0.5 / math.sqrt(2)


def wav_format(path):
    """``{"container": "wav", "kind": "int"|"float", "bits": N, "rate": Hz, "channels": N}`` for a WAV file."""
    with open(path, "rb") as f:
        head = f.read(12)
        if head[:4] != b"RIFF" or head[8:12] != b"WAVE":
            raise ValueError("not a WAV file")
        while True:
            hdr = f.read(8)
            if len(hdr) < 8:
                raise ValueError("WAV: missing fmt chunk")
            cid, size = hdr[:4], struct.unpack("<I", hdr[4:])[0]
            if cid == b"fmt ":
                body = f.read(min(size, 64))
                if len(body) < 16:
                    raise ValueError("WAV: short fmt chunk")
                tag, ch, rate, _, _, bits = struct.unpack("<HHIIHH", body[:16])
                if tag == 0xFFFE and len(body) >= 26:
                    tag = struct.unpack("<H", body[24:26])[0]
                    valid = struct.unpack("<H", body[18:20])[0]
                    if 0 < valid < bits:
                        bits = valid  # 16 valid bits in a wider container
                if rate <= 0:
                    raise ValueError("WAV: sample rate 0 in the header")
                return {"container": "wav", "kind": "float" if tag == 3 else "int", "bits": int(bits),
                        "rate": int(rate), "channels": int(ch)}
            f.seek(size + (size & 1), 1)


def flac_format(path):
    """The same record for a FLAC file, from its STREAMINFO block (FLAC holds integers only)."""
    with open(path, "rb") as f:
        head = f.read(42)
    if head[:4] != b"fLaC" or len(head) < 42:
        raise ValueError("not a FLAC file")
    v = int.from_bytes(head[18:26], "big")  # 20 bits rate, 3 bits channels - 1, 5 bits bits per sample - 1
    return {"container": "flac", "kind": "int", "bits": ((v >> 36) & 0x1F) + 1, "rate": v >> 44,
            "channels": ((v >> 41) & 0x7) + 1}


def audio_format(path):
    return flac_format(path) if Path(path).suffix.lower() == ".flac" else wav_format(path)


def name_of(fmt):
    """``"16-bit integer"`` or ``"32-bit float"``."""
    return f"{fmt['bits']}-bit {'integer' if fmt['kind'] == 'int' else fmt['kind']}"


def quantisation_sinad_db(bits, rate, band_hz=BAND_HZ, tone_shift_db=0.0):
    """SINAD (dB) that rounding to ``bits`` integer bits alone allows for the 0 dB SACD tone.

    Rounding noise is white with power (LSB squared) / 12; the analysis keeps the share inside
    ``band_hz``. Dither would cost about 4.8 dB more, so this is the best case for the format.
    ``tone_shift_db`` is how far the tone as written in the file sits above (+) or below (-) the nominal level
    (a tool that writes 6 dB low has 6 dB less to work with).
    """
    lsb = 2.0 ** (1 - bits)
    noise = lsb / math.sqrt(12) * math.sqrt(min(band_hz / (rate / 2), 1.0))
    return 20 * math.log10(TONE_RMS / noise) + tone_shift_db


def narrowest(formats):
    """The most limiting of the recorded formats (integer before float, fewer bits first), or None."""
    fs = [f for f in formats if f]
    return min(fs, key=lambda f: (f["kind"] != "int", f["bits"])) if fs else None


def summary(fmt, tone_shift_db=0.0):
    """What goes into the metrics: the format and the SINAD an integer format of that width allows.

    ``tone_shift_db`` is the level of the tone as the tool wrote it, relative to nominal.
    """
    if not fmt:
        return None
    out = {"container": fmt["container"], "kind": fmt["kind"], "bits": fmt["bits"], "rate": fmt["rate"], "text": name_of(fmt)}
    if fmt["kind"] == "int":
        out["quantisation_sinad_db"] = round(quantisation_sinad_db(fmt["bits"], fmt["rate"], tone_shift_db=tone_shift_db), 1)
        out["tone_shift_db"] = round(float(tone_shift_db), 1)
    return out


def limits_result(fmt):
    """True when the integer word length alone caps the result below the reference chain's floor (16-bit and shorter)."""
    return bool(fmt) and fmt.get("kind") == "int" and fmt.get("bits", 32) < 24


def warning(fmt, command=""):
    """The sentence that tells a user their output format limits the result, or None."""
    if not limits_result(fmt):
        return None
    limit = quantisation_sinad_db(fmt["bits"], fmt["rate"])
    msg = (f"the tool wrote {name_of(fmt)} PCM, which alone limits SINAD to about {limit:.1f} dB whatever the decoder "
           "does, so the report cannot judge the decoder. Ask the tool for floating-point output (or 32-bit integer)")
    words = str(command).split()
    if words and Path(words[0]).name == "ffmpeg":
        msg += " (for ffmpeg, add -c:a pcm_f32le before the output file)"
    return msg + "."
