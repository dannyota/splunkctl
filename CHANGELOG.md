# Changelog

## Unreleased

Live smoke coverage closed the remaining SIEM and SOAR gaps it can own, and
found the fixes below on Splunk Enterprise 10.6.1.1 and SOAR 8.8.0.282.

### Fixed

- `server tokens revoke` reported success without deleting anything:
  `DELETE authorization/tokens/<id>` returns 200 and leaves the token. It
  now looks up the token's user, deletes `authorization/tokens/<user>?id=<id>`,
  and reports `not_found` for an unknown id.
- `server tokens list --user` failed with HTTP 400 (`userName` is not a
  supported argument); it now sends `username`. The list requests every
  token (`count=0`) instead of Splunk's default page of 30, and `last_used`
  reads the `lastUsed` field.
- `server tokens create` requires `--audience`; Splunk rejects a token
  without one (HTTP 400).
- `soar approvals respond` posted to `/rest/external_prompt/<id>`, which
  returns 404 for an approval. It now posts to `/rest/approval/<id>`, takes
  prompt answers with `--response`, and requires `--message` or
  `--response`, as SOAR does.

### Tests

- The SIEM live smoke covers `alerts get` with an owned scheduled alert
  and `server tokens create`/`revoke`. The SOAR smoke covers `soar approvals
  get`/`respond` with `LIVE_SOAR_APPROVALS=1`, and tolerates a fast licensed
  action finishing before `soar actions cancel`.
- `lab/keycloak/auth-smoke.sh` runs browser `auth login`, `status` and
  `logout` for SIEM and SOAR against the Keycloak lab.

## 0.17.2

Browser SAML auth verified live on Splunk Enterprise 10.6.1.1 and SOAR
8.8.0.282 against the Keycloak lab: `auth login`, `status` and `logout` work
for both products, commands run on the browser session alone, and
`config init` detects SAML and derives the SOAR SSO URL.

### Fixed

- `auth login` used the 30-second request timeout as the whole browser
  deadline. `auth login --timeout` now sets it, default 300 seconds; the
  request timeout still applies to session validation.
- The sessions directory is created 0700 on save, including an existing
  directory that was created with a looser umask. Reads no longer touch the
  filesystem.
- With `verify: false`, auth commands showed a raw urllib3
  `InsecureRequestWarning`; they now print the usual splunkctl TLS warning.

### Lab

- `lab/keycloak/siem-configure.sh` configures Splunk SAML over SSH: it
  extracts the Keycloak signing certificate, backs up `authentication.conf`,
  restarts the systemd `Splunkd` unit, and confirms SAML is active.
- `lab/keycloak/e2e-login.py` runs the real login broker and fills only the
  Keycloak form, for repeatable end-to-end checks.
- The Keycloak `splunk-siem` client signs the SAML response and assertion,
  which Splunk requires. Unused SP entity URL defaults are removed.

## 0.17.1

SOAR fixes from the first live run of `scripts/live-smoke-soar.sh`. The SOAR
live smoke now passes with 0 failures on SOAR 8.8.0.282 (indicators and
licensed actions skipped).

### Fixed

- `soar workbook-templates update --add-phase` deleted the template's
  existing phases and their tasks. It now adds each phase through
  `workbook_phase_template` and leaves existing phases untouched.
- `soar cases promote --template` sent `template`, which SOAR ignores, so the
  default workbook was applied. It now sends `template_id`.
- Workbook template names and the default template resolve with server
  filters, so templates beyond the first page are found.
- `soar audit` paginates JSON and CSV (1-based pages). SOAR 8.8 rejects
  unpaginated audit queries longer than 24 hours.
- `soar evidence list` adds `object_type` (artifact, note, action_run), since
  SOAR returns `content_type` as a numeric id.
- `soar vault list` adds `vault_id`, the hash that `vault get` and
  `vault download` take.
- `soar playbooks enable|disable|trigger` explain a 404 from a stale id after
  a forced import, and `soar functions import` warns when SOAR saves the
  function as a draft.

### Added

- `soar workbook-templates get` shows phases and tasks.
- `soar functions update --python-version`.
- `soar playbooks list --name` (exact scoped name) and `--limit`.

### Changed

- SOAR live smoke: asset soft delete, Python 3.13 function fixture, playbook
  ids re-resolved by exact name after each import, and the manual run uses an
  inactive playbook with the `events` label.

## 0.17.0

