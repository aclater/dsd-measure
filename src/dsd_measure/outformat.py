"""Output word length: what a converter wrote, and what that format alone can hide.

A converter that writes integer PCM adds rounding noise whatever its decoder does: plain rounding to 16 bits
reads about 92.5 dB SINAD at 44.1 kHz output and 101.5 dB at 352.8 kHz, and a 24-bit file about 140.7 and 149.7 dB; with TPDF
dither, the usual way to write a file, the noise is 4.77 dB higher. Read as a verdict on the decoder, that noise would be wrong, so
every measured file's format is recorded and a result that the format may limit is reported as such, for any integer word length.
Floating-point output is not limited. Whether a file was dithered is not detected: both bounds are given.
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


#: TPDF dither of two LSB peak to peak adds LSB squared / 6 to the rounding noise of LSB squared / 12: 4.77 dB in all.
TPDF_COST_DB = 10 * math.log10(3.0)


def quantisation_sinad_db(bits, rate, band_hz=BAND_HZ, tone_shift_db=0.0, dithered=False):
    """SINAD (dB) that rounding to ``bits`` integer bits alone allows for the 0 dB SACD tone.

    Rounding noise is white with power (LSB squared) / 12; the analysis keeps the share inside
    ``band_hz``. Plain rounding is the best case for the format; ``dithered=True`` gives the figure with
    TPDF dither, which costs 4.77 dB more.
    ``tone_shift_db`` is how far the tone as written in the file sits above (+) or below (-) the nominal level
    (a tool that writes 6 dB low has 6 dB less to work with).
    """
    lsb = 2.0 ** (1 - bits)
    noise = lsb / math.sqrt(12) * math.sqrt(min(band_hz / (rate / 2), 1.0))
    return 20 * math.log10(TONE_RMS / noise) + tone_shift_db - (TPDF_COST_DB if dithered else 0.0)


def narrowest(formats):
    """The most limiting of the recorded formats (integer before float, fewer bits first), or None."""
    fs = [f for f in formats if f]
    return min(fs, key=lambda f: (f["kind"] != "int", f["bits"])) if fs else None


def summary(fmt, tone_shift_db=0.0):
    """What goes into the metrics: the format and the SINAD an integer format of that width allows, plain and with TPDF dither.

    ``tone_shift_db`` is the level of the tone as the tool wrote it, relative to nominal.
    """
    if not fmt:
        return None
    out = {"container": fmt["container"], "kind": fmt["kind"], "bits": fmt["bits"], "rate": fmt["rate"], "text": name_of(fmt)}
    if fmt["kind"] == "int":
        out["quantisation_sinad_db"] = round(quantisation_sinad_db(fmt["bits"], fmt["rate"], tone_shift_db=tone_shift_db), 1)
        out["quantisation_sinad_dithered_db"] = round(
            quantisation_sinad_db(fmt["bits"], fmt["rate"], tone_shift_db=tone_shift_db, dithered=True), 1)
        out["tone_shift_db"] = round(float(tone_shift_db), 1)
    return out


def limits_result(fmt):
    """True for integer output of any width below 32 bits: its rounding noise may cap a result (see ``bound_text``).

    Whether it does depends on the measured figure, which ``conclusions.format_limit`` checks against both bounds. Floating-point
    output is never limited.
    """
    return bool(fmt) and fmt.get("kind") == "int" and fmt.get("bits", 32) < 32


def bound_text(fmt):
    """``"140.7 dB with plain rounding or 135.9 dB with TPDF dither"`` for an integer format."""
    hi = quantisation_sinad_db(fmt["bits"], fmt["rate"])
    lo = quantisation_sinad_db(fmt["bits"], fmt["rate"], dithered=True)
    return f"{hi:.1f} dB with plain rounding or {lo:.1f} dB with TPDF dither"


def warning(fmt, command=""):
    """The sentence that tells a user their output format may limit the result, or None."""
    if not limits_result(fmt):
        return None
    msg = (f"the tool wrote {name_of(fmt)} PCM at {fmt['rate'] / 1000:g} kHz, which alone limits SINAD to about {bound_text(fmt)} "
           "whatever the decoder does, so a figure near that cannot be told from the file format. Ask the tool for floating-point output")
    words = str(command).split()
    if words and Path(words[0]).name == "ffmpeg":
        msg += " (for ffmpeg, add -c:a pcm_f32le before the output file)"
    return msg + "."
