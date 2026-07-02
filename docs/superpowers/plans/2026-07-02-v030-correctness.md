# v0.3.0 Correctness Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix every confirmed bug from the 2026-07-02 SecOps agent evaluation: output-contract violations, wrong REST args, broken Web-UI uploads, and the alerts command group.

**Architecture:** Surgical fixes inside existing modules; one new dependency (`requests`) replacing the stdlib urllib stack in `_WebSession`. Every fix lands with a mocked CliRunner test and, where marked, a live check against the local Splunk 10.4 instance (`export $(grep -v '^#' .env | xargs)`, objects prefixed `zzfix_`, deleted afterward).

**Tech Stack:** Python 3.13, Click ≥8.2, splunk-sdk fork, requests ≥2.32, pytest with `@patch("splunkctl.commands.<mod>.get_client")` + CliRunner.

## Global Constraints

- Python files ≤ 500 lines, Markdown ≤ 450 lines (`./scripts/check-lengths.sh`).
- `mypy --strict` clean; ruff check + format clean; all pytest green before each commit.
- Dry-run by default; `--yes` applies. Never bypass `guard.check`.
- No git push. No AI attribution in commits. No secrets/hostnames in code or docs.
- Live tests only against the local instance with `zzfix_*` names, cleaned up in the same task.

---

### Task 1: Output contract — CSV column union, empty-list `[]`, table-detection helper

**Files:** Modify `splunkctl/output.py`; test `tests/test_output.py`.

**Interfaces produced:**
- `output.render(ctx, data, *, empty: str | None = None)` — new keyword. Empty rows: JSON→`[]` on stdout; csv/jsonl→no stdout; table→`empty` (or "No results.") to **stderr**; the message never lands on stdout in data formats.
- `output.is_table(ctx) -> bool` — True when resolved format is table (explicit `--format table`, or no format flags and stdout is a TTY).
- `_csv(rows)` uses the ordered union of keys across all rows.

- [ ] Tests: `test_csv_sparse_columns_union` (rows `[{"a":1},{"a":2,"b":3}]` → header `a,b`, second row `2,3`), `test_json_empty_list_stdout` (`--json` + `[]` payload prints `[]`), `test_table_empty_message_stderr`, `test_is_table_resolution`.
- [ ] Implement: `_csv` builds `fieldnames` by first-seen order across rows; `render` gains `empty` kwarg with the branch table above; add `is_table`.
- [ ] Sweep callers that early-return before `render` on empty rows and delete the guard, passing `empty=` instead: `alerts.py` list (drop lines 36-38), `hec.py` list (drop 32-34), `users.py` list (92-94) + roles (120-122), `lookups.py` list (34-36), `rules_io.py` export keeps its message (file write, not render).
- [ ] Run `python -m pytest tests/ -q`, `ruff check .`, `mypy splunkctl/`; commit `fix: output contracts — CSV column union, JSON [] on empty, stderr-only messages`.

### Task 2: users/roles full capabilities in machine output

**Files:** Modify `splunkctl/commands/users.py`; test `tests/commands/test_users.py`.

- [ ] Test: `test_get_user_json_full_capabilities` — mock user with 8 capabilities; `--json users get x` output contains all 8 and no `"+3 more"`. `test_get_user_table_truncates` keeps truncation in table mode.
- [ ] Implement: `_user_detail(user, *, truncate: bool)` — truncate only when True; caller passes `output.is_table(ctx)`. Same for `_role_row`.
- [ ] Commit `fix: never truncate capabilities in machine-readable output`.

### Task 3: indexes — correct REST arg + clean timeout handling

**Files:** Modify `splunkctl/commands/indexes.py`; test `tests/commands/test_indexes.py`.

- [ ] Tests: `test_create_max_size_sends_maxTotalDataSizeMB` (assert `create` kwargs key `maxTotalDataSizeMB`), same for update; `test_clean_timeout_flag` (assert `idx.clean(timeout=120)`); `test_clean_operation_error` (clean raises `OperationError` → exit 1, message contains "--timeout", no traceback).
- [ ] Implement: rename kwarg at indexes.py:103 and :139; add `--timeout` option (default 60) to `clean` passing through; wrap `idx.clean` in `try/except OperationError` (import from `splunklib.client`), on failure `idx.refresh()` and report whether the index was left disabled; exit 1.
- [ ] Live check: `zzfix_idx` create with `--max-size 100 --frozen-period 86400 --yes` (must 200), get shows `maxTotalDataSizeMB=100`, update `--max-size 200`, delete. 
- [ ] Commit `fix: indexes --max-size maps to maxTotalDataSizeMB; clean gets --timeout and clean errors`.

