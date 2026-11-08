#!/usr/bin/env bash
# Manual test ONLY for a throwaway Splunk Enterprise profile. Never run in CI.
# "$PY" must have splunkctl and PyYAML installed (also used for stanza cleanup).
# LIVE_HEC_URL must match hec settings enableSSL: https by default, http if disabled.
set -uo pipefail
S="${SPLUNKCTL:-splunkctl}"
PY="${LIVE_PYTHON:-python3}"
T="$(mktemp -d)" || exit 1
N="sc_live_$(date +%s)_$$"
export SPLUNK_APP=search
fail=0
: > "$T/cleanup.sh"
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
delete_fixture() {
    "$S" --json "$@" > "$T/delete.log" 2>&1
    local status=$?
    cat "$T/delete.log"
    if [ "$status" -ne 0 ]; then
        is_not_found "$status" "$T/delete.log"
        return $?
    fi
    local group=$1 verb=$2 name=$3
    shift 3
    case "$group:$verb" in
        users:roles) absent users roles get "$1";;
        parsers:delete) absent conf get props "$name" --app search;;
        kvstore:delete) absent kvstore query "$name" --app search;;
        apps:uninstall) absent apps get "$name";;
        search:cancel) return 0;;
        *) absent "$group" get "$name";;
    esac
}
finish() {
    local status=$?
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
# No CLI stanza-delete verb exists. Use the same installed client and profile.
stanza_delete() {
    "$PY" - "$1" "$2" <<'PY'
import sys
from splunkctl.client import SplunkClient
from splunkctl.commands.conf_ops import get_stanza
assert sys.argv[2].startswith('sc_live_')
try:
    get_stanza(SplunkClient(), sys.argv[1], sys.argv[2], app='search').delete()
except KeyError:
    pass
except Exception as exc:
    if getattr(exc, 'status', None) != 404:
        raise
PY
}
"$PY" -c 'import splunkctl.client, yaml' || { bad '"$PY" needs splunkctl and PyYAML'; exit 1; }
command -v "$S" >/dev/null || { bad "binary missing: $S"; exit 1; }
printf 'ip,label\n10.0.0.1,test-a\n10.0.0.2,test-b\n' > "$T/lk.csv"
printf 'ip,label\n10.0.0.9,test-z\n' > "$T/lk2.csv"
printf 'sc_live_ smoke event\n' > "$T/event.txt"
printf '<dashboard version="1.1"><label>sc_live_v1</label></dashboard>\n' > "$T/dash.xml"
printf '<dashboard version="1.1"><label>sc_live_v2</label></dashboard>\n' > "$T/dash2.xml"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Files are sourced explicitly to preserve the documented group order.
. "$HERE/live-smoke.d/10-core.sh"
. "$HERE/live-smoke.d/20-content.sh"
. "$HERE/live-smoke.d/30-admin.sh"
