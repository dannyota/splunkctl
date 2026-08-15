#!/usr/bin/env bash
# vmlab shared library — sourced by the build/install scripts. Not executed directly.

VMLAB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
: "${INSTALLERS_DIR:=$(cd "$VMLAB_DIR/.." && pwd)}"
# shellcheck source=/dev/null
# Local (gitignored) overrides first, so config.env's defaults only fill gaps.
[ -f "$VMLAB_DIR/config.local.env" ] && source "$VMLAB_DIR/config.local.env"
source "$VMLAB_DIR/config.env"

log()  { printf '\033[1;34m[vmlab]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[vmlab] WARN:\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m[vmlab] ERROR:\033[0m %s\n' "$*" >&2; exit 1; }

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "required command not found: $1"
}

# Verify a required installer artifact exists in installers/.
require_artifact() {
  local f="$INSTALLERS_DIR/$1"
  [[ -f "$f" ]] || die "missing installer artifact: $f"
  printf '%s' "$f"
}

# Ensure the reusable lab SSH key exists.
ensure_ssh_key() {
  [[ -f "$LAB_SSH_KEY" ]] && return 0
  mkdir -p "$(dirname "$LAB_SSH_KEY")"
  ssh-keygen -t ed25519 -N '' -f "$LAB_SSH_KEY" -C 'vmlab' >/dev/null
  log "generated lab SSH key: $LAB_SSH_KEY"
}

_ssh_opts=(-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null
           -o ConnectTimeout=10 -o LogLevel=ERROR)

ssh_vm()  { ssh -i "$LAB_SSH_KEY" "${_ssh_opts[@]}" "labadmin@$1" "${@:2}"; }
scp_vm()  { scp -i "$LAB_SSH_KEY" "${_ssh_opts[@]}" "${@:2}" "labadmin@$1:${!#}"; }
scp_to()  { scp -i "$LAB_SSH_KEY" "${_ssh_opts[@]}" "$2" "labadmin@$1:$3"; }

# Install the lab pubkey onto a freshly-installed VM using password auth (headless).
seed_ssh_key() {
  local ip="$1" askpass; askpass="$(mktemp)"
  printf '#!/bin/sh\necho "%s"\n' "$LAB_PASSWORD" > "$askpass"; chmod +x "$askpass"
  SSH_ASKPASS="$askpass" SSH_ASKPASS_REQUIRE=force setsid -w \
    ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10 \
    "labadmin@$ip" "install -d -m700 ~/.ssh && echo '$(cat "$LAB_SSH_KEY.pub")' >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys" \
    >/dev/null 2>&1
  local rc=$?; rm -f "$askpass"; return $rc
}

# Build an OEMDRV-labelled ISO containing ks.cfg (Anaconda auto-loads it).
build_oemdrv() {
  local ks="$1" out="$2" root; root="$(mktemp -d)"
  cp "$ks" "$root/ks.cfg"
  rm -f "$out"
  xorriso -as mkisofs -V OEMDRV -J -R -o "$out" "$root" >/dev/null 2>&1 || die "OEMDRV build failed"
  rm -rf "$root"
}

vm_running() { vmrun list | grep -qF "$1"; }

vmx_path() {
  local name="$1"
  printf '%s' "$VM_BASE_DIR/$name/$name.vmx"
}

ensure_vm_running() {
  local name="$1" vmx
  vmx="$(vmx_path "$name")"
  [[ -f "$vmx" ]] || die "VMX not found: $vmx"
  if vm_running "$vmx"; then
    log "$name VM is already running"
    return 0
  fi
  log "starting existing $name VM"
  vmrun -T ws start "$vmx" nogui >/dev/null
}

wait_http() {
  local url="$1" expected="$2" limit="$3" start code
  start="$(date +%s)"
  while true; do
    code="$(curl -sk -o /dev/null -w '%{http_code}' "$url" || true)"
    [[ "$code" == "$expected" ]] && return 0
    (( $(date +%s) - start >= limit )) &&
      die "timeout waiting for HTTP $expected from $url (last: $code)"
    sleep 4
  done
}

require_sse_lab_index() {
  [[ "$SSE_INDEX" == "sse_lab" ]] ||
    die "refusing cleanup outside sse_lab (configured: $SSE_INDEX)"
}

splunk_is_ready() {
  ssh_vm "$1" 'sudo -u splunk /opt/splunk/bin/splunk status >/dev/null 2>&1' \
    >/dev/null 2>&1
}

soar_is_ready() {
  ssh_vm "$1" 'test -x /opt/phantom/bin/phsvc && code=$(curl -sk -o /dev/null -w "%{http_code}" https://localhost:8443); [[ "$code" == 200 || "$code" == 302 ]]' \
    >/dev/null 2>&1
}

# Poll until a VM powers itself off (kickstart 'poweroff'), or timeout (seconds).
wait_poweroff() {
  local vmx="$1" limit="${2:-2400}" start; start=$(date +%s)
  while vm_running "$vmx"; do
    (( $(date +%s) - start >= limit )) && die "timeout waiting for install poweroff"
    sleep 20
  done
}

# Poll until sshd answers on the VM (seconds timeout).
wait_ssh() {
  local ip="$1" limit="${2:-180}" start; start=$(date +%s)
  until nc -z -w2 "$ip" 22 2>/dev/null; do
    (( $(date +%s) - start >= limit )) && die "timeout waiting for ssh on $ip"
    sleep 4
  done
}

# Render a template: replace @@KEY@@ tokens from the given key=value pairs.
render() {
  local tmpl="$1"; shift
  local out; out="$(cat "$tmpl")"
  local pair k v
  for pair in "$@"; do k="${pair%%=*}"; v="${pair#*=}"; out="${out//@@${k}@@/$v}"; done
  printf '%s\n' "$out"
}
