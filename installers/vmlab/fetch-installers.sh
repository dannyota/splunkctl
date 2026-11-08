#!/usr/bin/env bash
# Fetch public installers and verify every selected artifact.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$HERE/lib.sh"

usage() {
  printf 'Usage: %s [--only siem|soar|both] [--check]\n' "${0##*/}"
}

ONLY=both
CHECK=no
while [[ $# -gt 0 ]]; do
  case "$1" in
    --only)
      [[ $# -ge 2 ]] || die "--only requires siem, soar, or both"
      ONLY="$2"
      shift 2
      ;;
    --check) CHECK=yes; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown argument: $1" ;;
  esac
done
case "$ONLY" in
  siem|soar|both) ;;
  *) die "--only must be siem, soar, or both" ;;
esac

verify_checksum() {
  local file="$1" algorithm="$2" expected="$3" actual
  if command -v "sha${algorithm}sum" >/dev/null 2>&1; then
    actual="$("sha${algorithm}sum" "$file")" || return 1
  else
    require_command shasum
    actual="$(shasum -a "$algorithm" "$file")" || return 1
  fi
  [[ "${actual%% *}" == "$expected" ]]
}

tmp=''
cleanup() {
  [[ -z "$tmp" ]] || rm -f "$tmp"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

ok=0
failed=0
fetch_artifact() {
  local name="$1" algorithm="$2" checksum="$3" url="$4" guidance="$5"
  local dest="$INSTALLERS_DIR/$name"
  if [[ -e "$dest" || -L "$dest" ]]; then
    if [[ -f "$dest" ]] && verify_checksum "$dest" "$algorithm" "$checksum"; then
      log "OK: $name"
      ok=$((ok + 1))
      return
    fi
    warn "checksum mismatch: $dest (left unchanged)"
  elif [[ -z "$url" ]]; then
    warn "missing $name: $guidance; save it in $INSTALLERS_DIR"
  elif [[ "$CHECK" == yes ]]; then
    warn "missing $name (--check never downloads)"
  else
    require_command curl
    mkdir -p "$INSTALLERS_DIR"
    tmp="$(mktemp "$INSTALLERS_DIR/.$name.XXXXXX")"
    log "downloading $name"
    if ! curl -fL "$url" -o "$tmp"; then
      rm -f "$tmp"
      warn "download failed: $name"
    elif ! verify_checksum "$tmp" "$algorithm" "$checksum"; then
      rm -f "$tmp"
      warn "checksum mismatch: $name (download removed)"
    elif ! ln "$tmp" "$dest" 2>/dev/null; then
      rm -f "$tmp"
      warn "destination appeared during download (left unchanged): $dest"
    else
      rm -f "$tmp"
      log "OK: $name"
      ok=$((ok + 1))
      tmp=''
      return
    fi
    tmp=''
  fi
  failed=$((failed + 1))
}

fetch_artifact "$RHEL_ISO" 256 "$RHEL_ISO_SHA256" '' \
  'download RHEL 9.8 DVD from Red Hat with a Red Hat Developer Subscription (https://developers.redhat.com/products/rhel/download)'
if [[ "$ONLY" == siem || "$ONLY" == both ]]; then
  fetch_artifact "$SPLUNK_RPM" 512 "$SPLUNK_RPM_SHA512" "$SPLUNK_RPM_URL" ''
  fetch_artifact "$SSE_TGZ" 256 "$SSE_TGZ_SHA256" '' \
    'download Splunkbase app 3435 release 3.8.3 (login required, https://splunkbase.splunk.com/app/3435)'
fi
if [[ "$ONLY" == soar || "$ONLY" == both ]]; then
  fetch_artifact "$SOAR_TGZ" 512 "$SOAR_TGZ_SHA512" "$SOAR_TGZ_URL" ''
fi
log "Summary: $ok OK, $failed missing or failed"
[[ "$failed" == 0 ]]
