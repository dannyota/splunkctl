<!-- summary: Register splunkctl as an MCP server so Claude Code, Claude Desktop, Cursor, or any MCP client can run its commands with the same guard. -->

# Set up the MCP server

When to use: you want an AI agent (Claude Code, Claude Desktop, Cursor, Windsurf, or any other [Model Context Protocol](https://modelcontextprotocol.io) client) to query and change your Splunk Enterprise and Splunk SOAR instances through splunkctl, with the same dry-run guard the CLI applies.

## Prerequisites

- splunkctl installed (`pip install splunkctl`, see [Install](install.md)).
- A working profile: `splunkctl doctor` passes for Splunk and, if you use SOAR, `splunkctl soar test` passes (see [Configure](configure.md) and [Set up and check SOAR](soar.md)).
- A least-privilege Splunk account. The server inherits whatever your credentials can do.
- An MCP client that can launch a stdio command or connect to a local HTTP URL.

## Synopsis

```text
splunkctl mcp serve [--transport stdio|http] [--host 127.0.0.1|localhost|::1] [--port N]
splunkctl mcp install [--transport stdio|http] [--host 127.0.0.1|localhost|::1] [--port N]
```

`serve` starts the server (stdio by default). `install` writes a `splunkctl` entry into `.mcp.json` in the current directory for Claude Code. `--host` and `--port` apply only to `--transport http`; the default listener is `127.0.0.1:8765` and the MCP URL is `http://127.0.0.1:8765/mcp`.

## Workflow

### Install splunkctl

```bash
pip install splunkctl
```

Or install from source:

```bash
git clone https://github.com/dannyota/splunkctl.git
cd splunkctl && pip install -e .
```

Expected result: `splunkctl --version` prints the version.

### Configure credentials

The MCP server reads the same config as the CLI. Either export environment variables:

```bash
export SPLUNK_HOST=your-splunk-host
export SPLUNK_PORT=8089
export SPLUNK_USER=admin
export SPLUNK_PASS=your-password
```

or write `~/.splunkctl/config.yaml` with `splunkctl config init`, and add SOAR credentials with `splunkctl config init --soar`. Then verify:

```bash
splunkctl doctor
splunkctl soar test
```

Expected result: both commands exit 0. Credentials stay in the config file (mode 0600) or the environment, never in the MCP client config, unless you choose to put them there as in the Claude Desktop example below.

### Register with Claude Code

```bash
splunkctl mcp install
```

Expected result: `.mcp.json` in the current directory gains a `splunkctl` server entry that runs the current Python interpreter with `-m splunkctl mcp serve`. An existing `.mcp.json` is merged, not replaced. Restart Claude Code to pick up the server.

### Register with Claude Desktop

Add this to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "splunkctl": {
      "command": "splunkctl",
      "args": ["mcp", "serve"],
      "env": {
        "SPLUNK_HOST": "your-splunk-host",
        "SPLUNK_PORT": "8089",
        "SPLUNK_USER": "admin",
        "SPLUNK_PASS": "your-password"
      }
    }
  }
}
```

Expected result: after a restart, Claude Desktop lists the `splunkctl` tools. Omit `env` if `~/.splunkctl/config.yaml` exists.

### Point Cursor or another client at stdio

```bash
splunkctl mcp serve
```

Expected result: the server speaks MCP over stdin and stdout, one agent per process, with no network listener. Pass `SPLUNK_HOST`, `SPLUNK_PORT`, `SPLUNK_USER`, and `SPLUNK_PASS` as environment variables, or make sure `~/.splunkctl/config.yaml` exists.

### Run the Streamable HTTP transport

For local clients that need a URL instead of a command:

```bash
splunkctl mcp serve --transport http
splunkctl mcp serve --transport http --host localhost --port 9000
splunkctl mcp install --transport http
splunkctl mcp install --transport http --host ::1 --port 9000
```

Expected result: a Streamable HTTP listener on `127.0.0.1:8765` (or the host and port you pass) serving `/mcp`, and `install --transport http` writes a URL-based entry instead of a command entry. The host is restricted to `127.0.0.1`, `localhost`, or `::1`; a non-loopback address is a usage error. HTTP mode has no authentication of its own, so anything on the machine that can reach the port can call the tools with your credentials.

### Discover tools progressively

The server uses dynamic tool loading. It starts with five meta-tools and loads typed, group-specific tools on demand, which keeps the agent's context window small while still covering every command. It is built on MCP Python SDK 2 (`mcp>=2.3`) and sends `tools/list_changed` notifications whenever `focus`, `unfocus`, or `usage` changes the tool list.

- Meta-tools, always loaded: `help`, `usage`, `focus`, `unfocus`, `run`.
- Group tools, loaded by `focus` (for example `focus group="rules"` loads `rules_list`, `rules_get`, and so on).
- Resources, one per guide, at `guide://{name}`.
- Prompts: `investigate-ioc`, `triage-notable`, `audit-detection`, and `export-state`.

