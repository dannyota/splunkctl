# v0.3.0 Surface, Agent UX & Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the remaining capability gaps (search jobs, dashboards, HEC global settings, roles, server views), make the CLI fully agent-discoverable (guard markers), and ship v0.3.0 with truthful docs.

**Architecture:** Extend existing groups; one new group `server` (`splunkctl/commands/server.py`); guard metadata via a `@guard.guarded` decorator read by `commands_meta`; docs updated last against the real surface.

**Tech Stack:** Python 3.13, Click ≥8.2, splunk-sdk fork, difflib/xml.etree stdlib.

## Global Constraints

- Python ≤ 500 lines/file, Markdown ≤ 450 except `splunkctl/skill/SKILL.md` (`./scripts/check-lengths.sh`).
- `mypy --strict`, ruff, pytest green per commit; dry-run default; no push; no AI attribution; live objects `zzfix_*` cleaned in-task.

---

### Task 1: search — detach, job paging, truncation warning, jobs context

**Files:** Modify `splunkctl/commands/search.py`; test `tests/commands/test_search.py`.

- [ ] `search run --detach`: create the job, render `{"sid": ..., "status": "running"}`, exit 0 without polling. Poll loop only when not detached.
- [ ] Truncation notice: after `_read_results`, compare `int(job.content["resultCount"])` vs rendered rows; when more remain: `output.info(f"Showing {n} of {total} results (sid={job.sid}; use search job {job.sid} --offset ...)")`.
- [ ] `search job SID`: add `--offset INT` (0), `--count INT` (0=all), `--events` (raw events via `job.events(...)`), `--status-only`. Results fetch passes `offset`/`count`; header line to stderr `Job SID: DONE — N of TOTAL`. `--status-only` renders the status dict only.
- [ ] `search jobs`: add `owner` (`content.get("author","")`) and `spl` (`content.get("search","")` truncated to 60 chars) columns.
- [ ] Tests: detach renders sid and never calls `is_done` loop; truncation message when resultCount > limit; job paging kwargs asserted; jobs rows include spl/owner. Live: run `--detach` over `_internal`, then `search job <sid> --count 5 --offset 5`. Commit `feat: search detach, job result paging, truncation warnings`.

### Task 2: dashboards — validation, Studio, diff preview, bulk export, share

**Files:** Modify `splunkctl/commands/dashboards.py` (split helpers to `splunkctl/commands/dashboards_io.py` if >500); test `tests/commands/test_dashboards.py`.

- [ ] Client-side validation before guard preview in create/update: file starting with `{` (or `--type studio`) → `json.loads` (error: line/col from JSONDecodeError); else `xml.etree.ElementTree.fromstring` (error: `ParseError` line/col). Broken input now fails in DRY RUN too, exit 1.
- [ ] `--type classic|studio|auto` (default auto) on create/update. Studio: wrap JSON as `<dashboard version="2" theme="light"><label>{name}</label><definition><![CDATA[{json}]]></definition><meta type="hidden"><![CDATA[{"name":"splunkctl","version":1}]]></meta></dashboard>`.
- [ ] `dashboards get/export --definition`: when stored XML root carries `version="2"`, extract and pretty-print the CDATA JSON; error pointing at classic otherwise. `list` gains `type` column (`studio` when `version="2"` in `eai:data` root tag, else `classic`).
- [ ] Update dry-run diff: fetch current `eai:data`, `difflib.unified_diff(cur, new, lineterm="")`, show first 40 lines in guard details (note `… (+N more lines)`).
- [ ] `dashboards export --all [--app X] --dir DIR`: mutually exclusive with NAME; writes `<app>/<name>.xml` per dashboard (dashboards only, honoring Task-5-of-correctness filters); prints count.
- [ ] `dashboards share NAME --sharing app|global [--owner]` + `create --sharing` — via `client.set_acl`.
- [ ] Tests: broken XML → dry-run exit 1 with line/col; studio JSON wrapped (CDATA present, label injected); `--definition` unwraps; diff appears in dry-run output; `--all` writes N files (tmp_path); share posts acl. Live: studio round-trip create→export --definition compare, bulk export to temp dir, delete `zzfix_*`. Commit `feat: dashboards — client-side validation, Studio support, update diffs, bulk export, share`.

