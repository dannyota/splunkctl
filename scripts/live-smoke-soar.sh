#!/usr/bin/env bash
# shellcheck source-path=SCRIPTDIR
# Manual test ONLY for a throwaway SOAR profile with Basic authentication.
set -uo pipefail
S="${SPLUNKCTL:-splunkctl}"
PY="${LIVE_PYTHON:-python3}"
T="$(mktemp -d "${TMPDIR:-/tmp}/sc-live-soar.XXXXXX")" || exit 1
N="sc_live_$(date +%s)_$$"
fail=0
: > "$T/cleanup.sh"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=live-smoke-lib.sh
. "$HERE/live-smoke-lib.sh"
soar_finish() {
    local status=$?
    if [ -f "$T/json-failures" ]; then
        while IFS= read -r expression; do bad "JSON extraction: $expression"; done < "$T/json-failures"
    fi
    finish "$status"
}
trap soar_finish EXIT
json_value() {
    "$PY" -c 'import json,sys; d=json.load(open(sys.argv[1])); print(eval(sys.argv[2]))' "$1" "$2" || {
        printf '%s\n' "$2" >> "$T/json-failures"
        return 1
    }
}
# Asset DELETE disables the record; the default list must also hide it.
asset_absent() {
    local id=$1 status
    "$S" --json soar assets get "$id" > "$T/asset-absent.json" 2>&1
    status=$?
    if ! is_not_found "$status" "$T/asset-absent.json"; then
        [ "$status" -eq 0 ] || { cat "$T/asset-absent.json"; return 1; }
        "$PY" - "$T/asset-absent.json" <<'PY_ASSET' || return 1
import json, sys
data = json.load(open(sys.argv[1]))
rows = data if isinstance(data, list) else [data]
assert rows and all(row.get('disabled') is True for row in rows)
PY_ASSET
    fi
    "$S" --json soar assets list --limit 100000 > "$T/asset-absent-list.json" || return 1
    "$PY" - "$T/asset-absent-list.json" "$id" <<'PY_ASSET'
import json, sys
assert not any(str(row['id']) == sys.argv[2] for row in json.load(open(sys.argv[1])))
PY_ASSET
}
# Resolve names exactly, including after a lost create response. Never sweep prefixes.
soar_cleanup() {
    local group=$1 reference=$2 id status
    case "$group" in
        lists|workbook-templates)
            "$S" --json soar "$group" get "$reference" > "$T/cleanup-get.json" 2>&1
            status=$?
            if is_not_found "$status" "$T/cleanup-get.json"; then return 0; fi
            [ "$status" -eq 0 ] || { cat "$T/cleanup-get.json"; return 1; }
            id=$reference;;
        containers)
            case "$reference" in
                *[!0-9]*)
                    local filter
                    filter=$("$PY" -c 'import json,sys; print("_filter_name="+json.dumps(sys.argv[1]))' "$reference") || return 1
                    "$S" --json soar containers list --filter "$filter" > "$T/cleanup-list.json" || return 1
                    id=$(json_value "$T/cleanup-list.json" '[r["id"] for r in d if r["name"] == '"\"$reference\""'][0] if d else ""') || return 1
                    [ -n "$id" ] || return 0;;
                *) id=$reference;;
            esac;;
        assets)
            "$S" --json soar assets list --limit 100000 > "$T/cleanup-list.json" || return 1
            id=$("$PY" - "$T/cleanup-list.json" "$reference" <<'PY'
import json,sys
rows = [r for r in json.load(open(sys.argv[1])) if r['name'] == sys.argv[2]]
assert len(rows) <= 1, rows
print(rows[0]['id'] if rows else '')
PY
            ) || return 1
            [ -n "$id" ] || return 0;;
        evidence) id=$reference;;
        artifacts|notes|vault) id=$reference;;
        *) echo "Unknown cleanup group: $group"; return 1;;
    esac
    case "$group" in
        containers) "$S" --json soar containers delete "$id" --yes;;
        artifacts) "$S" --json soar artifacts delete "$id" --yes;;
        notes) "$S" --json soar notes delete "$id" --yes;;
        evidence) "$S" --json soar evidence remove "$id" --yes;;
        vault) "$S" --json soar vault delete "$id" --yes;;
        lists) "$S" --json soar lists delete "$id" --yes;;
        assets) "$S" --json soar assets delete "$id" --yes;;
        workbook-templates) "$S" --json soar workbook-templates delete "$id" --yes;;
    esac > "$T/delete.log" 2>&1
    status=$?
    cat "$T/delete.log"
    if [ "$status" -ne 0 ]; then
        is_not_found "$status" "$T/delete.log"
        return $?
    fi
    case "$group" in
        evidence|vault|notes) return 0;;
        assets) asset_absent "$id";;
        *) absent soar "$group" get "$id";;
    esac
}
delete_fixture() {
    [ "$1" = soar ] || return 1
    shift
    local group=$1 verb=$2 reference=$3
    [ "$verb" = delete ] || return 1
    soar_cleanup "$group" "$reference"
}
command -v "$S" >/dev/null || { bad "binary missing: $S"; exit 1; }
"$PY" -c 'import json' || { bad 'LIVE_PYTHON unavailable'; exit 1; }
# Check once before the first mutating group, before our no-op playbook exists.
soar_preflight_state=unchecked
soar_selected() {
    selected "$1" || return 1
    case "$1" in 10-meta|90-users-roles) return 0;; esac
    if [ "$soar_preflight_state" = unchecked ]; then
        soar_preflight_state=blocked
        local label
        soar_preflight_state=safe
        # Filtering server-side avoids missing a match beyond the first page.
        for label in events '*' all; do
            if ! capture "$T/active-playbooks.json" "$S" soar playbooks list --active --label "$label" --json; then
                soar_preflight_state=blocked
                break
            fi
            if ! "$PY" - "$T/active-playbooks.json" <<'PYACTIVE'
