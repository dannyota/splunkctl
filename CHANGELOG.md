# Changelog

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

## 0.9.0

SOAR case-management, response ops, and SIEM-to-SOAR integration
(waves 33-34): the CLI now covers the full SOAR operational surface
and bridges SIEM data into SOAR containers. Live-verified against
SOAR 8.5.0.248.

### Added
- **`soar cases`** — promote containers to cases with workbook templates
  (NIST 800-61 etc.), view phases and tasks, add phases/tasks, update
  task status with integer-code transitions (0/1/2) and client-side
  closing-note enforcement.
- **`soar approvals`** — list pending/all approvals, get detail summary,
  approve/deny external prompts to unblock paused automation.
- **`soar lists`** — custom decided-list CRUD: create (JSON/CSV),
  update (full replace), add-row/remove-row, export (JSON or CSV via
  `formatted_content`), import (create-or-update).
- **`soar indicators`** / **`soar evidence`** — IOC pivot (by value,
  common containers, stats); evidence add/remove on containers.
  Indicators are feature-flag gated (`use_indicators`); commands exit 1
  with an actionable message when the flag is off.
- **`soar users`** / **`soar roles`** / **`soar audit`** — user CRUD
  (password reset, role read-modify-write, soft-delete semantics),
  automation-user creation with token-reality notice (plaintext is
  UI-only), role permission matrix (7 immutable built-in roles), and
  audit log queries (bare-array normalized, CSV export).
- **`soar search`** — cross-object free-text search via `/rest/search`
  with 1-based pagination (page=0 returns empty — discovered live) and
  comma-separated category filtering.
- **`soar ingest`** — SIEM search results to SOAR containers + typed
  CEF artifacts: `--spl` or `--sid` source, built-in CIM-to-CEF field
  map (upstream `butesIn` typo fixed), auto severity from
  severity/urgency, SDI dedup (container + artifact), last-artifact-true
  automation batching, dry-run preview with mapping table and sample CEF.
  Notable-event recipe: `event_id` SDI, `rule_name` container naming.
- **MCP subgroup focus** — `focus soar containers` now loads only that
  subgroup's tools instead of the entire soar tree, keeping the agent's
  tool context narrow.

## 0.8.0

SOAR automation wave (32): the CLI now drives apps, assets, playbooks,
actions, and custom functions — including the first playbooks-as-code
loop anywhere. Live-verified against SOAR 8.5.0.248.

### Added
- **`soar apps` / `soar assets`** — app inventory with config schemas and
  per-app actions; asset CRUD that respects the server's full-replace
  semantics (fetch-merge by default, `--replace` to opt out), password
  fields masked in previews, `assets test` connectivity checks, and
  `soar ingest-status` for polling-ingestion health.
- **`soar playbooks`** — list/get/enable/disable/trigger plus the
  as-code loop: `export` (tgz, `--unpack` to the json+py pair) and
  `import` (dir or tgz), `repos`, and `sync` with the local-repo
  limitation explained. Duplicate-name resolution errors instead of
  guessing.
- **`soar playbooks run` / `runs`** — run playbooks against containers
  with `--scope`, `--input`, and `--wait` polling to terminal status;
  inspect run history and per-block results; cancel in-progress runs.
- **`soar actions`** — run any connector action (`--asset` name
  resolution to app targets, `--param`), poll with `--wait`, inspect
  per-asset `results`, cancel. Mid-poll server errors surface as real
  errors, never fake timeouts.
- **`soar functions`** — custom-function list/get/import/export/update/
  delete; the export REST route was verified live; editing a Python 2.7
  function warns before upgrading it to Python 3.
- SOAR response normalization extended (`playbook_run_id` → `id`), and
  all SOAR guides registered in the docs navigation.


## 0.7.0

Splunk SOAR support arrives: splunkctl now operates Splunk Enterprise
**and** Splunk SOAR from one CLI. Foundation + containers/artifacts
waves (30-31), live-verified against SOAR 8.5.0.248.

### Added
- **SOAR profiles** — `soar:` section per profile (host, port, token,
  username, password, verify) with `SOAR_*` env overlay; secrets
  redacted in `config show`; `config init --soar` prompts. SIEM-only
  profiles unaffected.
