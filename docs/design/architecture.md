<!-- summary: How splunkctl is built: the layers, the request flow, auth resolution, and the design decisions behind them. -->

# Architecture

How splunkctl is built: the layers, the request flow, and the design
decisions. The command surface itself is documented in the generated
[command reference](../commands/README.md).

## Layers

```mermaid
flowchart TD
  CLI["<b>CLI layer</b> · Click<br/>main.py + commands/**<br/>Global flags, command groups, SPL write-command check"]
  MCP["<b>MCP layer</b><br/>mcp/*<br/>Meta-tools, generated tools, guide resources"]
  SVC["<b>Service layer</b><br/>config.py · client.py · output.py · guard.py · errors.py · auth/*<br/>Profiles, auth, formatting, mutation guard, error envelope"]
  SIEM["<b>Splunk transport</b><br/>splunklib (upstream splunk-sdk) + rest_adapters.py + _WebSession"]
  SOAR["<b>SOAR transport</b><br/>soar/client.py (REST) · soar/web.py (Django Web UI)"]
  API1["Splunk Enterprise / ES<br/>REST :8089 · Web UI :8000"]
  API2["Splunk SOAR<br/>REST :8443"]
  MCP --> CLI --> SVC
  SVC --> SIEM --> API1
  SVC --> SOAR --> API2
```

One file per command group under `splunkctl/commands/`, with SOAR groups
under `splunkctl/commands/soar/`. Files stay under 500 lines; a group
that outgrows that splits into sibling modules (for example
`rules.py`, `rules_io.py`, `rules_schedule.py`).

The MCP server builds its tool schemas by inspecting the imported Click
tree. The meta-tools answer locally; every generated tool builds a
`splunkctl` argv and runs the CLI as a subprocess, so command behavior
has one implementation.

## Request flow

```mermaid
flowchart TD
  A["User or agent"] --> B["main.py: hoist global flags,\nresolve output format"]
  B --> C["config.py: profile + env + flags"]
  C --> D{"Mutation?"}
  D -- "no" --> E["client.py / soar client: lazy connect"]
  D -- "guarded, no --yes" --> F["guard.py: [DRY RUN] preview, exit 0\n(some previews read the server first)"]
  D -- "guarded, --yes" --> E
  E --> G["output.py: table, JSON, CSV, JSONL"]
  E -. "exception" .-> H["errors.py: one JSON error line on stderr"]
```

Global flags (`--json`, `--format`, `--profile`, `--config`, `--yes`,
...) are accepted anywhere on the command line. There is no `--dry-run`
flag: a guarded command is a dry run whenever `--yes` is absent. `main.py`
moves them in front of the command before Click parses, stopping at `--`
and never touching a value that belongs to a subcommand option.

## Configuration

- Default file: `~/.splunkctl/config.yaml`, schema v2 (`profiles:` plus
  `current:`). Each profile holds the SIEM connection and an optional
  `soar:` section. Written with mode 0600 through a temp file and
  `os.replace`.
- Precedence, highest first: CLI flags, environment, then the profile.
  SIEM variables: `SPLUNK_HOST`, `SPLUNK_PORT`, `SPLUNK_SCHEME`,
  `SPLUNK_USER`, `SPLUNK_PASS`, `SPLUNK_TOKEN`, `SPLUNK_APP`,
  `SPLUNK_OWNER`, `SPLUNK_VERIFY`. SOAR variables: `SOAR_HOST`,
  `SOAR_PORT`, `SOAR_USER`, `SOAR_PASS`, `SOAR_TOKEN`, `SOAR_VERIFY`.
  The SIEM guard banner names the layer (profile, env or flags) that
  supplied the connection fields; the SOAR banner shows host and port.
