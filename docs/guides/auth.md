# Browser SAML authentication

splunkctl can complete Splunk SAML single sign-on (including a second factor)
in a headed Chromium window and then reuse the resulting product session until
it expires. The browser handles the identity provider; splunkctl never reads or
stores TOTP secrets or codes.

## How it works

1. `splunkctl config init` probes the public login route. When it sees a
   redirect to an external identity provider, it records `auth_mode: browser`
   and stores the product `web_url`.
2. `splunkctl auth login --target <siem|soar>` opens Chromium at the product
   login route. You complete the IdP prompts, including any TOTP code.
3. splunkctl extracts only the product session (Splunk `splunkd_<port>` cookie,
   or SOAR `sessionid` + `csrftoken`) and proves it against the product API.
4. Normal commands reuse the cached session whenever the active profile selects
   browser mode. A missing or expired session never opens a browser; the command
   prints the exact login instruction instead.

## Commands

```text
splunkctl auth login --target siem
splunkctl auth login --target soar
splunkctl auth status [--target siem|soar|both]
splunkctl auth logout [--target siem|soar|both]
```

`login` requires exactly one target; two back-to-back browser flows are easy to
confuse. `status` reports `missing`, `valid`, `expired`, or `unreachable`.
`logout` always removes the local session, even if the remote endpoint refuses.

## Optional dependency

Browser login needs Playwright and Chromium:

```bash
pip install 'splunkctl[browser]'
python -m playwright install chromium
```

Configuration still succeeds without them. `splunkctl auth login` prints the
exact commands when they are missing.

## Session storage and security

Sessions are stored under `~/.splunkctl/sessions/<profile>/<target>.json` with
directory mode `0700` and file mode `0600`. A record holds only the target,
profile, product origin, product session values, and validation timestamps. It
never stores passwords, Playwright storage state, identity-provider cookies, or
TOTP secrets. Session values are redacted from all output.

## What is and is not supported

Supported: SAML browser login for SIEM and SOAR, one target per login, session
status and logout, automatic SAML detection, and a reusable Keycloak lab.

Not supported in this release: reading or storing TOTP secrets, native Splunk
Duo or RSA flows, OpenID Connect or OAuth, logging in to both products in one
command, and a local splunkctl callback redirect.
