# Architecture

How splunkctl is built — the layers, the data flow, and the design decisions.

## Layers

```
┌─────────────────────────────────────────────┐
│  CLI layer (Click)                          │
│  splunkctl/main.py + commands/*.py          │
│  Global flags, command groups, subcommands  │
├─────────────────────────────────────────────┤
│  Service layer                              │
│  config.py · client.py · output.py · guard  │
│  Auth, formatting, mutation guard           │
├─────────────────────────────────────────────┤
│  SDK layer                                  │
│  splunklib (forked splunk-sdk-python)       │
│  REST API bindings, typed collections       │
├─────────────────────────────────────────────┤
│  Splunk Enterprise REST API (:8089)         │
│  /services/search/jobs, /services/data/...  │
└─────────────────────────────────────────────┘
```

## Data flow

```
User / Agent
  │
  ▼
splunkctl CLI (Click)
  │ parse flags, resolve format
  ▼
config.py ──► ~/.splunkctl/config.yaml (lazy load)
  │
  ▼
client.py ──► splunklib.client.connect() (lazy, on first API call)
  │
  ▼
guard.py ──► [DRY RUN] preview  ──or──  --yes → apply
  │
  ▼
output.py ──► table (TTY) / JSON (pipe) / csv / jsonl → stdout
```

## Auth resolution

Priority (highest first):

1. CLI flags (`--host`, `--port`, `--token`)
2. Environment variables (`SPLUNK_HOST`, `SPLUNK_PORT`, `SPLUNK_TOKEN`,
   `SPLUNK_USER`, `SPLUNK_PASS`)
3. Config file (`--config <path>` or `~/.splunkctl/config.yaml`)

Auth is **lazy** — credentials resolve on first API call. Help, version,
config, and offline commands never trigger auth.

## SDK gap strategy

The forked SDK at `dannyota/splunk-sdk-python` covers ~80% of the API surface.
Gaps are filled by adding proper collection/entity classes that wrap the
underlying REST endpoints, following the SDK's existing patterns.

For surfaces not worth a full SDK class (tags, field aliases), the generic
`confs` API (`client.confs["props"]`) serves as an escape hatch for any
`.conf` file manipulation.

Raw REST is used only where the SDK has no support and the surface is
important enough to warrant first-class CLI commands (dashboards, lookups).

## Design principles

1. **Dry-run by default.** Every mutation previews before applying.
2. **Dual output.** TTY gets tables, pipes get JSON. Always overridable.
3. **Lazy everything.** Auth, SDK connection, config loading — all deferred
   until needed.
4. **One file per command group.** Each `commands/*.py` is self-contained.
5. **SDK-first.** Use the SDK for everything it supports; raw REST only for
   documented gaps.
6. **Agent-friendly.** Machine-readable output, self-discovery, embedded skill.
