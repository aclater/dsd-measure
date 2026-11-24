#!/bin/sh
# Public-text audit: fail if a tracked file or a commit identity matches the private-names list.
# The list is a single extended regex kept OUTSIDE the repository:
#   CI:    the PRIVATE_NAMES environment variable (a repository variable)
#   local: the file named by DSDM_PRIVATE_NAMES_FILE (default ~/.config/dsd-measure/private-names.regex),
#          which must not be accessible to group or others.
# Fails closed: no list, a bad list, or any error running the check is a failure, never a pass.
# Optional: BASE_SHA limits the identity scan to BASE_SHA..HEAD (default: all of HEAD).
set -u
cd "$(dirname "$0")/.."

fail() { echo "public-text audit FAILED: $1" >&2; exit 2; }

patterns=${PRIVATE_NAMES:-}
if [ -z "$patterns" ]; then
    file=${DSDM_PRIVATE_NAMES_FILE:-${HOME:-/nonexistent}/.config/dsd-measure/private-names.regex}
    [ -f "$file" ] || fail "no private-names list (set PRIVATE_NAMES or DSDM_PRIVATE_NAMES_FILE)"
    mode=$(stat -c %a -- "$file") || fail "cannot stat the private-names file"
    case $mode in
        *00) ;;
        *) fail "the private-names file must be mode 0600 (it is $mode)" ;;
    esac
    patterns=$(cat -- "$file") || fail "cannot read the private-names file"
fi

# An empty alternative or an empty list would match every line.
case $patterns in
    '' | *[![:space:]]*) ;;
    *) fail "no private-names list (it is empty)" ;;
esac
[ -n "$patterns" ] || fail "no private-names list (it is empty)"
case $patterns in
    '|'* | *'|' | *'||'* | *'(|'* | *'|)'* | *'
'*) fail "the private-names list has an empty alternative or more than one line" ;;
esac

status=0

rc=0
git grep -nIiE -e "$patterns" -- . || rc=$?
case $rc in
    0) echo "public-text audit FAILED: private details in tracked files" >&2; status=1 ;;
    1) ;;
    *) fail "the check could not run on tracked files (git grep exit $rc)" ;;
esac

if [ -n "${BASE_SHA:-}" ]; then range="$BASE_SHA..HEAD"; else range=HEAD; fi
log=$(git log --format='%h %an <%ae> %cn <%ce>' "$range") \
    || fail "the check could not run on commit identities (git log failed)"
rc=0
hits=$(printf '%s\n' "$log" | grep -iE -e "$patterns") || rc=$?
case $rc in
    0) echo "public-text audit FAILED: private details in commit identities:" >&2
       printf '%s\n' "$hits" >&2; status=1 ;;
    1) ;;
    *) fail "the check could not run on commit identities (grep exit $rc)" ;;
esac

[ "$status" -eq 0 ] && echo "public-text audit passed"
exit "$status"
