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
  wait_http "$KC_URL/health/ready" "200" 180
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
  code="$(curl -s -o /dev/null -w '%{http_code}' "$KC_URL/health/ready" 2>/dev/null || true)"
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

case "$1" in
  start)    do_start ;;
  stop)     do_stop ;;
  status)   do_status ;;
  configure) do_configure ;;
  verify)   do_verify ;;
  *) printf 'usage: %s <start|stop|status|configure|verify>\n' "$0" >&2; exit 2 ;;
esac
