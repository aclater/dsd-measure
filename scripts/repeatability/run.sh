#!/bin/sh
# The repeatability ensemble: the quick suite of the reference chain, SEEDS perturbed runs with the
# FFT interpolator and SEEDS with the direct-form one, JOBS at a time, then the statistics.
# usage: sh scripts/repeatability/run.sh OUTDIR [SEEDS] [JOBS]      (defaults: 12 seeds, 4 at a time)
# Each run takes one core for one to three minutes and up to 2.5 GB of memory.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
seeds=${2:-12}
jobs=${3:-4}
PY=${PYTHON:-python3}
mkdir -p "$1"
out=$(cd "$1" && pwd)
cd "$out"
$PY -m dsd_measure.cli init suite.toml > /dev/null
for s in $(seq 1 "$seeds"); do
    echo "fft $s"
    echo "direct $s"
done | xargs -P "$jobs" -L 1 sh "$here/one.sh" "$out" "$PY"
$PY "$here/stats.py" "$out"