A reusable single-host lab for Splunk Enterprise 10.6.1.1 and SOAR 8.8, Splunk
10.6 KV store support, `SPLUNK_WEB_URL`, and a SOAR live smoke test with the
SOAR fixes found while building it. The SIEM live smoke passed with 0
failures on Splunk 10.6.1.1 (macOS arm64 build and an Ubuntu 24.04 podman
container). The SOAR changes are unit-tested; they have not yet run against
a SOAR instance.

### Added

- `SPLUNK_WEB_URL` sets `web_url` from the environment, so env-only setups
  against a port-mapped Splunk Web (for example a container) can use lookup
  upload, app install and data upload.
- `soar artifacts update --no-automation` suppresses playbook automation.
- `scripts/live-smoke-soar.sh`: a maintainer SOAR live smoke test with owned
  fixtures, no licensed actions by default (`LIVE_SOAR_ACTIONS=1` opts in),
  an active-playbook preflight, reverse cleanup, and offline coverage and
  runner checks. Shared helpers move to `scripts/live-smoke-lib.sh`.
- `installers/vmlab/fetch-installers.sh` downloads public installers and
  verifies selected artifacts, with a download-free `--check` mode.

### Changed

- VMware lab pins: Splunk Enterprise 10.6.1.1 and SOAR 8.8.0.282.
- Reusable single-host Ubuntu 24.04 setup docs for VMware and Keycloak.
- Lab timezone defaults to UTC; SOAR RAM defaults to 8 GB.
- Keycloak realm configuration requires an explicit `TEST_USER_PASSWORD`;
  the example file no longer ships a default.
- Security scanning: CodeQL (Python and GitHub Actions, security-extended
  queries) and gitleaks replace semgrep. pip-audit continues to cover
  dependency vulnerabilities.

### Fixed

- `soar assets update` and `soar actions run` resolve the asset's app name
  (as SOAR returns it) to the numeric `app_id`, and reject ambiguous names,
  instead of failing with `ValueError`.
- `soar playbooks list` exits 1 on a response without a data list instead of
  printing an empty list.
- `server kvstore` reports Splunk 10.6 cohosted, migration, and backup/restore
  fields; `doctor` also requires cohosted KV Store readiness when the
  cohosted block is present.

## 0.16.0

Live-verified against Splunk Enterprise 10.6.1.1 and SOAR 8.6.0.530: a
maintainer smoke test for every SIEM command group, five bugs it found,
and data model acceleration as a first-class command.

### Added

- `datamodels accelerate NAME --earliest WINDOW [--cron EXPR] [--disable]`:
  a guarded command that previews and writes the acceleration keys of
  datamodels.conf, replacing the raw `conf set` workaround.
- `datamodels acceleration --app` scopes the status lookup to one app and
  refuses ambiguous model names.
- `hec send --url` overrides the HEC base URL for hosts where the HEC port
  is mapped away from the management port.
- `server license --usage` reports `active_group` and `active_group_status`.
- `scripts/live-smoke.sh` replaces `scripts/live-adapter-smoke.sh`: a
  maintainer smoke test for every SIEM command group against a throwaway
  Splunk instance, with `LIVE_ONLY`, `LIVE_SKIP`, `CIM_TGZ`,
  `LIVE_MONITOR_PATH`, `LIVE_HEC_URL` and `LIVE_PYTHON` knobs and
  self-cleaning `sc_live_` fixtures. A unit test keeps it in step with the
  command tree.

### Changed

- `rules enable`, `rules update --enabled` and `rules create` schedule a
  rule only when it has a cron expression; a rule without one is enabled
  with a note instead of failing with HTTP 400.
- `rules test` on a disabled rule runs its SPL ad hoc in the rule's app and
  owner namespace; enabled rules still dispatch the saved search with
  alert actions suppressed.
- `server license --usage` counts validity, quota and the soonest expiry
  over the active license group only.
- `splunk-sdk>=3.0` on Python 3.13 and later; Python 3.12 installs stay on
  `splunk-sdk>=2.1` because 3.x requires Python 3.13.
- CI runs `pip-audit` against the installed runtime dependencies.
- Generated command pages use no em dashes.

### Fixed

- `datamodels rebuild` sent `acceleration=0` and `acceleration=1` as bare
  form fields; the `datamodel/model` endpoint takes one JSON object and
  answered HTTP 500. It now posts `{"enabled": false}` and then the
  model's full acceleration configuration with `enabled` true.
- `soar meta cef` and `soar meta features` returned only the first REST
  page of 10 rows; every vocabulary now walks all pages.
- The install guide no longer mentions the retired SDK fork.

## 0.15.0

Python 3.12 support, no more SDK fork for dashboards, lookup files, and
HEC tokens, and every guide rewritten to the task-based contract.

### Changed

