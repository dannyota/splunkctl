# shellcheck shell=bash
ensure_lookup() {
    if [ "${lookup_ready:-0}" = 0 ]; then
        if run "$S" lookups upload "$N.csv" --file "$T/lk.csv" --app search --yes; then
            lookup_ready=1
            defer "$S" lookups delete "$N.csv" --app search --yes
        else bad 'upload fixture lookup'; return 1; fi
    fi
}
ensure_dashboard() {
    if [ "${dashboard_ready:-0}" = 0 ]; then
        if run "$S" dashboards create --name "$N" --file "$T/dash.xml" --app search --yes; then
            dashboard_ready=1
            defer "$S" dashboards delete "$N" --app search --yes
        else bad 'create fixture dashboard'; return 1; fi
    fi
}
if selected lookups; then
    step "lookups"
    if ensure_lookup; then
        expect_ok "$S" lookups list --app search --filter "$N" --json
        check_json 'd[0]["name"].startswith("sc_live_")' lookups get "$N.csv" --app search
        expect_ok "$S" lookups download "$N.csv" --app search --out "$T/dl.csv"
        expect_ok "$PY" -c 'import csv,sys; assert list(csv.DictReader(open(sys.argv[1])))[1]["label"]=="test-b"' "$T/dl.csv"
        expect_ok "$S" lookups update "$N.csv" --file "$T/lk2.csv" --app search --yes
        expect_ok "$S" lookups download "$N.csv" --app search --out "$T/dl2.csv"
        expect_ok "$PY" -c 'import csv,sys; p=open(sys.argv[1]); assert p.read(1)=="i"; p.seek(0); assert list(csv.DictReader(p))==[{"ip":"10.0.0.9","label":"test-z"}]' "$T/dl2.csv"
        if run "$S" lookups define "$N" --file "$N.csv" --app search --yes; then
            defer stanza_delete transforms "$N"
            check_json 'len(d)==1 and d[0]["filename"].startswith("sc_live_")' lookups definitions --app search --filter "$N"
            # Own props stanza, deleted through parsers at EXIT.
            if run "$S" parsers create --sourcetype "${N}_auto" --yes; then
                defer "$S" parsers delete "${N}_auto" --yes
                expect_ok "$S" lookups auto "$N" --sourcetype "${N}_auto" --input ip --output label --app search --yes
                check_json 'any(k.startswith("LOOKUP-") for k in d[0])' conf get props "${N}_auto" --app search
            else bad 'create auto lookup props fixture'; fi
        else bad 'define lookup'; fi
    fi
fi
if selected dashboards; then
    step "dashboards"
    if ensure_dashboard; then
        check_json 'len(d)==1' dashboards list --app search --filter "$N"
        expect_ok "$S" dashboards get "$N" --app search --json
        expect_ok "$S" dashboards export "$N" --app search --out "$T/export.xml"
        expect_ok "$PY" -c 'import sys; assert "sc_live_v1" in open(sys.argv[1]).read()' "$T/export.xml"
        expect_ok "$S" dashboards update "$N" --file "$T/dash2.xml" --app search --yes
        check_json '"sc_live_v2" in str(d)' dashboards get "$N" --app search
        expect_ok "$S" dashboards share "$N" --sharing app --app search --yes
        check_json 'd[0]["sharing"]=="app"' dashboards list --app search --filter "$N"
        expect_ok "$S" dashboards share "$N" --sharing global --app search --yes
        check_json 'd[0]["sharing"]=="global"' dashboards list --app search --filter "$N"
    fi