- Coexistence with Splunk's Go CLI: both tools default to
  `~/.splunkctl/config.yaml`. If that file is a flat `host`/`token`
  document written by the other tool, splunkctl treats it as foreign,
  falls back to `~/.splunkctl/profiles.yaml`, and prints one notice.
  Details in [Relationship to Splunk's splunkctl](../guides/splunk-cli.md).

## Authentication

Default is username/password or a bearer token from the profile. The
config file is read when the CLI starts, but credentials are used only on
the first API call. Help, `config init`, `config show`, `config use`,
`commands` and `docs` never connect; `config test` does.

Browser SAML is opt-in per profile (`auth_mode: browser`). `auth login`
opens a temporary Chromium through Playwright, keeps only the product
cookies, and stores a session under `~/.splunkctl/sessions/` with mode
0600. On use, the SIEM client validates the stored session first; if it
is missing or expired it re-probes the login route and falls back to
token or password unless the route still reports SAML. The SOAR client
does not fall back: a missing or expired SOAR session exits with an
`auth` error that names `auth login --target soar`. Module roles:

| Module | Role |
|---|---|
| `auth/detector.py` | Classifies the public login route as SAML or password; never uses stored credentials |
| `auth/broker.py` | Headed browser login, identity-provider cookies discarded |
| `auth/adapters.py` | Turns browser cookies into a Splunk session key or a SOAR Django session |
| `auth/session.py` | Session records, store, target resolution |

SOAR requests use the browser session cookies when present, otherwise
the `ph-auth-token` header, with HTTP Basic for `DELETE` because the
server refuses tokens there (except on `decided_list`). See
[SOAR REST API notes](soar-api.md).

## Remote-first design

The CLI runs on the engineer's workstation and operates a remote
instance. It never assumes filesystem access to the server. Everything
goes through the REST API, with the Web UI used only where REST has gaps:

| Operation | Why REST fails | Path used |
|---|---|---|
| Lookup upload | `eai:data` requires a server-side path | `POST /manager/{app}/data/lookup-table-files/_new` |
| App install | REST expects a server-side file path | `POST /manager/appinstall/_upload` |
| SOAR playbook delete | No working REST route on 8.5 | Django login, then `POST /playbooks` |

`_WebSession` in `client.py` handles Splunk Web login, CSRF and multipart
upload. It honors the profile's `web_url` when the Web UI is not on the
API host. `soar/web.py` handles the SOAR Web UI with the host and port of
the REST API; it reuses a browser session when one exists and otherwise
needs username/password.

## REST adapters

`splunkctl/rest_adapters.py` provides the three entity collections that
upstream `splunk-sdk` lacks, over the SDK's authenticated transport:

| Entity | Endpoint | Client property |
|---|---|---|
| `Dashboard` | `data/ui/views` | `client.dashboards` |
| `LookupTableFile` | `data/lookup-table-files` | `client.lookup_table_files` |
| `HECToken` | `data/inputs/http` | `client.hec_tokens` |

Mutations use the entity's own `links.alternate` path returned by the
server, so names with special characters and app, global and system
sharing all route correctly. Other configuration objects use the SDK's
generic `service.confs` API or raw REST helpers in `client.py`.

## Safety model

- **Dry-run by default.** Every command that changes a remote instance
  is `@guarded`: it previews and exits 0 unless `--yes` is given, and the
  marker is exposed in the `commands --json` tree and the MCP tool
  schemas. Some previews read the server first to show the exact change.
  Local-only writes such as `config use` are not guarded.
- **SPL write commands.** `search run`, `export` and `oneshot` refuse SPL
  that contains `outputlookup`, `collect`, `sendalert`, `delete` and the
  other write commands in `spl_safety.py` unless `--yes` is given; the
  refusal is a `confirmation_required` error with exit 1.
- **Secrets.** Config is redacted on `config show`; SOAR asset previews
  mask keys that look like passwords or tokens; session values never
  appear in error strings.
- **Error envelope.** In JSON mode a classified failure is one stderr
  line with `kind` (auth, permission, not_found, conflict, http,
  connection, timeout, config, usage, confirmation_required, or the
  fallback `error`), `http_status` and `message`. Exceptions the
  classifier does not recognize propagate as a Python traceback. See
  [Exit codes](../guides/exit-codes.md).

## Agent access

`mcp serve` exposes the CLI over MCP. Five meta-tools (`help`, `usage`,
`focus`, `unfocus`, `run`) give progressive discovery; `focus` registers
one command group as typed tools generated from the Click tree. The guides
in `docs/guides/` ship inside the package as MCP resources. Transport is
stdio by default; `--transport http` binds loopback only and has no
authentication, which is why it is documented for a single-user machine.
`docs/llms.txt`, `docs/llms-full.txt` and `docs/commands.json` serve the
same content to agents that read the website instead.

## Design principles

1. **Dry-run by default.** Mutations preview before they apply.
2. **Dual output.** TTY gets tables, pipes get JSON. Always overridable.
3. **Lazy everything.** Auth, SDK connection and config loading are
   deferred until needed.
4. **One implementation.** The command reference, the `commands --json`
   tree and the MCP tool schemas all derive from the Click CLI.
5. **SDK-first.** Use the SDK where it works; adapters and Web UI
   workarounds only for documented gaps.
6. **Remote-first.** Never touch the server's filesystem.
7. **Agent-friendly.** Machine-readable output, self-discovery, docs that
   read well raw.
