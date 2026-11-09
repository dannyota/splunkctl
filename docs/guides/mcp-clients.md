<!-- summary: Register splunkctl in project configurations for Claude Code, Codex, Cursor and Gemini CLI. -->

# Install MCP client registrations

Run `mcp install` in the project directory. Claude is the default client.

```bash
splunkctl mcp install --preview
splunkctl mcp install --client claude
splunkctl mcp install --client codex --read-only
splunkctl mcp install --client cursor
splunkctl mcp install --client gemini
```

| Client | Project file | Server key | HTTP field |
| --- | --- | --- | --- |
| Claude | `.mcp.json` | `mcpServers.splunkctl` | `type: http`, `url` |
| Codex | `.codex/config.toml` | `mcp_servers.splunkctl` | `url` |
| Cursor | `.cursor/mcp.json` | `mcpServers.splunkctl` | `url` |
| Gemini | `.gemini/settings.json` | `mcpServers.splunkctl` | `httpUrl` |

Stdio entries launch the current Python interpreter with `-m splunkctl mcp serve`. `--read-only` adds the server's mutation policy. HTTP registrations cannot enforce that policy, so `--read-only --transport http` is rejected. Start the HTTP server separately with the desired policy:

```bash
splunkctl mcp serve --transport http --read-only
splunkctl mcp install --client codex --transport http
```

The default URL is `http://127.0.0.1:8765/mcp`. `--host` accepts loopback addresses only; `--port` selects the listener port.

Installation writes immediately unless `--preview` is supplied. It preserves unrelated servers and settings, removes obsolete connection fields when switching transports, and preserves TOML comments. Identical registrations leave file bytes and modification time unchanged. Changed files are replaced atomically with their existing permissions.

JSON files must contain strict JSON. JSONC, malformed JSON and incompatible configuration shapes are refused with a usage error and the entry to add by hand. The installer never rewrites JSONC. User-wide registration and VS Code registration are deferred.

Client references: [Claude Code](https://code.claude.com/docs/en/mcp), [Codex](https://developers.openai.com/codex/mcp), [Cursor](https://cursor.com/docs/mcp), [Gemini CLI](https://geminicli.com/docs/tools/mcp-server/).

See [MCP setup and transports](mcp.md), [Read-only access](read-only.md) and [Command reference: mcp](../commands/mcp.md).