fi
hec_disabled_value() {
    "$PY" - "$1" <<'PYHEC'
import json, sys
value = str(json.load(open(sys.argv[1]))[0]['disabled']).lower()
assert value in ('0', '1', 'false', 'true'), value
print(int(value in ('1', 'true')))
PYHEC
}
restore_hec_settings() {
    local original=$1 current action
    capture "$T/hec-restore.json" "$S" hec settings --json || return 1
    current=$(hec_disabled_value "$T/hec-restore.json") || return 1
    if [ "$current" != "$original" ]; then
        case "$original" in 1) action=--disable;; *) action=--enable;; esac
        run "$S" hec settings "$action" --yes || return 1
    fi
    capture "$T/hec-restored.json" "$S" hec settings --json || return 1
    current=$(hec_disabled_value "$T/hec-restored.json") || return 1
    [ "$current" = "$original" ]
}
verify_hec_event() {
    local deadline=$((SECONDS+30)) remaining found=0
    while [ "$SECONDS" -lt "$deadline" ]; do
        remaining=$((deadline-SECONDS))
        [ "$remaining" -gt 0 ] || break
        if capture "$T/hec-event.json" "$S" --timeout "$remaining" search oneshot \
            "index=$N \"$N\" | stats count" --earliest -15m --json; then
            if "$PY" -c 'import json,sys; d=json.load(open(sys.argv[1])); sys.exit(0 if len(d)==1 and int(d[0]["count"])==1 else 1)' "$T/hec-event.json"; then
                found=1
                break
            fi
        else return 1; fi
        [ "$SECONDS" -lt "$deadline" ] && sleep 1
    done
    [ "$found" = 1 ] || { bad 'HEC event not indexed within 30 seconds'; return 1; }
}
if selected hec; then
    step "hec"
    if capture "$T/hec-settings.json" "$S" hec settings --json && ensure_index; then
        hec_disabled=$(hec_disabled_value "$T/hec-settings.json")
        case "$hec_disabled" in
            0|1)
                # Register before changing settings, including a failed enable request.
                defer restore_hec_settings "$hec_disabled"
                case "$hec_disabled" in 1) expect_ok "$S" hec settings --enable --yes;; esac
                if run "$S" hec create --name "$N" --index "$N" --indexes "$N" --yes; then
                    defer "$S" hec delete "$N" --yes
                    expect_ok "$S" hec list --filter "$N" --json
                    expect_ok "$S" hec get "$N" --json
                    expect_ok "$S" hec get "http://$N" --json
                    expect_ok "$S" hec disable "$N" --yes
                    check_json 'str(d[0]["disabled"]).lower() in ("1","true")' hec get "$N"
                    expect_ok "$S" hec enable "$N" --yes
                    check_json 'str(d[0]["disabled"]).lower() in ("0","false")' hec get "$N"
                    if [ -n "${LIVE_HEC_URL:-}" ]; then
                        run "$S" hec send "$N" "$N HEC smoke event" --index "$N" --url "$LIVE_HEC_URL" --yes
                    else
                        run "$S" hec send "$N" "$N HEC smoke event" --index "$N" --yes
                    fi
                    if [ "$?" = 0 ]; then verify_hec_event
                    else bad 'HEC send failed'; fi
                else bad 'create HEC token'; fi;;
            *) bad 'invalid HEC disabled setting';;
        esac
    fi
fi
if selected parsers; then
    step "parsers"
    expect_ok "$S" parsers sourcetypes --json
    expect_ok "$S" parsers extractions --json
    if run "$S" parsers create --sourcetype "$N" --category sc_live_initial --yes; then
        defer "$S" parsers delete "$N" --yes
        expect_ok "$S" parsers get "$N" --json
        expect_ok "$S" parsers set "$N" SHOULD_LINEMERGE=false --yes
        check_json 'str(d[0]["SHOULD_LINEMERGE"]).lower() in ("0","false")' parsers get "$N" --explicit
        expect_ok "$S" parsers unset "$N" SHOULD_LINEMERGE --yes
        expect_ok "$S" parsers update "$N" --category sc_live_updated --yes
        check_json 'd[0]["category"]=="sc_live_updated"' parsers get "$N" --explicit
        expect_ok "$S" parsers export --path "$T/parsers.yml" --conf props --filter "$N"
        expect_ok "$S" parsers import --path "$T/parsers.yml" --json
        expect_ok "$S" parsers import --path "$T/parsers.yml" --yes
        expect_ok "$S" parsers reload --yes
    else bad 'create sourcetype'; fi
fi
if selected conf; then
    step "conf"
    expect_ok "$S" conf files --app search --json
    # props has a dedicated delete verb, unlike generic conf stanzas.
    if run "$S" conf set props "${N}_conf" category=sc_live_conf --yes; then
        defer "$S" parsers delete "${N}_conf" --yes
        expect_ok "$S" conf list props --app search --json
        check_json 'd[0]["category"]=="sc_live_conf"' conf get props "${N}_conf" --app search
        expect_ok "$S" conf unset props "${N}_conf" category --yes
        check_json 'd[0]["category"]==""' conf get props "${N}_conf" --app search
        expect_ok "$S" conf reload props --yes
    else bad 'create conf stanza'; fi
fi
if selected macros; then
    step "macros"
    if run "$S" macros set "$N" --definition 'makeresults' --yes; then
        defer stanza_delete macros "$N"
        expect_ok "$S" macros list --app search --json
        check_json 'd[0]["definition"]=="makeresults"' macros get "$N" --app search
    else bad 'set macro'; fi
fi
if selected eventtypes; then
    step "eventtypes"
    if run "$S" conf set eventtypes "$N" "search=index=$N" --yes; then
        defer stanza_delete eventtypes "$N"
        expect_ok "$S" eventtypes list --app search --json
        check_json 'd[0]["name"].startswith("sc_live_")' eventtypes get "$N" --app search
    else bad 'create eventtype fixture'; fi
fi
if selected tags; then
    step "tags"
    if run "$S" conf set tags "${N}=sc_live_value" sc_live_tag=enabled --yes; then
        defer stanza_delete tags "${N}=sc_live_value"
        expect_ok "$S" tags list --app search --json
        check_json 'd[0]["sc_live_tag"]=="enabled"' tags get "${N}=sc_live_value" --app search
    else bad 'create tag fixture'; fi
fi
