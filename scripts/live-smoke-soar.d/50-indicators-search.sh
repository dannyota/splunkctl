#!/usr/bin/env bash
indicators_group() {
    ensure_event || return
    # Domain is unique and reserved. Removing the artifact does not remove IOC records.
    IOC="$N.invalid"
    defer cleanup_child artifacts "$C" "${N}_ioc"
    expect_ok "$S" soar artifacts create --container "$C" --name "${N}_ioc" \
        --sdi "${N}_ioc" --cef "destinationDnsDomain=$IOC" --cef-type destinationDnsDomain=domain \
        --no-automation --yes
    "$S" soar indicators list --limit 1 --json > "$T/indicators.json" 2> "$T/indicators.err"
    local status=$?
    if [ "$status" -ne 0 ]; then
        if "$PY" - "$T/indicators.err" <<'PY'
import json, sys
assert any(json.loads(line).get('error', {}).get('kind') == 'feature'
           for line in open(sys.argv[1]) if line.startswith('{'))
PY
        then
            skip '50-indicators-search indicators: feature disabled'
        else
            cat "$T/indicators.err"
            bad 'indicators list failed'
        fi
    else
        expect_ok "$S" soar indicators get "$IOC" --json
        expect_ok "$S" soar indicators stats --json
        expect_ok "$S" soar indicators pivot "$IOC" --json
    fi
    check_json 'isinstance(d, list) and len(d) > 0' soar search "$N" --page 1 --categories container,artifact --page-size 20
}
if soar_selected 50-indicators-search; then
    step '50-indicators-search'
    indicators_group
fi
