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
(filter first, then paging; defaults fetch everything) — see SKILL.md.

| Group | Status | Subcommands |
|---|---|---|
| `config` | ✅ built | init (--profile), show (--profile), use, test — multi-instance profiles |
| `info` | ✅ built | (default) |
| `search` | ✅ built | run (--detach), export, oneshot, jobs, job (--offset/--count/--events/--status-only), cancel, upload |
| `rules` | ✅ built | list (--filter, --app, --owner), get (--app, --owner), create, update, delete, enable, disable, share, history |
| `rules import/export` | ✅ built | YAML round-trip with alert semantics, dry-run diff |
| `alerts` | ✅ built | list, get, actions, suppress, unsuppress |
| `dashboards` | ✅ built | list (type column), get (--definition), create (--type classic/studio/auto, --sharing), update (diff preview), delete, export (--definition, --all --dir), share |
| `indexes` | ✅ built | list, get, create, update, delete, clean, reload |
| `inputs` | ✅ built | list, get, create, update, delete, enable, disable |
| `lookups` | ✅ built | list, get, upload, update, download, delete |
| `hec` | ✅ built | list, get, create (--set), delete, enable, disable, settings (--enable/--disable), send |
| `parsers` | ✅ built | sourcetypes, get (--key), set, unset, create, update, delete, reload |
| `parsers import/export` | ✅ built | YAML round-trip for props/transforms stanzas |
| `conf` | ✅ built | files (--app), list (--app), get (--key), set (diff preview), unset, reload — generic stanza editor for any conf file (macros/eventtypes/tags/authorize/...), no blocklist; shares its stanza get/set/unset/reload core with `parsers` via `conf_ops.py` |
| `macros` | ✅ built | list (--app, F2 paging/filter, arg-form stanza `name(n)`), get (--app, resolves bare name to its arg-form), set (--definition, --args, diff preview) — thin `conf_ops` wrapper over `macros.conf`; only mutation in this group |
| `eventtypes` | ✅ built | list (--app, F2 paging/filter), get (--app) — read-only `conf_ops` wrapper over `eventtypes.conf` |
| `tags` | ✅ built | list (--app, F2 paging/filter, enabled-tags-only summary), get (--app, full enabled/disabled breakdown) — read-only `conf_ops` wrapper over `tags.conf`'s `field=value` stanza shape |
| `apps` | ✅ built | list, get, install, uninstall, update, reload |
| `users` | ✅ built | list, get, create, update (--password), delete |
| `users roles` | ✅ built | list, get, create, update, delete |
| `server` | ✅ built | messages (--dismiss), license, kvstore |
| `es` | ✅ built | notables list (--since/--until/--status/--owner/--rule/--limit), get, update (bulk triage via `notable_update`) — feature-detected on `SplunkEnterpriseSecuritySuite`; live-verified against ES: pending (local dev instance has SSE, not ES) |
| `audit` | ✅ built | changes (--since/--until/--user/--action/--object-type/--limit, normalizes both `_audit` event shapes, zero SPL composition), rbac (--roles-only, transitive capability/index aggregation) — read-only, live-verified |
| `kvstore` | ✅ built | collections (--app), create, delete, query (--query/--limit/--skip/--sort), insert/update/remove (--data/--file/--query), export/import (JSONL, batch_save chunked at 500) — raw REST (no SDK entity), F1-classified errors; live round-trip pending healthy KV store (local dev instance's KV store is down; negative path live-verified) |
| `doctor` | ✅ built | Connection/auth/health/permissions/skill check, --strict, remediation hints |
| `commands` | ✅ built | Machine-readable JSON tree with guard markers, global options |
| `skill` | ✅ built | print, install |

## Agent integration

| Feature | Status | Notes |
|---|---|---|
| `SKILL.md` | ✅ built | Full agent operating guide |
| `commands --json` | ✅ built | Guard markers, global options, note field |
| `skill install` | ✅ built | Write to `~/.claude/skills/` |
| `doctor --strict` | ✅ built | CI-friendly health gate |
| JSON error envelope | ✅ built | `--json`/`--format json` errors as one `jq`-able stderr line: kind + http_status + message |
| Multi-instance profiles | ✅ built | `profiles:`/`current:` config schema v2, `--profile` global flag, guard banner (`profile`/`env`/`flags` source) on every dry-run and `--yes` confirmation, no network I/O |

## SDK fork status

Gaps to fill in `dannyota/splunk-sdk-python`:

| Gap | Status | Target |
|---|---|---|
| Dashboards | ✅ built | `Dashboard`/`Dashboards` on `splunkctl` branch |
| Lookup tables | ✅ built | `LookupTableFile`/`LookupTableFiles` on `splunkctl` branch |
| HEC tokens | ✅ built | `HECToken`/`HECTokens` on `splunkctl` branch |
| Alert actions | - planned | Extend `SavedSearch` |