- Dashboard, lookup file, and HEC token commands no longer need the
  optional SDK fork. Thin REST adapters over `data/ui/views`,
  `data/lookup-table-files`, and `data/inputs/http` replace its entity
  classes; the upstream `splunk-sdk` from PyPI is sufficient.

### Fixed

- `doctor` and `lookups upload` honor the profile's `web_url` instead of
  deriving the Web UI address from the server's `httpport`, so port-mapped
  and proxied instances work.
- `lookups download` no longer writes the blank first line that Splunk's
  CSV export emits, so downloaded files round-trip through `upload`.

### Added

- `scripts/live-adapter-smoke.sh`: a maintainer smoke test that exercises
  dashboards, lookup files, HEC tokens, and `state pull` against a live
  Splunk instance.

- Support Python 3.12. The command reference generator normalizes help
  text so generated pages are identical across Python versions.

## 0.14.0

Coexistence with Splunk's own `splunkctl` Go CLI, which shares our command
name and config path; security fixes for TLS verification, flag hoisting,
and write SPL; a docs site rebuilt for security operations engineers and
AI readers; green CI on current MCP releases.

### Added

- **`splunkctl-py` executable** — a second entry point for hosts where
  Splunk's `splunkctl` binary shadows ours on `PATH`.
- **Config coexistence** — when `~/.splunkctl/config.yaml` is in Splunk's
  flat `host`/`token` format, this tool leaves it untouched, uses
  `~/.splunkctl/profiles.yaml` instead, and prints one notice on standard
  error. An explicit `--config FILE` in Splunk's format is refused with a
  `config` error rather than redirected. `doctor` reports the config file
  in use as its first check, warns when the file is missing, and fails on
  unreadable or malformed files. A token-only flat file is still read as
  this tool's own legacy format.
- README section comparing this project with `splunk/splunkctl`, and a
  ROADMAP note recording the decision to keep the name.

### Security

- **TLS verification was silently off for Splunk Enterprise.** `verify: true`
  profiles never passed `verify` to the SDK, whose default is off. The
  client now always passes the profile's value; the default is on.
- **Argument values could become global flags.** A positional or option
  value such as `--yes` was hoisted into the global flags, which let an MCP
  tool call apply a mutation without `yes=true`. The parser now stops at
  `--` and never inspects option values, and the MCP runner separates
  positionals with `--`.
- **SPL that writes is a mutation.** `search run`, `search export`,
  `search oneshot`, and `soar ingest` refuse SPL containing `outputlookup`,
  `collect`, `mcollect`, `meventcollect`, `sendalert`, `delete`,
  `outputcsv`, `outputtext`, `sendemail`, `runshellscript`, or `script`
  unless `--yes` is passed. A refusal exits with code 1 and, in JSON
  output mode, emits a `confirmation_required` error so scripts notice.
  Field comparisons such as `outputlookup=x`, search terms after
  `search`, and macro arguments are not treated as commands. MCP search
  tools have no `yes` parameter, so such SPL is refused there.
- Config files are written through a `0600` temporary file and renamed into
  place, writing through symlinks; the config directory is created with
  mode `0700`.
- The SOAR token prompt in `config init --soar` no longer echoes input.
- `soar assets create` and `update` previews mask configuration values
  whose key contains `password`, `secret`, `token`, or `api_key`.
- SOAR asset and artifact `KEY=VALUE` options reject a missing `=`.
- Lab scripts: Keycloak realm files are rendered under `umask 077`, and VM
  provisioning refuses the placeholder lab password.
- Docs site: CDN assets are pinned to exact versions that match their
  integrity hashes; a dead stylesheet link was removed.
- Added SECURITY.md with private vulnerability reporting, and
  CONTRIBUTING.md with the release procedure.

### Docs

- Docs site and README rewritten for security operations engineers:
  task-based navigation (Investigate, Detect, Respond with SOAR, Change
  safely, Give it to an agent, Operate and audit, Reference), a guide
  contract with synopsis, workflow, and Safety notes, and new guides for
  SOAR incidents, SOAR assets, ES detections, and the relationship to
  Splunk's own `splunkctl`.
- Minimal light-first theme with a dark toggle, system fonts only, WCAG
  contrast, print styles, and a shared `>_` mark for the banner, social
  image, and favicon.
- For AI readers: every page declares a one-line summary that
  `llms.txt` uses verbatim, `llms-full.txt` holds the home page and the
  operator guides, and `commands.json` publishes the full command tree.
  `splunkctl docs generate` and `scripts/gen-seo.sh` check all of it in CI.

### Changed

