#!/bin/sh
# One ensemble member in its own stimulus cache (the perturbed signals must not be shared).
# usage: one.sh OUTDIR PYTHON METHOD SEED
set -u
here=$(cd "$(dirname "$0")" && pwd)
out=$(cd "$1" && pwd) || exit 2  # absolute paths: the script changes directory below
py=$2
case $py in */*) py=$(cd "$(dirname "$py")" && pwd)/$(basename "$py") ;; esac
method=$3
seed=$4
cache=$(mktemp -d "$out/cache.XXXXXX")
cd "$out"
DSD_MEASURE_CACHE_DIR=$cache "$py" "$here/member.py" "$method" "$seed" "$out/$method-$seed" > "$out/$method-$seed.log" 2>&1
status=$?
rm -rf "$cache"
echo "$method $seed: exit $status"
exit $status
