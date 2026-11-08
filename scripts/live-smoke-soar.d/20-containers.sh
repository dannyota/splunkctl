#!/usr/bin/env bash
# Sourced by live-smoke-soar.sh. Child cleanup is scoped to an owned container.
ensure_event() {
    [ -z "${C:-}" ] || return 0
    capture "$T/event-precheck.json" "$S" soar containers list --filter "_filter_name=\"$N\"" --json || return 1
    [ "$(json_value "$T/event-precheck.json" 'len(d)')" = 0 ] || { bad 'event name already exists'; return 1; }
    defer soar_cleanup containers "$N"
    capture "$T/container-create.json" "$S" soar containers create --name "$N" \
        --label events --sdi "$N" --yes --json || return 1
    C=$(json_value "$T/container-create.json" 'int(d[0]["id"])') || return 1
}
list_children() {
    local kind=$1 container=$2
    case "$kind" in
        artifacts) "$S" soar artifacts list --container "$container" --json > "$T/children.json";;
        notes) "$S" soar notes list --container "$container" --json > "$T/children.json";;
        evidence) "$S" soar evidence list --container "$container" --json > "$T/children.json";;
        vault) "$S" soar vault list --container "$container" --json > "$T/children.json";;
        *) return 1;;
    esac
}
cleanup_child() {
    local kind=$1 container=$2 match=$3 ids id
    list_children "$kind" "$container" || return 1
    ids=$("$PY" - "$T/children.json" "$kind" "$match" <<'PY'
import json, sys
rows = json.load(open(sys.argv[1]))
kind, match = sys.argv[2:]
key = {'artifacts': 'name', 'notes': 'title', 'vault': 'file_name', 'evidence': 'object_id'}[kind]
for row in rows:
    if str(row.get(key)) == match:
        print(int(row['id']))
PY
    ) || return 1
    local failed=0
    for id in $ids; do soar_cleanup "$kind" "$id" || failed=1; done
    list_children "$kind" "$container" || return 1
    "$PY" - "$T/children.json" "$kind" "$match" <<'PYTEST' || failed=1
import json, sys
key = {'artifacts': 'name', 'notes': 'title', 'vault': 'file_name', 'evidence': 'object_id'}[sys.argv[2]]
assert not any(str(row.get(key)) == sys.argv[3] for row in json.load(open(sys.argv[1])))
PYTEST
    return "$failed"
}

containers_group() {
    ensure_event || return
    expect_ok "$S" soar containers list --filter "_filter_name=\"$N\"" --json
    check_json 'd[0]["name"].startswith("sc_live_")' soar containers get "$C"
    expect_ok "$S" soar containers update "$C" --description "$N updated" --yes
    capture "$T/principals.json" "$S" soar users list --json || return
    U=$(json_value "$T/principals.json" 'next(int(x["id"]) for x in d if x.get("is_active", True) and x.get("type") != "automation")') || return
    capture "$T/roles.json" "$S" soar roles list --json || return
    R=$(json_value "$T/roles.json" 'int(d[0]["id"])') || return
    expect_fail "$S" soar containers assign "$C" --owner "$U" --role "$R" --yes
    expect_fail "$S" soar containers update "$C" --owner "$U" --role "$R" --yes
    expect_ok "$S" soar containers assign "$C" --owner "$U" --yes
    check_json "int(d[0]['owner']) == $U and not d[0].get('role')" soar containers get "$C"
    expect_ok "$S" soar containers assign "$C" --role "$R" --yes
    check_json "int(d[0]['role']) == $R and not d[0].get('owner')" soar containers get "$C"
    defer cleanup_child artifacts "$C" "$N"
    capture "$T/artifact.json" "$S" soar artifacts create --container "$C" --name "$N" \
        --sdi "$N" --cef sourceAddress=192.0.2.1 --no-automation --yes --json || return
    A=$(json_value "$T/artifact.json" 'int(d[0]["id"])') || return
    expect_ok "$S" soar artifacts get "$A" --json
    expect_ok "$S" soar artifacts list --container "$C" --json
    expect_ok "$S" soar artifacts update "$A" --no-automation --cef destinationAddress=192.0.2.2 --yes
    check_json 'd[0]["cef"]["sourceAddress"] == "192.0.2.1" and d[0]["cef"]["destinationAddress"] == "192.0.2.2"' soar artifacts get "$A"
    defer cleanup_child notes "$C" "$N"
    capture "$T/note.json" "$S" soar notes add --container "$C" --title "$N" "$N note" --yes --json || return
    NOTE=$(json_value "$T/note.json" 'int(d[0]["id"])') || return
    expect_ok "$S" soar notes list --container "$C" --json
    capture "$T/comment.json" "$S" soar notes comment "$C" "$N comment" --yes --json || return
    COMMENT=$(json_value "$T/comment.json" 'int(d[0]["id"])') || return
    expect_fail "$S" soar notes comment-delete "$COMMENT"
    defer cleanup_child evidence "$C" "$A"
    expect_ok "$S" soar evidence add "$C" --object artifact --id "$A" --yes
    defer cleanup_child evidence "$C" "$NOTE"
    expect_ok "$S" soar evidence add "$C" --object note --id "$NOTE" --yes
    check_json "any(x.get('content_type') == 'artifact' and int(x['object_id']) == $A for x in d) and any(x.get('content_type') == 'note' and int(x['object_id']) == $NOTE for x in d)" soar evidence list --container "$C"
}
if soar_selected 20-containers; then
    step '20-containers'
    containers_group
fi
