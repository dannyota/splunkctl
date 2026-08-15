#!/usr/bin/env bash
# Prepare, import, inspect, or reset the lab-owned SSE sample event index.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$HERE/lib.sh"

usage() {
  cat <<EOF
Usage:
  ${0##*/} prepare [--anchor ISO_8601] [--dry-run]
  ${0##*/} import [--clear-existing]
  ${0##*/} status
  ${0##*/} reset [--anchor ISO_8601]
EOF
}

COMMAND="${1:-}"
[[ -n "$COMMAND" ]] || { usage >&2; exit 2; }
shift

prepare_data() {
  local anchor="$1" dry_run="$2" package
  package="$(require_artifact "$SSE_TGZ")"
  local args=(--package "$package" --output-dir "$SSE_DATA_DIR" --index "$SSE_INDEX")
  [[ -n "$anchor" ]] && args+=(--anchor "$anchor")
  [[ "$dry_run" == yes ]] && args+=(--dry-run)
  "$HERE/prepare-sse-data.py" "${args[@]}"
}

require_manifest() {
  [[ -f "$SSE_DATA_DIR/manifest.json" ]] ||
    die "prepared manifest not found; run: ${0##*/} prepare"
}

ensure_siem_access() {
  ensure_ssh_key
  wait_ssh "$SIEM_IP"
  if ! ssh_vm "$SIEM_IP" true >/dev/null 2>&1; then
    seed_ssh_key "$SIEM_IP" || die "cannot authenticate to $SIEM_IP"
  fi
  splunk_is_ready "$SIEM_IP" || die "Splunk is not ready on $SIEM_IP"
}

ensure_hec_token() {
  if [[ ! -f "$SSE_HEC_TOKEN_FILE" ]]; then
    mkdir -p "$(dirname "$SSE_HEC_TOKEN_FILE")"
    umask 077
    openssl rand -hex 32 > "$SSE_HEC_TOKEN_FILE"
    chmod 600 "$SSE_HEC_TOKEN_FILE"
    log "created the lab HEC token file"
  fi
  [[ "$(stat -c '%a' "$SSE_HEC_TOKEN_FILE")" == 600 ]] ||
    chmod 600 "$SSE_HEC_TOKEN_FILE"
}

configure_hec() {
  local token config_dir changed
  token="$(<"$SSE_HEC_TOKEN_FILE")"
  config_dir="$(mktemp -d)"
  cat > "$config_dir/indexes.conf" <<EOF
[$SSE_INDEX]
homePath = \$SPLUNK_DB/$SSE_INDEX/db
coldPath = \$SPLUNK_DB/$SSE_INDEX/colddb
thawedPath = \$SPLUNK_DB/$SSE_INDEX/thaweddb
EOF
  cat > "$config_dir/inputs.conf" <<EOF
[http]
disabled = 0
enableSSL = 1

[http://sse-lab]
disabled = 0
token = $token
index = $SSE_INDEX
indexes = $SSE_INDEX
EOF
  cat > "$config_dir/fields.conf" <<'EOF'
[lab_import_id]
INDEXED = true

[lab_batch_id]
INDEXED = true

[lab_dataset]
INDEXED = true
EOF
  python3 - "$SSE_DATA_DIR/manifest.json" > "$config_dir/props.conf" <<'PY'
import json
import sys

manifest = json.load(open(sys.argv[1], encoding="utf-8"))
for dataset in manifest["datasets"]:
    print(f'[{dataset["sourcetype"]}]')
    print("KV_MODE = json")
    print("TRUNCATE = 0")
    print()
PY
  for name in indexes inputs fields props; do
    scp_to "$SIEM_IP" "$config_dir/$name.conf" "/var/tmp/sse-lab-$name.conf"
  done
  changed="$(ssh_vm "$SIEM_IP" 'sudo bash -s' <<'REMOTE'
set -e
target=/opt/splunk/etc/apps/sse_lab_loader/local
install -d -o splunk -g splunk -m 750 "$target"
changed=no
for name in indexes inputs fields props; do
  source="/var/tmp/sse-lab-$name.conf"
  destination="$target/$name.conf"
  if ! cmp -s "$source" "$destination"; then
    install -o splunk -g splunk -m 600 "$source" "$destination"
    changed=yes
  fi
  rm -f "$source"
done
printf '%s' "$changed"
REMOTE
)"
  rm -rf "$config_dir"
  if [[ "$changed" == yes ]]; then
    log "applying lab index and HEC configuration"
    ssh_vm "$SIEM_IP" 'sudo systemctl restart Splunkd'
    wait_http "http://$SIEM_IP:8000" 303 240
  fi
  wait_http "https://$SIEM_IP:8088/services/collector/health" 200 180
}

splunk_curl() {
  local netrc result rc
  netrc="$(mktemp)"
  chmod 600 "$netrc"
  printf 'machine %s login admin password %s\n' \
    "$SIEM_IP" "$SPLUNK_ADMIN_PASSWORD" > "$netrc"
  rc=0
  result="$(curl --netrc-file "$netrc" --insecure --silent --show-error \
    --fail-with-body "$@")" || rc=$?
  rm -f "$netrc"
  printf '%s' "$result"
  return "$rc"
}

splunk_search() {
  splunk_curl -X POST "https://$SIEM_IP:8089/services/search/jobs/export" \
    --data-urlencode "search=search $1" \
    --data-urlencode 'output_mode=json' \
    --data-urlencode 'earliest_time=0' \
    --data-urlencode 'latest_time=now'
}

manifest_value() {
  python3 - "$SSE_DATA_DIR/manifest.json" "$1" <<'PY'
import json
import sys

print(json.load(open(sys.argv[1], encoding="utf-8"))[sys.argv[2]])
PY
}

manifest_batches() {
  python3 - "$SSE_DATA_DIR/manifest.json" <<'PY'
import json
import sys

manifest = json.load(open(sys.argv[1], encoding="utf-8"))
for batch in manifest["batches"]:
    print(f'{batch["id"]}\t{batch["file"]}\t{batch["events"]}')
PY
}

indexed_batch_counts() {
  local import_id="$1"
  splunk_search "index=$SSE_INDEX lab_import_id=\"$import_id\" | stats count by lab_batch_id" |
    python3 -c '
import json, sys
for line in sys.stdin:
    record = json.loads(line)
    result = record.get("result")
    if result:
        print("{}\t{}".format(result["lab_batch_id"], result["count"]))'
}

clear_existing() {
  require_sse_lab_index
  log "clearing event data only from index $SSE_INDEX"
  ssh_vm "$SIEM_IP" "sudo -u splunk /opt/splunk/bin/splunk stop >/dev/null; \
    sudo -u splunk /opt/splunk/bin/splunk clean eventdata -index '$SSE_INDEX' -f >/dev/null; \
    sudo systemctl start Splunkd"
  wait_http "http://$SIEM_IP:8000" 303 240
  wait_http "https://$SIEM_IP:8088/services/collector/health" 200 180
}

post_batch() {
  local batch="$1" token response
  token="$(<"$SSE_HEC_TOKEN_FILE")"
  response="$({ printf 'header = "Authorization: Splunk %s"\n' "$token"; } |
    curl --config - --insecure --silent --show-error --fail-with-body \
      -X POST "https://$SIEM_IP:8088/services/collector/event" \
      --data-binary "@$batch")"
  python3 - "$response" <<'PY'
import json
import sys

response = json.loads(sys.argv[1])
if response.get("code") != 0:
    raise SystemExit(f"HEC rejected batch: {response}")
PY
}

verify_import_count() {
  local import_id="$1" expected="$2" actual=0
  for _attempt in $(seq 1 60); do
    actual="$(splunk_search "index=$SSE_INDEX lab_import_id=\"$import_id\" | stats count" |
      python3 -c 'import json,sys
for line in sys.stdin:
 result=json.loads(line).get("result")
 if result: print(result["count"])')"
    [[ "${actual:-0}" == "$expected" ]] && return 0
    sleep 2
  done
  die "indexed count mismatch for $import_id: expected $expected, got ${actual:-0}"
}

import_data() {
  local clear="$1" import_id expected batch_id relative count existing_count
  require_sse_lab_index
  require_manifest
  ensure_siem_access
  ensure_hec_token
  configure_hec
  [[ "$clear" == yes ]] && clear_existing

  import_id="$(manifest_value import_id)"
  expected="$(manifest_value event_count)"
  declare -A existing=()
  while IFS=$'\t' read -r batch_id count; do
    [[ -n "$batch_id" ]] && existing["$batch_id"]="$count"
  done < <(indexed_batch_counts "$import_id")

  while IFS=$'\t' read -r batch_id relative count; do
    existing_count="${existing[$batch_id]:-0}"
    if [[ "$existing_count" == "$count" ]]; then
      log "batch $batch_id already indexed; skipping"
      continue
    fi
    [[ "$existing_count" == 0 ]] ||
      die "batch $batch_id is partial ($existing_count/$count); rerun with --clear-existing"
    log "importing batch $batch_id ($count events)"
    post_batch "$SSE_DATA_DIR/$relative"
  done < <(manifest_batches)

  verify_import_count "$import_id" "$expected"
  log "SSE import $import_id verified: $expected events"
}

show_status() {
  local import_id expected summary
  require_sse_lab_index
  require_manifest
  ensure_siem_access
  import_id="$(manifest_value import_id)"
  expected="$(manifest_value event_count)"
  summary="$(splunk_search "index=$SSE_INDEX lab_import_id=\"$import_id\" | stats count dc(lab_dataset) as datasets earliest(_time) as earliest latest(_time) as latest" |
    python3 -c 'import json,sys
for line in sys.stdin:
 result=json.loads(line).get("result")
 if result: print("\t".join(result.get(k, "0") for k in ("count","datasets","earliest","latest")))')"
  printf 'import_id=%s\nexpected=%s\nindexed=%s\n' \
    "$import_id" "$expected" "${summary:-0\t0\t0\t0}"
}

case "$COMMAND" in
  prepare)
    anchor="" dry_run=no
    while [[ $# -gt 0 ]]; do
      case "$1" in
        --anchor) [[ $# -ge 2 ]] || die "--anchor requires a value"; anchor="$2"; shift 2 ;;
        --dry-run) dry_run=yes; shift ;;
        -h|--help) usage; exit 0 ;;
        *) die "unknown prepare argument: $1" ;;
      esac
    done
    prepare_data "$anchor" "$dry_run"
    ;;
  import)
    clear=no
    while [[ $# -gt 0 ]]; do
      case "$1" in
        --clear-existing) clear=yes; shift ;;
        -h|--help) usage; exit 0 ;;
        *) die "unknown import argument: $1" ;;
      esac
    done
    [[ "$clear" == yes ]] && require_sse_lab_index
    import_data "$clear"
    ;;
  status)
    [[ $# -eq 0 ]] || die "status takes no arguments"
    show_status
    ;;
  reset)
    require_sse_lab_index
    anchor=""
    while [[ $# -gt 0 ]]; do
      case "$1" in
        --anchor) [[ $# -ge 2 ]] || die "--anchor requires a value"; anchor="$2"; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) die "unknown reset argument: $1" ;;
      esac
    done
    prepare_data "$anchor" no
    import_data yes
    ;;
  -h|--help) usage ;;
  *) die "unknown command: $COMMAND" ;;
esac
