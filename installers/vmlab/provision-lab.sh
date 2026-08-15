#!/usr/bin/env bash
# Reuse or create the VMs, then run each idempotent lab stage in order.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$HERE/lib.sh"

usage() {
  printf 'Usage: %s [--only siem|soar|both] [--skip-data]\n' "${0##*/}"
}

ONLY=both
SKIP_DATA=no
while [[ $# -gt 0 ]]; do
  case "$1" in
    --only)
      [[ $# -ge 2 ]] || die "--only requires siem, soar, or both"
      ONLY="$2"
      shift 2
      ;;
    --skip-data)
      SKIP_DATA=yes
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *) die "unknown argument: $1" ;;
  esac
done
[[ "$ONLY" == siem || "$ONLY" == soar || "$ONLY" == both ]] ||
  die "--only must be siem, soar, or both"

"$HERE/check-lab.sh" --only "$ONLY"

ensure_role_vm() {
  local name="$1" ip="$2" ram="$3" cpu="$4" vnc_port="$5" vmx
  vmx="$(vmx_path "$name")"
  if [[ -f "$vmx" ]]; then
    ensure_vm_running "$name"
    wait_ssh "$ip"
    return 0
  fi
  [[ ! -d "$VM_BASE_DIR/$name" ]] ||
    die "VM directory exists without $vmx; inspect it before building"
  "$HERE/build-rhel-vm.sh" --name "$name" --ip "$ip" --ram "$ram" \
    --cpu "$cpu" --vnc-port "$vnc_port"
}

prepared_data_current() {
  local package manifest="$SSE_DATA_DIR/manifest.json"
  [[ -f "$manifest" ]] || return 1
  package="$(require_artifact "$SSE_TGZ")"
  python3 - "$manifest" "$package" "$SSE_INDEX" <<'PY'
import hashlib
import json
import sys

manifest_path, package_path, expected_index = sys.argv[1:]
with open(manifest_path, encoding="utf-8") as stream:
    manifest = json.load(stream)
digest = hashlib.sha256()
with open(package_path, "rb") as stream:
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        digest.update(chunk)
valid = (
    manifest.get("schema_version") == 1
    and manifest.get("package_sha256") == digest.hexdigest()
    and manifest.get("index") == expected_index
)
raise SystemExit(0 if valid else 1)
PY
}

if [[ "$ONLY" == siem || "$ONLY" == both ]]; then
  log "=== SIEM stages ==="
  ensure_role_vm siem "$SIEM_IP" "$SIEM_RAM" "$SIEM_CPU" 5901
  "$HERE/install-splunk.sh" --ip "$SIEM_IP"
  "$HERE/install-sse.sh" --ip "$SIEM_IP"
  if [[ "$SKIP_DATA" == no ]]; then
    if ! prepared_data_current; then
      "$HERE/import-sse-data.sh" prepare
    fi
    "$HERE/import-sse-data.sh" import
  fi
fi

if [[ "$ONLY" == soar || "$ONLY" == both ]]; then
  log "=== SOAR stages ==="
  ensure_role_vm soar "$SOAR_IP" "$SOAR_RAM" "$SOAR_CPU" 5902
  "$HERE/install-soar.sh" --name soar --ip "$SOAR_IP"
fi

verify_args=(--only "$ONLY")
[[ "$SKIP_DATA" == yes ]] && verify_args+=(--skip-data)
"$HERE/verify-lab.sh" "${verify_args[@]}"

[[ "$ONLY" == siem || "$ONLY" == both ]] &&
  log "SIEM: http://$SIEM_IP:8000"
[[ "$ONLY" == soar || "$ONLY" == both ]] &&
  log "SOAR: https://$SOAR_IP:8443"
