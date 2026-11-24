#!/bin/sh
# Run a pinned black-box reference tool in a rootless, network-less container.
#
#   tools/reftool.sh build
#   tools/reftool.sh versions [FILE]
#   tools/reftool.sh sox-dsd       IN_DIR OUT_DIR ARGS...
#   tools/reftool.sh sacd-extract  IN_DIR OUT_DIR ARGS...
#   tools/reftool.sh sox           IN_DIR OUT_DIR ARGS...   (stock SoX)
#   tools/reftool.sh ffmpeg        IN_DIR OUT_DIR ARGS...
#
# Inside the container IN_DIR is /in (read-only) and OUT_DIR is /out (writable),
# so ARGS name files as /in/name and /out/name.
set -eu

here=$(cd "$(dirname "$0")" && pwd)
root=$(dirname "$here")
engine=${REFTOOL_ENGINE:-podman}
prefix=${REFTOOL_PREFIX:-localhost/dsdm}
# REFTOOL_RELABEL=1: on hosts where a confined user may not run containers unconfined, mount the
# folders with the shared SELinux label (:z) instead of switching the label check off.
relabel=${REFTOOL_RELABEL:-0}

build() {
    for t in sox-dsd sacd-extract ffmpeg-sox; do
        "$engine" build -q -t "$prefix-$t" "$root/containers/$t" >/dev/null
        echo "built $prefix-$t"
    done
}

run() {
    image=$1; entry=$2; shift 2
    [ $# -ge 2 ] || { echo "usage: reftool.sh TOOL IN_DIR OUT_DIR ARGS..." >&2; exit 2; }
    in=$(cd "$1" && pwd); mkdir -p "$2"; out=$(cd "$2" && pwd); shift 2
    if [ "$relabel" = 1 ]; then
        sel=""; vin="$in:/in:ro,z"; vout="$out:/out:z"
    else
        sel="--security-opt=label=disable"; vin="$in:/in:ro"; vout="$out:/out"
    fi
    exec "$engine" run --rm --network=none --cap-drop=all \
        --security-opt=no-new-privileges $sel \
        --userns=keep-id --user "$(id -u):$(id -g)" --read-only --tmpfs /tmp \
        -v "$vin" -v "$vout" -w /out \
        ${entry:+--entrypoint "$entry"} "$prefix-$image" "$@"
}

# Print one JSON document: tool versions, pinned source and image ids.
versions() {
    img() { "$engine" image inspect --format '{{.Id}}' "$prefix-$1"; }
    
    soxd=$("$engine" run --rm --network=none "$prefix-sox-dsd" --version | sed 's/.*SoX //')
    sacd=$("$engine" run --rm --network=none "$prefix-sacd-extract" -v 2>&1 | sed -n 's/.*[Vv]ersion[: ]*//p' | head -1)
    ff=$("$engine" run --rm --network=none --entrypoint ffmpeg "$prefix-ffmpeg-sox" -version | sed -n '1s/ffmpeg version \([^ ]*\).*/\1/p')
    sx=$("$engine" run --rm --network=none --entrypoint sox "$prefix-ffmpeg-sox" --version | sed 's/.*SoX //')
    sc=$("$engine" run --rm --network=none --entrypoint cat "$prefix-sox-dsd" /opt/sox/SOURCE_COMMIT)
    sr=$("$engine" run --rm --network=none --entrypoint cat "$prefix-sacd-extract" /opt/sacd/SOURCE_COMMIT)
    cat <<JSON
{
  "sox-dsd": {"version": "$soxd", "source": "https://github.com/mansr/sox", "commit": "$sc", "image_id": "$(img sox-dsd)"},
  "sacd-extract": {"version": "${sacd:-0.3.9.3}", "source": "https://github.com/sacd-ripper/sacd-ripper", "tag_and_commit": "$sr", "image_id": "$(img sacd-extract)"},
  "ffmpeg": {"version": "$ff", "source": "Fedora 43 ffmpeg-free", "image_id": "$(img ffmpeg-sox)"},
  "sox": {"version": "$sx", "source": "Fedora 43 sox", "image_id": "$(img ffmpeg-sox)"}
}
JSON
}

cmd=${1:-}; [ $# -gt 0 ] && shift
case $cmd in
    build) build ;;
    versions) if [ $# -gt 0 ]; then versions >"$1"; else versions; fi ;;
    sox-dsd) run sox-dsd "" "$@" ;;
    sacd-extract) run sacd-extract "" "$@" ;;
    sox) run ffmpeg-sox sox "$@" ;;
    ffmpeg) run ffmpeg-sox ffmpeg "$@" ;;
    *) echo "usage: reftool.sh build|versions|sox-dsd|sacd-extract|sox|ffmpeg ..." >&2; exit 2 ;;
esac
