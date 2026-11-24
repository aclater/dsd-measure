"""Level conventions (see docs/footprint.md)."""

import math

#: 0 dB SACD is 50 % modulation, which is -6.02 dBFS (nominally -6 dBFS).
REF_DBFS = 20 * math.log10(0.5)
#: Peak level, +3.1 dB SACD, is 71.43 % modulation.
PEAK_PCT = 71.43
PEAK_DBFS = 20 * math.log10(PEAK_PCT / 100)


def db_to_amp(db):
    return 10 ** (db / 20)


def amp_to_db(a):
    return 20 * math.log10(max(a, 1e-300))


def dbfs_to_sacd(dbfs):
    """PCM level in dBFS to dB SACD (0 dB SACD = 50 % = -6.02 dBFS)."""
    return dbfs - REF_DBFS


def sacd_to_dbfs(db_sacd):
    return db_sacd + REF_DBFS
