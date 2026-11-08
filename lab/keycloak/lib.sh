#!/usr/bin/env bash
# Keycloak lab shared library — sourced by labctl.sh. Not executed directly.

LAB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Local (gitignored) secrets first, so .env.example's defaults only fill gaps.
# shellcheck source=/dev/null
[ -f "$LAB_DIR/.env" ] && source "$LAB_DIR/.env"
source "$LAB_DIR/.env.example"

# Used by scripts that source this library.
# shellcheck disable=SC2034
KC_URL="http://${KEYCLOAK_HOST}:${KEYCLOAK_PORT}"

log()  { printf '\033[1;34m[keycloak]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[keycloak] WARN:\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m[keycloak] ERROR:\033[0m %s\n' "$*" >&2; exit 1; }

require_podman() {
  command -v podman >/dev/null 2>&1 || die "required command not found: podman"
}

# Render JSON templates whose @@KEY@@ tokens occur inside JSON strings.
render() {
  python3 - "$@" <<'PYTHON'
import json
from pathlib import Path
import re
import sys

values = dict(pair.split("=", 1) for pair in sys.argv[2:])
text = Path(sys.argv[1]).read_text()
text = re.sub(
    r"@@([^@]+)@@",
    lambda match: json.dumps(values[match[1]])[1:-1],
    text,
)
json.loads(text)
print(text, end="" if text.endswith("\n") else "\n")
PYTHON
}
