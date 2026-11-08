# shellcheck shell=bash
if selected doctor; then
    step "doctor"
    expect_ok "$S" doctor --json
    "$S" doctor --strict --json > "$T/strict.json"
    strict_status=$?
    cat "$T/strict.json"
    expect_ok "$PY" - "$T/strict.json" "$strict_status" <<'PYDOCTOR'
import json, sys
rows = json.load(open(sys.argv[1]))
assert int(sys.argv[2]) == int(any(r['status'] in ('WARN', 'FAIL') for r in rows))
PYDOCTOR
fi
if selected info; then
    step "info"
    check_json 'isinstance(d, (dict,list))' info
fi
if selected config; then
    step "config"
    expect_ok "$S" config show --json
    expect_ok "$S" config test --json
fi
# Shared fixtures are lazy: LIVE_ONLY=search or inputs works without indexes.
ensure_index() {
    if [ "${index_ready:-0}" = 0 ]; then
        if run "$S" indexes create --name "$N" --yes; then
            index_ready=1
            defer "$S" indexes delete "$N" --yes
        else bad 'create fixture index'; return 1; fi
    fi
}
ensure_rule() {
    if [ "${rule_ready:-0}" = 0 ]; then
        if run "$S" rules create --name "$N" --search '| makeresults | eval sc_live_n=1' --app search --yes; then
            rule_ready=1
            defer "$S" rules delete "$N" --yes
        else bad 'create fixture rule'; return 1; fi
    fi
}
if selected search; then
    step "search"
    check_json 'len(d)==1 and str(d[0]["sc_live_n"])=="1"' search run \
        '| makeresults | eval sc_live_n=1' --earliest -15m
    if capture "$T/job.json" "$S" search run '| makeresults' --earliest -15m --detach --json; then
        sid=$("$PY" -c 'import json,sys; print(json.load(open(sys.argv[1]))[0]["sid"])' "$T/job.json")
        if [ -n "$sid" ]; then
            defer "$S" search cancel "$sid" --yes
            expect_ok "$S" search jobs --json
            expect_ok "$S" search job "$sid" --status-only --json
            # Cancellation is deferred so EXIT also cleans up after later failures.
        else bad 'missing detached SID'; fi
    fi
    check_json 'len(d)==1' search export '| makeresults' --earliest -15m
    check_json 'len(d)==1' search oneshot '| makeresults' --earliest -15m
    if run "$S" indexes create --name "${N}_metrics" --datatype metric --yes; then
        defer "$S" indexes delete "${N}_metrics" --yes
        check_json 'isinstance(d,list)' search metrics --index "${N}_metrics"
    else bad 'create metrics index'; fi
    if ensure_index; then
        expect_ok "$S" search upload --path "$T/event.txt" --index "$N" --yes
    fi
    error_kind confirmation_required search run '| makeresults | outputlookup sc_live_x.csv'
fi
if selected indexes; then
    step "indexes"
    if ensure_index; then
        check_json 'd[0]["name"].startswith("sc_live_")' indexes get "$N"
        check_json 'len(d)>=1' indexes list --filter "$N"
        expect_ok "$S" indexes update "$N" --max-size 100 --yes
        check_json 'str(d[0]["maxTotalDataSizeMB"])=="100"' indexes get "$N"
        expect_ok "$S" indexes reload --yes
        expect_ok "$S" indexes clean "$N" --yes
    fi
fi
if selected inputs; then
    step "inputs"
    # Monitor names are server paths. Never attach to or delete an existing /tmp input.
    monitor="${LIVE_MONITOR_PATH:-/tmp}/$N"
    if ensure_index && run "$S" inputs create --name "$monitor" --kind monitor --index "$N" --disabled --yes; then
        defer "$S" inputs delete "$monitor" --yes
        expect_ok "$S" inputs get "$monitor" --json
        check_json 'len(d)==1' inputs list --filter "$N"
        expect_ok "$S" inputs update "$monitor" --sourcetype "$N" --yes
        expect_ok "$S" inputs disable "$monitor" --yes
        check_json 'str(d[0]["disabled"]).lower() in ("1","true")' inputs get "$monitor"
        expect_ok "$S" inputs enable "$monitor" --yes
        check_json 'str(d[0]["disabled"]).lower() in ("0","false")' inputs get "$monitor"
        expect_ok "$S" inputs disable "$monitor" --yes
    else bad 'create monitor input (server path must be monitorable)'; fi
fi
if selected rules; then
    step "rules"
    if ensure_rule; then
        expect_ok "$S" rules get "$N" --json
        check_json 'len(d)==1' rules list --filter "$N"
        expect_ok "$S" rules update "$N" --description sc_live_updated --yes
        expect_ok "$S" rules enable "$N" --yes
        check_json 'str(d[0]["disabled"]).lower() in ("0","false")' rules get "$N"
        expect_ok "$S" rules disable "$N" --yes
        check_json 'str(d[0]["disabled"]).lower() in ("1","true")' rules get "$N"
        expect_ok "$S" rules share "$N" --sharing app --yes
        check_json 'd[0]["sharing"]=="app"' rules get "$N"
        expect_ok "$S" rules history "$N" --json
        expect_ok "$S" rules test "$N" --earliest -15m --json
        expect_ok "$S" rules schedule --filter "$N" --json
        expect_ok "$S" rules export --name "$N" --path "$T/rules.yml"
        expect_ok "$PY" - "$T/rules.yml" <<'PYRULE'
import sys, yaml
p = sys.argv[1]
docs = yaml.safe_load(open(p))
assert len(docs) == 1
docs[0]['description'] = 'sc_live_import_preview'
with open(p, 'w') as f:
    yaml.safe_dump(docs, f)
PYRULE
        check_json 'd[0]["action"]=="update" and any(c["field"]=="description" for c in d[0]["changes"])' \
            rules import --path "$T/rules.yml" --update
        check_json 'd[0]["description"]=="sc_live_updated"' rules get "$N"
    fi
fi
if selected alerts; then
    step "alerts"
    expect_ok "$S" alerts list --json
    expect_ok "$S" alerts actions --json
    if ensure_rule; then
        expect_ok "$S" alerts suppress "$N" --duration 60 --yes
        expect_ok "$S" alerts unsuppress "$N" --yes
    fi
    skip 'alerts get: no fired alert is generated by the unscheduled fixture rule'
fi
