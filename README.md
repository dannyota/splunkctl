<div align="center">

<a href="https://splunkctl.danny.vn"><img src="https://raw.githubusercontent.com/dannyota/splunkctl/master/docs/assets/banner.svg" alt="splunkctl — operate Splunk Enterprise and Splunk SOAR as code" width="600"></a>

# splunkctl

[![PyPI](https://img.shields.io/pypi/v/splunkctl)](https://pypi.org/project/splunkctl/)
[![Python](https://img.shields.io/pypi/pyversions/splunkctl)](https://pypi.org/project/splunkctl/)
[![CI](https://img.shields.io/github/actions/workflow/status/dannyota/splunkctl/ci.yml?branch=master&label=CI)](https://github.com/dannyota/splunkctl/actions/workflows/ci.yml)
[![License](https://img.shields.io/pypi/l/splunkctl)](https://github.com/dannyota/splunkctl/blob/master/LICENSE)

**Operate Splunk Enterprise and Splunk SOAR as code with a CLI and MCP server.**

[Documentation](https://splunkctl.danny.vn) · [Command catalog](https://github.com/dannyota/splunkctl/blob/master/docs/design/catalog.md) · [Releases](https://github.com/dannyota/splunkctl/releases)

</div>

---

`splunkctl` is an open-source Python CLI and
[Model Context Protocol (MCP)](https://modelcontextprotocol.io) server for
remote Splunk Enterprise and Splunk SOAR instances. Use it interactively,
script its stable JSON output, or give an MCP client access to the same command
surface.

- **Manage Splunk Enterprise**: searches, detection rules, alerts, indexes,
  inputs, lookups, parsers, dashboards, apps, users, topology, audit, and
  Enterprise Security workflows.
- **Operate Splunk SOAR**: containers, artifacts, playbooks, actions, cases,
  approvals, assets, vault files, custom lists, administration, and SIEM-to-SOAR
  ingest.
- **Keep configuration as code**: pull live state, review structured drift,
  and push approved changes with change-evidence reports.
- **Automate safely**: mutations preview by default, machine output is
  structured, errors are typed, and every target profile and host is shown.

> **Every mutation is a dry run by default.** Nothing changes until you pass
> `--yes`. Review the target and proposed change before applying it.

> **Independent community project.** Not affiliated with or endorsed by
> Splunk Inc. It is unrelated to Splunk's own Go CLI of the same name,
> [`splunk/splunkctl`](https://github.com/splunk/splunkctl). See
> [Relationship to Splunk's splunkctl](#relationship-to-splunks-splunkctl).

## Install

```bash
python -m pip install splunkctl
```

Python 3.13 or newer is required. Core commands work with the upstream Splunk
SDK installed from PyPI.

Dashboard, lookup-file, and HTTP Event Collector (HEC) token commands use
entity classes provided by the optional `splunkctl` SDK fork:

```bash
python -m pip install git+https://github.com/dannyota/splunk-sdk-python@splunkctl
```

See the [installation guide](https://splunkctl.danny.vn/#/guides/install) for
environment-specific setup.

## Quickstart

```bash
# Configure and verify Splunk Enterprise
splunkctl config init
splunkctl doctor

# Read live state
splunkctl info
splunkctl search run 'index=main | head 10'
splunkctl rules list --json

# Preview a change; add --yes only after reviewing it
splunkctl rules disable 'My Rule'

# Add and verify Splunk SOAR when needed
splunkctl config init --soar
splunkctl soar test
splunkctl auth login --target siem             # browser SAML/MFA login
splunkctl soar containers list
```

Use named profiles for separate development, UAT, and production instances:

```bash
splunkctl config init --profile uat
splunkctl --profile uat doctor
splunkctl --profile uat rules list
```

## Core workflows

### Configuration as code

The `state` engine covers rules, parsers, macros, lookups, and selected SOAR
objects. Dashboards support pull and diff. Push never deletes remote objects.

```bash
splunkctl state pull --dir config/
# Edit the exported files in version control.
splunkctl state diff --dir config/
splunkctl state push --dir config/ --report change-report.json
splunkctl state push --dir config/ --report change-report.json --yes
```

The report records before-and-after state and whether the change was applied,
so it can be attached to a change ticket.

### Detection and SIEM operations

```bash
splunkctl rules export --path rules.yaml
splunkctl rules import --path rules.yaml
splunkctl datamodels acceleration
splunkctl es notables list --status new --json
splunkctl audit rbac --format csv --out rbac.csv
splunkctl server cluster
```

Enterprise Security commands detect whether the required app is available and
return a clear error when it is not.

### Splunk SOAR operations

```bash
splunkctl soar containers list --severity high
splunkctl soar playbooks export my_playbook --unpack --out playbooks/
splunkctl soar playbooks run my_playbook --container 42 --wait
splunkctl soar actions run --action geolocate_ip --asset maxmind \
  --container 42 --param ip=203.0.113.10 --wait
splunkctl soar ingest --spl 'index=notable' --label events
```

SOAR commands use the same profiles, dry-run guard, output formats, and error
contract as the Splunk Enterprise commands.

### MCP for AI agents

```bash
splunkctl mcp install
splunkctl mcp serve
```

The built-in MCP server generates typed tools from the CLI command tree and
uses progressive discovery: clients start with a small set of meta-tools, then
focus on the command groups needed for the task. Guarded tools require an
explicit `yes=true` before they can mutate a remote instance.

See the [MCP guide](https://splunkctl.danny.vn/#/guides/mcp) for stdio and
streamable HTTP configuration.

## Command groups

| Group | Purpose |
|---|---|
| `doctor` | Check connection, authentication, health, and permissions |
| `config` | Configure profiles and test connectivity |
| `auth` | Browser SAML login, session status, and logout |
| `info` | Show server version, operating system, and license details |
| `search` | Run, export, upload, and manage search jobs |
| `rules` | Manage detection rules and YAML import/export |
| `alerts` | Inspect fired alerts and manage suppression |
| `dashboards` | Manage Classic and Studio dashboards |
| `indexes` | Manage indexes |
| `inputs` | Manage monitor, TCP, UDP, script, and HTTP inputs |
| `lookups` | Manage lookup files, definitions, and automatic wiring |
| `hec` | Manage HEC tokens, settings, and events |
| `parsers` | Manage source types, props, transforms, and YAML state |
| `apps` | Install, update, reload, and uninstall apps |
| `users` | Manage users and roles |
| `server` | Inspect health, topology, deployment, auth, tokens, and workloads |
| `es` | Triage notables and manage correlations and threat intelligence |
| `audit` | Review changes and generate role-based access control attestations |
| `kvstore` | Manage KV Store collections and documents |
| `conf` | Edit any Splunk configuration file and stanza |
| `macros`, `eventtypes`, `tags` | Manage search knowledge objects |
| `datamodels` | Inspect definitions and acceleration health |
| `state` | Pull, diff, and push configuration state |
| `soar` | Operate Splunk SOAR and run SIEM-to-SOAR workflows |
| `commands` | Emit the machine-readable command tree |
| `completion` | Generate shell completion for Bash, Zsh, or Fish |
| `mcp` | Install and run the MCP server |

Run `splunkctl COMMAND --help` for local help, or use the
[generated command reference](https://splunkctl.danny.vn/#/commands/).

## Output and safety contracts

Global flags work before or after subcommands:

```text
--json              Force JSON output
--format FMT        Select table, json, csv, or jsonl
--fields f1,f2      Select output fields
--out FILE          Write output to a file
--yes, -y           Apply a mutation after previewing it
--timeout N         Set the request timeout in seconds
--watch N           Repeat a read-only command every N seconds
--config FILE       Use a specific configuration file
--profile NAME      Select a named profile
--debug             Log HTTP requests and responses
```

Under JSON output, failures emit one JSON object on standard error with a
stable error kind:

```json
{"error": {"kind": "not_found", "http_status": 404, "message": "..."}}
```

Kinds include `auth`, `permission`, `not_found`, `conflict`, `http`,
`connection`, `timeout`, and `error`. List commands share uniform filtering and
paging flags where the remote API supports them.

Every guarded operation identifies its target before it runs:

```text
$ splunkctl --profile uat rules delete 'My Rule'
[DRY RUN] Delete saved search 'My Rule' (profile: uat @ uat.splunk.internal:8089)
Pass --yes to apply.
```

## Relationship to Splunk's splunkctl

This project started in June 2026. In August 2026 Splunk Inc. published an
unrelated, experimental Go CLI with the same name at
[`splunk/splunkctl`](https://github.com/splunk/splunkctl). The two tools
share a name and nothing else. This project is not a fork, wrapper, or
replacement for Splunk's tool, and it focuses on SOC workflows across
Splunk Enterprise, Enterprise Security, and Splunk SOAR rather than on
general Splunk administration.

| | This project (`pip install splunkctl`) | `splunk/splunkctl` |
|---|---|---|
| Language and install | Python package from PyPI | Go binary from GitHub Releases |
| Products | Splunk Enterprise, Enterprise Security, Splunk SOAR | Splunk Enterprise, Splunk Cloud Platform |
| Authentication | Username and password by default, bearer token, optional browser SAML SSO | Bearer token only |
| Profiles | Named profiles for dev, UAT, and production | One host and token |
| Mutations | Dry run by default, `--yes` to apply | Prompt, or `CONFIRMATION_REQUIRED` for non-interactive callers; `--read-only` |
| AI agents | Built-in MCP server plus `commands --json` | `schema` JSON and agent skill files; pairs with Splunk's MCP server |
| Configuration as code | `state pull`, `diff`, and `push` with change reports | Not provided |
| Command surface | SOC-focused groups listed above | Generated from Splunk's REST definitions, including cluster and licenser internals |
| Config file | `~/.splunkctl/config.yaml` with profiles | `~/.splunkctl/config.yaml` with flat `host` and `token` keys |
| Support | Community project, Apache-2.0 | Experimental, Apache-2.0, pull requests not accepted |

Both tools install an executable named `splunkctl` and read the same
configuration path. See [Coexistence](#coexistence) for how this package
handles that when both are installed.

### Coexistence

- **Executable name.** This package installs both `splunkctl` and
  `splunkctl-py`. If Splunk's binary shadows `splunkctl` on your `PATH`,
  call `splunkctl-py` instead.
- **Config file.** If `~/.splunkctl/config.yaml` holds Splunk's flat
  `host`/`token` format, this tool leaves it untouched and keeps its own
  profiles in `~/.splunkctl/profiles.yaml`. It prints one notice on
  standard error when that happens, and `splunkctl doctor` reports which
  file is in use. Pass `--config FILE` to choose a file explicitly; an
  explicit file in Splunk's format is refused rather than redirected.
- **Credentials are not shared.** The two tools do not read each other's
  settings. Run `splunkctl config init` once to set up this tool.

## Development

```bash
git clone https://github.com/dannyota/splunkctl
cd splunkctl
python -m pip install -e '.[dev]'
python -m pytest
```

## License

[Apache-2.0](https://github.com/dannyota/splunkctl/blob/master/LICENSE)
