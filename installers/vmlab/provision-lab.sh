#!/usr/bin/env bash
# Provision the full Splunk SIEM + SOAR lab as two dedicated VMs.
# Each product runs natively (no port hacks, no disabled features).
#
#   ./provision-lab.sh                 # build both
#   ./provision-lab.sh --only siem     # just the SIEM VM
#   ./provision-lab.sh --only soar     # just the SOAR VM
#
# Tunables via env: SIEM_IP SOAR_IP SIEM_RAM SOAR_RAM SIEM_CPU SOAR_CPU
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; source "$HERE/lib.sh"

: "${SIEM_IP:=100.65.1.10}"; : "${SOAR_IP:=100.65.1.11}"
: "${SIEM_RAM:=4096}"; : "${SOAR_RAM:=6144}"
: "${SIEM_CPU:=4}"; : "${SOAR_CPU:=4}"
ONLY="both"
while [[ $# -gt 0 ]]; do case "$1" in --only) ONLY="$2"; shift 2;; *) die "unknown arg: $1";; esac; done

if [[ "$ONLY" == both || "$ONLY" == siem ]]; then
  log "=== SIEM VM ==="
  "$HERE/build-rhel-vm.sh" --name siem --ip "$SIEM_IP" --ram "$SIEM_RAM" --cpu "$SIEM_CPU" --vnc-port 5901
  "$HERE/install-splunk.sh" --ip "$SIEM_IP"
fi
if [[ "$ONLY" == both || "$ONLY" == soar ]]; then
  log "=== SOAR VM ==="
  "$HERE/build-rhel-vm.sh" --name soar --ip "$SOAR_IP" --ram "$SOAR_RAM" --cpu "$SOAR_CPU" --vnc-port 5902
  "$HERE/install-soar.sh" --name soar --ip "$SOAR_IP"
fi

log "=== lab ready ==="
[[ "$ONLY" == both || "$ONLY" == siem ]] && log "SIEM: http://$SIEM_IP:8000  (admin / $SPLUNK_ADMIN_PASSWORD)  mgmt $SIEM_IP:8089"
[[ "$ONLY" == both || "$ONLY" == soar ]] && log "SOAR: https://$SOAR_IP:8443"
