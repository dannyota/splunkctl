# splunkctl

CLI tool for Splunk Enterprise SIEM operations — query, inspect, and manage a
remote Splunk instance from your laptop. Built on the
[splunk-sdk-python](https://github.com/dannyota/splunk-sdk-python/tree/splunkctl)
fork with [Click](https://click.palletsprojects.com/).

> All write operations are **dry-run by default** — nothing changes until you
> pass `--yes`.

## Quick start

```bash
pip install git+https://github.com/dannyota/splunkctl
splunkctl config init                    # interactive setup
splunkctl doctor                         # check connection, auth, permissions
splunkctl search run 'index=main | head 10'
```

## Commands

| Group | Description |
|---|---|
| `doctor` | Connection, auth, health, and permissions check |
| `config` | Setup, show config, test connectivity |
| `info` | Server info (version, OS, license) |
| `search` | Run, export, oneshot, upload, job management |
| `rules` | Detection rules — CRUD, import/export (YAML) |
| `alerts` | Fired alerts, alert actions, suppression |
| `dashboards` | Dashboard CRUD (XML) |
| `indexes` | Index management |
| `inputs` | Data inputs (monitor, tcp, udp, script, http) |
| `lookups` | Lookup table CRUD (CSV, mmdb) |
| `hec` | HEC token management |
| `parsers` | Source types and field extractions |
| `apps` | App install (.spl/.tar.gz), uninstall, update |
| `users` | User and role management |
| `commands` | Machine-readable command tree (JSON) |
| `skill` | Embedded agent operating guide |

## Key features

### Detection-as-code

Export rules to YAML, version control them, deploy across instances:

```bash
splunkctl rules export --path detections.yml
splunkctl rules import --path detections.yml        # dry-run preview
splunkctl --yes rules import --path detections.yml  # apply
```

### Remote file operations

Upload files from your laptop without SSH access to the server:

```bash
splunkctl --yes search upload --path threats.csv --index threat_intel
splunkctl --yes lookups upload threats.csv --file threats.csv --app search
splunkctl --yes apps install --path TA_windows.spl
```

### Diagnostics

```bash
splunkctl doctor             # check everything
splunkctl doctor --json      # machine-readable output
```

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

## Output formats

```bash
splunkctl rules list                      # table (TTY) or JSON (pipe)
splunkctl rules list --json               # force JSON
splunkctl rules list --format csv         # CSV
splunkctl rules list --fields name,cron   # project fields
splunkctl rules list --out rules.json     # write to file
```

## SDK fork

splunkctl depends on a [fork of splunk-sdk-python](https://github.com/dannyota/splunk-sdk-python/tree/splunkctl)
that adds entity classes missing from the upstream SDK:

| Entity | Service property | Purpose |
|---|---|---|
| `Dashboard` | `service.dashboards` | Dashboard CRUD |
| `LookupTableFile` | `service.lookup_table_files` | Lookup table metadata + download |
| `HECToken` | `service.hec_tokens` | HEC token management |

## Agent integration

splunkctl ships with an embedded operating guide for AI agents:

```bash
splunkctl skill                           # print the guide
splunkctl skill install                   # install to ~/.claude/skills/
splunkctl commands                        # JSON command tree for discovery
```
