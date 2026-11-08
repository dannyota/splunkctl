# Changelog

## Unreleased

### Changed

- Require `splunk-sdk>=3.0` on Python 3.13 and later. `splunk-sdk` 3.x
  needs Python 3.13, so Python 3.12 installs stay on `splunk-sdk>=2.1`.
- CI runs `pip-audit` against the installed runtime dependencies.
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

## 0.11.0

Whole-repo hardening + feature expansion, driven by a max-effort code
review (75 agents, 25 verified findings) and two feature-gap scouts
(SIEM + SOAR/MCP/DX). Live smoke-tested against Splunk 10.4.1 and
SOAR 8.5.0.248: 23 pass, 0 failures.

### Breaking

- **TLS verification defaults to ON** — new profiles verify server
  certificates by default. Self-signed lab instances need explicit
  `verify: false` in the profile (`config init` now asks). A one-time
  stderr warning fires when verification is disabled.

### Security

- **GitHub Actions pinned to commit SHAs** — all third-party actions
  use immutable refs; workflow-level `permissions:` blocks enforce
  least privilege (`contents: read` default; `id-token: write` only
  for PyPI OIDC).
- **SPL injection fixed** — lookup names in `| inputlookup` are now
  quoted via a shared helper; names with SPL metacharacters are
  rejected with a typed error.
- **Password handling** — `users create/update` gains `--password-stdin`
  and interactive prompt; passwords never appear in dry-run previews,
  error envelopes, or MCP tool output.

### Fixed

- `hec send` no longer crashes with NameError on connection errors;
  TLS verification reads from the profile (not a missing SDK attribute).
- Web-session failures (lookup upload, app install with expired creds)
  produce typed error envelopes instead of raw tracebacks.
- SOAR client sets HTTP timeouts (10s connect, 60s read) — no more
  indefinite hangs on unresponsive servers.
- `soar ingest` run_automation triggers correctly when the last input
  row is deduplicated.
- Tag read-modify-write aborts on fetch failure instead of silently
  wiping all tags.
- Broad `except Exception` in dashboards, lookups, and SOAR views
  narrowed to specific errors — auth failures no longer masquerade as
  "not found" or "unavailable".
- `soar functions list` paging aligned with other SOAR commands.
- Vault upload warns based on base64-encoded size (not raw); download
  `--out` handles directory paths.
- `mcp install` handles `"mcpServers": null` in existing config.
- Network reads moved after the guard in SOAR cases/artifacts/assets
  so dry-run stays offline.
- `_resolve_template` routes through the structured error envelope.

### Added

- **Doctor SOAR section** — connection, auth, health, and license
  checks with graceful skip when no SOAR profile is configured.
- **MCP output cap** — success output > 4 MiB spills to a temp file
  with a JSON pointer and steering hint; error output is UTF-8-safe
  truncated; subprocess timeout raised to 300s with clean messaging;
  stale spill files swept on startup (24h).
- **MCP prompts** — four `@mcp.prompt` workflows: `investigate-ioc`,
  `triage-notable`, `audit-detection`, `export-state`.
- **MCP streamable-HTTP transport** — `mcp serve --transport http`
  for team/remote use; `mcp install` generates URL-based config.
- **ES correlation-search admin** — `es correlations list/get/
  enable/disable` with security_domain and severity fields.
- **ES threat-intel management** — `es threat-intel list/upload/
  delete` via `/services/data/threat_intel`.
- **Scheduler health** — `rules schedule` view (cron, next_run,
  window, enabled) and `--scheduled` filter on `rules list`.
- **Auth-token management** — `server tokens list/create/revoke`
  via `/services/authorization/tokens`.
- **Deployment-server serverclasses** — `server serverclasses
  list/get/reload` with feature detection for disabled deployment
  server.
- **SAML/LDAP auth config read** — `server auth show/ldap/saml/
  role-mapping` for compliance visibility.
- **Workload management read** — `server workloads pools/rules/
  status` for resource allocation visibility (Splunk 8.1+).
- **Metrics catalog** — `search metrics --index` wraps `| mcatalog`
  for metric name and dimension discovery.
- **SOAR workbook-template CRUD** — `soar workbook-templates
  list/get/create/update/delete`.
- **SOAR app install/uninstall** — tgz upload and deletion via
  `/rest/app`.
- **Watch mode** — `--watch N` re-runs read-only commands every N
  seconds; rejects mutations; requires TTY.
- **Shell completion** — `splunkctl completion bash/zsh/fish` prints
  activation scripts.
- **Exit-code contract** — documented and normalized: 0 = success,
  1 = error, 2 = usage.
- **SOAR config-as-code** — `state pull/diff/push` extended with
  `soar-playbooks` (tgz round-trip), `soar-lists` (JSON round-trip),
  and `soar-assets` (JSON with secret masking, fetch-merge-post).
  Mixed SIEM+SOAR type requests work in one call.

### Structure

- Server-side paths removed from user output (remote-first).
- Duplicated `read_results` helpers consolidated.
- Phase/ticket-named test files renamed to feature names.
- Near-cap files split: `soar/admin.py` → users + roles/audit;
  oversized test files split by topic.
