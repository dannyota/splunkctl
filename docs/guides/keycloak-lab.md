# Keycloak SAML lab

The lab runs Keycloak in rootless Podman as an external identity provider for
the Splunk SIEM and SOAR VMs. It lets you exercise the browser SAML flow,
including manual TOTP entry, without giving splunkctl access to the TOTP secret.

See `lab/keycloak/README.md` in the source tree for topology, setup, reset, and
recovery. The short version:

```bash
cd lab/keycloak
cp .env.example .env      # set the two *_PASSWORD secrets
./labctl.sh start
./labctl.sh configure
./labctl.sh verify
```

Then run `splunkctl config init` against a product that uses SAML, or configure
the products to point at `http://100.65.1.1:8080` as their IdP, and log in with
`splunkctl auth login --target siem`.
