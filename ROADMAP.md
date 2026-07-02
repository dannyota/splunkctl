# splunkctl — Roadmap

Forward plan and wave sequencing. Build status lives in
[docs/design/catalog.md](docs/design/catalog.md).

> **Scope of this file.** What ships and in what order — not implementation
> detail. Completed waves are trimmed; full history remains in git.

## Wave map

Waves are done in order. Each ships a working increment with tests and updated
docs. Per-command status is in [docs/design/catalog.md](docs/design/catalog.md).

```
Phase 1 (1–3)   foundation ─► plumbing, config, info
Phase 2 (4–5)   search ─► the most-used commands
Phase 3 (6–8)   detection ─► rules, alerts, lookups
Phase 4 (9–11)  config surfaces ─► dashboards, inputs, parsers
Phase 5 (12–14) admin ─► indexes, apps, users (full CRUD)
Phase 6 (15–17) release ─► agent integration, hardening, v0.1.0
Phase 7 (18–20) reliability ─► SOC bug fixes, errors, paging, profiles
Phase 8 (21–23) bank SOC ─► ES notables, audit pack, KV store
Phase 9 (24–25) detection depth ─► conf editor, macros, data models
Phase 10 (26–27) change control ─► config-as-code state, topology health
```

Phases 7–10 come from the 2026-07 bank-SOC gap analysis; task-level detail
is in [PLAN.md](PLAN.md) (phases E–I).

---

## Recent waves (detail)

### Wave 1 — Core infrastructure *(done)*

Shared modules every command group depends on:

- `config.py` — load/save `~/.splunkctl/config.yaml`, env var overlay,
  0600 permissions, secret redaction
- `client.py` — lazy SDK connection, auth resolution
  (CLI flags → env vars → config file), SSL toggle, timeout
- `output.py` — dual output (TTY = table, pipe = JSON), `--format`,
  `--fields` projection, `--out`, error envelope on stderr
- `guard.py` — mutation guard: dry-run preview, `--yes` to apply
- Unit tests for all four modules

### Wave 2 — Config commands *(done)*

- `config init` — interactive setup (host, port, auth method, test, write)
- `config show` — display config with secrets redacted
- `config test` — verify connectivity and auth
- First end-to-end validation against a live Splunk instance

### Wave 3 — Info & version *(done)*

- `info` — server info, license, version, OS
- `version` — CLI version
- Validates the full stack: config → client → SDK → Splunk → output

### Wave 4 — Search *(done)*

- `search run` — sync search, print results
- `search export` — streaming export for large result sets
- `search oneshot` — quick one-off search
- SPL auto-prepend, time range (`--earliest`/`--latest`), `--limit`, `--app`

### Wave 5 — Search jobs *(done)*

- `search jobs` — list running/recent jobs
- `search job <sid>` — get status and results
- `search cancel <sid>` — cancel a running job (guarded)

### Wave 6 — Rules *(done)*

Detection rules (saved searches) — full CRUD:

- `rules list` / `get` / `create` / `update` / `delete`
- `rules enable` / `disable` — toggle scheduling
- `rules history` — run history
- `rules export` — export to YAML
- YAML rule format for create/update

### Wave 7 — Alerts *(done)*

- `alerts list` / `get` — fired alerts
- `alerts actions` — list alert action types
- `alerts suppress` — suppress an alert (guarded)

### Wave 8 — Lookups *(done)*

Lookup tables — full CRUD (raw REST, SDK gap):

- `lookups list` / `get` / `upload` / `update` / `download` / `delete`
- CSV upload and download handling

### Wave 9 — Dashboards *(done)*

Dashboard CRUD (raw REST, SDK gap):

- `dashboards list` / `get` / `create` / `update` / `delete` / `export`
- XML and JSON dashboard format support

### Wave 10 — Inputs *(done)*

Data inputs — full CRUD:

- `inputs list` / `get` / `create` / `update` / `delete`
- `inputs enable` / `disable`
- Types: monitor, tcp, udp, scripted, http (HEC)

### Wave 11 — Parsers *(done)*

Source types and field extractions:

- `parsers sourcetypes` / `get` / `extractions`
- `parsers create` / `update` / `delete`
- Backed by the SDK `confs` API (`props.conf`, `transforms.conf`)

