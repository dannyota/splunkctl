# v0.3.0 Detections & Parsers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the two core SecOps loops fully expressible through splunkctl: authoring real detections (alert semantics, ACLs, detection-as-code fidelity) and onboarding a new log source (props/transforms editing, sharing, reload, parsers-as-code).

**Architecture:** Extend `rules`/`parsers` command groups; shared `--set key=value` parser in new `splunkctl/commands/common.py`; generic ACL helper on `SplunkClient`; parsers-as-code lives in new `splunkctl/commands/parsers_io.py` mirroring `rules_io.py`.

**Tech Stack:** Python 3.13, Click ≥8.2, splunk-sdk fork (`service.confs`, `service.saved_searches`), PyYAML.

## Global Constraints

- Python ≤ 500 lines/file, Markdown ≤ 450 (`./scripts/check-lengths.sh`); split into sibling modules when over.
- `mypy --strict`, ruff, pytest green per commit. Dry-run default, `--yes` applies.
- No git push; no AI attribution; live objects `zzfix_*` only, deleted in-task.

---

### Task 1: shared `--set` parser + ACL helper

**Files:** Create `splunkctl/commands/common.py`; modify `splunkctl/client.py`; tests `tests/commands/test_common.py`, `tests/test_client.py`.

**Interfaces produced:**
- `common.parse_set(pairs: tuple[str, ...]) -> dict[str, str]` — splits on first `=`; raises `click.BadParameter("expected KEY=VALUE, got '...'")`; rejects keys starting `eai:`.
- `SplunkClient.set_acl(entity: Any, *, sharing: str, owner: str | None = None) -> None` — POST `{entity.path}acl` with `sharing`, `owner` (default: entity's current owner, falling back to "nobody" for app/global).

- [ ] Tests: `parse_set` happy path, value containing `=`, missing `=` → BadParameter, `eai:` rejected; `set_acl` posts to `<path>acl` with sharing/owner (mock service).
- [ ] Implement both; commit `feat: shared --set parser and ACL helper`.

### Task 2: rules create/update — alert semantics flags, --set, update --app

**Files:** Modify `splunkctl/commands/rules.py`; test `tests/commands/test_rules.py`.

**New options on `rules create` and `rules update`:**

| Flag | REST field |
|---|---|
| `--earliest` / `--latest` | `dispatch.earliest_time` / `dispatch.latest_time` |
| `--alert-type` (choice: custom, number of events, number of hosts, number of sources) | `alert_type` |
| `--alert-comparator` (choice: greater than, less than, equal to, not equal to, drops by, rises by) | `alert_comparator` |
| `--alert-threshold` | `alert_threshold` |
| `--severity` (1-6) | `alert.severity` |
| `--throttle SECONDS` | `alert.suppress=1` + `alert.suppress.period=<N>s` |
| `--throttle-fields` | `alert.suppress.fields` |
| `--track/--no-track` | `alert.track` |
| `--schedule-window` | `schedule_window` |
| `--set KEY=VALUE` (repeatable) | verbatim passthrough (e.g. `action.email.to=soc@example.com`) |

Setting any alert flag without `--alert-type` defaults `alert_type` to `number of events`; `--alert-comparator/threshold` require each other (BadParameter otherwise). `update` gains `--app` (resolve entity via `saved_searches.list(search=f"name={name}", app=app, count=1)` when given). Build kwargs via a shared `_alert_kwargs(...)` helper used by both commands; `--set` pairs merge last (explicit flags win — update kwargs with flag values after set-pairs).

- [ ] Tests: create with threshold trio asserts kwargs `{"alert_type": "number of events", "alert_comparator": "greater than", "alert_threshold": "5", "alert.track": "1"}`; throttle expands to two fields; `--set action.email.to=x` passes through; comparator without threshold → exit ≠0 usage error; update `--app` resolves namespaced.
- [ ] Implement; if rules.py > 500 lines move `_alert_kwargs` + option decorators into `common.py` as `alert_options(f)` decorator stack.
- [ ] Live: create `zzfix_det` with cron + threshold + throttle + severity `--yes`; `rules get` shows all fields; delete. Commit `feat: rules create/update express full alert semantics with --set passthrough`.

### Task 3: rules get/list enrichment + share

**Files:** Modify `splunkctl/commands/rules.py`; test `tests/commands/test_rules.py`.

- [ ] `rules get`: add `app`, `owner`, `sharing` from `ss.access`; add `alert_comparator`, `alert_threshold`, `alert.suppress.period`, `schedule_window` to `_DETAIL_FIELDS`.
- [ ] `rules list`: add `--filter SUBSTR` (case-insensitive name match, client-side) and include `description`, `severity` (`alert.severity`) in rows.
- [ ] New `rules share NAME --sharing user|app|global [--owner X]` — guarded; uses `client.set_acl`; preview shows current → target sharing.
- [ ] New `rules test NAME [--earliest X --latest Y] [--limit N]` (backfill/test-run): `ss.dispatch(**{"dispatch.earliest_time": earliest, "dispatch.latest_time": latest, "trigger_actions": "0"})`, poll like `search run` honoring `--timeout`, render results + `output.info` row count. Read-only dispatch (no alert actions fired) → not guarded.
- [ ] Tests: filter narrows; share posts acl; get shows acl fields; test dispatches with overridden window and renders rows. Live: share `zzfix_det2` to app, `rules test zzfix_det2 --earliest -1h`, delete. Commit `feat: rules share, test-run (backfill), richer get/list (--filter)`.

### Task 4: detection-as-code fidelity (export/import)

**Files:** Modify `splunkctl/commands/rules_io.py`; test `tests/commands/test_rules_io.py`.

**Design:**
- Export: extend `_EXPORT_FIELDS` with `alert_comparator`, `alert_threshold`, `alert_condition`, `alert.digest_mode`, `alert.expires`, `schedule_window`, `realtime_schedule`. Additionally export `action.<a>.<param>` keys for each action named in `actions` (non-empty values only). Value-keep rule becomes `val not in ("", None)` (stop dropping meaningful `"0"`).
- Import: stop whitelisting — pass through every scalar key except `name`, `app`, and computed/readonly prefixes (`eai:`, `embed.`, `next_scheduled_time`, `qualifiedSearch`, `triggered_alert_count`). YAML is authoritative.
- Import preview (dry-run) becomes a real diff: for each doc, fetch existing rule; print `create: <name>` or `update: <name>` with per-key `  key: old -> new` lines (values truncated to 60 chars), or `unchanged: <name>`.
- Result reporting: every skip prints `skip:<name>: <reason>` to stderr; exit 1 when skips or errors > 0. Re-import of identical file reports `N unchanged` (compare before update; skip server call when no delta).

- [ ] Tests: export includes comparator/threshold when set on mock; import passes unknown key `alert_comparator` through to `ss.update`; unchanged file → "unchanged", no update call, exit 0; missing-search doc → named skip + exit 1; dry-run prints `key: old -> new`.
- [ ] Live round-trip: export `zzfix_det`, edit threshold in YAML, import `--yes`, `rules get` shows new threshold; import again → unchanged, exit 0. Commit `fix: detection-as-code round-trips alert semantics; named skips fail the import`.

### Task 5: parsers set/unset — real conf key editing

**Files:** Modify `splunkctl/commands/parsers.py`; test `tests/commands/test_parsers.py`.

**Interface:**
```
splunkctl parsers set STANZA KEY=VALUE... [--conf props|transforms] [--app search]
    [--sharing user|app|global] [--no-create] --yes
splunkctl parsers unset STANZA KEY... [--conf props|transforms] --yes   # sets keys to ""
```
`set` creates the stanza when missing (unless `--no-create`), applies all pairs in one `stanza.update(**pairs)` (or `conf.create(stanza, **pairs)`), then promotes sharing via `client.set_acl` when `--sharing` given. **Default `--sharing app` on newly created stanzas** — user-private parsing stanzas don't apply at index time (evaluation bug); update of an existing stanza leaves ACL untouched unless flag present. `unset` warns: REST cannot remove conf keys; values are cleared to empty string.

- [ ] Tests: multi-pair update in one call; create-on-missing with sharing promotion posted to acl; `--no-create` + missing → exit 1; unset clears values and warns; invalid pair → BadParameter.
- [ ] `parsers create` (existing) gains the same `--sharing` (default app) — one-line reuse.
- [ ] Commit `feat: parsers set/unset edit props and transforms keys with app sharing by default`.

### Task 6: parsers reload / get --explicit / sourcetypes --filter

**Files:** Modify `splunkctl/commands/parsers.py`; test `tests/commands/test_parsers.py`.

- [ ] `parsers reload [--conf props|transforms|all]` (default all) — guarded; POST `/services/configs/conf-props/_reload` and/or `conf-transforms/_reload` via `svc.post`.
- [ ] `parsers get STANZA --explicit` — fetch `/servicesNS/nobody/{app}/configs/conf-props/{stanza}?output_mode=json` via `svc.get`, render content keys minus `eai:*` / `disabled`; plain `get` unchanged (merged view). Add `--conf` to `get` for transforms stanzas.
- [ ] `parsers sourcetypes --filter SUBSTR` client-side name filter.
- [ ] Tests for each (mock svc.post/get paths asserted). Live: `parsers reload --yes` returns OK. Commit `feat: parsers reload, explicit-key get, sourcetype filter`.

### Task 7: parsers-as-code (export/import YAML)

**Files:** Create `splunkctl/commands/parsers_io.py`; modify `splunkctl/commands/parsers.py` (register); test `tests/commands/test_parsers_io.py`.

**YAML shape (one doc per stanza):**
```yaml
- conf: props
  stanza: zzfix_acmefw
  sharing: app
  keys:
    TIME_PREFIX: ^
    TIME_FORMAT: '%Y-%m-%d %H:%M:%S.%3N %z'
    LINE_BREAKER: ([\r\n]+)\d{4}-\d{2}-\d{2}
    SHOULD_LINEMERGE: "false"
    EXTRACT-acme: action=(?<action>\w+)
```
- `parsers export --path f.yaml [--conf props|transforms|all] [--filter SUBSTR]` — explicit keys via the configs endpoint (same fetch as Task 6), skips stanzas with no explicit keys; writes list.
- `parsers import --path f.yaml --yes` — per-stanza create-or-update through the same code path as `parsers set` (factor `_apply_stanza(svc, client, doc) -> str` returning `created:|updated:|unchanged:|skip:<reason>`); dry-run prints per-key diff like rules import; exit 1 on skip/error.

- [ ] Tests: export writes explicit keys only; import applies pairs + acl; bad doc (no stanza) → named skip, exit 1; idempotent re-import → unchanged.
- [ ] Commit `feat: parsers-as-code — YAML export/import for props and transforms`.

### Task 8: live end-to-end AcmeFW onboarding (verification gate)

No new code — proves the loop the evaluation called impossible, using only splunkctl:

- [ ] Generate 20 synthetic `zzfix_acmefw` k=v lines (one multiline event) in a temp dir.
- [ ] `indexes create --name zzfix_acmefw --yes`; `parsers set zzfix_acmefw TIME_PREFIX=^ 'TIME_FORMAT=%Y-%m-%d %H:%M:%S.%3N %z' 'LINE_BREAKER=([\r\n]+)\d{4}-' SHOULD_LINEMERGE=false 'EXTRACT-acme=action=(?<action>\w+) .*user=(?<user>\w+)' --sharing app --yes`; `parsers reload --yes`.
- [ ] `search upload --path events.log --index zzfix_acmefw --sourcetype zzfix_acmefw --yes`; wait ~10s; `search run 'index=zzfix_acmefw | stats count by action, user' --earliest -1h` shows extracted fields; multiline event intact (`search run 'index=zzfix_acmefw' --limit 25` count matches events, not lines).
- [ ] `parsers export --path /tmp/zzfix_parsers.yaml --filter zzfix` round-trips; `parsers import` of same file → unchanged, exit 0.
- [ ] Cleanup: `parsers delete zzfix_acmefw --yes`, `indexes delete zzfix_acmefw --yes`, temp files removed; record results in commit message `test: verify AcmeFW onboarding end-to-end via CLI only`.
