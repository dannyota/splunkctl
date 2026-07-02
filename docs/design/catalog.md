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
| `config.py` | ✅ built | Config file management, env overlay, redact |
| `client.py` | ✅ built | SDK wrapper, lazy auth, Web UI session |
| `output.py` | ✅ built | Dual output (table/JSON/CSV/JSONL), empty-list contract |
| `guard.py` | ✅ built | Mutation guard (dry-run/--yes), `@guarded` markers |

## Command groups

| Group | Status | Subcommands |
|---|---|---|
| `config` | ✅ built | init, show, test |
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
| `apps` | ✅ built | list, get, install, uninstall, update, reload |
| `users` | ✅ built | list, get, create, update (--password), delete |
| `users roles` | ✅ built | list, get, create, update, delete |
| `server` | ✅ built | messages (--dismiss), license, kvstore |
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

## SDK fork status

Gaps to fill in `dannyota/splunk-sdk-python`:

| Gap | Status | Target |
|---|---|---|
| Dashboards | ✅ built | `Dashboard`/`Dashboards` on `splunkctl` branch |
| Lookup tables | ✅ built | `LookupTableFile`/`LookupTableFiles` on `splunkctl` branch |
| HEC tokens | ✅ built | `HECToken`/`HECTokens` on `splunkctl` branch |
| Alert actions | - planned | Extend `SavedSearch` |