A typical sequence:

```text
help                          list command groups
help group="rules"            list subcommands in a group
focus group="rules"           load typed tools with full parameter schemas
rules_list ...                call the typed tools
unfocus group="rules"         free the context when done
run command="search oneshot 'index=main | stats count' --earliest -1h"
```

`usage command="soar playbooks run"` shows one command's flags and loads it as a callable tool without focusing the whole group. `run` is an escape hatch for raw command strings with no argument validation. The `soar` tree has nested subgroups, so focus at subgroup granularity: `focus group="soar containers"`, not `focus group="soar"`. All tool output is JSON.

Example exchanges:

> **You:** How many failed login events are there in the last hour?
>
> The agent calls `run command="search oneshot 'index=main sourcetype=linux_secure action=failure | stats count' --earliest -1h"` and returns the count.

> **You:** Show me the detection rules that fire most often.
>
> The agent calls `focus group="rules"`, then `rules_list`, then `focus group="alerts"` and `alerts_list` to see which fired recently.

> **You:** List open SOAR containers from the last 24 hours.
>
> The agent calls `focus group="soar containers"`, then `soar_containers_list` with the matching filters.

### Apply a guarded change

> **Safety:** Target is the Splunk or SOAR host in the profile the server was started with. Impact: the same change the CLI command makes. Preview by calling the tool without `yes`, apply by calling it again with `yes=true`, and verify with the matching read tool (for example `rules_get` after `rules_update`).

Guarded tools carry `[guarded: dry-run by default, pass yes=true to apply]` in their description and a `yes` parameter. Without `yes=true` the call returns the dry-run preview and changes nothing, exactly like the CLI without `--yes`:

```text
rules_disable name="Old brute force rule"            preview only
rules_disable name="Old brute force rule" yes=true   apply
```

The same holds for `run`: include `--yes` in the command string to apply.

```bash
splunkctl rules get "Old brute force rule"
```

Expected result: the read-back shows `disabled: 1` after the apply.

## Troubleshooting

- `config` error or "No Splunk host configured" from every tool: the server process cannot see your profile. Export `SPLUNK_HOST` and friends in the client's `env`, or create `~/.splunkctl/config.yaml` with `splunkctl config init`.
- `auth` error: the credentials in the server's environment are wrong or expired. Run `splunkctl doctor` in the same environment the client uses.
- `connection` or `timeout` error: the server cannot reach the Splunk management port. Check `SPLUNK_HOST` and `SPLUNK_PORT` (8089 by default) and any VPN.
- `confirmation_required` error from `run`: the SPL contains a write command (`outputlookup`, `collect`, and others). Add `--yes` to the command string only if the write is intended.
- A guarded tool "did nothing": the call ran as a dry run. Pass `yes=true`.
- `--host 0.0.0.0` is rejected: HTTP mode binds only to a loopback address by design. Put a reverse proxy with authentication in front if you need remote access.
- The client does not list the server after `mcp install`: restart the client, and check that `.mcp.json` sits in the directory the client opened.

## See also

- [Install](install.md)
- [Configure](configure.md)
- [Diagnose a connection](doctor.md)
- [Set up and check SOAR](soar.md)
- [Run searches](search.md)
- [Command reference: mcp](../commands/mcp.md)
