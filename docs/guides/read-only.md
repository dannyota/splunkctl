<!-- summary: Refuse server mutations across CLI and MCP while allowing classified searches and local file writes. -->

# Use read-only access

`--read-only` guarantees no application-data, configuration or authentication changes on any server. Search execution can create search jobs, and servers can write their own audit and access logs. Local files may change.

```bash
splunkctl --read-only info
splunkctl --read-only search oneshot '| makeresults | stats count'
SPLUNKCTL_READ_ONLY=1 splunkctl api get server/info
splunkctl mcp serve --read-only
```

`SPLUNKCTL_READ_ONLY` accepts `1`, `true` and `yes`, case-insensitively. The global flag, environment setting and MCP setting combine with OR. No flag disables an enabled policy.

## What is allowed

GET and HEAD requests are allowed except known mutations such as logout. Redirects must stay on the configured origin. SOAR allows only GET requests.

Splunk password and Web session login requests needed to use existing credentials are allowed. Explicit `auth login`, `auth logout`, browser login and automatic browser reauthentication are refused.

Search dispatch is allowed only after SPL classification. Cancellation, finalization and deletion are allowed only for jobs created by the current invocation. Existing jobs can be read; an independent `search cancel --yes` is refused.

Local writes remain allowed: `--out`, `config init`, `config use`, session-file maintenance and `mcp install`. `config init` skips network autodetection under read-only mode.

## Search restrictions

Read-only mode refuses write commands, `map`, `savedsearch`, `dbxquery`, `dbxoutput` and `run`. It also refuses unknown and custom commands. Built-in read commands must appear in the explicit allowlist derived from the Splunk Enterprise 10.x Search Reference.

Macros and subsearches require expansion through Splunk's REST `search/parser` endpoint. The [Splunk 10.0 REST reference](https://help.splunk.com/en/splunk-enterprise/rest-api-reference/10.0/search-endpoints/search-endpoint-descriptions) documents GET for this endpoint, but marks it deprecated and disabled by default since 9.0.1. The newer v2 parser requires POST and is outside the read-only transport exceptions. Macros and subsearches therefore fail closed on servers where the GET parser is unavailable. The expanded commands must pass the same checks; parser failures refuse the search. The error identifies the offending command. See [Run searches](search.md).

These restrictions apply at transport dispatch as well as the command layer, including searches submitted through [the raw API](api.md). Without `--read-only`, the existing write-SPL confirmation behavior is unchanged.

## Previews and refusals

Guarded commands without `--yes` still preview and exit 0. With `--yes`, read-only mode refuses before any server request, exits 1 and reports `permission`, with `http_status: null` and a message starting `read-only:`. JSON errors go to stderr.

```bash
splunkctl --read-only rules delete 'Example Rule'        # preview
splunkctl --read-only --yes rules delete 'Example Rule'  # refused
```

For MCP, mutation tools are omitted from discovery and focus results. The generic `run` tool also refuses mutations, and every CLI subprocess inherits read-only mode. See [Set up the MCP server](mcp.md).
