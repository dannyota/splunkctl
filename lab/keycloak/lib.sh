#!/usr/bin/env bash
# Keycloak lab shared library — sourced by labctl.sh. Not executed directly.

LAB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Local (gitignored) secrets first, so .env.example's defaults only fill gaps.
[ -f "$LAB_DIR/.env" ] && source "$LAB_DIR/.env"
source "$LAB_DIR/.env.example"

KC_URL="http://${KEYCLOAK_HOST}:${KEYCLOAK_PORT}"

log()  { printf '\033[1;34m[keycloak]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[keycloak] WARN:\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m[keycloak] ERROR:\033[0m %s\n' "$*" >&2; exit 1; }

require_podman() {
  command -v podman >/dev/null 2>&1 || die "required command not found: podman"
}

# Render a template: replace @@KEY@@ tokens from the given key=value pairs.
render() {
  local tmpl="$1"; shift
  local out; out="$(cat "$tmpl")"
  local pair k v
  for pair in "$@"; do k="${pair%%=*}"; v="${pair#*=}"; out="${out//@@${k}@@/$v}"; done
  printf '%s\n' "$out"
}
