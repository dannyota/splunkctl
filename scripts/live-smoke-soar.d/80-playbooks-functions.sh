# shellcheck shell=bash
# Only the exact runtime-generated names are eligible for cleanup.
cleanup_owned_playbook() {
    local name=$1 id failed=0
    "$S" soar playbooks list --repo local --label "$N" --json > "$T/cleanup-playbooks.json" || return
    id=$(json_value "$T/cleanup-playbooks.json" \
        "next((str(r['id']) for r in d if r.get('name') == '$name'), '')") || return
    [ -n "$id" ] || return 0
    "$S" soar playbooks disable "$id" --cancel-runs --yes || failed=1
    "$S" soar playbooks delete "$id" --yes || failed=1
    "$S" soar playbooks list --repo local --label "$N" --json > "$T/cleanup-playbooks.json" || return
    "$PY" - "$T/cleanup-playbooks.json" "$name" <<'PY' || failed=1
import json, sys
assert not any(r.get('name') == sys.argv[2] for r in json.load(open(sys.argv[1])))
PY
    return "$failed"
}
cleanup_owned_function() {
    local name=$1 id
    "$S" soar functions list --limit 100000 --json > "$T/cleanup-functions.json" || return
    id=$(json_value "$T/cleanup-functions.json" \
        "next((str(r['id']) for r in d if r.get('name') == '$name'), '')") || return
    [ -n "$id" ] || return 0
    "$S" soar functions delete "$id" --yes || return
    "$S" soar functions list --limit 100000 --json > "$T/cleanup-functions.json" || return
    "$PY" - "$T/cleanup-functions.json" "$name" <<'PY'
import json, sys
assert not any(r.get('name') == sys.argv[2] for r in json.load(open(sys.argv[1])))
PY
}
soar_playbooks_functions() {
    local pb_id function_id run_id status
    ensure_event || return
    expect_ok "$S" soar playbooks repos --json
    # The playbook directory becomes the scoped name N/N. Function import
    # packs the two files at archive root, as functions._dir_to_tgz expects.
    "$PY" - "$T" "$N" <<'PY' || { bad 'bundle generation'; return; }
import json, pathlib, sys
root, name = pathlib.Path(sys.argv[1]), sys.argv[2]
pb = root / name
pb.mkdir()
nodes = {}
for key, kind, function in [('0', 'start', 'on_start'), ('1', 'end', 'on_finish')]:
    nodes[key] = {'id': key, 'type': kind, 'x': 0, 'y': int(key) * 200,
                  'data': {'id': key, 'type': kind, 'functionName': function,
                           'advanced': {'join': []}}, 'errors': {}, 'warnings': {}}
metadata = {
    'name': name, 'description': name, 'active': False, 'draft_mode': False,
    'labels': [name],
    'tags': [], 'input_spec': [], 'output_spec': [], 'blockly': False,
    'coa': {'schema': '5.0.8', 'python_version': '3.13', 'playbook_type': 'automation',
            'input_spec': [], 'output_spec': [], 'data': {
        'description': name, 'nodes': nodes, 'edges': [{
            'id': 'port_0_to_port_1', 'sourceNode': '0', 'sourcePort': '0_out',
            'targetNode': '1', 'targetPort': '1_in'}]}},
}
(pb / f'{name}.json').write_text(json.dumps(metadata))
(pb / f'{name}.py').write_text('''import phantom.rules as phantom

@phantom.playbook_block()
def on_start(container):
    # No actions, prompts, or child playbooks.
    return

@phantom.playbook_block()
def on_finish(container, summary):
    return
''')
function = name + '_function'
cf = root / function
cf.mkdir()
(cf / f'{function}.json').write_text(json.dumps({
    'name': function, 'module': function, 'description': name,
    'python_version': '3', 'draft_mode': False, 'inputs': [], 'outputs': [],
    'outputs_type': 'item', 'tags': []}))
(cf / f'{function}.py').write_text(
    f'def {function}(**kwargs):\n    return {{}}\n')
PY
    # Register both exact names before either import, including lost replies.
    # Reverse cleanup disables/cancels/deletes the playbook before the function.
    capture "$T/preexisting-functions.json" "$S" soar functions list --limit 100000 --json || return
    capture "$T/preexisting-playbooks.json" "$S" soar playbooks list --repo local --label "$N" --json || return
    if ! "$PY" - "$T/preexisting-functions.json" "$T/preexisting-playbooks.json" "$N" <<'PY'
import json, sys
functions, playbooks = (json.load(open(p)) for p in sys.argv[1:3])
name = sys.argv[3]
assert not any(r.get('name') == name + '_function' for r in functions)
assert not any(r.get('name') == name + '/' + name for r in playbooks)
PY
    then
        bad 'automation fixture name already exists'
        return
    fi
    defer cleanup_owned_function "${N}_function"
    defer cleanup_owned_playbook "$N/$N"
    capture "$T/function-import.json" "$S" soar functions import "$T/${N}_function" --yes --json || return
    capture "$T/functions.json" "$S" soar functions list --limit 100000 --json || return
    function_id=$(json_value "$T/functions.json" \
        "next(int(r['id']) for r in d if r.get('name') == '${N}_function')") || { bad 'imported function missing'; return; }
    expect_ok "$S" soar functions get "$function_id" --json
    expect_ok "$S" soar functions export "$function_id" --out "$T/function-export.tgz"
    "$PY" - "$T/function-export.tgz" <<'PY' || bad 'function export is not gzip'
import gzip, sys
assert gzip.decompress(open(sys.argv[1], 'rb').read())
PY
    expect_ok "$S" soar functions update "$function_id" --python "$T/${N}_function/${N}_function.py" \
        --message "$N update" --yes --json
    capture "$T/playbook-import.json" "$S" soar playbooks import "$T/$N" --scm local --yes --json || return
    capture "$T/playbooks.json" "$S" soar playbooks list --repo local --label "$N" --json || return
    pb_id=$(json_value "$T/playbooks.json" \
        "next(int(r['id']) for r in d if r.get('name') == '$N/$N')") || { bad 'imported playbook missing'; return; }
    expect_ok "$S" soar playbooks get "$pb_id" --json
    expect_ok "$S" soar playbooks export "$pb_id" --out "$T/playbook-export.tgz"
    # There is no playbooks update leaf. A forced import updates the owned pair.
    "$PY" - "$T/$N/$N.json" <<'PY' || { bad 'playbook metadata update'; return; }
import json, pathlib, sys
path = pathlib.Path(sys.argv[1])
data = json.loads(path.read_text())
data['description'] += ' updated'
path.write_text(json.dumps(data))
PY
    expect_ok "$S" soar playbooks import "$T/$N" --scm local --force --yes --json
    expect_ok "$S" soar playbooks enable "$pb_id" --yes --json
    expect_ok "$S" soar playbooks disable "$pb_id" --yes --json
    expect_ok "$S" soar playbooks trigger "$pb_id" --on artifact_created --yes --json
    if capture "$T/playbook-run.json" "$S" soar playbooks run "$N/$N" --container "$C" --wait --timeout 30 --yes --json; then
        run_id=$(json_value "$T/playbook-run.json" "int(d[0]['id'])") || { bad 'invalid playbook run id'; return; }
        expect_ok "$S" soar playbooks runs list --container "$C" --json
        capture "$T/run-status.json" "$S" soar playbooks runs get "$run_id" --json || return
        status=$(json_value "$T/run-status.json" "d[0].get('status', '')") || return
        if [ "$status" = success ]; then
            expect_fail "$S" soar playbooks runs cancel "$run_id" --yes --json
        else
            bad "no-op playbook did not succeed: $status"
        fi
    fi
    cleanup_owned_playbook "$N/$N" || bad 'playbook cleanup'
    cleanup_owned_function "${N}_function" || bad 'function cleanup'
}
if soar_selected 80-playbooks-functions; then
    step '80-playbooks-functions'
    soar_playbooks_functions
fi
