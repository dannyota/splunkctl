# splunkctl docs

CLI tool for Splunk Enterprise SIEM operations — query, inspect, and manage a
Splunk instance from the terminal. Built on the
[splunk-sdk-python](https://github.com/dannyota/splunk-sdk-python) fork with
[Click](https://click.palletsprojects.com/).

> All write operations are **dry-run by default** — nothing changes until you
> pass `--yes`.

New here? **[Install](guides/install.md) → [Configure](guides/configure.md) →
[Search](guides/search.md).** Building it?
**[Architecture](design/architecture.md).** Status of every command group?
**[Catalog](design/catalog.md).**

## Quick start

```bash
pip install splunkctl
splunkctl config init                    # interactive setup
splunkctl config test                    # verify connectivity
splunkctl search run 'index=main | head 10'
```

## Command groups

| Group | What it does |
|---|---|
| `config` | Setup, show config, test connectivity |
| `search` | Run SPL queries, manage search jobs |
| `rules` | Detection rules (saved searches) CRUD |
| `alerts` | Fired alerts, alert actions |
| `dashboards` | Dashboard CRUD |
| `indexes` | Index management |
| `inputs` | Data input management |
| `lookups` | Lookup table management |
| `parsers` | Source types and field extractions |
| `apps` | Installed app management |
| `users` | User and role management |
| `commands` | Self-discovery for agents (`--json`) |
| `skill` | Print/install the agent operating guide |
| `info` | Server info and license |

## Find your way

| Folder | For | Start here |
|---|---|---|
| **[guides/](guides/)** | using splunkctl | [Install](guides/install.md) → [Configure](guides/configure.md) → [Search](guides/search.md) |
| **[design/](design/)** | building splunkctl | [Architecture](design/architecture.md) · [Catalog](design/catalog.md) |
