# shellcheck shell=bash
ensure_cim() {
    [ "${cim_installed:-0}" = 1 ] && return 0
    # CIM is the prefix exception: the shipped app/model names are fixed.
    if [ -z "${CIM_TGZ:-}" ] || [ ! -r "$CIM_TGZ" ]; then
        skip 'CIM install, update, acceleration enable/rebuild, uninstall: CIM_TGZ unset or unreadable'
        return 1
    fi
    capture "$T/cim-existing.json" "$S" apps list --json || return 1
    if ! "$PY" -c 'import json,sys; assert all(r["name"] != "Splunk_SA_CIM" for r in json.load(open(sys.argv[1])))' "$T/cim-existing.json"; then
        skip 'CIM steps: Splunk_SA_CIM already installed'
        return 1
    fi
    # Validate the root so cleanup cannot uninstall an unrelated package.
    if ! "$PY" - "$CIM_TGZ" <<'PYCIM'
import sys, tarfile
with tarfile.open(sys.argv[1]) as tgz:
    roots = {n.lstrip('./').split('/')[0] for n in tgz.getnames() if n.lstrip('./')}
assert roots == {'Splunk_SA_CIM'}, roots
PYCIM
    then bad 'CIM_TGZ must contain only Splunk_SA_CIM'; return 1; fi
    defer "$S" apps uninstall Splunk_SA_CIM --yes
    if run "$S" apps install --path "$CIM_TGZ" --yes; then
        cim_installed=1
    else bad 'CIM install'; return 1; fi
}
if selected datamodels; then
    step "datamodels"
    if capture "$T/models.json" "$S" datamodels list --json; then
        model=$("$PY" -c 'import json,sys; d=json.load(open(sys.argv[1])); print(d[0]["name"] if d else "")' "$T/models.json")
        if [ -n "$model" ]; then
            expect_ok "$S" datamodels get "$model" --json
            expect_ok "$S" datamodels acceleration "$model" --json
        else skip 'datamodels get: no built-in models'; fi
    fi
    expect_ok "$S" datamodels acceleration --json
    if ensure_cim; then
        if capture "$T/cim.json" "$S" datamodels list --app Splunk_SA_CIM --json; then
            model=$("$PY" -c 'import json,sys; d=json.load(open(sys.argv[1])); print(d[0]["name"] if d else "")' "$T/cim.json")
            if [ -n "$model" ]; then
                expect_ok "$S" datamodels get "$model" --app Splunk_SA_CIM --json
                expect_ok "$S" datamodels accelerate "$model" --app Splunk_SA_CIM \
                    --earliest -15m --cron '*/5 * * * *' --yes
                # rebuild needs acceleration enabled, not a populated summary
                # (the first summary search can take a full cron period).
                accel_wait=${LIVE_ACCEL_WAIT:-90}
                deadline=$((SECONDS+accel_wait))
                enabled=0
                poll_status=0
                invalid=0
                last_status=''
                while [ "$SECONDS" -lt "$deadline" ]; do
                    if "$S" --timeout 30 datamodels acceleration "$model" \
                        --app Splunk_SA_CIM --json > "$T/acceleration.json" 2> "$T/acceleration.err"; then
                        last_status=$(cat "$T/acceleration.json")
                        # 0 enabled, 2 valid but not enabled yet, 1 invalid row.
                        "$PY" - "$T/acceleration.json" 2>/dev/null <<'PYSTATS'
import json, sys
try:
    rows = json.load(open(sys.argv[1]))
    r, = rows
    assert isinstance(r.get('enabled'), bool)
except Exception:
    sys.exit(1)
sys.exit(0 if r['enabled'] else 2)
PYSTATS
                        case $? in
                            0) enabled=1; break;;
                            2) ;;
                            *) bad "datamodels acceleration returned an invalid row: $last_status"; invalid=1; break;;
                        esac
                    else
                        poll_status=$?
                        last_error=$(tail -n 1 "$T/acceleration.err")
                    fi
                    [ "$SECONDS" -lt "$deadline" ] && sleep "${LIVE_ACCEL_INTERVAL:-5}"
                done
                if [ "$poll_status" -ne 0 ]; then
                    bad "datamodels acceleration poll exited $poll_status: $last_error"
                fi
                if [ "$enabled" = 1 ]; then
                    expect_ok "$S" datamodels rebuild "$model" --app Splunk_SA_CIM --yes
                    check_json 'd[0]["enabled"] is True' datamodels acceleration "$model" --app Splunk_SA_CIM
                    # Disabling clears the window server-side; the re-enable must restore it.
                    check_json 'd["acceleration_enabled"] is True and d["acceleration_earliest_time"]=="-15m"' \
                        datamodels get "$model" --app Splunk_SA_CIM
                elif [ "$invalid" = 0 ]; then
                    skip "datamodels rebuild: acceleration not reported enabled within $accel_wait seconds; last status: ${last_status:-${last_error:-no attempts}}"
                fi
            else bad 'CIM package contains no models'; fi
        fi
    fi
