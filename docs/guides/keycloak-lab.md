<!-- summary: Run the contributor Keycloak SAML lab in rootless Podman so you can exercise splunkctl's browser SAML login against Splunk and SOAR test VMs. -->

# Contributor lab: Keycloak SAML

When to use: you are developing or testing splunkctl's browser SAML flow and need an external identity provider for the Splunk SIEM and SOAR lab VMs without touching a corporate IdP. This is a contributor tool, not something a splunkctl user needs.

## Prerequisites

- A clone of the repository; the lab lives under `lab/keycloak/`.
- `podman` with `podman compose` (or `podman-compose`), `curl`, `grep`, `sed`, and `python3`. No root on the host.
- Splunk SIEM and SOAR VMs that can reach a port on the host. The lab defaults assume VMware NAT addresses (`100.65.1.1` for the host, `100.65.1.10` SIEM, `100.65.1.11` SOAR); override them in `.env` for a different network.
- For product configuration over SSH: a `labadmin` account on both VMs and the vmlab key under `$VM_BASE_DIR` (default `~/vmware/.vmlab_key`; override with `SSH_KEY`).

## Synopsis

```text
./labctl.sh <start|configure|verify|status|stop>
./siem-configure.sh
./soar-configure.sh
splunkctl auth login --target <siem|soar>
splunkctl auth status --target <siem|soar>
```

Full topology, realm contents, reset, and recovery are in `lab/keycloak/README.md`.

## Workflow

### Start and configure Keycloak

```bash
cd lab/keycloak
cp .env.example .env
./labctl.sh start
./labctl.sh configure
./labctl.sh verify
```

Edit `.env` first and set the three `*_PASSWORD` secrets: `KEYCLOAK_ADMIN_PASSWORD`, `POSTGRES_PASSWORD`, and `TEST_USER_PASSWORD`; the file is gitignored. `start` brings up Postgres and Keycloak and waits for health. `configure` imports the `splunklab` realm with two SAML clients (`splunk-siem`, `splunk-soar`), realm roles `splunk-admin` and `soar-admin`, and a test user `samluser` with a plain password and no second factor. Expected result: `verify` reports health, admin login, and both clients.

### Point the products at Keycloak

```bash
./siem-configure.sh
./soar-configure.sh
```

Both scripts are idempotent. `siem-configure.sh` backs up and installs `authentication.conf` and the IdP certificate, runs btool, restarts Splunk, and waits for Web. `soar-configure.sh` writes SOAR's SAML settings over SSH. The Keycloak `splunk-siem` client must sign both the response and assertion; Splunk uses `signedAssertion = true` with `allowPartialSignatures = false` and entity ID `splunk-siem`.

### Log in with splunkctl

```bash
splunkctl config init --web-url http://100.65.1.10:8000
splunkctl auth login --target siem
splunkctl auth status --target siem
```

`config init --web-url` lets splunkctl probe the login route and detect SAML. `auth login` opens Chromium, redirects to Keycloak, and asks for `samluser`'s password. Expected result: `auth status` reports `valid`. Use `--target soar` for the SOAR flow.

### Stop the lab

```bash
./labctl.sh status
./labctl.sh stop
```

## End-to-end check

From the repository root, install the browser extra and Chromium (see the
[auth guide](auth.md)). Initialize a `lab` profile for both products:

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

## Troubleshooting

- `verify` fails on health: check `podman ps` and the Keycloak logs; the first start can take a minute.
- The browser never reaches Keycloak: the VM cannot reach the host port. Confirm the host address in `.env` matches your NAT network.
- `auth login` fails on the password step: the realm was not imported; rerun `./labctl.sh configure`.
- Reset and recovery steps are in `lab/keycloak/README.md`.

## See also

- [Log in through browser SAML](auth.md)
- [Configure](configure.md)
- [CONTRIBUTING.md](https://github.com/dannyota/splunkctl/blob/master/CONTRIBUTING.md)
