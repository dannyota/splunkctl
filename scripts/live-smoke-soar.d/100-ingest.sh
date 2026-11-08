#!/usr/bin/env bash
# Bounded SIEM input, no source events or licensed actions required.
smoke_ingest() {
    if ! "$S" server health --json > "$T/siem-health.json" 2>&1; then
        skip '100-ingest: SIEM profile unavailable'
        return
    fi
    local ingest_name="${N}_ingest" ingest_id spl
    spl="| makeresults count=1 | eval event_id=\"${N}_ingest\", src=\"192.0.2.10\", dest=\"198.51.100.20\", src_port=\"1234\", dest_port=\"443\", user=\"smoke-user\", bytes_in=\"17\", url=\"https://example.invalid/${N}\", severity=\"critical\" | fields event_id src dest src_port dest_port user bytes_in url severity"
    capture "$T/ingest-existing.json" "$S" soar containers list \
        --filter "_filter_name=\"$ingest_name\"" --json || return
    if [ "$(json_value "$T/ingest-existing.json" 'len(d)')" != 0 ]; then
        bad 'ingest fixture name already exists'
        return
    fi
    # Exact name handles a lost create response. Never enumerate by prefix.
    defer soar_cleanup containers "$ingest_name"
    capture "$T/ingest-first.json" "$S" soar ingest --spl "$spl" \
        --container-name "$ingest_name" --grouping --no-automation \
        --earliest=-1m --latest=now --yes --json || return
    assert_json "$T/ingest-first.json" 'd[0]["containers_created"] == 1 and d[0]["artifacts_created"] == 1'
    ingest_id=$(json_value "$T/ingest-first.json" 'd[0].get("container_ids", [""])[0]')
    if [ -z "$ingest_id" ]; then
        bad 'ingest did not return a container ID'
        return
    fi
    # Record the returned id in addition to the pre-registered name fallback.
    printf '%s\n' "$ingest_id" > "$T/ingest-container-id"
    capture "$T/ingest-second.json" "$S" soar ingest --spl "$spl" \
        --container-name "$ingest_name" --grouping --no-automation \
        --earliest=-1m --latest=now --yes --json || return
    assert_json "$T/ingest-second.json" 'd[0]["containers_created"] == 0 and d[0]["containers_skipped"] == 1 and d[0]["artifacts_created"] == 0'
    check_json 'len(d) == 1 and d[0]["id"] == int(open("'"$T"'/ingest-container-id").read())' \
        soar containers list --filter "_filter_source_data_identifier=\"${N}_ingest\""
    capture "$T/ingest-container.json" "$S" soar containers get "$ingest_id" --json || return
    assert_json "$T/ingest-container.json" 'd[0]["severity"] == "high"'
    capture "$T/ingest-artifacts.json" "$S" soar artifacts list --container "$ingest_id" --json || return
    "$PY" - "$T/ingest-artifacts.json" "$N" <<'PY' || bad 'CIM to CEF mapping mismatch'
import json
import sys
rows = json.load(open(sys.argv[1]))
assert len(rows) == 1, rows
row = rows[0]
cef = row['cef']
expected = {
    'sourceAddress': '192.0.2.10', 'destinationAddress': '198.51.100.20',
    'sourcePort': '1234', 'destinationPort': '443',
    'destinationUserName': 'smoke-user', 'bytesIn': '17',
    'requestURL': 'https://example.invalid/' + sys.argv[2],
}
assert all(str(cef.get(k)) == v for k, v in expected.items()), cef
assert row['source_data_identifier'] == sys.argv[2] + '_ingest', row
assert row['severity'] == 'high', row
assert 'ip' in row['cef_types']['sourceAddress'], row
assert 'url' in row['cef_types']['requestURL'], row
PY
    expect_ok "$S" soar ingest-status --json
    # Delete by the recorded ID; the exact-name fallback remains for EXIT.
    expect_ok "$S" soar containers delete "$ingest_id" --yes
    absent soar containers get "$ingest_id"
}
if soar_selected 100-ingest; then
    step "100-ingest"
    smoke_ingest
fi
