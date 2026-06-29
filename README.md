# splunkctl

CLI tool for Splunk Enterprise SIEM operations.

Query, inspect, and manage a remote Splunk Enterprise instance from your
laptop. Built on the [splunk-sdk-python](https://github.com/dannyota/splunk-sdk-python/tree/splunkctl)
fork with [Click](https://click.palletsprojects.com/).

## Install

```bash
pip install git+https://github.com/dannyota/splunkctl
```

Requires Python 3.13+. The forked SDK (`splunkctl` branch) is installed
automatically as a dependency.

### Development

```bash
git clone https://github.com/dannyota/splunkctl
cd splunkctl
pip install -e .
splunkctl --version
```

## Quick start

```bash
splunkctl config init                         # interactive setup
splunkctl doctor                              # check connection, auth, permissions
splunkctl search run 'index=main | head 10'   # run a search
splunkctl rules list                          # list detection rules
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

Export existing rules to YAML, version control them, deploy across
instances:

```bash
splunkctl rules export --path detections.yml
splunkctl rules import --path detections.yml        # dry-run preview
splunkctl --yes rules import --path detections.yml  # apply
```

### Remote file operations

Upload files from your laptop without SSH access to the server:

```bash
# Upload threat intel, logs, or sample data for indexing
splunkctl --yes search upload --path threats.csv --index threat_intel --sourcetype csv

# Upload lookup tables (CSV or GeoIP mmdb)
splunkctl --yes lookups upload --name threats.csv --path threats.csv

# Install apps from local .spl/.tar.gz packages
splunkctl --yes apps install --path TA_windows.spl
```

### Diagnostics

```bash
splunkctl doctor             # check everything: connection, auth, health, permissions
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

## SDK fork

splunkctl depends on a [fork of splunk-sdk-python](https://github.com/dannyota/splunk-sdk-python/tree/splunkctl)
that adds entity classes missing from the upstream SDK:

| Entity | Service property | Purpose |
|---|---|---|
| `Dashboard` | `service.dashboards` | Dashboard CRUD |
| `LookupTableFile` | `service.lookup_table_files` | Lookup table metadata + download |
| `HECToken` | `service.hec_tokens` | HEC token management |

Install the fork directly:

```bash
pip install git+https://github.com/dannyota/splunk-sdk-python@splunkctl
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
