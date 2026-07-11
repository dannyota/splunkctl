# splunkctl

CLI tool for Splunk Enterprise and Splunk SOAR operations -- query, inspect,
and manage remote Splunk instances from your laptop. SIEM commands are built
on the
[splunk-sdk-python](https://github.com/dannyota/splunk-sdk-python/tree/splunkctl)
fork with [Click](https://click.palletsprojects.com/); SOAR commands use
`SOARClient`, a requests-based Django REST client with dual auth.

> All write operations are **dry-run by default** -- nothing changes until you
> pass `--yes`.

## Quick start

```bash
pip install git+https://github.com/dannyota/splunkctl
splunkctl config init                    # interactive SIEM setup
splunkctl config init --soar             # add SOAR credentials
splunkctl doctor                         # check SIEM connection
splunkctl soar test                      # check SOAR connection
splunkctl search run 'index=main | head 10'
splunkctl soar containers list
```

## Commands

| Group | Description |
|---|---|
| `doctor` | Connection, auth, health, and permissions check |
| `config` | Setup, profiles (dev/UAT/prod), test connectivity |
| `info` | Server info (version, OS, license) |
| `search` | Run, export, oneshot, upload, job management |
| `rules` | Detection rules -- CRUD, import/export (YAML), alert-action flags |
| `alerts` | Fired alerts, alert actions, suppression |
| `dashboards` | Dashboard CRUD (XML/JSON) |
| `indexes` | Index management |
| `inputs` | Data inputs (monitor, tcp, udp, script, http) |
| `lookups` | Lookup tables, definitions, automatic lookups |
| `hec` | HEC token management |
| `parsers` | Source types, field extractions, import/export |
| `conf` | Generic conf file/stanza editor (any .conf) |
| `macros` | Search macros -- list, get, set |
| `apps` | App install (.spl/.tar.gz), uninstall, update |
| `users` | User and role management |
| `server` | Messages, license, KV store, cluster/SHC/deployment health |
| `es` | ES notable-event triage (feature-detected) |
| `audit` | Change audit + RBAC attestation |
| `kvstore` | KV store collection + document CRUD |
| `state` | Config-as-code pull/diff/push with change-evidence reports |
| `soar` | SOAR: containers, artifacts, vault, playbooks, actions, cases, ingest |
| `commands` | Machine-readable command tree (JSON) |
| `mcp` | Built-in MCP server for AI agent integration |

## Key features

### Detection-as-code

Export rules to YAML, version control them, deploy across instances:

```bash
splunkctl rules export --path detections.yml
splunkctl rules import --path detections.yml        # dry-run preview
splunkctl --yes rules import --path detections.yml  # apply
```

### Config-as-code

```bash
splunkctl state pull --dir config/            # snapshot live state
splunkctl state diff --dir config/            # structured drift report
splunkctl state push --dir config/ --report r.json --yes  # deploy + evidence
```

### SOAR operations

```bash
splunkctl soar containers list --label events
splunkctl soar playbooks export my-playbook --unpack --out ./playbooks/
splunkctl soar ingest --spl 'index=notable | head 5' --yes
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
--profile NAME      Named profile (dev/UAT/prod)
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

## Agent integration (MCP)

splunkctl ships with a built-in MCP server with 237 auto-generated tools:

```bash
splunkctl mcp install              # register in .mcp.json
splunkctl mcp serve                # start stdio MCP server
splunkctl commands --json          # JSON command tree for discovery
```
