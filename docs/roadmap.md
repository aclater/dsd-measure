[dsd-measure](../README.md) › [Documentation](README.md) › Roadmap

# Roadmap

What is planned and what has been done.

## Done: real-music difference test

Status: done, in `dsd-measure null`.

Decode a DSD file you supply, with two or more decoders, and report the difference between the outputs (a null test): the level of the difference and its spectrum, aligned in time and level first. It is distinct from the synthetic tests: it cannot be repeated without the same file, and it shows that two decoders differ, not which one is right. See the [user guide](user-guide.md#compare-decoders-on-your-own-music) and [options](options.md#null-test).

## Not done in 0.1.2 (methodology review)

A hostile methodology review of 0.1.2 found the claims in the reports too strong; those were fixed before the release (see the changelog and [methodology limits](methodology-limits.md)). What it asks for next, in order, for 0.2:

- **Repeatability intervals** over at least eight realisations (dither seed, tone phase, sub-sample offset, record start), so a table can say "differs by x +- y dB" and mark a difference only when intervals do not overlap and neither figure is at the floor.
- **A matrix of stimuli and readbacks** that are not ours: class A devices fed by SoX-DSD and a plain 5th-order loop as well as the built-in modulator, class B devices read back by SoX-DSD and ffmpeg as well as the built-in decoder, and a published frozen set of stimulus files with hashes.
- **Every decoder at every common output rate**, an equalised table at one common format, and detection of dither and truncation from the output's low bits.
- **A pinned container with the competitor builds**, kept device outputs and a checked table of stimulus hashes across platforms.
- **Outside validation**: a cross-language analyser written from the footprint alone, readings from REW, Multitone Analyzer and DeltaWave, an Audio Precision owner's APx run, and an outside reader of the method.
- **An `aes17` profile** (997 Hz, CCIR-RMS, the standard notch and low-pass, levels re maximum) for the cross-check, an idle-tone search, a common-low-pass figure and a close-in energy row.
- **A pre-registered protocol** for any published comparison, with a maintainer review window of at least 14 days.

## Not done in 0.1.1 (second review)

Found by the second internal review of 0.1.1 and left for 0.1.2. None changes a figure that a conclusion uses.

- **Stability flag.** `saturated` (28 equal bits) misses a loop that clipping keeps bounded but broken (SINAD 6 to 11 dB at the peak level still reads "Stable"). Plan: also call a hold unstable when its THD+N is more than 20 dB worse than at 0 dB SACD or above -40 dB. The stability conclusion stays off until then.
- **Density at 50 kHz** is a third-octave mean, 5.6 dB above the density at 50 kHz at DSD64. Plan: a narrow-band density, or rename the row.
- **Polarity** searches a window shifted by the device delay, not the whole record; the polarity conclusion stays off.
- **Flat response** in the conclusions is read from five tones, not the whole tone list, and 0.5 dB is the threshold a reviewer will dispute.
- **Nits:** the multitone floor uses 3 periods and the full profile 8; "IMD sweep, worst SMPTE" is the noise at -60 dB SACD; the 15 kHz "strongest unwanted tone" is the noise maximum; the idle noise of a single-bit loop is below its noise with a tone (compare dynamic range); class B crosstalk is the modulator's own noise; the class B floor row reads -280.9 dB; two unused signals in `measure.py`; a null-only run logs a report path that does not exist; the alias floor flag uses the noise at 1 kHz.
- **Filter rows at wide-band outputs** are "not measurable". A better way to read them (a longer or louder impulse record) is open.

## See also

- [User guide](user-guide.md)
- [Measurement footprint](footprint.md)

Part of the [DSD Toolbox](https://github.com/dsd-toolbox/dsd-toolbox).
