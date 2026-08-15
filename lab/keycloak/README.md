# Keycloak SAML lab

A rootless Podman Keycloak deployment that acts as an external identity
provider for the Splunk SIEM and SOAR VMs. Keycloak runs on the laptop and is
reachable at the VMware NAT host address `100.65.1.1:8080`; the products stay
on `100.65.1.10` (SIEM) and `100.65.1.11` (SOAR).

## Topology

| Role | Address | Notes |
|---|---|---|
| Keycloak IdP | `http://100.65.1.1:8080` | Rootless Podman, realm `splunklab` |
| SIEM service provider | `http://100.65.1.10:8000` | SAML client `splunk-siem` |
| SOAR service provider | `https://100.65.1.11:8443` | SAML client `splunk-soar` |

## Requirements

- `podman` with `podman compose` (or `podman-compose`), `curl`, `grep`, `sed`.
- No host root. Keycloak binds a host port in the NAT range, so the VMs can
  reach it without changes to either VM.

## First-time setup

```bash
cd lab/keycloak
cp .env.example .env      # then edit .env: set the two *_PASSWORD secrets
./labctl.sh start         # starts Postgres + Keycloak, waits for health
./labctl.sh configure     # imports the splunklab realm + SAML clients
./labctl.sh verify        # confirms health, admin login, and both clients
```

The `.env` file is gitignored. Set at least:

```bash
KEYCLOAK_ADMIN_PASSWORD='...'
POSTGRES_PASSWORD='...'
```

All other defaults are in `.env.example`; export any setting to override it.

## Realm contents

`configure` renders `realm-template.json` and imports it. The realm defines:

- two SAML clients, `splunk-siem` and `splunk-soar`, with product-specific
  assertion consumer URLs;
- realm roles `splunk-admin` and `soar-admin`;
- a test user `samluser` with a `CONFIGURE_TOTP` required action (the user
  enrolls a TOTP QR code on first login and types codes manually).

## Daily use

```bash
./labctl.sh status
./labctl.sh stop
```

## Verify the SAML flow by hand

1. `./labctl.sh start && ./labctl.sh configure`.
2. Run `splunkctl auth login --target siem` (see the auth guide). Chromium
   opens, redirects to Keycloak, asks for `samluser`'s password, then a TOTP
   code.
3. Confirm `splunkctl auth status --target siem` reports `valid`.

## Reset and recovery

| Failure | Rerun |
|---|---|
| Containers down | `./labctl.sh start` |
| Realm missing or misconfigured | `./labctl.sh configure` |
| Health or clients wrong | `./labctl.sh verify` |
| Full reset (drops the Postgres volume) | `./labctl.sh stop && podman volume rm splunkctl-keycloak_pgdata` |

`configure` is idempotent: an existing realm returns HTTP 409 and is left
untouched. To force a clean realm, stop the stack, delete the `pgdata`
volume, start, and configure again. The product VMs are never rebuilt.

## Local state

`.runtime/` holds the rendered realm and Keycloak runtime state; it is
gitignored. Generated certificates and secrets are gitignored too. Only the
reusable deployment files (compose, template, scripts, this README, and
`.env.example`) are tracked.