- **`SOARClient`** — requests-based Django REST client: token auth with
  automatic Basic fallback for DELETE (tokens are refused there),
  Django-style filter builder (quoted strings, `__op`, Python booleans,
  `__in`), pagination, bulk array POST, binary downloads, and response
  normalization for every server quirk (`succeeded`/`success`,
  `failed:true` on HTTP 200, `action_run_id`/`id`, bare-array audit,
  `{results}` search envelope).
- **`soar test/info/health/license`** — platform reads; health rolls up
  daemons + warm standby + cluster with graceful empties; license
  surfaces the community 100 actions/day cap.
- **`soar settings/stats/meta`** — system_settings dump, SOC widget
  metrics (17 widgets), and vocabulary reads (severities, statuses,
  labels, tags, CEF fields, feature flags).
- **`soar containers`** — list with composable filters (label, status
  by name, severity, owner, --since, type) and offset/limit contract;
  get with artifact/note/comment/audit/activity/playbook-run/phase
  sub-views; create/update/close/assign/delete with dry-run guard,
  bulk single-array-POST, SDI dedup precheck, per-container tag merge.
- **`soar artifacts`** — CRUD with typed CEF (`--cef`, `--cef-file`,
  `--cef-type`), built-in CEF contains map, client-side SDI dedup
  warning (the server does not dedup), fetch-merge updates with
  `--replace-cef` for wholesale replacement.
- **`soar notes`** — container and task notes (markdown from arg or
  file), comments, and honest immutability UX for comment deletion.
- **`soar vault`** — upload (base64, size warning), byte-identical
  download, list/get/delete with the vault_document 405 explained.
- All SOAR mutations are dry-run by default with the SOAR host in the
  guard banner; `--yes` applies. Every command doubles as an MCP tool.


## 0.6.0

MCP hardening + SIEM polish, driven by a protocol-level MCP verification
and a live SIEM audit (2026-07-11).

### Fixed
- **MCP focused tools work again** — every focused typed-tool call
  failed argument validation (the runner's auto-generated Pydantic
  model expected a literal `kwargs` field no client could send). Tools
  now pass arguments through to the CLI, where Click validates for
  real; only the `run` escape hatch worked before.
- **MCP array parameters** — variadic arguments (`conf set` pairs,
  `es notables update` event ids) and repeatable options
  (`rules export --name`, `--set`) advertised `string` schemas; they
  are arrays now. Positional values are emitted in Click argument
  order instead of client dict order (multi-positional commands like
  `conf set FILE STANZA PAIRS...` were order-sensitive), and
  JSON-encoded array strings from sloppy clients are tolerated.
- **MCP `usage` re-registration** — `usage` on a command already loaded
  via `focus` left a stale tracking entry that blocked re-loading the
  tool after `unfocus`.
- **server cluster/shcluster/deployment** disabled-state `detail` now
  carries the REST message text instead of `str(exc)` with an embedded
  `b'...'` bytes literal.
- **tags list/get** URL-decode stanza names
  (`eventtype=cim:audit_account`, not `...cim%3Aaudit_account`);
  `tags get` accepts either form.

### Added
- **server health** — component-level splunkd health report
  (scheduler, disk, KV store, ingestion latency...) flattened to one
  row per component with reason text for unhealthy nodes; reports
  without gating (red still exits 0).
- **server license --usage** — today's indexed volume vs licensed
  daily quota, valid-license count, soonest expiry.
- **server search-peers** — distributed-search peer status/replication/
  version; clean empty on standalone.
- **MCP protocol test suite** — in-memory client/server integration
  tests covering the initialize handshake, focus/unfocus lifecycle
  with list_changed notifications, usage auto-registration, resources,
  and error paths.
- **MCP schema polish** — `serverInfo.version` reports the splunkctl
  version; guarded tool schemas carry an explicit `yes` boolean;
  `additionalProperties: false` rejects typo'd params; `prompt=True`
  options are forced required so the subprocess can never hang.

### Docs
- SOAR REST API discovery reference
  ([docs/design/soar-api.md](docs/design/soar-api.md)) — live-verified
  endpoint inventory, auth model, query semantics, and recipes for the
  upcoming `splunkctl soar` arc (waves 30–34).
- Catalog refresh: `rules test` row, new server subcommands,
  alert-actions SDK entity marked not-needed.

## 0.5.0

- **Built-in MCP server** — 5 meta-tools with progressive discovery;
  typed tools auto-generated from Click; `guide://` resources.
