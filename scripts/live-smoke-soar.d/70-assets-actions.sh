# shellcheck shell=bash
# Installed apps and credential-free assets. No shipped asset is modified.
# Lost action-run responses are resolved only within the owned event by exact name.
cleanup_owned_action() {
    local container=$1 name=$2 id failed=0
    "$S" soar actions list --container "$container" --limit 100000 --json > "$T/cleanup-actions.json" || return
    "$PY" - "$T/cleanup-actions.json" "$name" > "$T/cleanup-action-ids" <<'PY' || return
import json, sys
for row in json.load(open(sys.argv[1])):
    if row.get('name') == sys.argv[2] and row.get('status') not in ('success', 'failed', 'cancelled'):
        print(int(row['id']))
PY
    while IFS= read -r id; do
        "$S" soar actions cancel "$id" --yes || failed=1
    done < "$T/cleanup-action-ids"
    return "$failed"
}
soar_assets_actions() {
    local app_id asset_id='' configured_asset='' run_id cancel_status
    local -a action_params=()
    capture "$T/apps.json" "$S" soar apps list --installed --json || return
    capture "$T/assets.json" "$S" soar assets list --limit 100000 --json || return
    expect_ok "$S" soar actions list --json
    # Inspect complete schemas, not just catalog summaries. Reject every app
    # with a credential-looking or password field, including optional fields.
    app_id=''
    while IFS= read -r candidate; do
        [ -n "$candidate" ] || continue
        capture "$T/app.json" "$S" soar apps get "$candidate" --json || return
        if "$PY" - "$T/app.json" "$T/asset-config.json" <<'PY'
import json, sys
app = json.load(open(sys.argv[1]))[0]
schema = app.get('configuration')
if not isinstance(schema, dict):
    sys.exit(1)
config = {}
for name, field in schema.items():
    if not isinstance(field, dict):
        sys.exit(1)
    if field.get('data_type') == 'password' or any(
        hint in name.lower() for hint in ('password', 'secret', 'token', 'credential', 'api_key', 'apikey')
    ):
        sys.exit(1)
    if field.get('required') and field.get('default') in (None, ''):
        sys.exit(1)
    if 'default' in field:
        config[name] = field['default']
json.dump(config, open(sys.argv[2], 'w'))
PY
        then
            app_id=$candidate
            break
        fi
    done < <(json_value "$T/apps.json" "'\\n'.join(str(r['id']) for r in d)")
    if [ -n "$app_id" ]; then
        if ! "$PY" - "$T/assets.json" "$N" <<'PY_CHECK'
import json, sys
assert not any(r.get('name') == sys.argv[2] for r in json.load(open(sys.argv[1])))
PY_CHECK
        then
            bad 'asset fixture name already exists'
            return
        fi
        defer soar_cleanup assets "$N"
        if capture "$T/asset-create.json" "$S" soar assets create --name "$N" \
            --app-id "$app_id" --file "$T/asset-config.json" --yes --json; then
            asset_id=$(json_value "$T/asset-create.json" "int(d[0]['id'])") || return
            capture "$T/asset-before.json" "$S" soar assets get "$asset_id" --json || return
            expect_ok "$S" soar assets update "$asset_id" --description "$N updated" --yes --json
            if capture "$T/asset-after.json" "$S" soar assets get "$asset_id" --json; then
                "$PY" - "$T/asset-before.json" "$T/asset-after.json" <<'PY' || bad 'asset update lost configuration'
import json, sys
before, after = (json.load(open(p))[0] for p in sys.argv[1:])
assert before.get('configuration', {}) == after.get('configuration', {})
PY
            fi
        fi
    else
        skip '70-assets-actions: no installed app has a credential-free default configuration'
        configured_asset=$(json_value "$T/assets.json" "str(d[0]['id']) if d else ''")
        if [ -n "$configured_asset" ]; then
            expect_ok "$S" soar assets get "$configured_asset" --json
        fi
    fi
    if [ "${LIVE_SOAR_ACTIONS:-}" = 1 ] && [ -n "${LIVE_SOAR_ACTION_ASSET:-}" ] && \
        [ -n "${LIVE_SOAR_ACTION:-}" ]; then
        ensure_event || return
        expect_ok "$S" soar license --json
        if "$PY" - "${LIVE_SOAR_ACTION_PARAMS:-}" > "$T/action-params" <<'PY'
import json, sys
params = json.loads(sys.argv[1] or '{}')
assert isinstance(params, dict)
for key, value in params.items():
    text = f'{key}={value}'
    assert '\n' not in text
    print(text)
PY
        then
            while IFS= read -r parameter; do action_params+=(--param "$parameter"); done < "$T/action-params"
            defer cleanup_owned_action "$C" "$N"
            # Exactly one run, with no retry, scoped to the owned event.
            if capture "$T/action.json" "$S" soar actions run --action "$LIVE_SOAR_ACTION" \
                --asset "$LIVE_SOAR_ACTION_ASSET" --container "$C" --name "$N" \
                "${action_params[@]}" --yes --json; then
                run_id=$(json_value "$T/action.json" "int(d[0]['id'])") || return
                expect_ok "$S" soar actions status "$run_id" --json
                expect_ok "$S" soar actions results "$run_id" --json
                # A fast action can finish first: SOAR then answers HTTP 400
                # "Action is already finished executing", which also passes.
                printf '$ %s\n' "$S soar actions cancel $run_id --yes --json"
                "$S" soar actions cancel "$run_id" --yes --json > "$T/cancel.json" 2> "$T/cancel.err"
                cancel_status=$?
                cat "$T/cancel.json" "$T/cancel.err"
                if [ "$cancel_status" -ne 0 ] && ! grep -q 'already finished' "$T/cancel.err"; then
                    bad "actions cancel exited $cancel_status"
                fi
            fi
        else
            bad 'LIVE_SOAR_ACTION_PARAMS must be a JSON object'
        fi
        if [ -n "$asset_id" ]; then
            expect_ok "$S" soar assets test "$asset_id" --yes --json
        else
            skip 'assets test: no owned credential-free asset'
        fi
        expect_ok "$S" soar license --json
    else
        skip 'licensed actions: set LIVE_SOAR_ACTIONS=1, LIVE_SOAR_ACTION_ASSET and LIVE_SOAR_ACTION'
    fi
    if [ -n "$asset_id" ]; then
        expect_ok "$S" soar assets delete "$asset_id" --yes --json
        asset_absent "$asset_id" || bad "asset $asset_id still present"
    fi
}
if soar_selected 70-assets-actions; then
    step '70-assets-actions'
    soar_assets_actions
fi
