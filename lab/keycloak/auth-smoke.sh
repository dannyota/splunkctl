#!/usr/bin/env bash
# Browser SAML smoke for the Keycloak lab: auth login, status and logout for
# SIEM and SOAR, with e2e-login.py filling only the Keycloak form. Run from the
# repository root inside the dev environment with the browser extra:
#   uv sync --extra dev --extra browser && uv run bash lab/keycloak/auth-smoke.sh
# Needs a configured lab: labctl.sh start/configure, siem-configure.sh and
# soar-configure.sh. Set E2E_HEADLESS=1 on hosts without a display.
set -uo pipefail
LAB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$LAB_DIR/lib.sh"
S="${SPLUNKCTL:-splunkctl}"
PY="${LIVE_PYTHON:-python3}"
T="$(mktemp -d "${TMPDIR:-/tmp}/sc-auth-smoke.XXXXXX")" || exit 1
# shellcheck disable=SC2034  # used by the shared library
N="sc_live_auth_$$"
fail=0
: > "$T/cleanup.sh"
# shellcheck source=../../scripts/live-smoke-lib.sh
. "$LAB_DIR/../../scripts/live-smoke-lib.sh"
[ -n "${TEST_USER_PASSWORD:-}" ] || { bad 'TEST_USER_PASSWORD is not set in lab/keycloak/.env'; exit 1; }
unset KEYCLOAK_ADMIN_PASSWORD POSTGRES_PASSWORD
export TEST_USER TEST_USER_PASSWORD KEYCLOAK_HOST KEYCLOAK_PORT
# Keep the lab addresses first: the loop below also clears exported
# SOAR_HOST and SOAR_PORT.
soar_host=${SOAR_HOST:?} soar_port=${SOAR_PORT:?}
# Only the browser session may authenticate: drop basic-auth overrides.
for v in $(env | grep -oE '^(SPLUNK|SOAR)_[A-Z_]*'); do unset "$v"; done
IDP="http://${KEYCLOAK_HOST}:${KEYCLOAK_PORT}/realms/${REALM}"
SOAR_WEB="https://${soar_host}:${soar_port}"
SSO_URL="$SOAR_WEB/saml2/login?idp=$("$PY" -c 'import sys, urllib.parse; print(urllib.parse.quote(sys.argv[1], safe=""))' "$IDP")&next=%2F"
CFG="$T/config.yaml"
cat > "$CFG" <<EOF
profiles:
  lab-auth-smoke:
    host: $SIEM_HOST
    port: 8089
    scheme: https
    verify: false
    web_url: http://$SIEM_HOST:$SIEM_WEB_PORT
    auth_mode: browser
    soar:
      host: $soar_host
      port: $soar_port
      verify: false
      auth_mode: browser
      web_url: $SOAR_WEB
      sso_url: "$SSO_URL"
current: lab-auth-smoke
EOF
logout_target() { "$S" --config "$CFG" auth logout --target "$1"; }
for target in siem soar; do
    step "auth $target"
    # A failed run must not leave a stored session behind.
    defer logout_target "$target"
    if run "$PY" "$LAB_DIR/e2e-login.py" --config "$CFG" auth login --target "$target"; then
        check_json "d==[{'target': '$target', 'status': 'valid'}]" --config "$CFG" auth status --target "$target"
        case "$target" in
            siem) check_json 'len(d)>=1' --config "$CFG" info;;
            soar) check_json 'len(d)>=1' --config "$CFG" soar info;;
        esac
        expect_ok "$S" --config "$CFG" auth logout --target "$target"
        check_json "d==[{'target': '$target', 'status': 'missing'}]" --config "$CFG" auth status --target "$target"
    else bad "auth login --target $target"; fi
done
