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
    if run "$S" apps install --path "$CIM_TGZ" --yes; then
        cim_installed=1
        defer "$S" apps uninstall Splunk_SA_CIM --yes
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
                # Generic conf can scope writes through SPLUNK_APP.
                expect_ok env SPLUNK_APP=Splunk_SA_CIM "$S" conf set datamodels "$model" \
                    acceleration='{"enabled":true,"earliest_time":"-15m","cron_schedule":"*/5 * * * *"}' --yes
                check_json 'd[0]["enabled"] is True' datamodels acceleration "$model"
                expect_ok "$S" datamodels rebuild "$model" --app Splunk_SA_CIM --yes
                expect_ok "$S" datamodels acceleration "$model" --json
            else bad 'CIM package contains no models'; fi
        fi
    fi
fi
if selected kvstore; then
    step "kvstore"
    expect_ok "$S" kvstore collections --app search --json
    if capture "$T/kvhealth.json" "$S" server kvstore --json; then
        if "$PY" -c 'import json,sys; d=json.load(open(sys.argv[1])); assert d[0]["status"] == "ready"' "$T/kvhealth.json"; then
            if run "$S" kvstore create "$N" --app search --yes; then
                defer "$S" kvstore delete "$N" --app search --yes
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
    if run "$S" users create --name "$N" --password "$password" --roles user --yes; then
        defer "$S" users delete "$N" --yes
        expect_ok "$S" users get "$N" --json
        expect_ok "$S" users list --filter "$N" --json
        expect_ok "$S" users update "$N" --password "${password}X" --realname sc_live_updated --yes
        check_json 'd[0]["realname"]=="sc_live_updated"' users get "$N"
    else bad 'create user'; fi
    step "users roles"
    if run "$S" users roles create "$N" --imported-roles user --yes; then
        defer "$S" users roles delete "$N" --yes
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
        expect_ok "$PY" - "$T/state/rules.yml" "$N" <<'PY'
import sys, yaml
p, name = sys.argv[1:]
docs = yaml.safe_load(open(p))
ours = [d for d in docs if d['name'] == name]
assert len(ours) == 1
ours[0]['description'] = 'sc_live_state_changed'
with open(p, 'w') as f:
    yaml.safe_dump(docs, f)
PY
        check_json 'any(r["change"]=="modified" and r["name"].startswith("sc_live_") for r in d)' \
            state diff --dir "$T/state" --app search --types rules,lookups,dashboards
        expect_ok "$S" state push --dir "$T/state" --app search --types rules --report "$T/dry.json"
        # Refuse to apply if the plan touches anything except our own rule.
        if "$PY" - "$T/dry.json" "$N" <<'PYPLAN'
import json, sys
report = json.load(open(sys.argv[1]))
assert report['applied'] is False
assert len(report['changes']) == 1
assert report['changes'][0]['name'] == sys.argv[2]
PYPLAN
        then
            expect_ok "$S" state push --dir "$T/state" --app search --types rules --yes --report "$T/applied.json"
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
