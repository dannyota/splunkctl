#!/usr/bin/env bash
# Install or verify Splunk Enterprise on the existing SIEM VM.
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

RPM="$(require_artifact "$SPLUNK_RPM")"
RPM_BASE="$(basename "$RPM")"
EXPECTED_VERSION="${RPM_BASE#splunk-}"
EXPECTED_VERSION="${EXPECTED_VERSION%.rpm}"

ensure_ssh_key
wait_ssh "$IP"
if ! ssh_vm "$IP" true >/dev/null 2>&1; then
  seed_ssh_key "$IP" || die "cannot authenticate to $IP"
fi

log "verifying Splunk host settings"
ssh_vm "$IP" 'sudo bash -s' <<'REMOTE'
set -e
getent group splunk >/dev/null || groupadd -r splunk
id splunk >/dev/null 2>&1 || useradd -r -g splunk -m -d /opt/splunk -s /bin/bash splunk
cat > /etc/systemd/system/disable-thp.service <<'EOF'
[Unit]
Description=Disable Transparent Huge Pages (Splunk)
After=local-fs.target
[Service]
Type=oneshot
ExecStart=/bin/sh -c 'echo never > /sys/kernel/mm/transparent_hugepage/enabled; echo never > /sys/kernel/mm/transparent_hugepage/defrag'
[Install]
WantedBy=multi-user.target
EOF
systemctl enable --now disable-thp.service >/dev/null
cat > /etc/security/limits.d/99-splunk.conf <<'EOF'
splunk soft nofile 64000
splunk hard nofile 64000
splunk soft nproc  16000
splunk hard nproc  16000
splunk soft fsize  unlimited
splunk hard fsize  unlimited
EOF
REMOTE

installed_version="$(ssh_vm "$IP" \
  "rpm -q --qf '%{VERSION}-%{RELEASE}.%{ARCH}' splunk 2>/dev/null || true")"
was_ready=no
if [[ "$installed_version" == "$EXPECTED_VERSION" ]] && splunk_is_ready "$IP"; then
  was_ready=yes
fi

if [[ "$installed_version" != "$EXPECTED_VERSION" ]]; then
  log "copying $RPM_BASE to $IP"
  scp_to "$IP" "$RPM" "/var/tmp/$RPM_BASE"
  log "installing pinned Splunk Enterprise $EXPECTED_VERSION"
  ssh_vm "$IP" "sudo rpm -Uvh --replacepkgs '/var/tmp/$RPM_BASE' >/dev/null; \
    sudo chown -R splunk:splunk /opt/splunk; sudo rm -f '/var/tmp/$RPM_BASE'"
fi

if ! ssh_vm "$IP" 'sudo test -s /opt/splunk/etc/passwd'; then
  log "seeding the first-start administrator credential"
  seed="$(mktemp)"
  chmod 600 "$seed"
  printf '[user_info]\nUSERNAME = admin\nPASSWORD = %s\n' \
    "$SPLUNK_ADMIN_PASSWORD" > "$seed"
  scp_to "$IP" "$seed" /var/tmp/user-seed.conf
  rm -f "$seed"
  ssh_vm "$IP" 'sudo install -o splunk -g splunk -m 600 /var/tmp/user-seed.conf /opt/splunk/etc/system/local/user-seed.conf; sudo rm -f /var/tmp/user-seed.conf'
fi

if ! ssh_vm "$IP" 'sudo test -f /etc/systemd/system/Splunkd.service'; then
  log "enabling Splunk boot-start"
  ssh_vm "$IP" 'sudo /opt/splunk/bin/splunk enable boot-start -user splunk -systemd-managed 1 --accept-license --answer-yes --no-prompt >/dev/null'
fi
ssh_vm "$IP" 'sudo systemctl enable --now Splunkd >/dev/null'

log "verifying Splunk firewall ports"
ssh_vm "$IP" 'sudo firewall-cmd --permanent --add-port=8000/tcp --add-port=8089/tcp --add-port=8088/tcp --add-port=8191/tcp >/dev/null 2>&1 && sudo firewall-cmd --reload >/dev/null'
wait_http "http://$IP:8000" 303 240

installed_version="$(ssh_vm "$IP" \
  "rpm -q --qf '%{VERSION}-%{RELEASE}.%{ARCH}' splunk")"
[[ "$installed_version" == "$EXPECTED_VERSION" ]] ||
  die "Splunk version mismatch: expected $EXPECTED_VERSION, got $installed_version"
splunk_is_ready "$IP" || die "Splunk service verification failed on $IP"

if [[ "$was_ready" == yes ]]; then
  log "Splunk $EXPECTED_VERSION is already installed and running on $IP"
else
  log "Splunk $EXPECTED_VERSION is ready on $IP"
fi
