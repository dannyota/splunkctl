#!/usr/bin/env bash
# Run ONLY against a throwaway Splunk Enterprise instance: the lab, a local
# container, or the CI container in .github/workflows/live-siem.yml.
# "$PY" must have splunkctl and PyYAML installed (also used for stanza cleanup).
# LIVE_HEC_URL must match hec settings enableSSL: https by default, http if disabled.
set -uo pipefail
S="${SPLUNKCTL:-splunkctl}"
PY="${LIVE_PYTHON:-python3}"
# Explicit template: BSD and GNU mktemp differ on when TMPDIR applies.
T="$(mktemp -d "${TMPDIR:-/tmp}/sc-live.XXXXXX")" || exit 1
N="sc_live_$(date +%s)_$$"
export SPLUNK_APP=search
fail=0
: > "$T/cleanup.sh"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=live-smoke-lib.sh
. "$HERE/live-smoke-lib.sh"
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
# Resolve again at cleanup: sharing moves objects to the nobody namespace.
shared_fixture_delete() {
    local resource=$1 name=$2 status paths path
    case "$resource" in saved/searches|data/ui/views|configs/conf-macros) ;; *) return 1;; esac
    case "$name" in sc_live_*) ;; *) return 1;; esac
    "$S" --json api get "/servicesNS/-/search/$resource/$name" \
        > "$T/shared-get.json" 2> "$T/shared-get.err"
    status=$?
    if [ "$status" -ne 0 ]; then
        is_not_found "$status" "$T/shared-get.err"
        return $?
    fi
    paths=$("$PY" - "$T/shared-get.json" "$name" "$resource" <<'PYSHARED' 2> "$T/shared-path.err"
import json, sys
from urllib.parse import urlsplit
body, name, resource = sys.argv[1:]
for entry in json.load(open(body))[0].get('entry', []):
    assert entry['name'] == name and entry['acl']['app'] == 'search'
    target = urlsplit(entry['id']).path
    assert target.startswith('/servicesNS/') and '/' + resource + '/' in target
    print(target)
PYSHARED
) || return 1
    while IFS= read -r path; do
        [ -n "$path" ] || continue
        "$S" --json api delete "$path" --yes > "$T/shared-delete.json" 2> "$T/shared-delete.err"
        status=$?
        if [ "$status" -ne 0 ]; then
            is_not_found "$status" "$T/shared-delete.err" || return 1
        fi
    done <<< "$paths"
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
# shellcheck disable=SC2016
"$PY" -c 'import splunkctl.client, yaml' || { bad '"$PY" needs splunkctl and PyYAML'; exit 1; }
command -v "$S" >/dev/null || { bad "binary missing: $S"; exit 1; }
printf 'ip,label\n10.0.0.1,test-a\n10.0.0.2,test-b\n' > "$T/lk.csv"
printf 'ip,label\n10.0.0.9,test-z\n' > "$T/lk2.csv"
printf 'sc_live_ smoke event\n' > "$T/event.txt"
printf '<dashboard version="1.1"><label>sc_live_v1</label></dashboard>\n' > "$T/dash.xml"
printf '<dashboard version="1.1"><label>sc_live_v2</label></dashboard>\n' > "$T/dash2.xml"
# Files are sourced explicitly to preserve the documented group order.
. "$HERE/live-smoke.d/10-core.sh"
. "$HERE/live-smoke.d/20-content.sh"
. "$HERE/live-smoke.d/30-admin.sh"
. "$HERE/live-smoke.d/40-api.sh"
. "$HERE/live-smoke.d/45-acl-server.sh"
if [ -n "${alert_started:-}" ]; then finish_fired_alert; fi
