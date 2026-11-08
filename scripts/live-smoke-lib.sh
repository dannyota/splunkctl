# shellcheck shell=bash
# Shared maintainer smoke mechanics. S, PY, T, N and fail are set by the runner.
step() { printf '\n### %s\n' "$*"; }
run() { printf '$ %s\n' "$*"; "$@"; rc=$?; printf '[exit=%s]\n' "$rc"; return "$rc"; }
bad() { echo "FAIL $*"; fail=$((fail+1)); }
expect_ok() { run "$@" || bad 'expected exit 0'; }
expect_fail() { if run "$@"; then bad 'expected non-zero exit'; fi; }
skip() { echo "SKIPPED $*"; }
selected() {
    case ",${LIVE_SKIP:-}," in *",$1,"*) skip "$1: LIVE_SKIP"; return 1;; esac
    case ",${LIVE_ONLY:-}," in ,,|*",$1,"*) return 0;; esac
    skip "$1: not in LIVE_ONLY"; return 1
}
# Register before creation. Reverse order respects dependencies.
defer() {
    if [ "$1" = "$S" ]; then
        shift
        set -- delete_fixture "$@"
    fi
    printf '%q ' "$@" >> "$T/cleanup.sh"
    printf '\n' >> "$T/cleanup.sh"
}
is_not_found() {
    [ "$1" -eq 1 ] && "$PY" - "$2" <<'PY'
import json, sys
rows = [json.loads(s) for s in open(sys.argv[1]) if s.startswith('{')]
assert any(r.get('error', {}).get('kind') == 'not_found' for r in rows)
PY
}
absent() {
    "$S" --json "$@" > "$T/absent.json" 2>&1
    local status=$?
    is_not_found "$status" "$T/absent.json" || {
        cat "$T/absent.json"
        bad "fixture must be absent: $*"
        return 1
    }
}
finish() {
    local status=${1:-$?}
    trap - EXIT
    [ "$status" -eq 0 ] || bad "script exited $status"
    local cleanup_failed=0
    if "$PY" -c 'import sys; print("".join(reversed(open(sys.argv[1]).readlines())), end="")' \
        "$T/cleanup.sh" > "$T/reverse.sh"; then
        : > "$T/remaining.sh"
        while IFS= read -r command; do
            if ! eval "$command"; then
                bad "cleanup: $command"
                cleanup_failed=1
                printf '%s\n' "$command" >> "$T/remaining.sh"
            fi
        done < "$T/reverse.sh"
    else
        bad 'could not reverse cleanup commands'
        cleanup_failed=1
        cp "$T/cleanup.sh" "$T/remaining.sh"
    fi
    if [ "$cleanup_failed" -eq 0 ]; then
        rm -rf "$T"
    else
        printf 'Cleanup incomplete; retained %s\nRemaining commands:\n' "$T"
        cat "$T/remaining.sh"
    fi
    printf '\nRESULT: %s failure(s)\n' "$fail"
    [ "$fail" -eq 0 ]
    exit $?
}
trap finish EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
# Capture stdout only, keeping progress and diagnostics outside JSON artifacts.
capture() {
    local file=$1
    shift
    printf '$ %s\n' "$*"
    "$@" > "$file"
    local status=$?
    cat "$file"
    [ "$status" -eq 0 ] || { bad "expected exit 0, got $status"; return 1; }
}
assert_json() {
    local file=$1 expression=$2
    "$PY" -c 'import json,sys; d=json.load(open(sys.argv[1])); assert eval(sys.argv[2]), d' \
        "$file" "$expression" || bad "JSON assertion: $expression"
}
check_json() {
    local expression=$1
    shift
    if capture "$T/result.json" "$S" --json "$@"; then
        assert_json "$T/result.json" "$expression"
    fi
}
error_kind() {
    local kind=$1
    shift
    expect_fail "$S" --json "$@" > "$T/error.log" 2>&1
    cat "$T/error.log"
    "$PY" - "$T/error.log" "$kind" <<'PY' || bad "expected exit 1 and JSON error kind $kind"
import json, sys
lines = open(sys.argv[1]).readlines()
assert '[exit=1]\n' in lines
errors = [json.loads(s) for s in lines if s.startswith('{')]
assert any(e.get('error', {}).get('kind') == sys.argv[2] for e in errors), errors
PY
}
