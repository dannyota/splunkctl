#!/usr/bin/env bash
# Install or verify the pinned Splunk Security Essentials app on the SIEM VM.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$HERE/lib.sh"

usage() {
  printf 'Usage: %s [--ip ADDRESS]\n' "${0##*/}"
}

IP="$SIEM_IP"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --ip)
      [[ $# -ge 2 ]] || die "--ip requires an address"
      IP="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *) die "unknown argument: $1" ;;
  esac
done

APP_ID=Splunk_Security_Essentials
APP_VERSION=3.8.3
TGZ="$(require_artifact "$SSE_TGZ")"
TGZ_BASE="$(basename "$TGZ")"

package_setting() {
  local section="$1" key="$2"
  tar -xOzf "$TGZ" "$APP_ID/default/app.conf" |
    awk -F= -v wanted_section="$section" -v wanted_key="$key" '
      /^\[/ { current=$0; gsub(/^\[|\]$/, "", current) }
      current == wanted_section {
        name=$1; gsub(/^[[:space:]]+|[[:space:]]+$/, "", name)
        if (name == wanted_key) {
          value=$2; gsub(/^[[:space:]]+|[[:space:]]+$/, "", value)
          print value; exit
        }
      }'
}

[[ "$(package_setting package id)" == "$APP_ID" ]] ||
  die "unexpected app ID in $TGZ_BASE"
[[ "$(package_setting launcher version)" == "$APP_VERSION" ]] ||
  die "unexpected app version in $TGZ_BASE"

ensure_ssh_key
wait_ssh "$IP"
if ! ssh_vm "$IP" true >/dev/null 2>&1; then
  seed_ssh_key "$IP" || die "cannot authenticate to $IP"
fi
splunk_is_ready "$IP" || die "Splunk is not ready on $IP"

read_installed_version() {
  ssh_vm "$IP" "sudo sed -n '/^\\[launcher\\]/,/^\\[/ {
    s/^[[:space:]]*version[[:space:]]*=[[:space:]]*//p
  }' /opt/splunk/etc/apps/$APP_ID/default/app.conf 2>/dev/null | head -1 | tr -d '[:space:]'"
}

installed_version="$(read_installed_version)"
if [[ "$installed_version" == "$APP_VERSION" ]]; then
  log "SSE $APP_VERSION is already installed on $IP"
  exit 0
fi

log "copying $TGZ_BASE to $IP"
scp_to "$IP" "$TGZ" "/var/tmp/$TGZ_BASE"
password_b64="$(printf '%s' "$SPLUNK_ADMIN_PASSWORD" | base64 -w0)"
cleanup_remote() {
  ssh_vm "$IP" "sudo rm -f /var/tmp/$TGZ_BASE" >/dev/null 2>&1 || true
}
trap cleanup_remote EXIT

log "installing SSE $APP_VERSION"
ssh_vm "$IP" "password=\$(printf '%s' '$password_b64' | base64 -d); \
  sudo -u splunk /opt/splunk/bin/splunk install app '/var/tmp/$TGZ_BASE' \
  -update 1 --answer-yes --no-prompt -auth \"admin:\$password\" >/dev/null"
ssh_vm "$IP" 'sudo systemctl restart Splunkd'
wait_http "http://$IP:8000" 303 240

installed_version="$(read_installed_version)"
[[ "$installed_version" == "$APP_VERSION" ]] ||
  die "SSE verification failed: expected $APP_VERSION, got $installed_version"
log "SSE $APP_VERSION is ready on $IP"
