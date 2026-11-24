#!/bin/sh
# Release check in a fresh Fedora container, installing from this working tree (committed files only):
#
#   sh scripts/container-check.sh quickstart   the README Quick start (measures ffmpeg)
#   sh scripts/container-check.sh selftest     the reference chain measured by itself (dsd-measure init, run)
#   sh scripts/container-check.sh compare      the README two-decoder example
#
# The container starts from an empty Fedora image, so a package missing from the README's install
# line shows up as a failure. Needs Podman. Nothing from the host is writable inside the container.
set -eu
cd "$(dirname "$0")/.."
mode=${1:-quickstart}
case "$mode" in
    quickstart) pkgs="gcc git python3-pip pipx ffmpeg-free"
        steps=$(cat <<'EOF'
dsd-measure --version
dsd-measure quick ffmpeg --plan
dsd-measure quick ffmpeg | tee quick.log
test "$(tail -n 1 quick.log | cut -c1-7)" = "Result:"
ls report/ffmpeg
test -f report/ffmpeg/index.html
grep -q '^\*\*Result:' report/ffmpeg/index.md
EOF
) ;;
    selftest) pkgs="gcc git python3-pip pipx"
        steps=$(cat <<'EOF'
dsd-measure --version
dsd-measure init
dsd-measure run suite.toml
ls report/comparison
EOF
) ;;
    compare) pkgs="gcc git python3-pip pipx ffmpeg-free"
        steps=$(cat <<'EOF'
sed -n '/^```toml/,/^```/p' /work/README.md | sed '1d;$d' > compare.toml
dsd-measure run compare.toml --plan
dsd-measure run compare.toml
ls report report/comparison
test -f report/ffmpeg/index.md
test -f report/reference-decoder/index.md
test -f report/comparison/index.md
EOF
) ;;
    *) echo "usage: $0 quickstart|selftest|compare" >&2; exit 2 ;;
esac
inner="dnf install -y -q $pkgs
git config --global --add safe.directory /src
git clone -q /src /work
pipx install /work
PATH=/root/.local/bin:\$PATH
cd /tmp
$steps"
exec podman run --rm -v "$PWD":/src:ro,Z registry.fedoraproject.org/fedora:43 sh -eu -c "$inner"
