# Keycloak SAML lab

A rootless Podman Keycloak deployment that acts as an external identity
provider for the Splunk SIEM and SOAR VMs. Keycloak runs on the lab host and is
reachable at the VMware NAT host address `100.65.1.1:8080`; the products stay
on `100.65.1.10` (SIEM) and `100.65.1.11` (SOAR).

## Topology

| Role | Address | Notes |
|---|---|---|
| Keycloak IdP | `http://100.65.1.1:8080` | Rootless Podman, realm `splunklab` |
| SIEM service provider | `http://100.65.1.10:8000` | SAML client `splunk-siem` |
| SOAR service provider | `https://100.65.1.11:8443` | SAML client `splunk-soar` |

## Requirements

- `podman` with `podman compose` (or `podman-compose`), `curl`, `grep`, `sed`, `python3`.
- No host root. Keycloak binds a host port in the NAT range, so the VMs can
  reach it without changes to either VM.

## First-time setup

```bash
cd lab/keycloak
cp .env.example .env      # then edit .env: set the three *_PASSWORD secrets
./labctl.sh start         # starts Postgres + Keycloak, waits for health
./labctl.sh configure     # imports the splunklab realm + SAML clients
./labctl.sh verify        # confirms health, admin login, and both clients
```

The `.env` file is gitignored. Set the three `*_PASSWORD` secrets:

```bash
KEYCLOAK_ADMIN_PASSWORD='...'
POSTGRES_PASSWORD='...'
TEST_USER_PASSWORD='...'
```

All other defaults are in `.env.example`; export any setting to override it.

## Realm contents

`configure` renders `realm-template.json` and imports it. The realm defines:

- two SAML clients, `splunk-siem` and `splunk-soar`, with product-specific
  assertion consumer URLs;
- realm roles `splunk-admin` and `soar-admin`;
- a test user `samluser` with a plain password (no second factor; the lab
  exercises the browser SAML flow without MFA).

## Point the products at Keycloak

Both products have idempotent configuration scripts.

```bash
./siem-configure.sh    # installs authentication.conf and the IdP cert, restarts Splunk
./soar-configure.sh    # writes SOAR's SystemSettings SAML config over SSH
```

`soar-configure.sh` builds SOAR's `SystemSettings.auth` JSON (with the Keycloak
IdP metadata inlined) and writes it to the SOAR VM. Idempotent. It SSHes as
`labadmin` with the vmlab key under `$VM_BASE_DIR` (default `~/vmware/.vmlab_key`; override with `SSH_KEY`), and maps the
SAML `splunk-admin`/`soar-admin` roles to SOAR `Administrator` (role id 1).

`siem-configure.sh` uses the same SSH account and key. It backs up the existing
`authentication.conf`, installs the Keycloak certificate, checks btool, and
waits for Splunk Web after restarting. Set `SIEM_HOST`, `SIEM_WEB_PORT`,
`SIEM_WEB_SCHEME`, or `SPLUNK_HOME` to override the defaults.

The `splunk-siem` Keycloak client must sign both the response and assertion;
Splunk requires `signedAssertion = true` and `allowPartialSignatures = false`.
Its SP entity ID is the Keycloak client ID `splunk-siem`.

## End-to-end check

From the repository root, install the browser extra and Chromium (see the
[auth guide](../../docs/guides/auth.md)). Initialize a `lab` profile for both products:

```bash
uv run splunkctl --profile lab config init --web-url http://100.65.1.10:8000
uv run splunkctl --profile lab config init --soar --web-url https://100.65.1.11:8443
```

The profile needs `auth_mode: browser` and `web_url` for each product.
`config init --soar` derives `sso_url` from the SIEM profile's IdP:
`https://100.65.1.11:8443/saml2/login?idp=http://100.65.1.1:8080/realms/splunklab&next=/`.
Use `verify: false` for the lab's self-signed certificates. Local SIEM admin
credentials still work over REST on port 8089 with SAML enabled.

Load the test password without printing it, then run the real broker with
only the Keycloak form automated. Keep shell tracing off:

```bash
set +x
source lab/keycloak/.env
export TEST_USER_PASSWORD
for target in siem soar; do
    uv run python lab/keycloak/e2e-login.py --profile lab auth login --target "$target"
    uv run splunkctl --profile lab auth status --target "$target"
    uv run splunkctl --profile lab auth logout --target "$target"
done
unset TEST_USER_PASSWORD
```

Expected: login stores a session, status reports `valid`, and logout clears
it. Set `E2E_HEADLESS=1` on hosts without a display.

## Daily use

```bash
./labctl.sh status
./labctl.sh stop
```

## Verify the SAML flow by hand

1. `./labctl.sh start && ./labctl.sh configure && ./siem-configure.sh && ./soar-configure.sh`.
2. Run `splunkctl auth login --target siem` or `--target soar` (see the auth
   guide). Chromium opens, redirects to Keycloak, asks for `samluser`'s
   password.
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