### Task 3: HEC global settings + --set passthrough sweep

**Files:** Modify `splunkctl/commands/hec.py`, `splunkctl/commands/inputs.py`, `splunkctl/commands/indexes.py`, `splunkctl/commands/users.py`; tests in matching test files.

- [ ] `hec settings`: GET `/services/data/inputs/http/http?output_mode=json` via `svc.get`; render `disabled`, `port`, `enableSSL`, `dedicatedIoThreads`. `hec settings --enable|--disable --yes`: POST same path `disabled=0|1`. Preview names the global endpoint explicitly.
- [ ] `hec create --set KEY=VALUE` (e.g. `useACK=1`); `inputs create/update --set` (covers interval, connection_host, whitelist…); `indexes create/update --set`; `users update --set`. All via `common.parse_set`, flags win over pairs.
- [ ] `hec send NAME EVENT [--index X --sourcetype Y]` — resolve the token value via `service.hec_tokens[NAME]`, resolve HEC port/SSL from global settings, POST `{"event": EVENT, ...}` to `<scheme>://host:<port>/services/collector/event` with `Authorization: Splunk <token>` via `requests` (reuse the client's `verify` setting; timeout from ctx). Guarded (it writes an event). Errors surface HEC's JSON `text` field (e.g. disabled endpoint) so a freshly created token is testable end-to-end.
- [ ] Tests: settings GET/POST paths asserted; `--set` merges into create kwargs for each group (one test per file); `hec send` posts correct auth header/body and reports HEC error text. Live: `hec settings` shows current state; toggle enable→send one `zzfix_` event through a `zzfix_` token→verify via search→restore original disabled state; token with `--set useACK=1` then delete. Commit `feat: hec global settings, hec send, generic --set passthrough`.

### Task 4: users — roles CRUD + password reset

**Files:** Modify `splunkctl/commands/users.py` (split `roles` into `splunkctl/commands/roles.py` if >500); test `tests/commands/test_users.py`.

- [ ] Convert `users roles` to a `click.Group(invoke_without_command=True)` — bare invocation still lists (back-compat). Subcommands:
  - `users roles get NAME` (full detail, capabilities NOT truncated in data formats),
  - `users roles create NAME --capabilities a,b --imported-roles user --search-indexes idx1,idx2 --search-filter '...' --default-app search --set K=V` (maps to `capabilities`, `imported_roles`, `srchIndexesAllowed`, `srchFilter`, `defaultApp`),
  - `users roles update NAME <same flags>`,
  - `users roles delete NAME`. All guarded.
- [ ] `users update --password` (str; preview shows `password: ***`).
- [ ] Tests: bare `users roles` lists; create maps flags to REST names; delete guarded; password masked in dry-run output but passed to update. Live: create role `zzfix_tier1` with `--search-indexes main --capabilities search`, assign to `zzfix_user`, password change, delete both. Commit `feat: role management and password reset`.

### Task 5: server group — messages, license, kvstore

**Files:** Create `splunkctl/commands/server.py`; register in `splunkctl/main.py`; test `tests/commands/test_server.py`.

- [ ] `server messages`: rows from `svc.messages.list()` → name, severity, message, timeCreated_iso; `empty="No system messages."`. `server messages --dismiss NAME --yes` deletes the message entity.
- [ ] `server license`: GET `/services/licenser/pools?output_mode=json` → title, used_bytes, effective_quota per pool; plus `/services/licenser/localpeer` quota summary if present.
- [ ] `server kvstore`: GET `/services/kvstore/status?output_mode=json` → current.status, replicaSet member states.
- [ ] Tests: three commands render mocked payloads; dismiss guarded. Live: all three read-only against the box (kvstore expected red — good realism). Commit `feat: server group — system messages, license usage, kvstore status`.

### Task 6: agent discovery — guard markers + global options in commands --json

**Files:** Modify `splunkctl/guard.py`, `splunkctl/commands/commands_meta.py`, every command module (decorator sweep); test `tests/commands/test_commands_meta.py`.

- [ ] `guard.guarded(cmd: click.Command) -> click.Command` decorator setting `cmd.guarded = True`; apply above every mutation command (`@guard.guarded` between `@group.command(...)` and options) across all groups — the sweep list is every command whose body calls `guard.check`.
- [ ] `commands_meta`: emit `"guarded": true` per marked command; add top-level `"global_options": [...]` from root group params (reuse `_param_entry`); add `"note": "guarded commands are dry-run by default; pass --yes to apply"`.
- [ ] Test: tree marks `indexes delete` guarded and `indexes list` not; `global_options` includes `--yes` and `--format`; assert no command calling guard.check lacks the marker via introspection test — walk `splunkctl.commands.*` sources with `ast` for `guard.check` calls and compare against markers (cheap tripwire for future commands).
- [ ] Commit `feat: commands --json exposes guard markers and global options`.

### Task 7: doctor — --strict, skill freshness, remediation hints

**Files:** Modify `splunkctl/commands/doctor.py`, `splunkctl/commands/skill_cmd.py`; test `tests/commands/test_doctor.py`.

- [ ] `--strict`: exit 1 when warnings > 0 (not just failures).
- [ ] Skill freshness check (offline, runs first): compare installed `~/.claude/skills/splunkctl/SKILL.md` bytes vs embedded resource; missing → OK ("not installed"); differs → WARN `stale — run: splunkctl skill install`.
- [ ] Health remediation: when splunkd health ≠ green, fetch the unhealthy features from the health endpoint response (`features` subtree) and print the first 3 reasons as detail; system-message check now includes first line of each error message text, not just names.
- [ ] Tests: strict exit code; stale-skill WARN (tmp home monkeypatch); health red detail includes feature name. Commit `feat: doctor --strict, skill staleness check, actionable health details`.

### Task 8: docs & release

**Files:** Modify `splunkctl/skill/SKILL.md`, `docs/design/catalog.md`, `docs/guides/*.md` (touched groups), `README.md`, `splunkctl/__init__.py`; create `CHANGELOG.md`.

- [ ] SKILL.md: global-flags table gains "work in any position"; fix `indexes create --max-size` example (now correct against server); lookups section unchanged (works now); rules section documents alert-semantics flags, `--set`, `share`, import diff/exit codes; alerts section documents suppress = saved-search throttle + `unsuppress`; parsers section rewritten around `set/unset/reload/export/import` + sharing default; search section adds `--detach`, `job --offset/--count/--events`, truncation note; dashboards adds studio/`--definition`/`--all`/share/validation; new `server`, `hec settings`, `users roles` blocks; JSON contract note: data formats always emit valid payload (`[]` when empty).
- [ ] catalog.md: statuses for every new command; note suppression semantics change and parsers default-sharing change under a "Behavior changes" heading.
- [ ] CHANGELOG.md: v0.3.0 — Fixed / Added / Changed lists from the three plans (one line per task).
- [ ] README.md: feature bullets for detection-as-code fidelity, parsers-as-code, studio dashboards, agent discovery markers.
- [ ] `__version__ = "0.3.0"`.
- [ ] Commit `docs: v0.3.0 command guide, catalog, changelog; bump version`.

### Task 9: release verification gate

- [ ] `ruff check . && ruff format --check . && mypy splunkctl/ && python -m pytest -q && ./scripts/check-lengths.sh` all green; `semgrep --pro --error .` if logged in (record outcome either way).
- [ ] Live smoke (each ends clean): lookup upload/update/delete; thresholded rule create→export→import→fire→alerts list/get→suppress→delete; parsers set/reload/export; dashboard studio create/export/delete; `search run --detach` + paged job fetch; `hec settings`; `server messages`; `doctor --strict` (expect exit 1 only for the box's known KV-store red — acceptable), `commands --json | jq '.commands[] | select(.name=="indexes")'` shows guard markers.
- [ ] Verify zero `zzfix_*` objects; `git log --oneline master..` reads as a clean story; leave branch unpushed for review.
