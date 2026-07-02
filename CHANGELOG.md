# Changelog

## 0.3.0

### New commands
- **`server messages`** — list/dismiss system messages
- **`server license`** — license pool usage
- **`server kvstore`** — KV store status
- **`hec settings`** — global HEC state (port, SSL, enable/disable)
- **`hec send`** — send an event through HEC
- **`users roles get/create/update/delete`** — full role CRUD
- **`dashboards share`** — change dashboard sharing/ownership
- **`alerts unsuppress`** — remove alert throttling
- **`parsers set/unset`** — edit props/transforms keys
- **`parsers reload`** — reload parser configs
- **`parsers export/import`** — YAML round-trip for props/transforms

### Enhancements
- **search run** `--detach` starts a job and returns the SID without polling
- **search run** prints truncation notice when results are capped
- **search jobs** shows `owner` and `spl` preview columns
- **search job** gains `--offset`, `--count`, `--events`, `--status-only`
- **dashboards list** shows `type` column (classic/studio)
- **dashboards get/export** `--definition` extracts Studio JSON
- **dashboards create** `--type classic|studio|auto` with JSON-to-XML wrapping
- **dashboards create** `--sharing` sets ACL on creation
- **dashboards update** shows unified diff preview in dry-run
- **dashboards export** `--all --dir` for bulk export
- **hec create** `--set key=value` for arbitrary token properties
- **users update** `--password` for password reset (masked in dry-run)
- **rules list** `--filter key=value` for field filtering
- **rules share** sets sharing/ownership
- **rules create/update** `--set` passthrough for full alert semantics
- **rules import** shows diff in dry-run, fails on skip-only imports
- **parsers get** `--key` for single key retrieval
- **parsers sourcetypes** `--sourcetype` filter
- **doctor** `--strict` treats warnings as failures
- **doctor** prints remediation hints for failures/warnings
- **doctor** checks skill freshness (installed vs embedded SKILL.md)
- **commands --json** exposes `guarded` markers, `global_options`, and `note`

### Fixes
- Output contracts: JSON always emits `[]` on empty, CSV uses column union
- Info messages to stderr only in table mode; clean stdout for piping
- `indexes --max-size` maps to correct REST arg `maxTotalDataSizeMB`
- `indexes clean --clean-timeout` with graceful error handling
- `lookups download` fails with clear error when lookup doesn't exist
- `dashboards list` hides non-dashboard views by default (`--all` to show)
- Capabilities never truncated in machine-readable output
- Global flags work after subcommands without shadowing leaf options
- Web UI session ported from urllib to requests (fixes Splunk 10.4 redirects)
- XML parsing uses `defusedxml` to prevent XXE attacks

### Infrastructure
- `@guard.guarded` decorator on all 52 mutation commands with AST tripwire test
- `defusedxml` added as dependency
- `click>=8.2` required for CliRunner stderr separation
- 321 tests passing

## 0.2.0

Initial public release with full CLI for Splunk Enterprise.

## 0.1.0

Internal scaffold.
