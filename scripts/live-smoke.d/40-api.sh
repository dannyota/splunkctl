# shellcheck shell=bash
# Keep raw REST bodies and error streams out of public CI logs.
api_capture() {
    local file=$1
    shift
    API_CALL=$("$PY" - "$@" <<'PYCALL'
import sys
args = sys.argv[1:]
for group in ("api", "search"):
    if group in args:
        i = args.index(group)
        # Show only the known command words and option names, never values.
        words = args[i:i+2]
        flags = [a.split("=", 1)[0] for a in args if a.startswith("--")]
        print(" ".join(words + flags))
        break
else:
    print("unknown")
PYCALL
)
    "$@" > "$file" 2> "$T/api.err"
    local status=$?
    if [ "$status" -ne 0 ]; then
        local diagnostic
        diagnostic=$("$PY" - "$T/api.err" <<'PYERROR'
import json, re, sys

def clean(value):
    text = str(value)
    # Drop the suffix so quoted, spaced and multiline credentials stay private.
    text = re.split(r"Splunk\s|Bearer\s|Basic\s|(?:[\w-]*token|password|passwd|authorization)[\s\"']*[:=]",
                    text, maxsplit=1, flags=re.I)[0]
    return " ".join(text.split())[:200]

kind, message = "unknown", "No JSON error envelope"
with open(sys.argv[1]) as stream:
    for line in stream:
        try:
            error = json.loads(line).get("error")
        except (ValueError, AttributeError):
            continue
        if isinstance(error, dict):
            kind = clean(error.get("kind", "unknown"))
            message = clean(error.get("message", ""))
            break
print(f"kind={kind} message={message}")
PYERROR
)
        bad "API smoke expected exit 0, got $status: ${file##*/}: $API_CALL: $diagnostic"
        return 1
    fi
}
api_assert() {
    "$PY" - "$1" "$2" <<'PYAPI' 2>/dev/null || bad "API smoke JSON assertion: ${API_CALL:-unknown}: ${1##*/}"
import json, sys
with open(sys.argv[1]) as stream:
    d = json.load(stream)
assert eval(sys.argv[2]), 'unexpected API result'
PYAPI
}
api_cleanup() {
    case "$1" in */sc_live_*) ;; *) return 1;; esac
    "$S" --json api delete "$1" --yes > "$T/api-cleanup.json" 2> "$T/api-cleanup.err"
    local status=$?
    [ "$status" -eq 0 ] || is_not_found "$status" "$T/api-cleanup.err"
}
if selected api; then
    step "api"
    api_capture "$T/api-get.json" "$S" --json api get server/info
    api_assert "$T/api-get.json" 'bool(d)'
    api_capture "$T/api-describe.json" "$S" --json api get saved/searches --describe
    api_assert "$T/api-describe.json" 'bool(d)'
    api_path="/servicesNS/nobody/search/saved/searches/${N}_api"
    "$S" --json api get "$api_path" > "$T/api-absent.json" 2> "$T/api-absent.err"
    api_status=$?
    if is_not_found "$api_status" "$T/api-absent.err"; then
        api_capture "$T/api-preview.json" "$S" --json api post saved/searches --param "name=${N}_api" --param 'search=| makeresults'
        api_capture "$T/api-preview.json" "$S" --json api delete "$api_path"
        defer api_cleanup "$api_path"
        if api_capture "$T/api-create.json" "$S" --json api post /servicesNS/nobody/search/saved/searches \
            --param "name=${N}_api" --param 'search=| makeresults' --param disabled=1 --param description=sc_live_before --yes; then
            api_capture "$T/api-before.json" "$S" --json api get "$api_path"
            "$S" --json --read-only --yes api post "$api_path" --param description=sc_live_after \
                > "$T/api-blocked.json" 2> "$T/api-blocked.err"
            api_status=$?
            "$PY" - "$api_status" "$T/api-blocked.err" <<'PYAPI' || bad 'read-only API write must be refused'
import json, sys
assert sys.argv[1] == '1'
errors = [json.loads(line)['error'] for line in open(sys.argv[2]) if line.startswith('{')]
assert any(e['kind'] == 'permission' and e['http_status'] is None and e['message'].startswith('read-only:') for e in errors)
PYAPI
            api_capture "$T/api-after.json" "$S" --json api get "$api_path"
            "$PY" - "$T/api-before.json" "$T/api-after.json" <<'PYAPI' || bad 'read-only API changed fixture'
import json, sys
before, after = [json.load(open(path)) for path in sys.argv[1:]]
assert before[0]['entry'][0]['content']['description'] == 'sc_live_before'
assert after[0]['entry'][0]['content']['description'] == 'sc_live_before'
PYAPI
            api_capture "$T/api-delete.json" "$S" --json api delete "$api_path" --yes
            "$S" --json api get "$api_path" > "$T/api-absent.json" 2> "$T/api-absent.err"
            is_not_found "$?" "$T/api-absent.err" || bad 'API fixture remains after delete'
        fi
    else bad 'API fixture must be absent before creation'; fi
    api_capture "$T/api-search.json" "$S" --json --read-only search oneshot '| makeresults | stats count' --earliest -5m
    api_assert "$T/api-search.json" 'len(d) == 1 and str(d[0]["count"]) == "1"'
    "$S" --json --read-only --yes search oneshot '| makeresults | outputlookup sc_live_blocked.csv' \
        > "$T/api-blocked-spl.json" 2> "$T/api-blocked-spl.err"
    api_status=$?
    "$PY" - "$api_status" "$T/api-blocked-spl.err" <<'PYAPI' || bad 'read-only write SPL must be refused'
import json, sys
assert sys.argv[1] == '1'
errors = [json.loads(line)['error'] for line in open(sys.argv[2]) if line.startswith('{')]
assert any(e['kind'] == 'permission' and 'outputlookup' in e['message'] for e in errors)
PYAPI
fi
