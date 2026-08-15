#!/usr/bin/env bash
# Install, resume, or verify Splunk SOAR on the existing SOAR VM.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$HERE/lib.sh"

usage() {
  printf 'Usage: %s [--name NAME] [--ip ADDRESS]\n' "${0##*/}"
}

NAME=soar
IP="$SOAR_IP"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --name)
      [[ $# -ge 2 ]] || die "--name requires a value"
      NAME="$2"
      shift 2
      ;;
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

SOAR_VERSION=8.6.0.530
VMX="$(vmx_path "$NAME")"
dvd_attached=no

ensure_ssh_key
wait_ssh "$IP"
if ! ssh_vm "$IP" true >/dev/null 2>&1; then
  seed_ssh_key "$IP" || die "cannot authenticate to $IP"
fi

product_installed() {
  ssh_vm "$IP" 'test -x /opt/phantom/bin/phsvc' >/dev/null 2>&1
}

installed_version() {
  ssh_vm "$IP" "cd /tmp && sudo -u soar /opt/phantom/bin/phenv python -c \
    'import sys; sys.path.insert(0, \"/opt/phantom/www\"); \
from phantom_ui.product_version import PRODUCT_VERSION; print(PRODUCT_VERSION)'"
}

soar_auth_ready() {
  local netrc code rc=0
  netrc="$(mktemp)"
  chmod 600 "$netrc"
  printf 'machine %s login soar_local_admin password %s\n' \
    "$IP" "$LAB_PASSWORD" > "$netrc"
  code="$(curl --netrc-file "$netrc" --insecure --silent --output /dev/null \
    --write-out '%{http_code}' "https://$IP:8443/rest/version")" || rc=$?
  rm -f "$netrc"
  [[ "$rc" == 0 && "$code" == 200 ]]
}

wait_soar_web() {
  local start code
  start="$(date +%s)"
  while true; do
    code="$(curl -sk -o /dev/null -w '%{http_code}' "https://$IP:8443" || true)"
    [[ "$code" == 200 || "$code" == 302 ]] && return 0
    (( $(date +%s) - start >= 240 )) &&
      die "timeout waiting for SOAR web on $IP (last: $code)"
    sleep 5
  done
}

configure_password() {
  soar_auth_ready && return 0
  local password_b64
  password_b64="$(printf '%s' "$LAB_PASSWORD" | base64 -w0)"
  log "setting the SOAR local administrator credential"
  ssh_vm "$IP" "password=\$(printf '%s' '$password_b64' | base64 -d); cd /tmp; \
    printf '%s\\n%s\\n' \"\$password\" \"\$password\" | \
    sudo -u soar /opt/phantom/bin/phenv python /opt/phantom/www/manage.py \
    changepassword soar_local_admin >/dev/null"
  soar_auth_ready || die "SOAR administrator authentication failed"
}

configure_firewall() {
  ssh_vm "$IP" 'sudo firewall-cmd --permanent --add-port=8443/tcp >/dev/null 2>&1 && sudo firewall-cmd --reload >/dev/null'
}

cleanup_dvd() {
  [[ "$dvd_attached" == yes ]] || return 0
  ssh_vm "$IP" 'sudo sed -i "s/enabled=1/enabled=0/" /etc/yum.repos.d/dvd.repo; sudo umount /mnt/dvd 2>/dev/null || true' \
    >/dev/null 2>&1 || true
  vmrun -T ws disconnectNamedDevice "$VMX" sata0:0 >/dev/null 2>&1 || true
  dvd_attached=no
}
trap cleanup_dvd EXIT

if product_installed; then
  current_version="$(installed_version)"
  [[ "$current_version" == "$SOAR_VERSION" ]] ||
    die "SOAR version mismatch: expected $SOAR_VERSION, got $current_version"
  configure_firewall
  wait_soar_web
  configure_password
  log "Splunk SOAR $SOAR_VERSION is already installed and running on $IP"
  exit 0
fi

TGZ="$(require_artifact "$SOAR_TGZ")"
TGZ_BASE="$(basename "$TGZ")"
[[ -f "$VMX" ]] || die "VMX not found: $VMX"

log "verifying the SOAR service account"
ssh_vm "$IP" 'sudo bash -c "id soar >/dev/null 2>&1 || useradd -m -s /bin/bash soar; echo \"soar ALL=(ALL) NOPASSWD:ALL\" > /etc/sudoers.d/soar; chmod 440 /etc/sudoers.d/soar; install -d -o soar -g soar -m 755 /opt/phantom"'

log "attaching the RHEL DVD for offline dependencies"
vmrun -T ws connectNamedDevice "$VMX" sata0:0 >/dev/null
dvd_attached=yes
sleep 3
ssh_vm "$IP" 'sudo mkdir -p /mnt/dvd; mountpoint -q /mnt/dvd || sudo mount -o ro /dev/sr0 /mnt/dvd; sudo sed -i "s/enabled=0/enabled=1/" /etc/yum.repos.d/dvd.repo'

if ! ssh_vm "$IP" 'test -x /home/soar/splunk-soar/soar-install'; then
  log "copying and extracting SOAR $SOAR_VERSION"
  scp_to "$IP" "$TGZ" "/var/tmp/$TGZ_BASE"
  ssh_vm "$IP" "sudo cp '/var/tmp/$TGZ_BASE' /home/soar/; \
    sudo chown soar:soar '/home/soar/$TGZ_BASE'; \
    sudo -u soar tar xzf '/home/soar/$TGZ_BASE' -C /home/soar; \
    sudo rm -f '/var/tmp/$TGZ_BASE'"
fi

if ! ssh_vm "$IP" 'rpm -q compat-openssl11 initscripts >/dev/null 2>&1'; then
  log "running soar-prepare-system"
  ssh_vm "$IP" 'sudo /home/soar/splunk-soar/soar-prepare-system --splunk-soar-home /opt/phantom --splunk-soar-user soar --https-port 8443 -y --no-spinners --log-format plain' \
    2>&1 | tail -5
fi

if ! product_installed; then
  log "running soar-install; this takes several minutes"
  ssh_vm "$IP" "sudo -u soar bash -c \
    'cd /home/soar/splunk-soar && ./soar-install --splunk-soar-home /opt/phantom \
    --https-port 8443 --offline --with-apps --ignore-warnings -y --no-spinners \
    --log-format plain'" 2>&1 | tail -8
fi

cleanup_dvd
trap - EXIT
product_installed || die "SOAR installation did not create /opt/phantom/bin/phsvc"
current_version="$(installed_version)"
[[ "$current_version" == "$SOAR_VERSION" ]] ||
  die "SOAR version mismatch: expected $SOAR_VERSION, got $current_version"
configure_firewall
wait_soar_web
configure_password
log "Splunk SOAR $SOAR_VERSION is ready on $IP"
