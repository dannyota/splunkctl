#!/usr/bin/env bash
# Verify product, authentication, SSE, HEC, and prepared-data postconditions.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$HERE/lib.sh"

usage() {
  printf 'Usage: %s [--only siem|soar|both] [--skip-data]\n' "${0##*/}"
}

ONLY=both
SKIP_DATA=no
while [[ $# -gt 0 ]]; do
  case "$1" in
    --only)
      [[ $# -ge 2 ]] || die "--only requires siem, soar, or both"
      ONLY="$2"
      shift 2
      ;;
    --skip-data)
      SKIP_DATA=yes
      shift
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

require_running_vm() {
  local name="$1" ip="$2" vmx
  vmx="$(vmx_path "$name")"
  [[ -f "$vmx" ]] || die "$name VMX not found: $vmx"
  vm_running "$vmx" || die "$name VM is not running"
  ssh_vm "$ip" true >/dev/null || die "$name SSH failed at $ip"
}

authenticated_curl() {
  local host="$1" user="$2" password="$3"
  shift 3
  local netrc result rc=0
  netrc="$(mktemp)"
  chmod 600 "$netrc"
  printf 'machine %s login %s password %s\n' "$host" "$user" "$password" > "$netrc"
  result="$(curl --netrc-file "$netrc" --insecure --silent --show-error \
    --fail-with-body "$@")" || rc=$?
  rm -f "$netrc"
  printf '%s' "$result"
  return "$rc"
}

splunk_search() {
  authenticated_curl "$SIEM_IP" admin "$SPLUNK_ADMIN_PASSWORD" \
    -X POST "https://$SIEM_IP:8089/services/search/jobs/export" \
    --data-urlencode "search=search $1" \
    --data-urlencode 'output_mode=json' \
    --data-urlencode 'earliest_time=0' \
    --data-urlencode 'latest_time=+1d'
}

verify_siem_data() {
  local manifest="$SSE_DATA_DIR/manifest.json" values import_id expected datasets anchor
  [[ -f "$manifest" ]] || die "SSE data manifest not found: $manifest"
  values="$(python3 - "$manifest" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as stream:
    manifest = json.load(stream)
print(manifest["import_id"])
print(manifest["event_count"])
print(manifest["dataset_count"])
print(manifest["anchor"])
PY
)"
  mapfile -t manifest_values <<< "$values"
  import_id="${manifest_values[0]}"
  expected="${manifest_values[1]}"
  datasets="${manifest_values[2]}"
  anchor="${manifest_values[3]}"
  [[ "$datasets" == 43 ]] || die "manifest dataset count is $datasets, expected 43"

  summary="$(splunk_search "index=$SSE_INDEX lab_import_id=\"$import_id\" | stats count dc(lab_dataset) as datasets earliest(_time) as earliest latest(_time) as latest" |
    python3 -c 'import json,sys
for line in sys.stdin:
 record=json.loads(line); result=record.get("result")
 if result and not record.get("preview", False):
  print("\t".join(result.get(k, "0") for k in ("count","datasets","earliest","latest")))')"
  IFS=$'\t' read -r actual actual_datasets earliest latest <<< "$summary"
  [[ "$actual" == "$expected" ]] ||
    die "SSE event count mismatch: expected $expected, got ${actual:-0}"
  [[ "$actual_datasets" == "$datasets" ]] ||
    die "SSE dataset coverage mismatch: expected $datasets, got ${actual_datasets:-0}"
  python3 - "$anchor" "$latest" <<'PY'
import sys
from datetime import datetime

anchor = datetime.fromisoformat(sys.argv[1].replace("Z", "+00:00")).timestamp()
latest = float(sys.argv[2])
if abs(anchor - latest) > 0.01:
    raise SystemExit(f"latest event {latest} does not match anchor {anchor}")
PY
  log "SSE data: $actual events across $actual_datasets datasets; range=$earliest..$latest"
}

verify_siem() {
  local expected version app_version code
  require_running_vm siem "$SIEM_IP"
  expected="${SPLUNK_RPM#splunk-}"
  expected="${expected%.rpm}"
  version="$(ssh_vm "$SIEM_IP" \
    "rpm -q --qf '%{VERSION}-%{RELEASE}.%{ARCH}' splunk")"
  [[ "$version" == "$expected" ]] ||
    die "Splunk version mismatch: expected $expected, got $version"
  splunk_is_ready "$SIEM_IP" || die "Splunk service is not ready"
  code="$(curl -s -o /dev/null -w '%{http_code}' "http://$SIEM_IP:8000")"
  [[ "$code" == 303 ]] || die "Splunk web returned HTTP $code"
  authenticated_curl "$SIEM_IP" admin "$SPLUNK_ADMIN_PASSWORD" \
    "https://$SIEM_IP:8089/services/server/info?output_mode=json" >/dev/null

  app_version="$(ssh_vm "$SIEM_IP" "sudo sed -n '/^\\[launcher\\]/,/^\\[/ {
    s/^[[:space:]]*version[[:space:]]*=[[:space:]]*//p
  }' /opt/splunk/etc/apps/Splunk_Security_Essentials/default/app.conf | head -1 | tr -d '[:space:]'")"
  [[ "$app_version" == 3.8.3 ]] ||
    die "SSE version mismatch: expected 3.8.3, got $app_version"
  log "SIEM: Splunk $version; SSE $app_version; authentication OK"

  if [[ "$SKIP_DATA" == no ]]; then
    code="$(curl -sk -o /dev/null -w '%{http_code}' \
      "https://$SIEM_IP:8088/services/collector/health")"
    [[ "$code" == 200 ]] || die "HEC health returned HTTP $code"
    verify_siem_data
  fi
}

verify_soar() {
  local version response code
  require_running_vm soar "$SOAR_IP"
  version="$(ssh_vm "$SOAR_IP" "cd /tmp && sudo -u soar /opt/phantom/bin/phenv python -c \
    'import sys; sys.path.insert(0, \"/opt/phantom/www\"); \
from phantom_ui.product_version import PRODUCT_VERSION; print(PRODUCT_VERSION)'")"
  [[ "$version" == 8.6.0.530 ]] ||
    die "SOAR version mismatch: expected 8.6.0.530, got $version"
  response="$(authenticated_curl "$SOAR_IP" soar_local_admin "$LAB_PASSWORD" \
    "https://$SOAR_IP:8443/rest/version")"
  python3 - "$response" <<'PY'
import json
import sys

if json.loads(sys.argv[1]).get("version") != "8.6.0.530":
    raise SystemExit("SOAR authenticated version response is invalid")
PY
  code="$(curl -sk -o /dev/null -w '%{http_code}' "https://$SOAR_IP:8443")"
  [[ "$code" == 200 || "$code" == 302 ]] || die "SOAR web returned HTTP $code"
  log "SOAR: $version; authentication OK"
}

if [[ "$ONLY" == siem || "$ONLY" == both ]]; then
  verify_siem
fi
if [[ "$ONLY" == soar || "$ONLY" == both ]]; then
  verify_soar
fi
log "lab verification passed"
