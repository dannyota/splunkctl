# MCP server

Use splunkctl as a [Model Context Protocol](https://modelcontextprotocol.io)
server to give AI agents — Claude Code, Claude Desktop, Cursor, Windsurf, or
any MCP client — direct access to your Splunk Enterprise SIEM and Splunk SOAR
instances.

The server uses **dynamic tool loading**: instead of exposing all 229 tools
upfront, it starts with 5 meta-tools and loads group-specific typed tools on
demand. This keeps the agent's context window small while covering every
command.

## Install

```bash
pip install splunkctl
```

Or install from source:

```bash
git clone https://github.com/dannyota/splunkctl.git
cd splunkctl && pip install -e .
```

## Configure credentials

The MCP server reads the same config as the CLI. Set environment variables:

```bash
export SPLUNK_HOST=your-splunk-host
export SPLUNK_PORT=8089
export SPLUNK_USER=admin
export SPLUNK_PASS=your-password
```

Or run `splunkctl config init` to write `~/.splunkctl/config.yaml`. See
[Configure](guides/configure.md) for details.

For SOAR, add SOAR credentials:

```bash
splunkctl config init --soar
```

Verify connectivity:

```bash
splunkctl doctor         # check SIEM connection
splunkctl soar test      # check SOAR connection
```

## Register with your MCP client

### Claude Code

From your project directory:

```bash
splunkctl mcp install
```

This writes an entry to `.mcp.json` in the current directory. Restart Claude
Code to pick up the new server.

### Claude Desktop

Add to your `claude_desktop_config.json`:

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

### Cursor / other MCP clients

Point your client at the stdio command:

```text
splunkctl mcp serve
```

Pass `SPLUNK_HOST`, `SPLUNK_PORT`, `SPLUNK_USER`, and `SPLUNK_PASS` as
environment variables, or ensure `~/.splunkctl/config.yaml` exists.

## How it works

The server exposes:

- **Meta-tools** — `help`, `run`, `focus`, `unfocus`, `usage` (always loaded)
- **Group tools** — loaded on demand via `focus` (e.g. `focus group="rules"`)
- **Resources** — one per guide (`guide://{name}`)

### Workflow

1. Call `help` to discover available command groups
2. Call `help group="rules"` to list subcommands in a group
3. Call `focus group="rules"` to load typed tools (`rules_list`, `rules_get`, etc.)
4. Use the typed tools with full parameter schemas
5. Call `unfocus group="rules"` when done to free context
6. Use `run` anytime for quick one-off commands without focusing

### Example conversation

> **You:** How many failed login events are there in the last hour?
>
> The agent calls `run command="search oneshot 'index=main sourcetype=linux_secure action=failure | stats count' --earliest -1h"`
> and returns the count.

> **You:** Show me the detection rules that fire most often.
>
> The agent calls `focus group="rules"`, then `rules_list` to get all rules,
> then `focus group="alerts"` and `alerts_list` to see which fired recently.

> **You:** List open SOAR containers from the last 24 hours.
>
> The agent calls `focus group="soar containers"`, then
> `soar_containers_list` with the appropriate filters.

All tool output is JSON. Mutations are dry-run by default — the agent must
pass `yes=true` to apply, same as the CLI's `--yes`.

## Security

- The MCP server inherits the permissions of your Splunk credentials. Use a
  least-privilege account scoped to what the agent needs.
- All mutations require `yes=true` — the agent cannot accidentally modify your
  environment without explicit confirmation.
- The server runs locally on stdio. No network listener is opened.
- Credentials live in `~/.splunkctl/config.yaml` (0600) or environment
  variables, never in the MCP config itself.
