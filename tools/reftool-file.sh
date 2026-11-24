#!/bin/sh
# Run a pinned reference tool on one input file and one output file, for the "cli" adapter:
#
#   tools/reftool-file.sh TOOL INFILE OUTFILE ARGS...
#
# In ARGS, @IN and @OUT stand for the container paths of the two files. Example (ffmpeg-free
# decoding a DSDIFF file to 32-bit float WAV):
#
#   command = "tools/reftool-file.sh ffmpeg {input} {output} -v error -y -i @IN -c:a pcm_f32le @OUT"
set -eu
here=$(cd "$(dirname "$0")" && pwd)
tool=$1; in=$2; out=$3; shift 3
indir=$(dirname "$in"); outdir=$(dirname "$out")
mkdir -p "$outdir"
args=""
for a in "$@"; do
    case $a in
        @IN) a=/in/$(basename "$in") ;;
        @OUT) a=/out/$(basename "$out") ;;
    esac
    args="$args $(printf '%s' "$a" | sed "s/'/'\\\\''/g; s/^/'/; s/\$/'/")"
done
eval "set -- $args"
exec "$here/reftool.sh" "$tool" "$indir" "$outdir" "$@"
