#!/usr/bin/env bash
# Configure Splunk Enterprise SAML against the Keycloak realm. Safe to rerun.
set -euo pipefail

LAB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$LAB_DIR/lib.sh"

: "${VM_BASE_DIR:=$HOME/vmware}"
: "${SSH_KEY:=$VM_BASE_DIR/.vmlab_key}"
: "${SPLUNK_HOME:=/opt/splunk}"
: "${SIEM_WEB_SCHEME:=http}"

# REALM becomes part of a filename as well as a URL.
[[ "$REALM" =~ ^[a-zA-Z0-9_-]+$ ]] || die "invalid realm name"
IDP_ENTITY_ID="http://${KEYCLOAK_HOST}:${KEYCLOAK_PORT}/realms/${REALM}"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

curl -fsS --max-time 30 "${IDP_ENTITY_ID}/protocol/saml/descriptor" > "$tmp/descriptor.xml"
IDP_ENTITY_ID="$IDP_ENTITY_ID" SIEM_HOST="$SIEM_HOST" \
SIEM_WEB_PORT="$SIEM_WEB_PORT" SIEM_WEB_SCHEME="$SIEM_WEB_SCHEME" REALM="$REALM" \
python3 - "$tmp" <<'PY'
import os
import sys
import textwrap
import xml.etree.ElementTree as ET
from pathlib import Path

out = Path(sys.argv[1])
certs = ET.parse(out / "descriptor.xml").findall(
    ".//{http://www.w3.org/2000/09/xmldsig#}X509Certificate"
)
if len(certs) != 1:
    sys.exit("IdP metadata must contain exactly one ds:X509Certificate")
cert = "".join("".join(certs[0].itertext()).split())
if not cert:
    sys.exit("IdP certificate is empty")
name = f"keycloak-{os.environ['REALM']}.pem"
(out / name).write_text(
    "-----BEGIN CERTIFICATE-----\n"
    + "\n".join(textwrap.wrap(cert, 64))
    + "\n-----END CERTIFICATE-----\n"
)
idp = os.environ["IDP_ENTITY_ID"]
(out / "authentication.conf").write_text(f"""[authentication]
authType = SAML
authSettings = saml

[roleMap_SAML]
admin = splunk-admin

[authenticationResponseAttrMap_SAML]
role = Role

[saml]
allowPartialSignatures = false
entityId = splunk-siem
fqdn = {os.environ['SIEM_WEB_SCHEME']}://{os.environ['SIEM_HOST']}
idpCertPath = {name}
idpSSOUrl = {idp}/protocol/saml
inboundSignatureAlgorithm = RSA-SHA256;RSA-SHA384;RSA-SHA512
issuerId = {idp}
nameIdFormat = urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress
redirectPort = {os.environ['SIEM_WEB_PORT']}
replicateCertificates = false
signAuthnRequest = false
signedAssertion = true
ssoBinding = HTTPPost
""")
PY

# Unique staging names avoid collisions between runs.
staging="/tmp/splunkctl-siem-$(basename "$tmp")"
scp -i "$SSH_KEY" -o StrictHostKeyChecking=accept-new \
    "$tmp/authentication.conf" "labadmin@${SIEM_HOST}:${staging}.conf" >/dev/null
scp -i "$SSH_KEY" -o StrictHostKeyChecking=accept-new \
    "$tmp/keycloak-${REALM}.pem" "labadmin@${SIEM_HOST}:${staging}.pem" >/dev/null
printf -v remote_cmd 'sudo -n bash -s -- %q %q %q' "$SPLUNK_HOME" "$staging" "$REALM"
ssh -i "$SSH_KEY" -o StrictHostKeyChecking=accept-new "labadmin@${SIEM_HOST}" "$remote_cmd" <<'EOF'
set -euo pipefail
splunk_home="$1"
staging="$2"
realm="$3"
trap 'rm -f "${staging}.conf" "${staging}.pem"' EXIT
conf="$splunk_home/etc/system/local/authentication.conf"
if [ -f "$conf" ]; then
    cp -p "$conf" "${conf}.bak.$(date +%Y%m%d%H%M%S%N)"
else
    printf '%s\n' 'authentication.conf was absent'
fi
install -d -o splunk -g splunk -m 700 "$splunk_home/etc/auth/idpCerts"
install -o splunk -g splunk -m 644 "${staging}.pem" \
    "$splunk_home/etc/auth/idpCerts/keycloak-${realm}.pem"
install -d -o splunk -g splunk "$splunk_home/etc/system/local"
install -o splunk -g splunk -m 600 "${staging}.conf" "$conf"
rm -f "${staging}.conf" "${staging}.pem"
sudo -n -u splunk "$splunk_home/bin/splunk" btool check
if systemctl cat Splunkd >/dev/null 2>&1; then
    systemctl restart Splunkd
else
    sudo -n -u splunk "$splunk_home/bin/splunk" restart --answer-yes --no-prompt
fi
EOF

ready=false
web_up=false
saml_form_re="<form[[:space:]]([^>]*[[:space:]])?action=[\"']"
for ((attempt=0; attempt<120; attempt++)); do
    if login_page=$(curl -fksS --max-time 5 \
        "${SIEM_WEB_SCHEME}://${SIEM_HOST}:${SIEM_WEB_PORT}/en-US/account/login" 2>/dev/null); then
        web_up=true
        if [[ "$login_page" == *SAMLRequest* ||
            "$login_page" =~ $saml_form_re"${IDP_ENTITY_ID}/protocol/saml" ]]; then
            ready=true
            break
        fi
    fi
    sleep 2
done
if ! "$ready" && "$web_up"; then
    die "Splunk Web is up but SAML is not active (restart failed?)"
fi
"$ready" || die "Splunk Web did not become ready"
log "SIEM SAML is configured (entity id splunk-siem)"
