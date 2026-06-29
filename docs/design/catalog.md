# Catalog & status

The source of truth for **what exists and how mature it is** — one status per
command group, updated in the same commit that moves it forward.

**Status legend**

| | Status | Meaning |
|:-:|---|---|
| - | **planned** | designed, code not started |
| 🔨 | **scaffolded** | stub file exists, no logic |
| ✅ | **built** | functional, tested |

## Core infrastructure

These are shared modules used by all command groups.

| Module | Status | Notes |
|---|---|---|
| `main.py` | ✅ built | Click entry point, global flags |
| `config.py` | ✅ built | Config file management, env overlay, redact |
| `client.py` | ✅ built | SDK wrapper, lazy auth |
| `output.py` | ✅ built | Dual output (table/JSON/CSV/JSONL) |
| `guard.py` | ✅ built | Mutation guard (dry-run/--yes) |

## Command groups

| Group | Status | SDK | Notes |
|---|---|---|---|
| `config` | ✅ built | N/A | init, show, test |
| `info` | ✅ built | `splunklib.client.info` | Server info |
| `search` | ✅ built | `splunklib.client.Jobs` | run, export, oneshot, jobs, job, cancel |
| `rules` | ✅ built | `splunklib.client.SavedSearches` | list, get, create, update, delete, enable, disable, history |
| `alerts` | ✅ built | `splunklib.client.FiredAlerts` | list, get, actions, suppress |
| `dashboards` | ✅ built | `splunklib.client.Dashboards` | list, get, create, update, delete, export |
| `indexes` | ✅ built | `splunklib.client.Indexes` | list, get, create, update, delete, clean, reload |
| `inputs` | ✅ built | `splunklib.client.Inputs` | list, get, create, update, delete, enable, disable |
| `lookups` | ✅ built | `splunklib.client.LookupTableFiles` | list, get, upload, update, download, delete |
| `hec` | ✅ built | `splunklib.client.HECTokens` | list, get, create, delete, enable, disable |
| `parsers` | ✅ built | `splunklib.client.Confs` | sourcetypes, get, extractions, create, update, delete |
| `apps` | ✅ built | `splunklib.client.Apps` | list, get, install, uninstall, update, reload |
| `users` | ✅ built | `splunklib.client.Users` | list, get, roles, create, update, delete |
| `commands` | ✅ built | N/A | Self-discovery (`--json`) |
| `skill` | ✅ built | N/A | Print/install SKILL.md |

## Agent integration

| Feature | Status | Notes |
|---|---|---|
| `SKILL.md` | ✅ built | Full agent operating guide |
| `commands --json` | ✅ built | Machine-readable command tree |
| `skill install` | ✅ built | Write to `~/.claude/skills/` |

## SDK fork status

Gaps to fill in `dannyota/splunk-sdk-python`:

| Gap | Status | Target |
|---|---|---|
| Dashboards | ✅ built | `Dashboard`/`Dashboards` on `splunkctl` branch |
| Lookup tables | ✅ built | `LookupTableFile`/`LookupTableFiles` on `splunkctl` branch |
| HEC tokens | ✅ built | `HECToken`/`HECTokens` on `splunkctl` branch |
| Alert actions | - planned | Extend `SavedSearch` |