### Task 4: lookups download — fail on missing lookup

**Files:** Modify `splunkctl/commands/lookups.py`; test `tests/commands/test_lookups.py`.

- [ ] Test: `test_download_missing_lookup_fails` — `lookup_table_files.list` returns `[]` → exit 1, stderr contains "not found", no file written.
- [ ] Implement: before the oneshot, resolve the lookup via `lookup_table_files.list(search=f"name={name}", app=app, owner="-", count=1)`; empty → error + exit 1.
- [ ] Commit `fix: lookups download errors on nonexistent lookup instead of writing empty file`.

### Task 5: dashboards list — real app filter, dashboards-only default

**Files:** Modify `splunkctl/commands/dashboards.py`; test `tests/commands/test_dashboards.py`.

- [ ] Tests: `test_list_app_filters_rows` (mock entries with `access.app` "search"/"system" → only "search" rows when `--app search`); `test_list_excludes_non_dashboards_by_default` (`isDashboard: "0"` hidden; shown with `--all`).
- [ ] Implement: keep namespace query, then post-filter `d.access.app == app` when `app != "-"`; skip `isDashboard in ("0", False)` unless new `--all` flag; add `owner`, `sharing` (`d.access["sharing"]`), `updated` (`d.state.get("updated","")` — verify attr live, else omit) columns.
- [ ] Live check: `dashboards list --app search --json | jq '[.[].app] | unique'` → `["search"]`.
- [ ] Commit `fix: dashboards list --app filters by app and hides non-dashboard views by default`.

### Task 6: leaf-aware global flag hoisting (--out et al.)

**Files:** Modify `splunkctl/main.py`; test `tests/test_main_hoisting.py` (new).

**Design:** `_CLI.parse_args` gains leaf resolution: walk `rest` tokens through `self.commands` to find the target `click.Command`; hoist a flag only when the leaf does not define it itself. Add `--out`/`-o` to `_HOIST_VALUE`. This keeps `dashboards export --out`, `lookups download --out`, and the new `indexes clean --timeout` working while `splunkctl indexes list --out f.csv` starts working.

- [ ] Tests: `test_out_after_subcommand_writes_file` (indexes list --out), `test_dashboards_export_local_out_untouched` (leaf keeps its own `--out`), `test_timeout_hoists_except_leaf_param` (indexes clean --timeout stays local; search run --timeout hoists), existing hoist behaviors regression (`--json` trailing).
- [ ] Implement:
```python
def _leaf_opts(self, args: list[str]) -> frozenset[str]:
    cmd: click.Command | None = self
    opts: set[str] = set()
    for tok in args:
        if tok.startswith("-"):
            continue
        if isinstance(cmd, click.Group) and tok in cmd.commands:
            cmd = cmd.commands[tok]
        else:
            break
    if cmd is not self:
        for p in cmd.params:
            opts.update(p.opts + p.secondary_opts)
    return frozenset(opts)
```
   In the hoist loop, skip tokens present in `leaf_opts`.
- [ ] Commit `fix: global flags (incl. --out) work after subcommands without shadowing leaf options`.

### Task 7: _WebSession → requests (lookup upload/update, app install, --debug web logging)

**Files:** Modify `splunkctl/client.py`, `pyproject.toml` (add `requests>=2.32`, dev extra `types-requests`); test `tests/test_client.py`.

**Design (root cause proven 2026-07-02):** stdlib urllib flow draws a 303 from the manager form handler and follows it as GET → 404; `requests.Session` (keep-alive) gets the JSON 200 and the object is created. Replace transport wholesale; delete `_multipart_post` and cookiejar code.

```python
class _WebSession:
    def __init__(self, service: Any, *, verify: bool = True, debug: bool = False) -> None: ...
    def _request(self, method: str, url: str, **kw: Any) -> requests.Response:
        resp = self._session.request(method, url, timeout=30, **kw)
        if self._debug:
            click.echo(f"web {method} {url} -> {resp.status_code}", err=True)
        return resp
    def _login(self) -> None:  # GET login (cval regex) → POST creds → csrf cookie
    def upload_lookup(self, name, file_path, *, app="search", update=False) -> None:
        # POST multipart: data={"__action","__redirect","__ns","splunk_form_key",("name")},
        # files={"spl-ctrl_lookupfile": (name, file_path.read_bytes(), "text/csv")}
        # expect JSON {"status": "OK"}; non-JSON or status!=OK → RuntimeError with body head
    def install_app(self, file_path, *, force=False) -> None:  # GET _upload for state, POST multipart appfile
```
`SplunkClient._ensure_web_session` passes `debug=self._debug`. TLS verification stays ON by default; only when the user's config explicitly sets `verify: false` (local self-signed dev) does the session get `verify=False`, and urllib3's `InsecureRequestWarning` is left enabled so the unverified state stays visible on stderr (it fires once per process). Never suppress the warning globally.

