# Changelog archive

Older releases, moved out of [CHANGELOG.md](../CHANGELOG.md).

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