- Private cross-module imports promoted to public API.

### Stats

- 1728 tests (was 1424), ruff + mypy-strict + file-length budget
  all clean.

## 0.10.1

### Fixed
- **PyPI wheels were missing `splunkctl.commands.soar`** — a stale
  hardcoded package list broke every clean install from v0.7.0 to
  v0.10.0 (editable dev installs concealed it). Packages are now
  auto-discovered; CI installs the built wheel and imports the tree.

## 0.10.0

Bug-fix batch from a live MCP agent-journey test against the lab
(SIEM 10.4.1 + SOAR 8.5.0.248) — 28 issues, all fixed or documented —
plus `soar playbooks delete` and the fixes from its pre-release review.

### Added
- **`soar playbooks delete`** — deletes playbooks through the SOAR Web
  UI route (CSRF login + `POST /playbooks` with `{ids, delete: true}`),
  since no working REST deletion exists. Username/password required.
  Exact scoped name or numeric id only (a suffix-only match is a
  did-you-mean error); guarded with an offline dry-run preview;
  per-playbook change/error report; exit 1 on any failure.

### Fixed
- **MCP typed tools invoke real CLI flags** — renamed Click options
  (`--severity`, `--map`, `--container-name`, `--container`) broke
  typed-tool calls; schemas now carry a flag map, negatable flags emit
  their `--no-*` form on explicit false, and `wait_` surfaces as `wait`.
- **MCP schemas no longer strip leaf options** that share a global
  flag's name (`--field` on container create/update, `--out` on
  exports) — globals live on the root group only.
- **MCP `run` guard bypass** — `--yes`/`-y` inside the raw command
  string is rejected with a clear error (not silently stripped, which
  ate quoted values); only the `yes` parameter applies a mutation.
- **MCP binary output** — `playbooks export` without `--out` returns a
  size hint instead of crashing the server on a UTF-8 decode.
- **MCP output order** — guard banners (stderr) now precede the data
  payload; group counts recurse nested subgroups; the `run` tip
  suggests subgroup focus/usage for nested groups like soar.
- **`soar containers assign`/`update` owner+role** — the API silently
  ignores name-shaped fields; names resolve to `owner_id`/`role_id`
  (name lookup first, so all-digit usernames resolve by name), every
  container in a bulk write is read-back verified (exit 1 if ignored,
  warning if unverifiable), and owner+role together is a usage error
  (SOAR assigns one principal — writing one clears the other).
- **`soar evidence add`** — sent `object_type`; the API wants
  `content_type` (and `actionrun` without the underscore). Always
  400'd before.
- **`soar cases task update`** — status transitions requiring a
  closing note now send it inline (`note`) in the task POST; the old
  two-step always 400'd. Guide corrected: only 0→2 and 2→1 are allowed.
- **`soar playbooks list --repo`** — repo names resolve to the
  id-typed `_filter_scm` (a name string 400'd).
- **`soar playbooks trigger --on label`** removed — the REST endpoint
  always rejects it (import-metadata only).
- **`soar playbooks export/run <name>`** — bare module names resolve
  via suffix match against the scoped `<dir>/<module>` name (one
  shared resolver; `run` previously exact-matched only).
- **`soar playbooks runs cancel`** — pre-checks run status; cancelling
  a finished run is now a `conflict` error instead of a false success.
- **`soar playbooks import`** dry-run preview names the final scoped
  playbook (`<dir>/<module>`), not just the directory basename.
- **`soar artifacts update`** — auto-populates `cef_types` for newly
  merged CEF keys (create already did); `--severity` on create/update
  is validated against the instance vocabulary with a clear error.
- **`soar audit --limit`** — enforced client-side for JSON and CSV
  output alike (the bare-array endpoint ignores `page_size`).
- **SOAR filter escaping** — user-supplied `_filter_*` values are
  JSON-escaped everywhere; a quote no longer corrupts the filter.
- **`soar playbooks disable --cancel-runs`** — the destructive side
  effect is disclosed in the guard preview and apply banner; `trigger`
  previews name the trigger type.
- **Unicode-digit identifiers** — id parsing accepts ASCII decimals
  only; `"²"` (isdigit-true, int-invalid) no longer crashes.
- **`soar ingest` dry-run preview** renders `name (sdi: X)` instead of
  the internal `name::sdi` key (SDIs often contain colons).
- **urllib3 `InsecureRequestWarning` suppressed** when `verify: false`
  is explicit config — it flooded every SOAR/Web-UI call.

### Documented
- SOAR 8.5 has **no working REST playbook deletion** (405 / silent
  no-op) — `playbooks delete` goes through the Web UI route; response
  envelope `{done_count, fail_count, changes, errors}` captured live.
- soar-api.md corrections: owner/role numeric-id-only writes with
  mutual exclusion, evidence `content_type`, inline task closing note,
  playbook-run cancel no-op, id-typed `_filter_scm`, sync error is 400
  on 8.5.

---

Older releases (0.9.0 and earlier): [changelog archive](docs/changelog-archive.md).
