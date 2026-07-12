# Splunk SOAR REST API — discovery reference

Working reference for building `splunkctl soar`. Compiled 2026-07-11 from a
live probe of Splunk SOAR (On-premises) **8.5.0.248** (unprivileged, el9),
a live **write-path verification** (every mutation below marked "verified"
was executed and cleaned up on the lab), and official docs. Companion doc:
[soar-ingest-map.md](soar-ingest-map.md) (SIEM→SOAR field-mapping
conventions).

**Legend**: unmarked = live-verified on 8.5.0.248 (reads and writes);
*(docs)* = documented, not exercised here; *(unverified)* = confirm at
build time.

## Platform shape

- Django-backed REST API rooted at `https://<host>:8443/rest/`, served by
  nginx over TLS. Cloud and on-prem share nearly the same API.
- Backend: PostgreSQL 15, RabbitMQ, supervisord-managed workers (no
  systemd units). Install path `/opt/phantom`, OS user `soar`.
  Health-monitored daemons: `decided`, `ingestd`, `nginx`, `postgres`,
  `uwsgi`, `workflowd`.
- Community license: 100 actions/day cap — budget live `action_run` tests.
- No REST resource auto-discovery (`GET /rest/` → `{"failed": true}`); the
  bundled OpenAPI spec covers only ~30 newer paths.

## Auth model

1. **HTTP Basic** — username/password. Works on all `/rest/*`.
2. **Automation token** — header `ph-auth-token: <token>`; belongs to an
   automation-type user; per-user allowed-IP restriction.

Hard-won facts:

- **DELETE requires Basic auth — automation tokens are refused** (except
  `decided_list`) *(docs; shapes CLI client design)*.
- **Token plaintext cannot be obtained via REST.** `POST /rest/ph_user`
  (create automation user) auto-generates the token but never returns it;
  `GET /rest/ph_user/<id>/token` returns `{"key": <hash>, "expires_on"}`
  where `key` is the **hashed** form; `POST .../token` returns success but
  regenerates nothing. Tokens are shown once in the UI at creation. A CLI
  must accept a UI-pasted token or use Basic.
- `DELETE /rest/ph_user/<id>` is a **soft delete** (`is_active=False`);
  the dead user's token then errors "User is inactive".
- The system `automation` user is hidden from the `/rest/ph_user` list;
  reach it via id or `_filter_type="automation"`.

## Query semantics

```
GET /rest/<type>?page=0&page_size=10&sort=<field>&order=asc|desc
    &_filter_<field>__<op>=<value>&_exclude_<field>=<value>
    &pretty&include_expensive
```

- **Pagination**: `page` (0-based) + `page_size`; envelope
  `{"count", "num_pages", "data"}`. Exceptions: `/rest/audit` returns a
  **bare array** (accepts `format=csv`, `start`/`end` time params
  *(docs)*); `/rest/search` returns `{"results", "count", ...}`.
- **Filters** (Django-style, ANDed; no OR): quoted strings
  (`_filter_name="DNS"`); ops `contains/icontains/iexact/startswith/
  endswith/gt/gte/lt/lte/in/range/regex/iregex/isnull` + timestamp parts;
  booleans **Python-style** `True`/`False` (lowercase silently fails);
  related traversal `_filter_container__name__icontains="x"`; nested JSON
  `_filter_custom_fields__k__regex="..."`; `_exclude_<field>=` inverts.
- **Bulk update**: POST an **array** to a collection endpoint
  (`POST /rest/container [{"id": 1, ...}, {"id": 2, ...}]`) *(docs)*.
- **Status ids vs names**: `/rest/container_status` lists numeric ids, but
  container updates take the string **name** — `{"status": "closed"}`
  works, `{"status": 2}` fails (`'int' object has no attribute 'lower'`).
- Pseudo-fields per container: `/artifacts`, `/actions`, `/notes`,
  `/comments`, `/attachments`, `/audit`, `/activity_feed`,
  `/playbook_runs`, `/phases`, `/approvals`, `/permitted_users`.

## Verified write recipes

### Containers

- Create `POST /rest/container` `{name*, label*, severity, sensitivity,
  source_data_identifier, description, run_automation:false}` →
  `{"success": true, "id": N, "new_artifact_ids": []}`. Duplicate SDI →
  400 `{"failed": true, "existing_container_id": N}`.
