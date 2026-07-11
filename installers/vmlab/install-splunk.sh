#!/usr/bin/env bash
# Install Splunk Enterprise (SIEM) on a prepared RHEL VM. Embedded postgres stays
# ENABLED (SPL2 / Data Orchestration intact) — run this on a DEDICATED Splunk VM.
#
#   ./install-splunk.sh --ip 100.65.1.10
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

IP=""
while [[ $# -gt 0 ]]; do case "$1" in
  --ip) IP="$2"; shift 2;; *) die "unknown arg: $1";; esac; done
[[ -n "$IP" ]] || die "usage: --ip IP"
RPM="$(require_artifact "$SPLUNK_RPM")"; RPM_BASE="$(basename "$RPM")"

log "copying $RPM_BASE to $IP"
scp_to "$IP" "$RPM" /var/tmp/

log "OS prep: disable THP, raise ulimits, create splunk user"
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
systemctl enable --now disable-thp.service
cat > /etc/security/limits.d/99-splunk.conf <<'EOF'
splunk soft nofile 64000
splunk hard nofile 64000
splunk soft nproc  16000
splunk hard nproc  16000
splunk soft fsize  unlimited
splunk hard fsize  unlimited
EOF
REMOTE

log "installing RPM to /opt/splunk"
ssh_vm "$IP" "sudo rpm -q splunk >/dev/null 2>&1 || sudo rpm -i /var/tmp/$RPM_BASE; sudo chown -R splunk:splunk /opt/splunk"

log "seeding admin credentials"
seed="$(mktemp)"; printf '[user_info]\nUSERNAME = admin\nPASSWORD = %s\n' "$SPLUNK_ADMIN_PASSWORD" > "$seed"
scp_to "$IP" "$seed" /var/tmp/user-seed.conf; rm -f "$seed"
ssh_vm "$IP" 'sudo install -o splunk -g splunk -m600 /var/tmp/user-seed.conf /opt/splunk/etc/system/local/user-seed.conf && sudo rm -f /var/tmp/user-seed.conf'

log "enabling boot-start (systemd) and starting"
ssh_vm "$IP" 'sudo /opt/splunk/bin/splunk enable boot-start -user splunk -systemd-managed 1 --accept-license --answer-yes --no-prompt >/dev/null && sudo systemctl start Splunkd'

log "opening firewall (8000/8089/8088/8191)"
ssh_vm "$IP" 'sudo firewall-cmd --permanent --add-port=8000/tcp --add-port=8089/tcp --add-port=8088/tcp --add-port=8191/tcp >/dev/null && sudo firewall-cmd --reload >/dev/null'

log "waiting for Splunk web…"
ssh_vm "$IP" 'for i in $(seq 1 24); do c=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000); [ "$c" = "303" ] && break; sleep 5; done; echo "  web8000=$c"; sudo -u splunk /opt/splunk/bin/splunk status | head -1'
log "Splunk Enterprise ready: http://$IP:8000  (admin / $SPLUNK_ADMIN_PASSWORD)"