- MCP guide resources read their title past the leading summary comment.
- The publish workflow fails when the release tag does not match the
  package version. CI tests run on Ubuntu and macOS.
- `config init` now honors the global `--config` flag as its destination
  when `--path` is not given.
- Require `mcp>=2.3` to match the `MCPServer` Streamable HTTP signature the
  server subclasses.

### Fixed

- Typecheck against MCP 2.3 and click 8.5 (raw tgz exports write through
  `sys.stdout.buffer`).
- Script tests resolve `bash` from `PATH` and run on macOS.

## 0.13.0

Browser SAML single sign-on for SIEM and SOAR, plus a reusable Keycloak lab.

### Added

- **`auth` command group** — complete Splunk SAML single sign-on in a headed
  Chromium window and reuse the product session until it expires.
  `auth login --target <siem|soar>` runs the browser flow, `auth status`
  reports `missing`/`valid`/`expired`/`unreachable`, and `auth logout` clears
  the cached session.
- **Automatic SAML detection** — `config init` probes the public login route
  and records `auth_mode: browser` when it sees a redirect to an external
  identity provider.
- **SOAR SAML SSO** — `config init --soar --sso-url <url>` sets SOAR's SAML
  login URL, or `--soar` derives it from a browser-authenticated SIEM that
  shares the same IdP. `config init --soar` also accepts `--no-verify`.
- **Keycloak lab** — rootless Podman Keycloak (`lab/keycloak`) as an external
  IdP for the SIEM and SOAR VMs, with `labctl.sh` to run it and
  `soar-configure.sh` to script SOAR's SAML config.

### Fixed

- The browser broker now waits for the identity-provider round trip instead
  of returning early on a same-origin login page.
- SIEM falls back to token/password auth when SAML is removed, rather than
  demanding a doomed browser login.

## 0.12.0

MCP 2 migration for local agent integrations.

### Breaking

- Require MCP Python SDK 2.x. Use splunkctl 0.11.2 for clients or
  environments that still require MCP 1.x.
- Tool-list changes use MCP 2 subscriptions instead of legacy
  `notifications/tools/list_changed` delivery.
- Streamable HTTP accepts loopback hosts only: `127.0.0.1`,
  `localhost`, or `::1`.

### Changed

- Replace `FastMCP` with MCP 2's `MCPServer`, client, prompt, model,
  transport, and snake-case APIs.
- Keep progressive disclosure through the five meta-tools and
  Click-derived typed tools.
- Replace private SDK tool-manager mutation with a splunkctl-owned
  dynamic registry built on the public `list_tools()` and
  `call_tool()` extension points.
- Package MCP guide resources in source and wheel distributions.
- Move Streamable HTTP host and port configuration to MCP 2's
  transport runner.

## 0.11.2

MCP compatibility and repository documentation update.

### Fixed

- Constrain the MCP Python SDK to the supported 1.x line so fresh
  installs do not select the incompatible 2.x API.

### Changed

- Rewrite the README around installation, local MCP setup, core
  workflows, and safety behavior.
- Remove obsolete internal planning documents.

## 0.11.1

PyPI presentation and packaging polish — no functional changes.

### Security

- Dependabot cooldown (7 days) on pip and GitHub Actions updates —
  new upstream releases soak before update PRs open.
- Remaining semgrep findings resolved: two justified false positives
  annotated in place (PEP 706 `filter="data"` tar extraction; SRI on
  a non-subresource `canonical` link).

### Fixed

- README renders correctly on PyPI: the banner image and Catalog link
  now use absolute URLs (relative paths break on PyPI), and docs links
  point at the live domain (`splunkctl.danny.vn` — the old
  `splunk.danny.vn` never resolved).
- Stale MCP guide-resource count corrected (33 → 36) in README and
  catalog; `state` docs now mention the SOAR types added in 0.11.0.
- `py.typed` marker actually ships — the wheel is PEP 561 compliant.
  The marker was declared in package-data but missing from the tree,
  so `mypy` gave external consumers no types.
- sdist no longer bundles tests/docs/samples (`MANIFEST.in` prunes).
- Test suite isolated from the developer's real `~/.splunkctl` config
  and `SPLUNK_*`/`SOAR_*` env vars — a live SOAR profile made four
  doctor tests hit the network and fail when the lab was offline.

### Added

- README: PyPI/Python/CI/license badges; `--watch` global flag and
  `completion` command documented.
- PyPI sidebar links: `Documentation` and `Changelog` project URLs.
- Development Status classifier raised to Beta.
- Publish workflow runs `twine check --strict` before uploading.

Older releases (0.11.0 and earlier): [changelog archive](docs/changelog-archive.md).