import json, sys
rows = json.load(open(sys.argv[1]))
assert isinstance(rows, list), rows
for row in rows:
    print('Active playbook may run on fixture label events: ' + str(row.get('name', row)))
sys.exit(bool(rows))
PYACTIVE
            then
                soar_preflight_state=blocked
                break
            fi
        done
    fi
    if [ "$soar_preflight_state" != safe ] && [ "${LIVE_SOAR_ALLOW_ACTIVE_PLAYBOOKS:-0}" != 1 ]; then
        skip "$1: active playbooks can fire on fixture events (including container resolution) and consume licensed actions; set LIVE_SOAR_ALLOW_ACTIVE_PLAYBOOKS=1 to allow"
        return 1
    fi
    return 0
}
# Explicit order keeps fixture helpers available to groups selected alone.
# shellcheck source=live-smoke-soar.d/10-meta.sh
. "$HERE/live-smoke-soar.d/10-meta.sh"
# shellcheck source=live-smoke-soar.d/20-containers.sh
. "$HERE/live-smoke-soar.d/20-containers.sh"
# shellcheck source=live-smoke-soar.d/30-vault.sh
. "$HERE/live-smoke-soar.d/30-vault.sh"
# shellcheck source=live-smoke-soar.d/40-lists.sh
. "$HERE/live-smoke-soar.d/40-lists.sh"
# shellcheck source=live-smoke-soar.d/50-indicators-search.sh
. "$HERE/live-smoke-soar.d/50-indicators-search.sh"
# shellcheck source=live-smoke-soar.d/60-cases.sh
. "$HERE/live-smoke-soar.d/60-cases.sh"
# shellcheck source=live-smoke-soar.d/70-assets-actions.sh
. "$HERE/live-smoke-soar.d/70-assets-actions.sh"
# shellcheck source=live-smoke-soar.d/80-playbooks-functions.sh
. "$HERE/live-smoke-soar.d/80-playbooks-functions.sh"
# shellcheck source=live-smoke-soar.d/90-users-roles.sh
. "$HERE/live-smoke-soar.d/90-users-roles.sh"
# shellcheck source=live-smoke-soar.d/100-ingest.sh
. "$HERE/live-smoke-soar.d/100-ingest.sh"
