<!-- summary: Complete Splunk and SOAR SAML single sign-on, including a second factor, in a browser and reuse the session from every splunkctl command. -->

# Log in through browser SAML

When to use: your Splunk or SOAR instance authenticates through a SAML identity provider (with or without a second factor), so a username and password or a token cannot be stored in the profile, and you want every splunkctl command to reuse one browser login until it expires.

## Prerequisites

- splunkctl with the browser extra and Chromium:

  ```bash
  python -m pip install 'splunkctl[browser]'
  python -m playwright install chromium
  ```

  Configuration succeeds without them; `splunkctl auth login` prints these commands when they are missing.

- A machine with a display: login opens a headed Chromium window. The browser handles the identity provider; splunkctl never reads or stores TOTP secrets or codes.
- A profile in browser mode (`auth_mode: browser` with a `web_url`), written by `config init` as shown below.
- Not supported: reading or storing TOTP secrets, native Splunk Duo or RSA flows, OpenID Connect or OAuth, logging in to both products in one command, and a local splunkctl callback redirect.

## Synopsis

```text
splunkctl config init --web-url <https://splunk.example.com:8000> [--profile NAME] [--auth-mode auto|browser]
splunkctl config init --soar --web-url <https://soar.example.com> [--sso-url URL] [--profile NAME]
splunkctl auth login --target <siem|soar>
splunkctl auth status [--target siem|soar|both]
splunkctl auth logout [--target siem|soar|both]
```

## Workflow

### Detect SAML during setup

```bash
splunkctl config init --web-url https://splunk.example.com:8000
splunkctl config init --soar --web-url https://soar.example.com --sso-url 'https://soar.example.com/saml2/login?idp=okta&next=/'
```

Expected result: `config init` probes the product's public login route. When it sees a redirect to an external identity provider it records `auth_mode: browser` and stores the product `web_url` in the profile. SAML detection runs only when `--web-url` is given. Pass `--auth-mode browser` to force browser mode without probing. For SOAR, pass `--sso-url` because SOAR's `/login` route is local-only.

### Log in

```bash
splunkctl auth login --target siem
splunkctl auth login --target soar
```

Expected result: Chromium opens at the product login route; you complete the identity provider prompts, including any TOTP code; splunkctl extracts only the product session (the Splunk `splunkd_<port>` cookie, or the SOAR `sessionid` and `csrftoken` cookies), proves it against the product API, and prints `siem session stored (profile 'NAME').`. `login` requires exactly one target because two back-to-back browser flows are easy to confuse.

### Check the session

```bash
splunkctl auth status
splunkctl auth status --target siem
```

Expected result: one row per target with `status` set to `missing`, `valid`, `expired`, or `unreachable`. Without `--target`, only targets configured for browser mode are checked; if none are, it prints `No browser-authenticated targets configured.`.

### Use the session from normal commands

```bash
splunkctl search oneshot 'index=_internal | head 5'
splunkctl soar test
```

Expected result: commands reuse the cached session whenever the active profile selects browser mode. A missing or expired session never opens a browser; the command fails with the exact `splunkctl auth login --target ...` instruction to run instead.

### Log out

```bash
splunkctl auth logout --target siem
splunkctl auth logout --target both
```

Expected result: a best-effort remote logout, then `Logout complete.`. The local session is always removed, even if the remote endpoint refuses; a refused remote logout prints a warning.

Sessions live under `~/.splunkctl/sessions/<profile>/<target>.json` with directory mode `0700` and file mode `0600`. A record holds only the target, profile, product origin, product session values, and validation timestamps. It never stores passwords, Playwright storage state, identity-provider cookies, or TOTP secrets, and session values are redacted from all output.

## Troubleshooting

- `usage` error `siem is configured for token authentication, not browser login`: the profile has `auth_mode: token` or `password`; rerun `splunkctl config init --web-url URL` so SAML is detected, or pass `--auth-mode browser`.
- `login` prints `pip install` and `playwright install` commands: the browser extra is missing; run them and retry.
- `auth` error `login finished but the product session was rejected`: the browser ended on a different origin than `web_url`, or the identity provider flow did not complete; check `web_url` with `splunkctl config show` and log in again.
- `connection` error `SIEM is unreachable while checking the browser session`: the product API is down or blocked; fix connectivity with [Diagnose a connection](doctor.md).
- A command reports the session is missing or expired: run the `splunkctl auth login --target ...` command it prints; commands never open a browser on their own.
- `remote logout failed; clearing local session`: the product refused the logout call; the local file is still removed and a new `login` is required.

## See also

- [Configure](configure.md)
- [Install](install.md)
- [Set up and check SOAR](soar.md)
- [Contributor lab: Keycloak SAML](keycloak-lab.md)
- [Command reference: auth](../commands/auth.md)
