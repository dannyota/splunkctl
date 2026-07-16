# splunkctl

Open-source **MCP server** and **CLI** for Splunk Enterprise SIEM and Splunk
SOAR. One tool, two interfaces — operate your Splunk environment from any AI
agent that speaks [Model Context Protocol](https://modelcontextprotocol.io), or
from the terminal.

> Community project. Not affiliated with or endorsed by Splunk, Inc.

## Two ways in

| Interface | What it does | Get started |
|-----------|-------------|-------------|
| **MCP Server** | Give Claude, Cursor, or any MCP client full access to your Splunk SIEM and SOAR — 259 tools with dynamic loading | [MCP guide](guides/mcp.md) |
| **CLI** | `splunkctl search run`, `splunkctl rules export`, `splunkctl soar containers list` — operate Splunk as code from your laptop | [Install](guides/install.md) |

## MCP server — quick start

```bash
pip install splunkctl

export SPLUNK_HOST=your-splunk-host
export SPLUNK_PORT=8089
export SPLUNK_USER=admin
export SPLUNK_PASS=your-password

splunkctl mcp install   # writes .mcp.json in the current project
```

Restart your MCP client. The server exposes five meta-tools (`help`, `run`,
`focus`, `unfocus`, `usage`) and loads group-specific typed tools on demand —
staying within context limits while covering every command.

[Full MCP setup guide &rarr;](guides/mcp.md)

## CLI — quick start

```bash
pip install splunkctl

splunkctl config init                    # interactive SIEM setup
splunkctl config init --soar             # add SOAR credentials
splunkctl doctor                         # check SIEM connection
splunkctl soar test                      # check SOAR connection

splunkctl search run 'index=main | head 10'
splunkctl rules list
splunkctl soar containers list
```

All write operations are **dry-run by default** — nothing changes until you
pass `--yes`.

[Full CLI quickstart &rarr;](guides/install.md)

## Commands

| Group | Description |
|---|---|
| `doctor` | Connection, auth, health, and permissions check |
| `config` | Setup, profiles (dev/UAT/prod), test connectivity |
| `info` | Server info (version, OS, license) |
| `search` | Run, export, oneshot, upload, job management |
| `rules` | Detection rules — CRUD, import/export (YAML), alert-action flags |
| `alerts` | Fired alerts, alert actions, suppression |
| `dashboards` | Dashboard CRUD (XML/JSON) |
| `indexes` | Index management |
| `inputs` | Data inputs (monitor, tcp, udp, script, http) |
| `lookups` | Lookup tables, definitions, automatic lookups |
| `hec` | HEC token management |
| `parsers` | Source types, field extractions, import/export |
| `conf` | Generic conf file/stanza editor (any .conf) |
| `macros` | Search macros — list, get, set |
| `apps` | App install (.spl/.tar.gz), uninstall, update |
| `users` | User and role management |
| `server` | Messages, license, KV store, cluster/SHC/deployment health |
| `es` | ES notable-event triage (feature-detected) |
| `audit` | Change audit + RBAC attestation |
| `kvstore` | KV store collection + document CRUD |
| `state` | Config-as-code pull/diff/push with change-evidence reports |
| `soar` | SOAR: containers, artifacts, vault, playbooks, actions, cases, ingest |

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

## License

Apache 2.0. See [GitHub](https://github.com/dannyota/splunkctl) for source.
