<div align="center">

<a href="https://splunk.danny.vn"><img src="docs/assets/banner.svg" alt="splunkctl — operate Splunk Enterprise and Splunk SOAR as code" width="600"></a>

# splunkctl

**Operate Splunk Enterprise and Splunk SOAR as code — for SOC teams, detection engineers, and AI agents.**

[Docs](https://splunk.danny.vn) · [Catalog](docs/design/catalog.md) · [Releases](https://github.com/dannyota/splunkctl/releases)

</div>

---

A Python CLI that queries, inspects, and manages **remote** Splunk
Enterprise and Splunk SOAR instances over their REST APIs. SIEM commands
are built on the
[splunk-sdk-python](https://github.com/dannyota/splunk-sdk-python/tree/splunkctl)
fork with [Click](https://click.palletsprojects.com/); SOAR commands use
`SOARClient`, a requests-based Django REST client with dual auth (token +
Basic fallback). The SIEM core loop is **pull live state, review the diff,
push it back** -- one `state` engine covering rules, parsers, macros,
lookups, and dashboards, with a change-evidence report artifact for change
tickets. The SOAR surface covers ops visibility, container/artifact
lifecycle, the first playbooks-as-code loop anywhere, and SIEM-to-SOAR
ingest. Built for humans and LLM agents alike: deterministic flags,
`--json` everywhere, structured error envelopes, and a built-in MCP server
(`splunkctl mcp serve`) with progressive tool discovery.

> **Every mutation is dry-run by default.** Nothing changes until you pass
> `--yes`. Always preview, read it, then apply.

## What it does

- **Config as code** — `state pull` → edit → `state diff` → `state push`
  across rules, parsers, macros, lookups, and dashboards (diff-only). Push
  writes a before→after JSON report artifact usable as change-ticket
  evidence. Push never deletes.
- **Detection engineering** — rules CRUD + YAML import/export, macros,
  eventtypes, tags, data model acceleration health, lookup definitions +
  automatic lookups (transforms.conf/props.conf wiring), and first-class
  `--email-to`/`--webhook-url` alert-action flags.
- **ES incident review** — `es notables list/get/update` for the SOC
  triage loop (status, owner, urgency, disposition, comment via
  `notable_update`); feature-detected on Enterprise Security.
- **Compliance & audit** — `audit changes` normalizes both `_audit` event
  shapes into one schema; `audit rbac` produces a users × roles ×
  capabilities attestation view for access recertification.
- **KV store** — collection + document CRUD, JSONL import/export with
  500-doc batch chunking, query with server-side filtering.
- **Topology health** — `server cluster/shcluster/deployment` reads
  distinguish "no threat" from "an indexer is down" in clustered
  deployments.
- **Agent reliability** — structured JSON error envelope with typed
  taxonomy (`auth`/`permission`/`not_found`/`timeout`/...), uniform
  `--limit`/`--offset`/`--filter` on every list surface, multi-instance
  profiles with a bank-safety guard banner
  (`(profile: uat @ host:port)`).
- **SOAR ops** — `soar` command tree: containers, artifacts, vault, notes,
  cases/workbooks, approvals, custom lists, indicators, evidence, users,
  roles, audit, and cross-object search. Full lifecycle: create, update,
  close, assign, delete -- with the same dry-run guard and typed error
  envelopes.
- **Playbooks as code** — `soar playbooks export --unpack` / `import`
  round-trips playbook tgz bundles (the first such tool anywhere);
  `soar playbooks delete` removes them through the Web UI route (no
  REST deletion exists); `soar playbooks run --wait` drives and polls
  runs to completion; `soar actions run --wait` does the same for
  connector actions.
- **SIEM-to-SOAR ingest** — `soar ingest --spl` runs a SIEM search and
  creates SOAR containers + typed CEF artifacts using the official CIM-to-CEF
  field map, with SDI dedup, severity mapping, and last-artifact automation
  batching.
- **Built for agents** — built-in MCP server with 259 auto-generated tools,
  progressive discovery (5 meta-tools + focus/unfocus), 33 guide resources,
  guard markers on every mutation, dual output (TTY = table, pipe = JSON).

## Install

```bash
pip install splunkctl
pip install git+https://github.com/dannyota/splunk-sdk-python@splunkctl
```

Requires Python 3.13+. The second line installs the
[forked SDK](https://github.com/dannyota/splunk-sdk-python/tree/splunkctl)
which adds dashboard, lookup, and HEC token entity classes. Without it,
core commands (search, rules, alerts, indexes, inputs, apps, users) still
work.

### Development

```bash
git clone https://github.com/dannyota/splunkctl
cd splunkctl
pip install -e '.[dev]'
splunkctl --version
```

## Quickstart

```bash
splunkctl config init                         # interactive SIEM setup
splunkctl config init --soar                  # add SOAR credentials
splunkctl doctor                              # check SIEM connection
splunkctl soar test                           # check SOAR connection
splunkctl search run 'index=main | head 10'   # run a SIEM search
splunkctl soar containers list                # list SOAR containers
splunkctl commands --json                     # discover every verb
```

## CLI usage

```bash
# Read
splunkctl rules list --app Splunk_Security_Essentials --json
splunkctl alerts list --json
splunkctl datamodels acceleration
splunkctl audit rbac --format csv --out rbac.csv

# Mutate (dry-run first, --yes to apply)
splunkctl rules disable 'My Rule'             # preview
splunkctl rules disable 'My Rule' --yes       # apply
splunkctl es notables update <id> --status closed --owner analyst --yes

# Config-as-code
splunkctl state pull --dir config/            # snapshot live state
splunkctl state diff --dir config/            # structured drift report
splunkctl state push --dir config/ --report r.json --yes  # deploy + evidence
```

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
| `apps` | App install (.spl/.tar.gz), uninstall, update |
| `users` | User and role management |
| `server` | Messages, license, KV store, cluster/SHC/deployment health |
| `es` | ES notable-event triage (feature-detected) |
| `audit` | Change audit + RBAC attestation |
| `kvstore` | KV store collection + document CRUD |
| `conf` | Generic conf file/stanza editor (any .conf) |
| `macros` | Search macros — list, get, set |
| `eventtypes` | Event types — list, get |
| `tags` | Tags — list, get |
| `datamodels` | Data model definitions + acceleration health |
| `state` | Config-as-code pull/diff/push with change-evidence reports |
| `soar` | SOAR: containers, artifacts, vault, playbooks, actions, cases, ingest |
| `commands` | Machine-readable command tree (JSON) |
| `mcp` | Built-in MCP server for AI agent integration |

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

## Dry-run by default

All write operations preview what would change. Pass `--yes` to apply.
Every preview and confirmation includes the target profile and host so an
agent never mistakes UAT for prod.

```bash
splunkctl rules delete 'My Rule'
# [DRY RUN] Delete saved search 'My Rule' (profile: uat @ uat.splunk.internal:8089)
# Pass --yes to apply.

splunkctl rules delete 'My Rule' --yes
# Applying: Delete saved search 'My Rule' (profile: uat @ uat.splunk.internal:8089)
# Deleted saved search 'My Rule'.
```

## Structured errors

Under `--json` or piped output, errors emit a single-line JSON envelope on
stderr with a typed `kind` for programmatic branching:

```json
{"error": {"kind": "not_found", "http_status": 404, "message": "..."}}
```

Kinds: `auth`, `permission`, `not_found`, `conflict`, `http`, `connection`,
`timeout`, `error` (fallback).

## SDK fork

splunkctl depends on a
[fork of splunk-sdk-python](https://github.com/dannyota/splunk-sdk-python/tree/splunkctl)
that adds entity classes missing from the upstream SDK:

| Entity | Service property | Purpose |
|---|---|---|
| `Dashboard` | `service.dashboards` | Dashboard CRUD |
| `LookupTableFile` | `service.lookup_table_files` | Lookup table metadata + download |
| `HECToken` | `service.hec_tokens` | HEC token management |

```bash
pip install git+https://github.com/dannyota/splunk-sdk-python@splunkctl
```

## Agent integration (MCP)

splunkctl ships with a built-in
[MCP](https://modelcontextprotocol.io) server for AI agent integration:

```bash
splunkctl mcp install              # register in .mcp.json
splunkctl mcp serve                # start stdio MCP server
```

The MCP server auto-generates 259 typed tools from the Click command tree
(SIEM + SOAR) with progressive discovery -- agents start with 5 meta-tools
(`help`, `usage`, `focus`, `unfocus`, `run`) and dynamically load typed
schemas per command group. Subgroup-granular focus works for nested groups
like `soar containers`. 33 guide resources are served as `guide://` URIs.
Mutations are guarded: `yes=true` to apply (dry-run by default).

## License

Apache-2.0
