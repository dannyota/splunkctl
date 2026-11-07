<!-- summary: Diagnose connection, authentication, server health, and user permissions for the active splunkctl profile before doing real work. -->

# Diagnose a connection

When to use: you have just configured a profile, a command fails and you need to know whether the problem is the config file, the network, credentials, the license, or permissions, or a CI job or agent must confirm the instance is usable before it starts.

## Prerequisites

- splunkctl installed and a profile written with `splunkctl config init` (see [Configure](configure.md)). Without a config file, `doctor` warns and falls back to defaults and environment variables.
- Network access to the Splunk REST port (8089 by default). The Web UI check is optional and only matters for lookup upload and app install.

## Synopsis

```text
splunkctl doctor [--strict] [--json]
splunkctl config test
splunkctl info
```

## Workflow

### Run after setup

```bash
splunkctl doctor
```

Expected result: a check list on standard error, grouped as Config, Connection, Auth, Server, Health, KV Store, Permissions, Web UI, SOAR, and MCP, followed by `N/M passed, W warnings, F failures`. The checks are:

1. Config: the config file in use, including the `profiles.yaml` fallback when Splunk's own CLI owns `config.yaml`.
2. Connection: the REST API is reachable.
3. Auth: the credentials are valid, with the user name.
4. Server: Splunk version, OS, mode, and license state.
5. Health: `splunkd` health (green) and system messages with severity `error`.
6. KV store: status is `ready`.
7. Permissions: roles, then nine key capabilities: `search`, `admin_all_objects`, `edit_user`, `edit_roles`, `edit_tcp`, `edit_monitor`, `list_inputs`, `rest_apps_management`, `change_own_password`.
8. Web UI: the Splunk Web login page answers (needed for lookup upload and app install).
9. SOAR: connection, auth, health, and license, or `SKIP` when the profile has no `soar:` section.
10. MCP: a `splunkctl` entry exists in `.mcp.json` in the current directory.

Each failed check prints a `hint:` line naming the fix. Exit code is `0` when no check has status `FAIL` and `1` otherwise; warnings (`WARN`) do not fail the run unless you pass `--strict`.

### Gate a CI pipeline

```bash
splunkctl doctor --strict
```

Expected result: exit 1 on any failure or warning, so the pipeline stops early when the instance is unreachable, the license is not `OK`, the KV store is down, or the service account lacks a capability.

### Bootstrap an agent

```bash
splunkctl doctor --json | jq '.[] | select(.status == "FAIL")'
```

Expected result: the human-readable list still goes to standard error, and a JSON array of `{check, status, detail, hint}` objects goes to standard output. `status` is `OK`, `WARN`, `FAIL`, or `SKIP`. An agent should call `doctor --json` at session start, parse the array, and abort with a clear message when any check is `FAIL`.

### Isolate a failure layer

```bash
splunkctl doctor
splunkctl config test
splunkctl info
```

Expected result: `doctor` stops at the first layer that fails (config, then connection), so the first `FAIL` tells you whether to fix the file, the network, the credentials, the license, or a role. `config test` repeats only the connect-and-login step with a classified error (`auth`, `connection`, `timeout`); `info` prints the server details once authentication works.

## Troubleshooting

- `Config` fails with `Splunk-format config`: `~/.splunkctl/config.yaml` belongs to Splunk's CLI; run `splunkctl config init --path ~/.splunkctl/profiles.yaml` or see [Relationship to Splunk's splunkctl](splunk-cli.md).
- `Config` warns `not found`: run `splunkctl config init`, or set `SPLUNK_HOST` and `SPLUNK_TOKEN`.
- `REST API reachable` fails (`connection` or `timeout`): check `SPLUNK_HOST` and `SPLUNK_PORT`, that splunkd is running, and that port 8089 is open from this machine (`curl -k https://HOST:8089/services/server/info`).
- `Authenticated` fails, or `REST API reachable` fails with a login error (`auth`): verify `SPLUNK_USER` and `SPLUNK_PASS` or `SPLUNK_TOKEN`, or the profile's values with `splunkctl config show`.
- `License` warns: run `splunkctl server license`; a trial or expired license is reported in the detail.
- `Splunkd health` or `System messages` warns: run `splunkctl server messages`; dismiss a stale message with `splunkctl server messages --dismiss NAME --yes`.
- `KV Store` warns `failed`: ask the Splunk admin to restart Splunk or check `mongod.log`; `kvstore` commands return `http` 503 until it is `ready`.
- `cap:<name>` fails (`permission` later on): grant that capability to your user or role.
- `Web UI reachable` warns: lookup upload and app install need Splunk Web; other commands work.
- `MCP registered` warns: run `splunkctl mcp install` from the project directory, or ignore it when you are not using the MCP server.

## See also

- [Configure](configure.md)
- [Install](install.md)
- [Check server health and topology](server.md)
- [Set up the MCP server](mcp.md)
- [Exit codes](exit-codes.md)
