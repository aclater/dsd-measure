#!/bin/sh
# Full accuracy validation (docs/accuracy.md): known answers, estimator statistics, the reference
# chain, SoX and ffmpeg cross-checks, and the SoX-DSD conditions of the published tests.
#
#   scripts/validate.sh [known|stats|chain|tools|archimago|all] [--out DIR]
#
# Needs the Python environment of the repository (pip install -e '.[dev]'). The tools and
# archimago sections, and the SoX and ffmpeg columns of the chain section, need rootless Podman
# and the pinned images (tools/reftool.sh build); without them those parts are skipped and the
# output says so. Takes about 15 minutes. Runs at the lowest priority and under a memory cap.
# Variables: PYTHON, VALIDATE_MEM (default 16G), REFTOOL_PREFIX and REFTOOL_RELABEL (see reftool.sh).
set -eu
cd "$(dirname "$0")/.."
PY=${PYTHON:-python3}
if command -v systemd-run >/dev/null 2>&1; then
    exec nice -n 19 systemd-run --user --scope -q -p MemoryMax="${VALIDATE_MEM:-16G}" -p MemorySwapMax=0 \
        "$PY" scripts/validate.py "$@"
fi
exec nice -n 19 "$PY" scripts/validate.py "$@"