fi
if selected kvstore; then
    step "kvstore"
    expect_ok "$S" kvstore collections --app search --json
    if capture "$T/kvhealth.json" "$S" server kvstore --json; then
        if "$PY" -c 'import json,sys; d=json.load(open(sys.argv[1])); assert d[0]["status"] == "ready"' "$T/kvhealth.json"; then
            if absent kvstore query "$N" --app search && {
                defer "$S" kvstore delete "$N" --app search --yes
                run "$S" kvstore create "$N" --app search --yes
            }; then
                expect_ok "$S" kvstore insert "$N" --data '{"_key":"sc_live_row","value":1}' --yes
                check_json 'len(d)==1 and d[0]["value"]==1' kvstore query "$N"
                expect_ok "$S" kvstore update "$N" sc_live_row --data '{"value":2}' --yes
                check_json 'len(d)==1 and d[0]["value"]==2' kvstore query "$N"
                expect_ok "$S" kvstore export "$N" --out "$T/kv.jsonl"
                expect_ok "$S" kvstore remove "$N" sc_live_row --yes
                check_json 'd==[]' kvstore query "$N"
                expect_ok "$S" kvstore import "$N" --file "$T/kv.jsonl" --yes
                check_json 'len(d)==1 and d[0]["value"]==2' kvstore query "$N"
            else bad 'create KV collection'; fi
        else skip 'KV document round trip: KV store is not ready'; fi
    fi
fi
if selected apps; then
    step "apps"
    expect_ok "$S" apps list --json
    check_json 'd[0]["name"]=="search"' apps get search
    expect_ok "$S" apps reload --yes
    if ensure_cim; then
        expect_ok "$S" apps update Splunk_SA_CIM --hidden --yes
        check_json 'str(d[0]["visible"]).lower() in ("0","false")' apps get Splunk_SA_CIM
    fi
fi
if selected users; then
    step "users"
    # Random passwords belong only to the disposable account.
    password=$("$PY" -c 'import secrets; print("Sc_live_9!"+secrets.token_hex(16))')
    if absent users get "$N" && {
        defer "$S" users delete "$N" --yes
        run "$S" users create --name "$N" --password "$password" --roles user --yes
    }; then
        expect_ok "$S" users get "$N" --json
        expect_ok "$S" users list --filter "$N" --json
        expect_ok "$S" users update "$N" --password "${password}X" --realname sc_live_updated --yes
        check_json 'd[0]["realname"]=="sc_live_updated"' users get "$N"
    else bad 'create user'; fi
    step "users roles"
    if absent users roles get "$N" && {
        defer "$S" users roles delete "$N" --yes
        run "$S" users roles create "$N" --imported-roles user --yes
    }; then
        expect_ok "$S" users roles get "$N" --json
        expect_ok "$S" users roles list --filter "$N" --json
        expect_ok "$S" users roles update "$N" --default-app search --yes
        check_json 'd[0]["defaultApp"]=="search"' users roles get "$N"
    else bad 'create role'; fi
fi
if selected server; then
    step "server"
    for verb in messages license kvstore health cluster shcluster deployment search-peers; do
        expect_ok "$S" server "$verb" --json
    done
    expect_ok "$S" server license --usage --json
    for verb in show ldap saml role-mapping; do expect_ok "$S" server auth "$verb" --json; done
    expect_ok "$S" server serverclasses list --json
    expect_ok "$S" server tokens list --json
    for verb in pools rules status; do expect_ok "$S" server workloads "$verb" --json; done
fi
if selected audit; then
    step "audit"
    expect_ok "$S" audit changes --since -1h --json
    expect_ok "$S" audit rbac --json
    expect_ok "$S" audit rbac --roles-only --json
fi
if selected es; then
    step "es"
    error_kind not_found es notables list
    error_kind not_found es correlations list
    error_kind not_found es threat-intel list
fi
if selected state; then
    step "state"
    if ensure_rule && ensure_lookup && ensure_dashboard; then
        expect_ok "$S" state pull --dir "$T/state" --app search --types rules,lookups,dashboards
        # Change only our rule; keep the original snapshot for the final diff.
        expect_ok "$PY" - "$T/state/rules.yml" "$N" "$T/push" <<'PY'
import sys, yaml
from pathlib import Path
p, name, push = sys.argv[1:]
docs = yaml.safe_load(open(p))
ours = [d for d in docs if d['name'] == name]
assert len(ours) == 1
ours[0]['description'] = 'sc_live_state_changed'
with open(p, 'w') as f:
    yaml.safe_dump(docs, f)
Path(push).mkdir()
Path(push, "rules.yml").write_text(yaml.safe_dump(ours))
PY
        check_json 'any(r["change"]=="modified" and r["name"].startswith("sc_live_") for r in d)' \
            state diff --dir "$T/state" --app search --types rules,lookups,dashboards
        expect_ok "$S" state push --dir "$T/push" --app search --types rules --report "$T/dry.json"
        # Refuse to apply if the plan touches anything except our own rule.
        if "$PY" - "$T/dry.json" "$N" <<'PYPLAN'
import json, sys
report = json.load(open(sys.argv[1]))
assert report['applied'] is False
assert len(report['changes']) == 1
assert report['changes'][0]['name'] == sys.argv[2]
PYPLAN
        then
            expect_ok "$S" state push --dir "$T/push" --app search --types rules --yes --report "$T/applied.json"
            assert_json "$T/applied.json" 'd["applied"] is True and len(d["changes"])==1'
            check_json 'd[0]["description"]=="sc_live_state_changed"' rules get "$N"
            check_json 'all(r["change"]=="unchanged" for r in d)' \
                state diff --dir "$T/state" --app search --types rules,lookups,dashboards
        else bad 'state plan must change only the fixture rule'; fi
    fi
fi
if selected commands; then
    step "commands"
    if capture "$T/commands.json" "$S" commands --json; then
        expect_ok "$PY" -c 'import json,sys; json.load(sys.stdin)' < "$T/commands.json"
    fi
fi
if selected docs; then
    step "docs"
    skip 'docs generate --check: source documentation is not required on the live client'
fi
