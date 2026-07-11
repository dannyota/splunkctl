#!/usr/bin/env bash
# Install Splunk SOAR (On-premises, unprivileged) on a prepared RHEL VM.
# On a DEDICATED SOAR VM its bundled PostgreSQL owns 5432/6432 with no conflict.
#
#   ./install-soar.sh --name soar --ip 100.65.1.11
#
# --name is used to locate the VMX so the RHEL DVD can be hot-attached for the
# handful of OS dependencies (offline: pulled from the DVD, not the internet).
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

NAME="" IP=""
while [[ $# -gt 0 ]]; do case "$1" in
  --name) NAME="$2"; shift 2;; --ip) IP="$2"; shift 2;; *) die "unknown arg: $1";; esac; done
[[ -n "$NAME" && -n "$IP" ]] || die "usage: --name NAME --ip IP"
TGZ="$(require_artifact "$SOAR_TGZ")"; TGZ_BASE="$(basename "$TGZ")"
VMX="$VM_BASE_DIR/$NAME/$NAME.vmx"; [[ -f "$VMX" ]] || die "VMX not found: $VMX"

log "creating soar user"
ssh_vm "$IP" 'sudo bash -c "id soar >/dev/null 2>&1 || useradd -m -s /bin/bash soar; echo \"soar ALL=(ALL) NOPASSWD:ALL\" > /etc/sudoers.d/soar; chmod 440 /etc/sudoers.d/soar; install -d -o soar -g soar -m755 /opt/phantom"'

log "attaching RHEL DVD for offline dependency repo"
vmrun -T ws connectNamedDevice "$VMX" sata0:0 >/dev/null; sleep 3
ssh_vm "$IP" 'sudo mkdir -p /mnt/dvd; mountpoint -q /mnt/dvd || sudo mount -o ro /dev/sr0 /mnt/dvd; sudo sed -i "s/enabled=0/enabled=1/" /etc/yum.repos.d/dvd.repo; echo "  dvd repo:"; sudo yum -q --disablerepo="*" --enablerepo="dvd-*" list available compat-openssl11 >/dev/null 2>&1 && echo "  OK"'

log "copying + extracting SOAR ($TGZ_BASE)"
scp_to "$IP" "$TGZ" /var/tmp/
ssh_vm "$IP" "sudo cp /var/tmp/$TGZ_BASE /home/soar/ && sudo chown soar:soar /home/soar/$TGZ_BASE && sudo -u soar tar xzf /home/soar/$TGZ_BASE -C /home/soar"

log "running soar-prepare-system (installs OS deps from DVD)"
ssh_vm "$IP" "sudo /home/soar/splunk-soar/soar-prepare-system --splunk-soar-home /opt/phantom --splunk-soar-user soar --https-port 8443 -y --no-spinners --log-format plain 2>&1 | tail -3"

log "running soar-install (offline, with apps) — this takes a while"
# Must run from a soar-accessible CWD — phenv cd's to $PWD and can't enter labadmin's 700 home.
ssh_vm "$IP" "cd /home/soar/splunk-soar && sudo -u soar bash -c 'cd /home/soar/splunk-soar && ./soar-install --splunk-soar-home /opt/phantom --https-port 8443 --offline --with-apps --ignore-warnings -y --no-spinners --log-format plain' 2>&1 | tail -5"

log "opening firewall 8443; detaching DVD"
ssh_vm "$IP" 'sudo firewall-cmd --permanent --add-port=8443/tcp >/dev/null && sudo firewall-cmd --reload >/dev/null; sudo sed -i "s/enabled=1/enabled=0/" /etc/yum.repos.d/dvd.repo; sudo umount /mnt/dvd 2>/dev/null || true'
vmrun -T ws disconnectNamedDevice "$VMX" sata0:0 >/dev/null 2>&1 || true

log "verifying SOAR web"
ssh_vm "$IP" 'for i in $(seq 1 18); do c=$(curl -sk -o /dev/null -w "%{http_code}" https://localhost:8443); [ "$c" = "302" ] && break; sleep 5; done; echo "  web8443=$c"'
log "Splunk SOAR ready: https://$IP:8443"
