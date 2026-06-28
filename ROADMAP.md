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
```

---

## Recent waves (detail)

### Wave 1 — Core infrastructure *(planned)*

Shared modules every command group depends on:

- `config.py` — load/save `~/.splunkctl/config.yaml`, env var overlay,
  0600 permissions, secret redaction
- `client.py` — lazy SDK connection, auth resolution
  (CLI flags → env vars → config file), SSL toggle, timeout
- `output.py` — dual output (TTY = table, pipe = JSON), `--format`,
  `--fields` projection, `--out`, error envelope on stderr
- `guard.py` — mutation guard: dry-run preview, `--yes` to apply
- Unit tests for all four modules

### Wave 2 — Config commands *(planned)*

- `config init` — interactive setup (host, port, auth method, test, write)
- `config show` — display config with secrets redacted
- `config test` — verify connectivity and auth
- First end-to-end validation against a live Splunk instance

### Wave 3 — Info & version *(planned)*

- `info` — server info, license, version, OS
- `version` — CLI version
- Validates the full stack: config → client → SDK → Splunk → output

### Wave 4 — Search *(planned)*

- `search run` — sync search, print results
- `search export` — streaming export for large result sets
- `search oneshot` — quick one-off search
- SPL auto-prepend, time range (`--earliest`/`--latest`), `--limit`, `--app`

### Wave 5 — Search jobs *(planned)*

- `search jobs` — list running/recent jobs
- `search job <sid>` — get status and results
- `search cancel <sid>` — cancel a running job (guarded)

### Wave 6 — Rules *(planned)*

Detection rules (saved searches) — full CRUD:

- `rules list` / `get` / `create` / `update` / `delete`
- `rules enable` / `disable` — toggle scheduling
- `rules history` — run history
- `rules export` — export to YAML
- YAML rule format for create/update

### Wave 7 — Alerts *(planned)*

- `alerts list` / `get` — fired alerts
- `alerts actions` — list alert action types
- `alerts suppress` — suppress an alert (guarded)

### Wave 8 — Lookups *(planned)*

Lookup tables — full CRUD (raw REST, SDK gap):

- `lookups list` / `get` / `upload` / `update` / `download` / `delete`
- CSV upload and download handling

### Wave 9 — Dashboards *(planned)*

Dashboard CRUD (raw REST, SDK gap):

- `dashboards list` / `get` / `create` / `update` / `delete` / `export`
- XML and JSON dashboard format support

### Wave 10 — Inputs *(planned)*

Data inputs — full CRUD:

- `inputs list` / `get` / `create` / `update` / `delete`
- `inputs enable` / `disable`
- Types: monitor, tcp, udp, scripted, http (HEC)

### Wave 11 — Parsers *(planned)*

Source types and field extractions:

- `parsers sourcetypes` / `get` / `extractions`
- `parsers create` / `update` / `delete`
- Backed by the SDK `confs` API (`props.conf`, `transforms.conf`)

### Wave 12 — Indexes (full CRUD) *(planned)*

Extends the read-only `list`/`get` from Wave 4:

- `indexes create` / `update` / `delete` / `clean` / `reload`

### Wave 13 — Apps (full CRUD) *(planned)*

Extends the read-only `list`/`get` from Wave 4:

- `apps install` / `uninstall` / `update` / `reload`

### Wave 14 — Users & roles *(planned)*

- `users list` / `get` / `roles`
- `users create` / `update` / `delete`

### Wave 15 — Agent integration *(planned)*

- `commands --json` — machine-readable command tree for agents
- `skill` — print the embedded SKILL.md operating guide
- `skill install` — write SKILL.md to `~/.claude/skills/`
- Full SKILL.md authoring (auth, commands, workflows, SPL patterns)

### Wave 16 — Testing & hardening *(planned)*

- Integration test suite against a live Splunk instance
- Edge cases: large results, timeouts, auth failures, SSL errors
- All CI jobs green
- All guide docs filled in

### Wave 17 — v0.1.0 release *(planned)*

- README and docs polish
- PyPI trusted publishing setup
- GitHub release → PyPI publish
- Tag `v0.1.0`

---

## Post v0.1.0

- **SDK fork** — replace raw REST with proper SDK classes for dashboards,
  lookups, and HEC tokens in `dannyota/splunk-sdk-python`; upstream PRs
- **Multi-instance profiles** — `splunkctl config use <profile>`
- **Config as code** — pull/push workflow for rules and dashboards
