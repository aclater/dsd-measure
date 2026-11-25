"""Shared test setup: the stimulus cache is off unless a test turns it on in its own folder, and
runs are serial (one process) unless a test asks for jobs."""

import pytest


@pytest.fixture(autouse=True)
def _no_stimulus_cache(monkeypatch):
    from dsd_measure import stimcache
    monkeypatch.setenv("DSD_MEASURE_NO_CACHE", "1")
    monkeypatch.setenv("DSD_MEASURE_JOBS", "1")
    monkeypatch.setitem(stimcache._state, "enabled", None)
    yield


@pytest.fixture
def stim_cache(monkeypatch, tmp_path):
    """Turn the stimulus cache on in a private folder of this test; returns the cache root."""
    from dsd_measure import encode, stimcache
    root = tmp_path / "cache"
    monkeypatch.setenv("DSD_MEASURE_CACHE_DIR", str(root))
    monkeypatch.delenv("DSD_MEASURE_NO_CACHE")
    monkeypatch.delenv("DSD_MEASURE_CACHE_MAX_MB", raising=False)
    encode._lib.cache_clear()
    stimcache.reset_stats()
    yield root
    encode._lib.cache_clear()
