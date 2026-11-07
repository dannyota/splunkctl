#!/usr/bin/env bash
# Live test of the REST adapters that replaced the SDK fork.
# Usage: SPLUNKCTL=/path/to/splunkctl bash live-adapter-test.sh
# Needs: HOME pointing at a throwaway profile that reaches the test Splunk.
set -uo pipefail
S="${SPLUNKCTL:-splunkctl}"
T="$(mktemp -d)"
fail=0
step() { printf '\n### %s\n' "$*"; }
run() { printf '$ %s\n' "$*"; "$@"; rc=$?; printf '[exit=%s]\n' "$rc"; return $rc; }
expect_ok() { run "$@" || { echo "FAIL (expected exit 0)"; fail=$((fail+1)); }; }
expect_fail() { run "$@" && { echo "FAIL (expected non-zero exit)"; fail=$((fail+1)); }; }

cat > "$T/dash.xml" <<'XML'
<dashboard version="1.1"><label>splunkctl live test</label><row><panel><single><search><query>| makeresults | eval n=1</query></search></single></panel></row></dashboard>
XML
cat > "$T/dash2.xml" <<'XML'
<dashboard version="1.1"><label>splunkctl live test v2</label><row><panel><single><search><query>| makeresults | eval n=2</query></search></single></panel></row></dashboard>
XML
printf 'ip,label\n10.0.0.1,test-a\n10.0.0.2,test-b\n' > "$T/lk.csv"

step "doctor"
expect_ok "$S" doctor --json
step "dashboards: create, list, get, export, update, share, delete"
expect_ok "$S" dashboards create --name sc_live_dash --file "$T/dash.xml" --app search --yes
expect_ok "$S" dashboards list --app search --filter sc_live --json
expect_ok "$S" dashboards get sc_live_dash --app search --json
expect_ok "$S" dashboards export sc_live_dash --app search --out "$T/export.xml"
grep -q "splunkctl live test" "$T/export.xml" && echo "export OK" || { echo "FAIL export content"; fail=$((fail+1)); }
expect_ok "$S" dashboards update sc_live_dash --file "$T/dash2.xml" --app search --yes
"$S" dashboards get sc_live_dash --app search --definition 2>/dev/null | grep -q "v2" && echo "update OK" || { echo "FAIL update content"; fail=$((fail+1)); }
expect_ok "$S" dashboards share sc_live_dash --sharing app --app search --yes
"$S" dashboards list --app search --filter sc_live --json 2>/dev/null | grep -q '"sharing": "app"' && echo "share OK" || { echo "FAIL sharing"; fail=$((fail+1)); }
expect_ok "$S" dashboards share sc_live_dash --sharing global --app search --yes
expect_ok "$S" dashboards delete sc_live_dash --app search --yes
expect_fail "$S" dashboards get sc_live_dash --app search --json
step "lookups: upload, list, get, download, update, delete"
expect_ok "$S" lookups upload sc_live_lk.csv --file "$T/lk.csv" --app search --yes
expect_ok "$S" lookups list --app search --filter sc_live --json
expect_ok "$S" lookups get sc_live_lk.csv --app search --json
expect_ok "$S" lookups download sc_live_lk.csv --app search --out "$T/dl.csv"
grep -q "test-b" "$T/dl.csv" && echo "download OK" || { echo "FAIL download content"; fail=$((fail+1)); }
printf 'ip,label\n10.0.0.9,test-z\n' > "$T/lk2.csv"
expect_ok "$S" lookups update sc_live_lk.csv --file "$T/lk2.csv" --app search --yes
expect_ok "$S" lookups delete sc_live_lk.csv --app search --yes
expect_fail "$S" lookups get sc_live_lk.csv --app search --json
step "hec: settings, create, list, get (bare and http:// name), disable, enable, delete"
expect_ok "$S" hec settings --enable --yes
expect_ok "$S" hec create --name sc_live_tok --index main --yes
expect_ok "$S" hec list --filter sc_live --json
expect_ok "$S" hec get sc_live_tok --json
expect_ok "$S" hec get http://sc_live_tok --json
expect_ok "$S" hec disable sc_live_tok --yes
"$S" hec get sc_live_tok --json 2>/dev/null | grep -Eq '"disabled": (true|"1"|1)' && echo "disable OK" || { echo "FAIL disabled flag"; fail=$((fail+1)); }
expect_ok "$S" hec enable sc_live_tok --yes
"$S" hec get sc_live_tok --json 2>/dev/null | grep -Eq '"disabled": (false|"0"|0)' && echo "enable OK" || { echo "FAIL enabled flag"; fail=$((fail+1)); }
expect_ok "$S" hec delete sc_live_tok --yes
expect_fail "$S" hec get sc_live_tok --json
step "state pull with dashboards and lookups"
expect_ok "$S" state pull --dir "$T/state" --app search --types lookups,dashboards
find "$T/state" -type f | head -5
printf '\nRESULT: %s failure(s)\n' "$fail"
exit $fail
