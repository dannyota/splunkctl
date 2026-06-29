# splunkctl

CLI tool for Splunk Enterprise SIEM operations.

Query, inspect, and manage a Splunk Enterprise instance from the terminal.
Built on the [splunk-sdk-python](https://github.com/dannyota/splunk-sdk-python)
fork with [Click](https://click.palletsprojects.com/).

## Install

```bash
pip install splunkctl
```

Requires Python 3.13+.

## Quick start

```bash
splunkctl config init                         # interactive setup
splunkctl config test                         # verify connectivity
splunkctl search run 'index=main | head 10'   # run a search
splunkctl rules list                          # list detection rules
splunkctl dashboards list                     # list dashboards
```

## Commands

| Group | Description |
|---|---|
| `config` | Setup, show config, test connectivity |
| `info` | Server info (version, OS, license) |
| `search` | Run, export, oneshot, job management |
| `rules` | Detection rules (saved searches) — full CRUD |
| `alerts` | Fired alerts, alert actions, suppression |
| `dashboards` | Dashboard CRUD (XML) |
| `indexes` | Index management |
| `inputs` | Data inputs (monitor, tcp, udp, script, http) |
| `lookups` | Lookup table CRUD (CSV) |
| `parsers` | Source types and field extractions |
| `apps` | App install, uninstall, update |
| `users` | User and role management |
| `commands` | Machine-readable command tree (JSON) |
| `skill` | Embedded agent operating guide |

## Global flags

```
--json              Force JSON output
--format FMT        Output format: table, json, csv, jsonl
--fields f1,f2      Project specific fields
--out FILE          Write output to file
--yes / -y          Apply mutations (skip dry-run preview)
--timeout N         Request timeout in seconds (default 30)
--config FILE       Config file path
--debug             HTTP request/response logging
```

## Dry-run by default

All write operations preview what would change. Pass `--yes` to apply.

```bash
splunkctl rules delete 'My Rule'          # shows preview only
splunkctl rules delete 'My Rule' --yes    # actually deletes
```

## Output formats

```bash
splunkctl rules list                      # table (TTY) or JSON (pipe)
splunkctl rules list --json               # force JSON
splunkctl rules list --format csv         # CSV
splunkctl rules list --fields name,cron   # project fields
splunkctl rules list --out rules.json     # write to file
```

## Agent integration

splunkctl ships with an embedded operating guide for AI agents
(Claude Code, etc.):

```bash
splunkctl skill                           # print the guide
splunkctl skill install                   # install to ~/.claude/skills/
splunkctl commands                        # JSON command tree for discovery
```

## License

Apache-2.0
