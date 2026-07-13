# Catalog & status

The source of truth for **what exists and how mature it is** — one status per
command group, updated in the same commit that moves it forward.

**Status legend**

| | Status | Meaning |
|:-:|---|---|
| - | **planned** | designed, code not started |
| ✅ | **built** | functional, tested |

## Core infrastructure

| Module | Status | Notes |
|---|---|---|
| `main.py` | ✅ built | Click entry point, global flags |
| `config.py` | ✅ built | Profiles (schema v2) + legacy fallback, env overlay, redact |
| `client.py` | ✅ built | SDK wrapper, lazy auth, Web UI session |
| `output.py` | ✅ built | Dual output (table/JSON/CSV/JSONL), empty-list contract |
| `guard.py` | ✅ built | Mutation guard (dry-run/--yes), `@guarded` markers, profile/host banner |

## Command groups

All list surfaces accept uniform `--limit`/`--offset`/`--filter` options
(filter first, then paging; defaults fetch everything). Computed views
that are not SDK list surfaces (e.g. `audit rbac`) are exempt by design.

| Group | Status | Subcommands |
|---|---|---|
| `config` | ✅ built | init (--profile), show (--profile), use, test — multi-instance profiles |
| `info` | ✅ built | (default) |
| `search` | ✅ built | run (--detach), export, oneshot, jobs, job (--offset/--count/--events/--status-only), cancel, upload |
| `rules` | ✅ built | list (--filter, --app, --owner), get (--app, --owner), create (--email-to/--email-subject/--webhook-url conflict with --set), update (same), delete, enable, disable, share, history, test (dispatch now, alert actions suppressed) |
| `rules import/export` | ✅ built | YAML round-trip with alert semantics, dry-run diff |
| `alerts` | ✅ built | list, get, actions, suppress, unsuppress |
| `dashboards` | ✅ built | list (type column), get (--definition), create (--type classic/studio/auto, --sharing), update (diff preview), delete, export (--definition, --all --dir), share |
| `indexes` | ✅ built | list, get, create, update, delete, clean, reload |
| `inputs` | ✅ built | list, get, create, update, delete, enable, disable |
| `lookups` | ✅ built | list, get, upload, update, download, delete, define (--file/--collection), auto (LOOKUP-* wiring), definitions |
| `hec` | ✅ built | list, get, create (--set), delete, enable, disable, settings (--enable/--disable), send |
| `parsers` | ✅ built | sourcetypes, get (--key), set, unset, create, update, delete, reload |
| `parsers import/export` | ✅ built | YAML round-trip for props/transforms stanzas |
| `conf` | ✅ built | files (--app), list (--app), get (--key), set (diff preview), unset, reload — generic stanza editor for any conf file (macros/eventtypes/tags/authorize/...), no blocklist; shares its stanza get/set/unset/reload core with `parsers` via `conf_ops.py` |
| `macros` | ✅ built | list (--app, F2 paging/filter, arg-form stanza `name(n)`), get (--app, resolves bare name to its arg-form), set (--definition, --args, diff preview) — thin `conf_ops` wrapper over `macros.conf`; only mutation in this group |
| `eventtypes` | ✅ built | list (--app, F2 paging/filter), get (--app) — read-only `conf_ops` wrapper over `eventtypes.conf` |
| `tags` | ✅ built | list (--app, F2 paging/filter, enabled-tags-only summary), get (--app, full enabled/disabled breakdown) — read-only `conf_ops` wrapper over `tags.conf`'s `field=value` stanza shape |
| `datamodels` | ✅ built | list (--app, F2 paging/filter), get (--app, --definition), acceleration (`[name]`, build status: percent complete/summarized range/size/last error), rebuild (guarded, disable-then-re-enable) — no SDK entity, raw REST over `datamodel/model` + `admin/summarization`; live-verified for list/get/acceleration and rebuild's dry-run/not-accelerated paths, `rebuild --yes`/populated acceleration status unit-tested only (no CIM data model installed on the local dev instance) |
| `apps` | ✅ built | list, get, install, uninstall, update, reload |
| `users` | ✅ built | list, get, create, update (--password), delete |
| `users roles` | ✅ built | list, get, create, update, delete |
| `server` | ✅ built | messages (--dismiss), license (--usage: daily volume vs quota + soonest expiry), kvstore, health (component-level splunkd health report, flattened tree + reason text), cluster (indexer cluster health: mode/peers/SF-RF, manager→master fallback), shcluster (SH cluster: captain/members/replication), deployment (deployment server clients/check-in), search-peers (distributed-search peer status; empty on standalone) — topology/health reads are read-only with graceful not-enabled handling (exit 0 on non-clustered instances); live-verified |
| `es` | ✅ built | notables list (--since/--until/--status/--owner/--rule/--limit), get, update (bulk triage via `notable_update`) — feature-detected on `SplunkEnterpriseSecuritySuite`; live-verified against ES: pending (local dev instance has SSE, not ES) |
| `audit` | ✅ built | changes (--since/--until/--user/--action/--object-type/--limit, normalizes both `_audit` event shapes, zero SPL composition), rbac (--roles-only, transitive capability/index aggregation) — read-only, live-verified |
| `kvstore` | ✅ built | collections (--app), create, delete, query (--query/--limit/--skip/--sort), insert/update/remove (--data/--file/--query), export/import (JSONL, batch_save chunked at 500) — raw REST (no SDK entity), F1-classified errors; live round-trip pending healthy KV store (local dev instance's KV store is down; negative path live-verified) |
| `state` | ✅ built | pull (--dir/--app/--types), diff (--dir/--app/--types, structured drift, exit 0 always), push (guarded, --dir/--app/--types/--report) — unified config-as-code across rules/parsers/macros/lookups/dashboards, orchestrating `rules_io`/`parsers_io`/`conf_ops`/`client.upload_lookup` (no re-implemented serialization/apply); dashboards is pull+diff only (no import path); push never deletes (`removed` drift is reported, never applied); `--report` writes the before→after change-ticket artifact on both dry-run (`applied:false`) and `--yes` (`applied:true`); live-verified full pull→edit→diff→push→report cycle |
| `doctor` | ✅ built | Connection/auth/health/KV store/permissions/MCP check, --strict, hints |
| `commands` | ✅ built | Machine-readable JSON tree with guard markers, global options |
| `mcp` | ✅ built | serve (stdio MCP server), install (.mcp.json registration) |

## SOAR command groups

| Group | Status | Subcommands |
|---|---|---|
| `soar` | ✅ built | test, info, health, license, settings, stats, meta — platform reads via `SOARClient`; typed error envelopes; live-verified against lab SOAR 8.5.0.248 |
| `soar containers` | ✅ built | list (--label/--status/--severity/--owner/--since/--type/--filter/--limit/--offset; status validated via container_status), get (--artifacts/--notes/--comments/--audit/--activity/--playbook-runs/--phases sub-views), create (--name/--label/--severity/--sensitivity/--sdi/--description/--tag/--field; SDI dedup precheck), update (single+bulk array POST; --name/--label/--severity/--sensitivity/--description/--status/--owner/--role/--tag/--field; status by NAME only; tags read-modify-write per container at apply time), close (sugar for status=closed; single+bulk), assign (--owner OR --role, mutually exclusive; names resolved to owner_id/role_id, read-back verified; single+bulk), delete (Basic auth; cascading) |
| `soar artifacts` | ✅ built | list (--container, --limit/--offset), get, create (--name/--cef/--cef-file/--cef-type/--sdi/--severity/--type/--no-automation; auto cef_types from CEF contains map; SDI dedup precheck with warning), update (fetch-merge CEF or --replace-cef; --name/--severity/--type), delete |
| `soar vault` | ✅ built | list (--container), get (vault_id via vault_document hash), upload (--container, base64, >30 MB warning), download (vault_id, --out), delete (container_attachment id; 405 explanation); upload/download byte-identical round-trip verified |
| `soar notes` | ✅ built | list (--container, --task), add (content arg or --file, --title, --task-id), delete, comment (container_id + text; immutable), comment-delete (exits with immutability explanation, no API call) |
| `soar apps` | ✅ built | list (--installed via `_exclude_install_status=staged`, --category, --limit), get (config schema + --actions for supported actions) |
| `soar assets` | ✅ built | list (--limit), get, create (--name/--app-id/--set/--file/--description; secrets masked in preview), update (fetch-merge-post by default, --replace for full replace; --set/--file/--name/--description; secrets masked), delete, test (POST asset/<id>/test + poll app_status; async caveat documented) |
| `soar ingest-status` | ✅ built | /rest/ingestion_status + app_status rollup; per-poller records with app health |
| `soar playbooks` | ✅ built | list (--active/--label/--repo, repo name resolved to scm id), get, enable (guarded; draft_mode caveat), disable (--cancel-runs), trigger (--on artifact_created/container_resolved; label is import-metadata only, API rejects it), export (by id, scoped name, or bare module name via suffix match; --unpack json+py; --out), import (dir or tgz; --scm/--force; base64 POST import_playbook), repos (scm list), sync (pull+force; local-repo 400/500 explained), delete (Web UI route — no REST deletion exists; username/password required; exact name or id only, guarded, per-item change/error report), run (name or id, --container, --scope all/new, --input k=v, --wait/--timeout; name resolution via GET /rest/playbook; guarded mutation; polls to terminal status), runs list (--container, --status, --limit), runs get (--blocks for block_results), runs cancel (guarded; pre-checks terminal status); first playbooks-as-code loop; splunkctl_seed_noop fixture for round-trip testing |
| `soar actions` | ✅ built | run (--action/--asset/--app/--container/--param/--type/--name/--wait/--timeout; app_id resolved from asset record; targets[].assets carry names; dry-run previews exact payload), list (--container/--limit/--offset), status (action_run_id), results (per-asset app_runs detail), cancel (guarded) |
| `soar functions` | ✅ built | list (--limit/--offset), get, import (dir or tgz, base64 POST import_custom_function, force:true), export (tgz via GET custom_function/<id>/export, --out), update (--python/--message, auto SCM id resolution, fetch-merge-post, auto Python 2.7→3 upgrade), delete (Basic auth) |
| `soar cases` | ✅ built | promote (--template name or id; resolves via workbook_template; atomic container_type+template POST), workbook (phases + nested tasks view), phase add (--container/--name/--order), task add (--phase-id/--name/--description/--order), task update (--status incomplete/in_progress/complete mapped to integer codes 0/1/2, --owner, --note; client-side closing-note enforcement for in_progress); live-verified: NIST 800-61 promote creates 5 phases/19 tasks, 0→2 works, 0→1 without note blocked |
| `soar approvals` | ✅ built | list (--container/--pending), get (detail_summary_view), respond (approve/deny, --message; guarded; POST external_prompt) |
| `soar lists` | ✅ built | list (--limit), get (name or id), create (--name, --file JSON/CSV; CSV parsed client-side), update (full-replace via --file), add-row (--values; fetch-modify-replace), remove-row (--index; fetch-modify-replace), delete (token auth OK), export (--format json/csv; CSV via formatted_content route, --out), import (--name --file; create-or-update) |
| `soar indicators` | ✅ built | list (--type/--limit; feature-flag gated), get (indicator_by_value), pivot (common containers for an IOC), stats (type + severity aggregations); all commands exit 1 with actionable message when `use_indicators` flag is off |
| `soar evidence` | ✅ built | list (--container), add (--object artifact\|note\|action_run --id; guarded), remove (guarded; Basic auth) |
| `soar users` | ✅ built | list (--type normal/automation; surfaces hidden system automation user), get, create (--username/--password/--type/--role/--allowed-ip/--first-name/--last-name; token-provisioning reality notice for automation type), update (--password masked/--add-role/--remove-role read-modify-write/--first-name/--last-name/--allowed-ip), delete (soft-delete is_active=False; dry-run explains semantics), token (hashed key + expiry; explicit NOT-usable-token notice) |
| `soar roles` | ✅ built | list (permission matrix), get (single role with permissions) — 7 immutable built-in roles |
| `soar audit` | ✅ built | query audit log (bare-array normalized; --user/--playbook/--container/--start/--end/--format csv/--limit) |
| `soar search` | ✅ built | search QUERY (--categories comma-list, --page-size, --page; 1-based pagination; cross-object free-text via /rest/search); live-verified |
| `soar ingest` | ✅ built | SIEM search results to SOAR containers+artifacts (--spl/--sid, --label/--severity/--sensitivity/--sdi-field/--container-name/--container-name-field/--grouping/--map/--map-file/--include-unmapped/--no-automation/--earliest/--latest/--app); built-in CIM_CEF_MAP (bytesIn typo fixed) + CEF_CONTAINS_MAP; auto severity from severity/urgency; client-side SDI dedup precheck; last-artifact-true automation batching; dry-run preview: container count, artifacts per container, mapping table, sample CEF; notable recipe (event_id SDI, rule_name naming) |

## SOAR infrastructure

| Module | Status | Notes |
|---|---|---|
| `soar/client.py` | ✅ built | SOARClient — requests-based, lazy, normalizing; dual auth (token + Basic fallback for DELETE); `get_bytes` for binary downloads |
| `config.py` SOAR | ✅ built | `resolve_soar`, `redact_soar`, `SOAR_*` env overlay, profile `soar:` section |

## Agent integration

| Feature | Status | Notes |
|---|---|---|
| MCP server | ✅ built | 5 meta-tools (help/usage/focus/unfocus/run), 229 auto-generated typed tools (array schemas for variadic/repeated params, explicit `yes` on guarded schemas, additionalProperties:false), subgroup-granular focus for the nested soar tree, 33 guide resources, protocol-level test suite |
| `mcp install` | ✅ built | Write `.mcp.json` for Claude Code registration |
| `commands --json` | ✅ built | Guard markers, global options, note field |
| `doctor --strict` | ✅ built | CI-friendly health gate |
| `docs generate` | ✅ built | Hidden maintainer command: per-group reference pages in `docs/commands/` + sidebar sync from the Click tree; `--check` is the CI freshness gate |
| JSON error envelope | ✅ built | `--json`/`--format json` errors as one `jq`-able stderr line: kind + http_status + message |
| Multi-instance profiles | ✅ built | `profiles:`/`current:` config schema v2, `--profile` global flag, guard banner (`profile`/`env`/`flags` source) on every dry-run and `--yes` confirmation, no network I/O |

## SDK fork status

Gaps to fill in `dannyota/splunk-sdk-python`:

| Gap | Status | Target |
|---|---|---|
| Dashboards | ✅ built | `Dashboard`/`Dashboards` on `splunkctl` branch |
| Lookup tables | ✅ built | `LookupTableFile`/`LookupTableFiles` on `splunkctl` branch |
| HEC tokens | ✅ built | `HECToken`/`HECTokens` on `splunkctl` branch |
| Alert actions | not needed | Shipped as first-class CLI flags over `--set action.*` (Wave 25); no SDK entity required |