- **vmlab** — unattended SIEM + SOAR lab provisioning scripts.

## 0.4.0 – 0.4.1

Bank-SOC readiness: ES triage, compliance audit, KV store CRUD,
config-as-code `state pull/diff/push`, generic conf editor, macros,
eventtypes/tags, datamodels, structured JSON error envelopes, uniform
list paging, multi-instance profiles, lookup wiring, alert-action
flags. 0.4.1: cleanup pass (shared helpers, timeout kinds, scoping).

### New command groups
- **es notables** — ES incident-review loop (list/get/update with
  status, owner, urgency, disposition, comment via `notable_update`);
  feature-detected on `SplunkEnterpriseSecuritySuite`.
- **audit changes** — normalized `_audit` event stream (both legacy text
  and structured JSON shapes) into one six-key schema; client-side
  filters, zero user input composed into SPL.
- **audit rbac** — users × roles × capabilities × index-restrictions
  attestation view with transitive imported-role closure; csv-exportable
  for periodic access recertification.
- **kvstore** — KV store collection + document CRUD over raw REST
  (create/delete/query/insert/update/remove/export/import with JSONL
  round-trip and 500-doc batch chunking); UrlEncoded path-segment
  escaping for CIDR-notation keys.
- **conf** — generic conf-file/stanza editor (files/list/get/set/unset/
  reload) over any conf file; shared `conf_ops` core extracted from
  `parsers` (parsers behavior unchanged).
- **macros** — list/get/set with arg-form stanza resolution (`name(n)`);
  delegates to `conf_ops`.
- **eventtypes** / **tags** — read-only list/get over `eventtypes.conf`
  and `tags.conf`; tags shows enabled-only by default.
- **datamodels** — list/get (with `--definition`)/acceleration status/
  rebuild (guarded); acceleration sourced from `admin/summarization`.
- **state** — unified config-as-code pull/diff/push across rules,
  parsers, macros, lookups, and dashboards (diff-only). Change-evidence
  JSON report artifact written on both dry-run and `--yes` for
  change-ticket workflows. Push never deletes instance objects.
- **server cluster / shcluster / deployment** — read-only topology
  health (indexer cluster peers + SF/RF, SH cluster captain/members,
  deployment server clients); graceful not-enabled on single instances.

### Enhancements
- **Structured JSON error envelope** — under `--json` or piped output,
  errors emit `{"error": {"kind", "http_status", "message"}}` on stderr
  with a typed kind taxonomy (auth/permission/not_found/conflict/http/
  connection/timeout); `not_found` wired at every lookup-miss site.
- **Uniform list paging** — `--limit`/`--offset`/`--filter` on all 13
  list surfaces; no silent truncation (SDK fetch-all default locked in
  with a regression guard).
- **Multi-instance profiles** — named profiles in config.yaml with
  `config use <profile>` and `--profile` global flag; bank-safety guard
  banner prints `(profile: <name> @ host:port)` on every dry-run/`--yes`
  confirmation; no-network guarantee for banner construction.
- **Lookup wiring** — `lookups define` (transforms.conf definition
  binding file or KV store collection → fields) and `lookups auto`
  (props.conf `LOOKUP-*` automatic-lookup wiring with OUTPUT/OUTPUTNEW
  and AS renames); delegates to `conf_ops`.
- **First-class alert-action flags** — `--email-to`, `--email-subject`,
  `--webhook-url` on `rules create/update` (sugar over `--set`);
  conflict with equivalent `--set` → exit 2; integrated with the
  missing-field dry-run warning.

### Fixes
- **SPL injection** — shared `spl_quote` helper escapes backslashes
  before quotes, closing a filter-breakout primitive in the `name=`
  search filter (rules, es notables).
- **config init** never clobbers an existing multi-profile file (folds
  into `profiles.default` instead).
- **conf set/unset** classify missing-stanza and missing-file errors at
  apply time (not raw tracebacks).
- **datamodels rebuild** uses the resolved canonical model name on the
  wire (not the user's possibly wrong-cased input).

## 0.3.1 and earlier

See [GitHub releases](https://github.com/dannyota/splunkctl/releases)
for the full history: 0.3.1 (SOC bug-fix wave), 0.3.0 (server/HEC/
parsers/dashboards expansion, 321 tests), 0.2.0 (initial public
release), 0.1.0 (scaffold).
