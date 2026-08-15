#!/usr/bin/env bash
# Build and unattended-install a RHEL 9 VM in VMware Workstation.
#
#   ./build-rhel-vm.sh --name siem --ip 100.65.1.10 [options]
#
# Options (defaults):
#   --name NAME            VM folder + display name (required)
#   --ip IP               static NAT IP (required)
#   --hostname HOST       (NAME.lab)
#   --ram MB              (8192)
#   --cpu N               (4)
#   --disk GB             (150)
#   --vnc-port PORT       VMware VNC console port (5901)
#   --firewall-ports STR  kickstart firewall ports (Splunk+SOAR set)
#
# Result: a booted RHEL VM reachable at IP over SSH (key auth), media detached.
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

NAME="" IP="" HOSTNAME="" RAM=8192 CPU=4 DISK=150 VNC_PORT=5901
FIREWALL_PORTS="8000:tcp,8089:tcp,8088:tcp,8191:tcp,8443:tcp"
while [[ $# -gt 0 ]]; do case "$1" in
  --name) NAME="$2"; shift 2;;
  --ip) IP="$2"; shift 2;;
  --hostname) HOSTNAME="$2"; shift 2;;
  --ram) RAM="$2"; shift 2;;
  --cpu) CPU="$2"; shift 2;;
  --disk) DISK="$2"; shift 2;;
  --vnc-port) VNC_PORT="$2"; shift 2;;
  --firewall-ports) FIREWALL_PORTS="$2"; shift 2;;
  *) die "unknown arg: $1";;
esac; done
[[ -n "$NAME" && -n "$IP" ]] || die "usage: --name NAME --ip IP [options]"
HOSTNAME="${HOSTNAME:-$NAME.lab}"

RHEL="$(require_artifact "$RHEL_ISO")"
ensure_ssh_key
VMDIR="$VM_BASE_DIR/$NAME"; VMX="$VMDIR/$NAME.vmx"
if [[ -d "$VMDIR" ]]; then
  die "VM dir already exists: $VMDIR (remove it to rebuild)"
fi
mkdir -p "$VMDIR"

log "rendering kickstart ($HOSTNAME / $IP)"
PWHASH="$(openssl passwd -6 "$LAB_PASSWORD")"
render "$VMLAB_DIR/rhel-ks.tmpl" \
  "TIMEZONE=$TIMEZONE" "IP=$IP" "NETMASK=$NETMASK" "GATEWAY=$NAT_GATEWAY" \
  "HOSTNAME=$HOSTNAME" "PWHASH=$PWHASH" "SELINUX=$SELINUX_MODE" \
  "FIREWALL_PORTS=$FIREWALL_PORTS" > "$VMDIR/ks.cfg"

log "building OEMDRV ISO"
build_oemdrv "$VMDIR/ks.cfg" "$VMDIR/oemdrv.iso"

log "creating ${DISK}GB thin disk"
vmware-vdiskmanager -c -s "${DISK}GB" -a lsisas1068 -t 0 "$VMDIR/$NAME.vmdk" >/dev/null

log "writing VMX"
cat > "$VMX" <<EOF
.encoding = "UTF-8"
config.version = "8"
virtualHW.version = "$VM_HW_VERSION"
displayName = "$NAME"
guestOS = "$VM_GUEST_OS"
annotation = "vmlab | RHEL 9 | $HOSTNAME | NAT $IP"
memsize = "$RAM"
numvcpus = "$CPU"
cpuid.coresPerSocket = "$CPU"
firmware = "bios"
bios.bootOrder = "cdrom,hdd"
bios.hddOrder = "scsi0:0"
scsi0.present = "TRUE"
scsi0.virtualDev = "lsisas1068"
scsi0:0.present = "TRUE"
scsi0:0.fileName = "$NAME.vmdk"
scsi0:0.deviceType = "scsi-hardDisk"
sata0.present = "TRUE"
sata0:0.present = "TRUE"
sata0:0.deviceType = "cdrom-image"
sata0:0.fileName = "$RHEL"
sata0:0.startConnected = "TRUE"
sata0:1.present = "TRUE"
sata0:1.deviceType = "cdrom-image"
sata0:1.fileName = "$VMDIR/oemdrv.iso"
sata0:1.startConnected = "TRUE"
ethernet0.present = "TRUE"
ethernet0.connectionType = "nat"
ethernet0.virtualDev = "e1000e"
ethernet0.addressType = "generated"
ethernet0.startConnected = "TRUE"
usb.present = "TRUE"
usb_xhci.present = "TRUE"
vmci0.present = "TRUE"
svga.present = "TRUE"
svga.autodetect = "TRUE"
pciBridge0.present = "TRUE"
pciBridge4.present = "TRUE"
pciBridge4.virtualDev = "pcieRootPort"
pciBridge4.functions = "8"
pciBridge5.present = "TRUE"
pciBridge5.virtualDev = "pcieRootPort"
pciBridge5.functions = "8"
pciBridge6.present = "TRUE"
pciBridge6.virtualDev = "pcieRootPort"
pciBridge6.functions = "8"
pciBridge7.present = "TRUE"
pciBridge7.virtualDev = "pcieRootPort"
pciBridge7.functions = "8"
tools.syncTime = "TRUE"
msg.autoAnswer = "TRUE"
RemoteDisplay.vnc.enabled = "TRUE"
RemoteDisplay.vnc.port = "$VNC_PORT"
EOF

log "starting install (headless). VNC console: localhost:$VNC_PORT"
vmrun -T ws start "$VMX" nogui
# Best-effort: press Up+Enter at the boot menu to skip the DVD media check.
# If vncdo is absent, the menu auto-boots (with media check) after its timeout.
if command -v vncdo >/dev/null 2>&1; then
  ( sleep 8; vncdo -s "localhost::$VNC_PORT" key up pause 0.5 key enter >/dev/null 2>&1 ) &
fi
log "waiting for unattended install to finish (auto power-off)…"
wait_poweroff "$VMX"
log "install complete; detaching media, booting from disk"

sed -i \
  -e 's|^bios.bootOrder = "cdrom,hdd"|bios.bootOrder = "hdd,cdrom"|' \
  "$VMX"
# disconnect both CD-ROMs (keep RHEL DVD filename for later repo re-attach)
awk '/rhel-9|dvd\.iso|oemdrv\.iso/{f=1} f&&/startConnected = "TRUE"/{sub("TRUE","FALSE");f=0} {print}' \
  "$VMX" > "$VMX.tmp" && mv "$VMX.tmp" "$VMX"

vmrun -T ws start "$VMX" nogui
wait_ssh "$IP"
log "seeding SSH key"
seed_ssh_key "$IP" || die "failed to seed ssh key"
ssh_vm "$IP" 'echo "  guest: $(cat /etc/redhat-release) | selinux=$(getenforce)"'
log "VM '$NAME' ready at $IP (ssh labadmin@$IP with $LAB_SSH_KEY)"
