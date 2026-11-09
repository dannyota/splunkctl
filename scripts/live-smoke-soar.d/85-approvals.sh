# shellcheck shell=bash
# Opt-in owned prompt playbook. A phantom.prompt2() prompt is an action run:
# it consumes one licensed action (Community edition allows 100 per day).
# The prompt goes to the runner's own user; the playbook runs nothing else.
approvals_field() {
    "$PY" - "$@" <<'PY' 2>/dev/null
import json, sys
data = json.load(open(sys.argv[1]))
rows = data if isinstance(data, list) else [data]
print(eval(sys.argv[2], {'rows': rows}))
PY
}
soar_approvals() {
    local name="${N}_prompt" user run_id approval='' status='' deadline
    ensure_event || return
    capture "$T/config.json" "$S" config show --json || return
    user=$(json_value "$T/config.json" "d[0].get('soar', {}).get('username') or ''") || return
    [ -n "$user" ] || { bad 'approvals: the SOAR profile has no username'; return; }
    "$PY" - "$T" "$name" "$user" <<'PY' || { bad 'prompt bundle generation'; return; }
import json, pathlib, sys
root, name, user = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3]
pb = root / name
pb.mkdir()
nodes = {}
for key, kind, function in [('0', 'start', 'on_start'), ('1', 'end', 'on_finish')]:
    nodes[key] = {'id': key, 'type': kind, 'x': 0, 'y': int(key) * 200,
                  'data': {'id': key, 'type': kind, 'functionName': function,
                           'advanced': {'join': []}}, 'errors': {}, 'warnings': {}}
(pb / f'{name}.json').write_text(json.dumps({
    'name': name, 'description': name, 'active': False, 'draft_mode': False,
    'labels': ['events'], 'tags': [], 'input_spec': [], 'output_spec': [], 'blockly': False,
    'coa': {'schema': '5.0.8', 'python_version': '3.13', 'playbook_type': 'automation',
            'input_spec': [], 'output_spec': [], 'data': {
        'description': name, 'nodes': nodes, 'edges': [{
            'id': 'port_0_to_port_1', 'sourceNode': '0', 'sourcePort': '0_out',
            'targetNode': '1', 'targetPort': '1_in'}]}},
}))
(pb / f'{name}.py').write_text(f'''import phantom.rules as phantom

@phantom.playbook_block()
def on_start(container):
    # One prompt; no app actions or child playbooks.
    phantom.prompt2(container=container, user={user!r}, message={name!r},
                    respond_in_mins=10, name="sc_live_prompt", callback=prompt_callback,
                    response_types=[{{"prompt": "Proceed?",
                                      "options": {{"type": "list", "choices": ["Yes", "No"]}}}}])
    return

@phantom.playbook_block()
def prompt_callback(action=None, success=None, container=None, results=None, handle=None, **kwargs):
    return

@phantom.playbook_block()
def on_finish(container, summary):
    return
''')
PY
    capture "$T/prompt-existing.json" "$S" soar playbooks list --repo local --name "$name/$name" --json || return
    if [ "$(json_value "$T/prompt-existing.json" "sum(r.get('name') == '$name/$name' for r in d)")" != 0 ]; then
        bad 'prompt playbook name already exists'
        return
    fi
    # Disabling with --cancel-runs also closes a prompt left pending by a failure.
    defer cleanup_owned_playbook "$name/$name"
    capture "$T/prompt-import.json" "$S" soar playbooks import "$T/$name" --scm local --no-force --yes --json || return
    capture "$T/prompt-run.json" "$S" soar playbooks run "$name/$name" --container "$C" --yes --json || return
    run_id=$(json_value "$T/prompt-run.json" "int(d[0]['id'])") || return
    deadline=$((SECONDS + ${LIVE_SOAR_APPROVAL_WAIT:-90}))
    while [ -z "$approval" ] && [ "$SECONDS" -lt "$deadline" ]; do
        sleep 3
        "$S" soar approvals list --container "$C" --pending --json > "$T/approvals.json" 2> "$T/approvals.err" || continue
        approval=$(approvals_field "$T/approvals.json" \
            "next((r['id'] for r in rows if r.get('playbook_run') == $run_id), '')")
    done
    if [ -z "$approval" ]; then
        cat "$T/approvals.err" 2>/dev/null
        bad "no pending approval for playbook run $run_id"
        return
    fi
    capture "$T/approval.json" "$S" soar approvals get "$approval" --json || return
    [ "$(approvals_field "$T/approval.json" "rows[0].get('status')")" = pending ] || bad 'approval is not pending'
    expect_ok "$S" soar approvals respond "$approval" approve --response Yes --message "$N" --yes --json
    deadline=$((SECONDS + 60))
    while [ "$SECONDS" -lt "$deadline" ]; do
        "$S" soar playbooks runs get "$run_id" --json > "$T/prompt-status.json" 2>/dev/null || true
        status=$(approvals_field "$T/prompt-status.json" "rows[0].get('status', '')")
        case "$status" in success|failed|cancelled) break;; esac
        sleep 3
    done
    [ "$status" = success ] || bad "prompt playbook run ended as '${status:-unknown}'"
    capture "$T/approval.json" "$S" soar approvals get "$approval" --json || return
    [ "$(approvals_field "$T/approval.json" "rows[0].get('status')")" = approved ] || bad 'approval not approved'
    cleanup_owned_playbook "$name/$name" || bad 'prompt playbook cleanup'
}
if soar_selected 85-approvals; then
    step '85-approvals'
    if [ "${LIVE_SOAR_APPROVALS:-0}" = 1 ]; then
        soar_approvals
    else
        skip 'approvals get/respond: set LIVE_SOAR_APPROVALS=1 (the prompt consumes one licensed action)'
    fi
fi
