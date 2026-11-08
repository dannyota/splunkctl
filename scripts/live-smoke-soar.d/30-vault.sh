#!/usr/bin/env bash
vault_group() {
    ensure_event || return
    printf '%s\n' "$N unique vault bytes" > "$T/$N.bin"
    defer cleanup_child vault "$C" "$N.bin"
    capture "$T/vault-upload.json" "$S" soar vault upload --container "$C" "$T/$N.bin" --yes --json || return
    V=$(json_value "$T/vault-upload.json" 'int(d[0]["id"])') || return
    HASH=$("$PY" - "$T/$N.bin" <<'PY'
import hashlib, sys
print(hashlib.sha1(open(sys.argv[1], 'rb').read(), usedforsecurity=False).hexdigest())
PY
    ) || return
    check_json "any(x.get('hash') == '$HASH' for x in d)" soar vault get "$HASH"
    check_json "any(int(x['id']) == $V and (x.get('vault_id') or x.get('hash')) == '$HASH' for x in d)" soar vault list --container "$C"
    expect_ok "$S" soar vault download "$HASH" --out "$T/download.bin"
    cmp "$T/$N.bin" "$T/download.bin" || bad 'vault download differs'
    expect_ok "$S" soar vault delete "$V" --yes
    check_json "not any(int(x['id']) == $V for x in d)" soar vault list --container "$C"
}
if soar_selected 30-vault; then
    step '30-vault'
    vault_group
fi
