#!/usr/bin/env bash
# Keycloak lab control — start, stop, status, configure, verify.
# Usage: ./labctl.sh <start|stop|status|configure|verify>

LAB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$LAB_DIR/lib.sh"

compose_cmd() {
  if podman compose version >/dev/null 2>&1; then
    printf 'podman compose -f %s --env-file %s' "$LAB_DIR/compose.yaml" "$LAB_DIR/.env"
  else
    printf 'podman-compose -f %s --env-file %s' "$LAB_DIR/compose.yaml" "$LAB_DIR/.env"
  fi
}

do_start() {
  require_podman
  [ -f "$LAB_DIR/.env" ] || die "missing $LAB_DIR/.env (copy .env.example and fill secrets)"
  log "starting Keycloak at $KC_URL"
  # shellcheck disable=SC2046
  $(compose_cmd) up -d
  log "waiting for Keycloak health..."
  wait_http "$KC_URL/realms/master" "200" 180
  log "Keycloak is ready"
}

do_stop() {
  require_podman
  log "stopping Keycloak"
  # shellcheck disable=SC2046
  $(compose_cmd) down
}

do_status() {
  require_podman
  local code
  code="$(curl -s -o /dev/null -w '%{http_code}' "$KC_URL/realms/master" 2>/dev/null || true)"
  if [ "$code" == "200" ]; then
    log "Keycloak is running at $KC_URL"
    # shellcheck disable=SC2046
    $(compose_cmd) ps
  else
    log "Keycloak is not running (last health status: ${code:-none})"
  fi
}

wait_http() {
  local url="$1" expected="$2" limit="$3" start code
  start="$(date +%s)"
  while true; do
    code="$(curl -s -o /dev/null -w '%{http_code}' "$url" 2>/dev/null || true)"
    [ "$code" == "$expected" ] && return 0
    (( $(date +%s) - start >= limit )) && die "timeout waiting for HTTP $expected from $url (last: $code)"
    sleep 4
  done
}

admin_token() {
  local resp token
  resp="$(curl -s -X POST "$KC_URL/realms/master/protocol/openid-connect/token" \
    -H 'Content-Type: application/x-www-form-urlencoded' \
    -d "client_id=admin-cli&username=${KEYCLOAK_ADMIN}&password=${KEYCLOAK_ADMIN_PASSWORD}&grant_type=password")"
  token="$(printf '%s' "$resp" | grep -o '"access_token":"[^"]*"' | sed 's/.*:"//; s/"$//')"
  [ -n "$token" ] || die "could not obtain a Keycloak admin token (is the admin password correct?)"
  printf '%s' "$token"
}

do_configure() {
  require_podman
  [ -n "${KEYCLOAK_ADMIN_PASSWORD:-}" ] || die "missing KEYCLOAK_ADMIN_PASSWORD (copy .env.example to .env and fill secrets)"
  mkdir -p "$LAB_DIR/.runtime"
  local out="$LAB_DIR/.runtime/${REALM}-realm.json" token
  render "$LAB_DIR/realm-template.json" \
    "REALM=$REALM" \
    "SIEM_ACS=$SIEM_ACS" "SOAR_ACS=$SOAR_ACS" \
    "TEST_USER=$TEST_USER" "TEST_USER_PASSWORD=$TEST_USER_PASSWORD" > "$out"
  log "importing realm '$REALM'"
  token="$(admin_token)"
  code="$(curl -s -o /dev/null -w '%{http_code}' -X POST "$KC_URL/admin/realms" \
    -H "Authorization: Bearer $token" -H 'Content-Type: application/json' \
    --data-binary "@$out")"
  # 201 created, 409 already exists (idempotent) — anything else is an error.
  case "$code" in
    201) log "realm '$REALM' created" ;;
    409) log "realm '$REALM' already exists (skipping import)" ;;
    *)  die "realm import failed (HTTP $code)" ;;
  esac
}

do_verify() {
  require_podman
  local code
  code="$(curl -s -o /dev/null -w '%{http_code}' "$KC_URL/realms/master" 2>/dev/null || true)"
  [ "$code" == "200" ] || die "Keycloak health check failed (HTTP ${code:-none})"
  local token clients
  token="$(admin_token)"
  clients="$(curl -s "$KC_URL/admin/realms/$REALM/clients" -H "Authorization: Bearer $token")"
  printf '%s' "$clients" | grep -q '"clientId":"splunk-siem"' \
    || die "realm '$REALM' is missing the splunk-siem SAML client"
  printf '%s' "$clients" | grep -q '"clientId":"splunk-soar"' \
    || die "realm '$REALM' is missing the splunk-soar SAML client"
  log "Keycloak realm '$REALM' is configured with both SAML clients"
}

case "$1" in
  start)    do_start ;;
  stop)     do_stop ;;
  status)   do_status ;;
  configure) do_configure ;;
  verify)   do_verify ;;
  *) printf 'usage: %s <start|stop|status|configure|verify>\n' "$0" >&2; exit 2 ;;
esac
