#!/usr/bin/env bash
cases_group() {
    # Register template first so reverse cleanup deletes its container first.
    absent soar workbook-templates get "$N" || return
    defer soar_cleanup workbook-templates "$N"
    capture "$T/template.json" "$S" soar workbook-templates create --name "$N" --phases "$N" --yes --json || return
    expect_ok "$S" soar workbook-templates get "$N" --json
    expect_ok "$S" soar workbook-templates list --json
    expect_ok "$S" soar workbook-templates update "$N" --add-phase "${N}_second" --yes
    capture "$T/case-precheck.json" "$S" soar containers list --filter "_filter_name=\"${N}_case\"" --json || return
    [ "$(json_value "$T/case-precheck.json" 'len(d)')" = 0 ] || { bad 'case name already exists'; return; }
    defer soar_cleanup containers "${N}_case"
    capture "$T/case.json" "$S" soar containers create --name "${N}_case" \
        --label events --sdi "${N}_case" --yes --json || return
    CASE=$(json_value "$T/case.json" 'int(d[0]["id"])') || return
    expect_ok "$S" soar containers close "$CASE" --yes
    capture "$T/case-closed.json" "$S" soar containers get "$CASE" --json || return
    if [ "$(json_value "$T/case-closed.json" 'd[0]["status"]')" != closed ]; then
        bad 'owned container must be closed before promotion'
        skip '60-cases: close did not stick'
        return
    fi
    expect_ok "$S" soar cases promote "$CASE" --template "$N" --yes
    capture "$T/case-promoted.json" "$S" soar containers get "$CASE" --json || return
    if [ "$(json_value "$T/case-promoted.json" 'd[0]["status"]')" != closed ]; then
        bad 'promotion reopened owned case'
        expect_ok "$S" soar containers close "$CASE" --yes
        skip '60-cases: promotion reopened case; remaining case steps skipped'
        return
    fi
    assert_json "$T/case-promoted.json" 'd[0]["container_type"] == "case"'
    expect_ok "$S" soar cases workbook "$CASE" --json
    capture "$T/phase.json" "$S" soar cases phase add --container "$CASE" --name "${N}_manual" --yes --json || return
    PHASE=$(json_value "$T/phase.json" 'int(d[0]["id"])') || return
    capture "$T/task.json" "$S" soar cases task add --phase-id "$PHASE" --name "$N" --yes --json || return
    TASK=$(json_value "$T/task.json" 'int(d[0]["id"])') || return
    check_json "any(int(t['id']) == $TASK and t['status'] == 0 for p in d for t in p.get('tasks', []))" soar cases workbook "$CASE"
    capture "$T/case-users.json" "$S" soar users list --json || return
    USERNAME=$(json_value "$T/case-users.json" 'next(x["username"] for x in d if x.get("is_active", True) and x.get("type") != "automation")') || return
    OWNER_JSON=$("$PY" -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$USERNAME") || return
    expect_ok "$S" soar cases task update "$TASK" --owner "$USERNAME" --status complete --note "$N complete" --yes
    check_json "any(int(t['id']) == $TASK and t['status'] == 2 and t.get('owner') == $OWNER_JSON for p in d for t in p.get('tasks', []))" soar cases workbook "$CASE"
    expect_ok "$S" soar cases task update "$TASK" --status in_progress --note "$N reopen" --yes
    check_json "any(int(t['id']) == $TASK and t['status'] == 1 for p in d for t in p.get('tasks', []))" soar cases workbook "$CASE"
    check_json "any('$N reopen' in x.get('content', '') for x in d)" soar notes list --container "$CASE" --task "$TASK"
    expect_ok "$S" soar cases workbook "$CASE" --json
}
if soar_selected 60-cases; then
    step '60-cases'
    cases_group
fi
