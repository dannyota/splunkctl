#!/usr/bin/env bash
# Read-only host, artifact, VMware, and endpoint preflight for the lab.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$HERE/lib.sh"

usage() {
  printf 'Usage: %s [--only siem|soar|both]\n' "${0##*/}"
}

ONLY="both"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --only)
      [[ $# -ge 2 ]] || die "--only requires siem, soar, or both"
      ONLY="$2"
      shift 2
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

failed=0
for command_name in vmrun vmware-vdiskmanager xorriso ssh scp nc curl openssl python3; do
  if command -v "$command_name" >/dev/null 2>&1; then
    log "command $command_name: OK"
  else
    warn "command $command_name: missing"
    failed=1
  fi
done

check_artifact() {
  local name="$1"
  if [[ -f "$INSTALLERS_DIR/$name" ]]; then
    log "artifact $name: OK"
  else
    warn "artifact $name: missing from $INSTALLERS_DIR"
    failed=1
  fi
}

check_artifact "$RHEL_ISO"
if [[ "$ONLY" == siem || "$ONLY" == both ]]; then
  check_artifact "$SPLUNK_RPM"
  check_artifact "$SSE_TGZ"
fi
if [[ "$ONLY" == soar || "$ONLY" == both ]]; then
  check_artifact "$SOAR_TGZ"
fi

nat_conf=/etc/vmware/vmnet8/nat/nat.conf
if [[ -r "$nat_conf" ]]; then
  if grep -Eq "^[[:space:]]*ip[[:space:]]*=[[:space:]]*$NAT_GATEWAY([[:space:]]|$)" "$nat_conf"; then
    log "VMware NAT gateway $NAT_GATEWAY: OK"
  else
    warn "VMware NAT config does not contain gateway $NAT_GATEWAY"
    failed=1
  fi
else
  warn "cannot read VMware NAT config: $nat_conf"
  failed=1
fi

mkdir -p "$VM_BASE_DIR"
available_kb="$(df -Pk "$VM_BASE_DIR" | awk 'NR == 2 {print $4}')"
log "free space under $VM_BASE_DIR: $((available_kb / 1024 / 1024)) GiB"

check_vm() {
  local name="$1" ip="$2" vmx
  vmx="$(vmx_path "$name")"
  if [[ ! -f "$vmx" ]]; then
    log "$name VM: missing; build will create $vmx"
    return
  fi
  if vm_running "$vmx"; then
    log "$name VM: running"
  else
    log "$name VM: stopped"
  fi
  if nc -z -w2 "$ip" 22 2>/dev/null; then
    log "$name SSH $ip:22: reachable"
  else
    log "$name SSH $ip:22: not reachable"
  fi
}

if [[ "$ONLY" == siem || "$ONLY" == both ]]; then
  check_vm siem "$SIEM_IP"
  for port in 8000 8089 8088; do
    if nc -z -w2 "$SIEM_IP" "$port" 2>/dev/null; then
      log "SIEM $SIEM_IP:$port: reachable"
    else
      log "SIEM $SIEM_IP:$port: not reachable"
    fi
  done
fi
if [[ "$ONLY" == soar || "$ONLY" == both ]]; then
  check_vm soar "$SOAR_IP"
  if nc -z -w2 "$SOAR_IP" 8443 2>/dev/null; then
    log "SOAR $SOAR_IP:8443: reachable"
  else
    log "SOAR $SOAR_IP:8443: not reachable"
  fi
fi

(( failed == 0 )) || die "preflight failed"
log "preflight passed"
