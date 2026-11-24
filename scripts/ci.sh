#!/bin/sh
# Local CI: lint, then the tests under a memory cap when systemd-run is available.
set -eu
cd "$(dirname "$0")/.."
PY=${PYTHON:-python3}
$PY -m ruff check src tests
if command -v systemd-run >/dev/null 2>&1; then
    systemd-run --user --scope -q -p MemoryMax=4G -p MemorySwapMax=0 $PY -m pytest -q tests
else
    $PY -m pytest -q tests
fi