- Update `POST /rest/container/<id>` — status by **name**, `owner_id`
  / `role_id` (numeric ONLY: `owner_name` and role-by-name return
  success but silently change nothing — verify by read-back), owner
  and role are mutually exclusive per request AND per container
  (writing one clears the other; "Container cannot be assigned both
  an owner and a role"), `sensitivity`, `tags[]` (read-modify-write),
  `custom_fields{}`.
- Promote + workbook in one call:
  `{"container_type": "case", "template": <workbook_template_id>}` —
  atomic; phases/tasks instantiate immediately.
- DELETE cascades to artifacts/vault/comments/notes/phases/tasks
  (Basic auth).

### Artifacts

- Create `POST /rest/artifact` `{container_id*, name, cef{}, cef_types{},
  severity, source_data_identifier, type, label, run_automation}` →
  `{"success": true, "id": N}`.
- **No server-side dedup**: duplicate SDI in the same container creates a
  second artifact (contrary to older docs) — the CLI must precheck
  (`_filter_source_data_identifier=...&_filter_container=N`).
- Update replaces `cef{}` **wholesale** (no merge) — fetch-merge-post for
  partial edits.

### Notes, comments

- `POST /rest/note` `{container_id*, content*, title, note_type:
  "general", task_id, artifact}` — `note_format` is markdown; DELETE
  works.
- `POST /rest/container_comment` `{container_id*, comment*}`; **DELETE
  405** — comments are immutable, removed only with the container.

### Vault

- Upload `POST /rest/container_attachment` `{container_id*, file_name*,
  file_content* (base64, ~32 MB nginx cap), metadata{contains[],
  description}}` → note the response key is **`succeeded`** (not
  `success`) + `vault_id`/`hash` (SHA1), `id`, `size`.
- Download: `GET /rest/download_attachment?vault_id=<sha1>` → raw bytes.
  (The only working path; `vault_document/<hash>` variants 500/404.)
- Delete via `DELETE /rest/container_attachment/<id>`;
  `DELETE /rest/vault_document/<id>` is 405.

### Custom lists (decided_list)

- Create `POST /rest/decided_list` `{name*, content: [[col,...],...]}`
  (array-of-rows; **JSON only** — text/csv rejected). Update = full
  `content` replacement. DELETE works (token auth allowed here).
- CSV export: `GET /rest/decided_list/<id>/formatted_content?
  _output_format=csv` *(docs)*.

### Assets & apps

- Create `POST /rest/asset` `{name*, app_id*, configuration{},
  description}`; GET exposes `app` (name) but POST takes `app_id`
  (integer) — verified. Config keys/schema from `GET /rest/app/<id>`
  `.configuration` (data_type/required/default per key).
- **Asset POST is full-replace** *(docs)* — update must fetch-merge-post.
- Test connectivity: `POST /rest/asset/<id>/test` → 200 immediately, runs
  async, no visible action_run; results surface in `GET /rest/app_status`
  / UI.
- Per-app actions: `GET /rest/app/<id>/actions`. App install
  `POST /rest/app` (tgz) *(docs)*; uninstall DELETE *(docs)*.
- Ingestion monitoring: `GET /rest/ingestion_status` (per-poll records:
  asset, app, status, message, container_label) + `GET /rest/app_status`.

### Actions

- `POST /rest/action_run` `{action*: "lookup domain", container_id*,
  name*, targets*: [{app_id: <int>, assets: ["<asset NAME>"],
  parameters: [{...}]}], type: "investigate"}` → `{"success": true,
  "action_run_id": N}` (POST returns `action_run_id`; polls use `id`).
- Poll `GET /rest/action_run/<id>` (`status`: pending/running/success/
  failed); per-asset detail `GET /rest/action_run/<id>/app_runs`; cancel
  `POST {"cancel": true}` *(docs)*.

### Playbooks & runs

- `POST /rest/playbook_run` `{container_id*, playbook_id*, scope:
  "all"|"new", run: true, inputs?}` → `{"playbook_run_id": "<str>"}` —
  note the id is a **string** (client normalizes to int); bogus
  playbook_id → 404 `Playbook "N" not found` (validates first). Poll
  `GET /rest/playbook_run/<id>`; block detail `.../block_results`;
  cancel POST `{"cancel": true}`. All verified live.
- Metadata mutations `POST /rest/playbook/<id>` `{active, cancel_runs,
  playbook_trigger}` *(docs)*. Triggers: default = label match on ingest
  (`labels: ["*"]` = all), `"artifact_created"`, `"container_resolved"`.
  `draft_mode: true` playbooks cannot be activated. No REST test_mode.
- Export `GET /rest/playbook/<id>/export` → tgz *(docs; route confirmed)*.
  Import `POST /rest/import_playbook` `{playbook: <base64 tgz>, scm:
  "local", force: true}` (endpoint confirmed — 405 on GET). Same for
  `POST /rest/import_custom_function`.
- SCM: `GET /rest/scm` (lab: one `local` repo,
  `file:////opt/phantom/scm/git/local`, working tree, zero commits).
  `POST /rest/scm/<id>` `{"pull": true, "force": true}` syncs an external
  git repo *(docs)*; **on the lab's local repo, sync returns 500
  "Operation not supported"**. Repos are immutable after creation; HTTPS
  passwords stored cleartext in git config; repo needs ≥1 commit *(docs)*.

### Playbook anatomy (as-code)

A playbook = paired `<name>.json` (metadata + `coa` visual graph: nodes/
edges/input_spec/output_spec, `playbook_type` "automation"|"data",
`labels[]`, `python_version` "3.13") + `<name>.py` (generated
`@phantom.playbook_block()` functions; hand-edits live between
`## Custom Code Start/End` markers). Export bundle = tgz of that folder.
Custom functions are the same pair shape under `custom_functions/`;
`POST /rest/custom_function` accepts inline `python` + `commit_message`
(requires `scm_id`) *(docs; schema on box)*. Classic single-.py playbooks
are legacy (editor removed 6.4). Reference corpus:
github.com/phantomcyber/playbooks.

### Cases & workbooks

- Live phases/tasks: `GET /rest/container/<id>/phases` (nested tasks) or
  `workbook_phase`/`workbook_task` with `_filter_container=N`.
- Manual create: `POST /rest/workbook_phase` `{container_id*, name*,
  order}`; `POST /rest/workbook_task` `{phase_id*, name, description,
  order}` (field is `phase_id`, not `phase`).
- Task status is an **integer**: 0=incomplete, 2=complete; 0→2 allowed;
  status 1 (in progress) transitions demand a closing note ("Closing note
  content is required"); invalid transitions are rejected with an explicit
  message.
- Approvals: `GET /rest/approval` (+ per-container), detail
  `.../detail_summary_view`; respond via `POST /rest/external_prompt/<id>`
  `{status: "approve"|"deny", ...}` *(docs)*.

## Read-side inventory (beyond the above)

| Endpoint | Notes |
|---|---|
| `/rest/version`, `/rest/system_info`, `/rest/license`, `/rest/health` | Platform basics; health = per-daemon time-series |
| `/rest/system_settings` | 37 sections (auth, SLAs/response, debug log levels, password policy, concurrency) — read-only surface for a CLI |
| `/rest/feature_flag` | 10 flags on lab (not 70 — verified); toggle POST *(docs)* |
| `/rest/widget_data/<name>` | 17 SOC-metric widgets (container_stats, containers_workload, sla_stats, pending_approvals, top_playbooks_actions, roi_summary, ...) |
| `/rest/indicator`, `indicator_by_value`, `indicator_common_container`, `indicator_artifact`, `indicator_stats_*` | IOC pivots (needs indicators flag) |
| `/rest/evidence` | GET/POST/DELETE *(writes docs)* |
| `/rest/container_options`, `/rest/container_status`, `/rest/severity`, `/rest/cef`, `/rest/cef_metadata`, `/rest/custom_field`, `/rest/app_categories` | Vocabularies; labels have **no CRUD endpoint** (list via container_options; creation is UI-only) |
| `/rest/workbook_template` (+phase/task templates) | 10 preloaded, NIST 800-61 default; CRUD *(docs)* |
| `/rest/ph_user`, `/rest/role` | User/role CRUD *(writes docs)*; 7 immutable roles |
| `/rest/audit` | Bare array; `format=csv`, `start`/`end` *(docs)*; per-object audit routes |
| `/rest/warm_standby` | Standby status (`off` on lab) |
| `/rest/tenant`, `/rest/cluster_node`, `/rest/automation_proxy` | Single-tenant/unclustered/empty on lab |
| `/rest/search?query=&categories=` | Cross-object; `{results}` envelope |
| `/rest/notification` | Exists, empty, shape unknown |

**No REST**: case/exec PDF reports, container merge (playbook API only),
backup/restore (`phenv ibackup`), support bundle, certificates/proxy,
retention (`phenv configure_db_maintenance`), scheduled playbooks (no
cron — polling assets are the scheduler), label creation.

**Dead ends**: `/rest/case`, `/rest/status`, `/rest/label(s)`,
`/rest/tag`, `/rest/event`, `/rest/token`, `/rest/dashboard`,
`/rest/scheduled_playbook`, `/rest/saved_search`, `/rest/report` → 404;
`/rest/broker` → cloud-only (PsaasImpersonationToken).

## Response-shape quirks (client must normalize)

1. Success key is `success` everywhere except `container_attachment`
   (**`succeeded`**).
2. Errors can be HTTP 200/400 with `{"failed": true, "message"}` — treat
   `failed` as authoritative.
3. `action_run` POST returns `action_run_id`; everything else returns `id`.
4. `/rest/audit` bare array; `/rest/search` `{results}` envelope.
5. Artifact DELETE returns `id` as a **string**.

## Live-verified corrections (waves 30-34)

Corrections to the original discovery doc, all verified during the build:

- **Health/license response shapes** differ from the original doc
  sketches; actual shapes reflected in `SOARClient` normalization.
- **Feature flags**: lab ships **10** flags (not 70).
- **Asset record**: GET exposes `app` (name string); POST takes `app_id`
  (integer). Both verified.
- **`playbook_run` POST return**: `{"playbook_run_id": "<string>"}` —
  client normalizes the string to int.
- **Custom function export route**: `GET /rest/custom_function/<id>/export`
  returns `x-gzip` — **confirmed live**.
- **Task notes**: invisible on `container/<id>/notes` pseudo-field; must
  query `/rest/note` with `_filter_task_id` — verified.
- **Vault**: `container_attachment` lacks `vault_id` in the create
  response on older paths; vault lookup goes through `vault_document` +
  `_filter_hash`.
- **`/rest/search` pagination**: **1-based** (page=0 returns empty set;
  page=1 is the first page). `categories` is comma-separated only.
- **`/rest/audit` CSV**: `format=csv` returns raw CSV
  (`Content-Type: application/csv`).
- **`decided_list` create**: empty `content` → server 500; always provide
  at least `content: []`.
- **`external_prompt` respond**: shape remains docs-only (no live
  approval prompts exercised on the lab).
- **Container owner/role assign**: only numeric `owner_id`/`role_id`
  stick; `owner_name` returns success but writes nothing (the earlier
  "works live" note here trusted the 200 without a read-back). Owner
  and role are mutually exclusive — writing one clears the other.
- **Evidence create**: the discriminator field is `content_type`
  (values: `containerattachment`, `artifact`, `actionrun`,
  `container`, `note`) — NOT `object_type`; action runs drop the
  underscore.
- **Task status+note**: note-requiring transitions take the closing
  note INLINE in the `workbook_task` POST as `note` (singular); a
  separate `/rest/note` POST arrives too late. Allowed transitions:
  0→2, 2→1 only.
- **Playbook deletion**: no working REST route on 8.5 —
  `DELETE /rest/playbook/<id>` → 405; `POST` with `{"delete": true}`
  returns success without deleting. UI-only.
- **Playbook run cancel**: the server accepts `{"cancel": true}` on a
  finished run and does nothing — pre-check status client-side.
- **Playbook list `_filter_scm`**: id-typed; a repo *name* 400s —
  resolve via `/rest/scm` first.

## Prior art & versions

- No official SOAR ops CLI exists; `soarapps` (splunk-soar-sdk) is for
  connector-app dev only; community `soarsdk` wrapper stale (2023); no
  playbook-as-code tool exists anywhere — open field.
- 7.x → 8.4.0 was a version realignment with ES, not a breaking change;
  8.5.0 ≈ April 2026. REST stable since Phantom 4.x except
  `system_settings/features` → `feature_flag` (6.2.1) and `/rest/case`
  removal. Automations run Python 3.13 (7.0+); classic playbook editor
  removed (6.4.0).