- [ ] Tests: fake `requests.Session` via `unittest.mock.patch("splunkctl.client.requests.Session")` — `test_websession_login_extracts_csrf`, `test_upload_lookup_posts_form_fields` (asserts URL ends `/data/lookup-table-files/_new`, form key present, file tuple), `test_upload_lookup_error_raises` (JSON status fail → RuntimeError w/ msg), `test_install_app_posts_state`.
- [ ] Implement; delete urllib/cookiejar imports; keep token-auth guard message.
- [ ] Live check (the previously-broken path): `echo 'h,o\nzz,1' > /tmp/zzfix.csv; splunkctl lookups upload zzfix_websess.csv --file /tmp/zzfix.csv --app search --yes` → success; `lookups update ... --yes`; `--debug` shows `web POST ... -> 200` lines; `lookups delete ... --yes`. App install: build 1-file app tarball `zzfix_app.tar.gz` (app.conf only), `apps install --name zzfix_app --path ... --yes`, verify in `apps list`, `apps uninstall zzfix_app --yes`.
- [ ] Commit `fix: port Web UI session to requests — lookup upload/update and app install work on Splunk 10.4`.

### Task 8: alerts group rework (list firings, non-crashing get, working suppress)

**Files:** Modify `splunkctl/commands/alerts.py`; test `tests/commands/test_alerts.py`.

**Design:** fired-alert *groups* come from `service.fired_alerts`; each `AlertGroup.alerts` is a Collection of firings whose content carries `trigger_time_rendered`, `severity`, `sid`, `savedsearch_name`. Suppress moves to the saved search (`alert.suppress*`), since the fired-alerts handler only supports list|remove.

- [ ] Tests: `test_list_alerts_rows_per_firing` (group with 2 firings → 2 rows, each with sid + triggered time + severity), `test_get_alert_multiple_firings_no_crash` (regression for AmbiguousReferenceException — get iterates `group.alerts`, never `collection[name]` on firings), `test_suppress_sets_saved_search_fields` (asserts `ss.update(**{"alert.suppress": "1", "alert.suppress.period": "600s"})`), `test_unsuppress_clears`.
- [ ] Implement:
  - `list`: rows per firing: `{"rule": group.name, "triggered": c.get("trigger_time_rendered",""), "severity": c.get("severity",""), "sid": c.get("sid",""), "mode": c.get("digest_mode","")}`; `empty="No fired alerts."`.
  - `get NAME`: find group by name via iteration (`for g in fired_alerts: if g.name == name`), render one row per firing plus a summary row count; exit 1 when absent.
  - `suppress NAME --duration N`: guard preview "Throttle rule '<name>' for Ns (sets alert.suppress on the saved search)"; update the saved search; error if rule missing.
  - New `unsuppress NAME`: sets `alert.suppress: "0"`.
- [ ] Live check: create `zzfix_alert` rule (1-min cron, `index=_internal | head 1`, `--set alert_type='number of events' --set alert_comparator='greater than' --set alert_threshold=0 --set alert.track=1` — if Task D1 flags are not merged yet, use raw REST fallback documented in the test note), wait for a firing, `alerts list` shows sid+time, `alerts get zzfix_alert` no traceback, `alerts suppress zzfix_alert --duration 600 --yes`, verify `rules get` shows suppress fields, `alerts unsuppress --yes`, delete rule.
- [ ] Commit `fix: alerts list/get read firings correctly; suppress throttles the saved search`.

### Task 9: plan wrap-up

- [ ] Full suite: `ruff check . && ruff format --check . && mypy splunkctl/ && python -m pytest -q && ./scripts/check-lengths.sh`.
- [ ] Verify zero `zzfix_*` objects remain live (`lookups list`, `rules list`, `indexes list`, `apps list`).
- [ ] `git log --oneline` shows one commit per task above.
