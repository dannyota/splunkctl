# shellcheck shell=bash
# api_capture/api_assert keep bodies and diagnostic streams out of CI logs.
restore_logger() {
    api_capture "$T/logger-restore.json" "$S" --json server log-level set "$1" "$2" --yes || return 1
    api_capture "$T/logger-restored.json" "$S" --json server log-level get "$1" || return 1
    "$PY" - "$T/logger-restored.json" "$2" <<'PYLOGGER' 2>/dev/null
import json, sys
rows = json.load(open(sys.argv[1]))
assert len(rows) == 1 and rows[0]['level'] == sys.argv[2]
PYLOGGER
}
if selected acl; then
    step "acl"
    # Resolve the authenticated owner even when the profile uses token auth.
    if api_capture "$T/acl-context.json" "$S" --json api get authentication/current-context; then
        acl_owner=$("$PY" - "$T/acl-context.json" <<'PYOWNER' 2>/dev/null
import json, sys
from urllib.parse import quote
username = json.load(open(sys.argv[1]))[0]['entry'][0]['content']['username']
assert username and username not in ('-', 'nobody')
print(quote(username, safe=''))
PYOWNER
)
        if [ -n "$acl_owner" ]; then
            acl_base="/servicesNS/$acl_owner/search"
            acl_search="${N}_acl_search"
            acl_macro="${N}_acl_macro"
            defer shared_fixture_delete saved/searches "$acl_search"
            if api_capture "$T/acl-search-create.json" "$S" --json api post "$acl_base/saved/searches" \
                --param "name=$acl_search" --param 'search=| makeresults' --param disabled=1 --yes; then
                api_capture "$T/acl-search-get.json" "$S" --json acl get saved-search "$acl_search" --app search
                api_assert "$T/acl-search-get.json" 'len(d) == 1 and d[0]["sharing"] == "user" and d[0]["read"] is None and d[0]["write"] is None'
                api_capture "$T/acl-search-preview.json" "$S" --json acl set saved-search "$acl_search" --app search --sharing app --read '*'
                api_capture "$T/acl-search-before.json" "$S" --json acl get saved-search "$acl_search" --app search
                api_assert "$T/acl-search-before.json" 'd[0]["sharing"] == "user"'
                api_capture "$T/acl-search-set.json" "$S" --json acl set saved-search "$acl_search" --app search --sharing app --read '*' --yes
                api_capture "$T/acl-search-after.json" "$S" --json acl get saved-search "$acl_search" --app search
                api_assert "$T/acl-search-after.json" 'd[0]["sharing"] == "app" and d[0]["read"] == ["*"]'
                api_capture "$T/acl-search-private.json" "$S" --json acl set saved-search "$acl_search" --app search --sharing user --yes
                api_capture "$T/acl-search-back.json" "$S" --json acl get saved-search "$acl_search" --app search
                api_assert "$T/acl-search-back.json" 'd[0]["sharing"] == "user" and d[0]["read"] is None'
            fi
            defer shared_fixture_delete configs/conf-macros "$acl_macro"
            if api_capture "$T/acl-macro-create.json" "$S" --json api post "$acl_base/configs/conf-macros" \
                --param "name=$acl_macro" --param definition=makeresults --yes; then
                api_capture "$T/acl-macro-get.json" "$S" --json acl get macro "$acl_macro" --app search
                api_assert "$T/acl-macro-get.json" 'len(d) == 1 and d[0]["sharing"] == "user"'
                api_capture "$T/acl-macro-preview.json" "$S" --json acl set macro "$acl_macro" --app search --sharing app --read '*'
                api_capture "$T/acl-macro-before.json" "$S" --json acl get macro "$acl_macro" --app search
                api_assert "$T/acl-macro-before.json" 'd[0]["sharing"] == "user"'
                api_capture "$T/acl-macro-set.json" "$S" --json acl set macro "$acl_macro" --app search --sharing app --read '*' --yes
                api_capture "$T/acl-macro-after.json" "$S" --json acl get macro "$acl_macro" --app search
                api_assert "$T/acl-macro-after.json" 'd[0]["sharing"] == "app" and d[0]["read"] == ["*"]'
                api_capture "$T/acl-macro-private.json" "$S" --json acl set macro "$acl_macro" --app search --sharing user --yes
                api_capture "$T/acl-macro-back.json" "$S" --json acl get macro "$acl_macro" --app search
                api_assert "$T/acl-macro-back.json" 'd[0]["sharing"] == "user" and d[0]["read"] is None'
            fi
        else bad 'resolve authenticated ACL fixture owner'; fi
    fi
fi
if selected server; then
    step "server introspection and logging"
    api_capture "$T/queues.json" "$S" --json server introspection queues
    api_assert "$T/queues.json" 'bool(d) and all(set(("queue", "current", "maximum", "unit", "fill_ratio", "blocked")) <= r.keys() for r in d)'
    api_capture "$T/indexer.json" "$S" --json server introspection indexer
    api_assert "$T/indexer.json" 'bool(d) and all(set(("name", "status", "reason", "average_KBps")) <= r.keys() for r in d)'
    api_capture "$T/disk.json" "$S" --json server introspection disk
    api_assert "$T/disk.json" 'bool(d) and all(isinstance(r["capacity"], (int, float)) and isinstance(r["available"], (int, float)) and r["unit"] == "MB" and "fs_type" in r for r in d)'
    api_capture "$T/logger-list.json" "$S" --json server log-level get
    api_assert "$T/logger-list.json" 'bool(d) and all("level" in r for r in d)'
    logger_component=TcpOutputProc
    if api_capture "$T/logger-original.json" "$S" --json server log-level get "$logger_component"; then
        logger_original=$("$PY" - "$T/logger-original.json" <<'PYLOGGER' 2>/dev/null
import json, sys
rows = json.load(open(sys.argv[1]))
assert len(rows) == 1 and rows[0]['level'] in ('DEBUG', 'INFO', 'WARN', 'ERROR')
print(rows[0]['level'])
PYLOGGER
)
        if [ -n "$logger_original" ]; then
            # Register BEFORE even attempting the runtime change.
            defer restore_logger "$logger_component" "$logger_original"
            logger_target=DEBUG
            [ "$logger_original" != DEBUG ] || logger_target=INFO
            api_capture "$T/logger-preview.json" "$S" --json server log-level set "$logger_component" "$logger_target"
            api_capture "$T/logger-set.json" "$S" --json server log-level set "$logger_component" "$logger_target" --yes
            api_capture "$T/logger-after.json" "$S" --json server log-level get "$logger_component"
            "$PY" - "$T/logger-after.json" "$logger_target" <<'PYLOGGER' 2>/dev/null || bad 'logger read-back level'
import json, sys
assert json.load(open(sys.argv[1]))[0]['level'] == sys.argv[2]
PYLOGGER
        else bad 'save original runtime logging level'; fi
    fi
fi
