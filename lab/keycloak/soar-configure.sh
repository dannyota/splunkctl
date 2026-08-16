#!/usr/bin/env bash
# Configure Splunk SOAR SAML SSO against the Keycloak realm.
#
# SOAR stores its SAML config in the Django `SystemSettings.auth` JSON field,
# not a config file. This script builds that JSON (with the Keycloak IdP
# metadata inlined), copies it to the SOAR VM, and writes it over SSH.
# Idempotent: re-running overwrites the same single-row setting.
#
# Usage: ./soar-configure.sh

set -euo pipefail

LAB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$LAB_DIR/lib.sh"

: "${SSH_KEY:=$HOME/vmware/.vmlab_key}"
: "${SOAR_HOST:=100.65.1.11}"
: "${SOAR_PORT:=8443}"
# The SOAR SP entity ID must match the Keycloak `splunk-soar` client ID; the
# Keycloak client keeps its default entity ID (client ID), so keep these in
# sync. 1 = Administrator (SOAR role ID).
: "${SOAR_ENTITY_ID:=splunk-soar}"
: "${SOAR_ROLE_ID:=1}"

IDP_ENTITY_ID="http://${KEYCLOAK_HOST}:${KEYCLOAK_PORT}/realms/${REALM}"
IDP_SSO_URL="${IDP_ENTITY_ID}/protocol/saml"
IDP_METADATA_URL="${IDP_ENTITY_ID}/protocol/saml/descriptor"
SOAR_BASE_URL="https://${SOAR_HOST}:${SOAR_PORT}"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

log "fetching Keycloak IdP metadata from ${IDP_METADATA_URL}"
curl -sS "$IDP_METADATA_URL" > "$tmp/idp-metadata.xml"
[ -s "$tmp/idp-metadata.xml" ] || die "IdP metadata is empty"

log "building SOAR auth config"
IDP_ENTITY_ID="$IDP_ENTITY_ID" IDP_SSO_URL="$IDP_SSO_URL" \
SOAR_BASE_URL="$SOAR_BASE_URL" SOAR_ENTITY_ID="$SOAR_ENTITY_ID" \
SOAR_ROLE_ID="$SOAR_ROLE_ID" \
python3 - "$tmp/idp-metadata.xml" "$tmp/soar_auth.json" <<'PY'
import json
import os
import sys

metadata_xml = open(sys.argv[1], encoding="utf-8").read().strip()
out_path = sys.argv[2]

auth = {
    "saml2": {
        "enabled": True,
        "providers": [
            {
                "name": "keycloak",
                "id": "keycloak",
                "enabled": True,
                "issuer_id": os.environ["IDP_ENTITY_ID"],
                "phantom_base_url": os.environ["SOAR_BASE_URL"],
                "entityid": os.environ["SOAR_ENTITY_ID"],
                "single_sign_on_url": os.environ["IDP_SSO_URL"],
                "metadata_xml": metadata_xml,
                "sig_cert_file": "/opt/phantom/keystore/public_sig_saml2.pem",
                "sig_key_file": "/opt/phantom/keystore/private_sig_saml2.pem",
                "enc_cert_file": "/opt/phantom/keystore/public_enc_saml2.pem",
                "enc_key_file": "/opt/phantom/keystore/private_enc_saml2.pem",
                "user_attr_map": [{"external_attr": "email", "django_attr": "email"}],
                "group_key": "Role",
                "group_delimiter": ";",
                "group_role_mappings": [
                    {"group": "splunk-admin", "role": int(os.environ["SOAR_ROLE_ID"])},
                    {"group": "soar-admin", "role": int(os.environ["SOAR_ROLE_ID"])},
                ],
                "create_unknown_user": True,
                "want_response_signed": False,
                "want_assertions_signed": False,
                "authn_requests_signed": False,
                "allow_unknown_attributes": True,
                "allow_unsolicited": False,
            }
        ],
    },
    "ldap": {"enabled": False, "providers": []},
}
json.dump(auth, open(out_path, "w", encoding="utf-8"))
PY

log "copying config to SOAR (${SOAR_HOST})"
scp -i "$SSH_KEY" -o StrictHostKeyChecking=accept-new \
    "$tmp/soar_auth.json" "labadmin@${SOAR_HOST}:/tmp/soar_auth.json" >/dev/null

log "writing SOAR SAML config"
ssh -i "$SSH_KEY" -o StrictHostKeyChecking=accept-new "labadmin@${SOAR_HOST}" bash -s <<'EOF'
set -e
sudo -n chmod 644 /tmp/soar_auth.json
cd /opt/phantom
sudo -n -u soar /opt/phantom/bin/phenv python /opt/phantom/www/manage.py shell -c 'import json; from django.apps import apps; s=apps.get_model("ui","SystemSettings").objects.get(id=1); s.auth=json.load(open("/tmp/soar_auth.json")); s.save(); print("SOAR SAML config written")'
EOF

log "verifying SOAR SAML metadata"
body="$(curl -skG --max-time 10 "${SOAR_BASE_URL}/saml2/metadata/" \
    --data-urlencode "idp=${IDP_ENTITY_ID}")"
printf '%s' "$body" | grep -q "entityID=\"${SOAR_ENTITY_ID}\"" \
    || die "SOAR SAML metadata check failed"
log "SOAR SAML is configured (entity id ${SOAR_ENTITY_ID})"
