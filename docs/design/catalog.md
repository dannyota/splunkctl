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
| `config.py` | - planned | Config file management |
| `client.py` | - planned | SDK wrapper, lazy auth |
| `output.py` | - planned | Dual output (table/JSON) |
| `guard.py` | - planned | Mutation guard (dry-run/--yes) |

## Command groups

| Group | Status | SDK | Notes |
|---|---|---|---|
| `config` | - planned | N/A | Interactive setup, show, test |
| `search` | - planned | `splunklib.client.Jobs` | run, export, oneshot, jobs |
| `rules` | - planned | `splunklib.client.SavedSearches` | Detection rule CRUD |
| `alerts` | - planned | `splunklib.client.FiredAlerts` | Fired alerts, actions |
| `dashboards` | - planned | Raw REST | SDK gap — `/services/data/ui/views/` |
| `indexes` | - planned | `splunklib.client.Indexes` | Index management |
| `inputs` | - planned | `splunklib.client.Inputs` | Data input management |
| `lookups` | - planned | Raw REST | SDK gap — `/services/data/lookup-table-files/` |
| `parsers` | - planned | `splunklib.client.Confs` | props.conf / transforms.conf |
| `apps` | - planned | `splunklib.client.Apps` | App management |
| `users` | - planned | `splunklib.client.Users` | Users and roles |
| `commands` | - planned | N/A | Self-discovery (`--json`) |
| `skill` | - planned | N/A | Print/install SKILL.md |
| `info` | - planned | `splunklib.client.info` | Server info, license |

## Agent integration

| Feature | Status | Notes |
|---|---|---|
| `SKILL.md` | 🔨 scaffolded | Placeholder — full guide pending |
| `commands --json` | - planned | Machine-readable command tree |
| `skill install` | - planned | Write to `~/.claude/skills/` |

## SDK fork status

Gaps to fill in `dannyota/splunk-sdk-python`:

| Gap | Status | Target |
|---|---|---|
| Dashboards | - planned | `DashboardView`/`DashboardViews` |
| Lookup tables | - planned | `LookupTableFile`/`LookupTableFiles` |
| HEC tokens | - planned | `HECToken` wrapping `/services/data/inputs/http/` |
| Alert actions | - planned | Extend `SavedSearch` |