### Wave 12 — Indexes (full CRUD) *(done)*

Extends the read-only `list`/`get` from Wave 4:

- `indexes create` / `update` / `delete` / `clean` / `reload`

### Wave 13 — Apps (full CRUD) *(done)*

Extends the read-only `list`/`get` from Wave 4:

- `apps install` / `uninstall` / `update` / `reload`

### Wave 14 — Users & roles *(done)*

- `users list` / `get` / `roles`
- `users create` / `update` / `delete`

### Wave 15 — Agent integration *(done)*

- `commands --json` — machine-readable command tree for agents
- `skill` — print the embedded SKILL.md operating guide
- `skill install` — write SKILL.md to `~/.claude/skills/`
- Full SKILL.md authoring (auth, commands, workflows, SPL patterns)

### Wave 16 — Testing & hardening *(done)*

- Integration test suite against a live Splunk instance
- Edge cases: large results, timeouts, auth failures, SSL errors
- All CI jobs green
- All guide docs filled in

### Wave 17 — v0.1.0 release *(done)*

- README and docs polish
- PyPI trusted publishing setup
- GitHub release → PyPI publish
- Tag `v0.1.0`

---

## Upcoming waves

Sequenced from the 2026-07 bank-SOC gap analysis (live CLI evaluation +
REST surface audit). Detail per task in [PLAN.md](PLAN.md). Wave 18 ships
as v0.3.1; waves 19–27 ship together as v0.4.0.

### Wave 18 — SOC bug fixes & docs *(→ v0.3.1)*

Defects confirmed live: `rules list` blind to app-private detections
(`--app` scoping), `search jobs` empty owner, `rules get` hiding
`action.*` params, blank `server kvstore` on failure, dry-run not
validating required action fields, truncated non-JSON import diff. Plus
SKILL.md ES recipes (notables/risk read, `--set action.notable.*`) and the
`sid` → `search job` alert-investigation pivot.

### Wave 19 — Structured errors & pagination

JSON error envelope (kind/http-status) under `--json`; `--limit`/
`--offset`/`--all` and uniform `--filter` on every list command — no
silent truncation of detection or user inventories.

### Wave 20 — Multi-instance profiles

`config use <profile>` for dev/UAT/prod; active profile + host in every
dry-run banner as a prod-safety control.

### Wave 21 — ES notable triage

`es notables list/get/update` — the SOC incident-review loop (status,
owner, urgency, disposition, comment) via ES `notable_update`;
feature-detected, clean error without ES.

### Wave 22 — Audit & RBAC pack

`audit changes` normalizing both `_audit` event shapes; `audit rbac`
users × roles × capabilities attestation export — regulator evidence.

### Wave 23 — KV store

Collections + data CRUD + JSONL import/export — allowlists, threat intel,
ES asset/identity.

### Wave 24 — Generic conf editor & knowledge objects

`conf files/list/get/set/unset/reload` over any conf file; thin
`macros`/`eventtypes`/`tags` verbs on top.

### Wave 25 — Detection depth

`datamodels` (list/acceleration/rebuild), lookup definitions + automatic
lookups, first-class alert-action flags (`--email-to`, `--webhook-url`).

### Wave 26 — Config-as-code state

`state pull/push/diff` across rules, parsers, dashboards, lookups, macros;
push writes a before→after diff artifact for change tickets.

### Wave 27 — Topology health *(→ v0.4.0)*

Read-only `server cluster`/`shcluster`/`deployment` — distinguish "no
threat" from "an indexer is down".

## Deferred

- Forwarder fleet / deployment-server management (health read is Wave 27)
- ES governance surfaces (incident-review settings, threat-intel framework)
- Workflow actions CRUD; auth-token minting; JSON `schemaVersion`

## Done post v0.1.0

- **SDK fork** — `Dashboard`, `LookupTableFile`, `HECToken` classes in
  `dannyota/splunk-sdk-python`, integrated (v0.2.0); first-class alert
  actions folded into Wave 25 as CLI flags (no fork work needed)
- **Doctor & Web UI workarounds** — lookup upload, app install, data
  upload (v0.2.0–v0.3.0)
