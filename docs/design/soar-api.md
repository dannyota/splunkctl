# Splunk SOAR REST API — discovery reference

Working reference for building `splunkctl soar`. Compiled 2026-07-11 from a
live probe of Splunk SOAR (On-premises) **8.5.0.248** (unprivileged, el9)
plus the official REST API docs (help.splunk.com, SOAR on-prem 8.4/8.5 and
legacy Phantom 4.10 pages — content stable across versions).

**Verification legend**: facts below are live-verified against 8.5.0 unless
marked *(docs)* (documented, not yet exercised here) or *(unverified)*
(inferred from older docs/community usage — confirm at build time).

## Platform shape

- Django-backed REST API rooted at `https://<host>:8443/rest/`, served by
  nginx over TLS. Cloud and on-prem share nearly the same API.
- Backend: PostgreSQL 15, RabbitMQ, supervisord-managed workers (no systemd
  units). Install path `/opt/phantom`, OS user `soar`, `phenv` requires that
  user. Health-monitored daemons: `decided`, `ingestd`, `nginx`, `postgres`,
  `uwsgi`, `workflowd`.
- Community license: 100 actions/day cap — relevant when live-testing
  `action_run` against the lab.
- No REST resource auto-discovery: `GET /rest/` returns `{"failed": true}`.
  The bundled OpenAPI spec covers only ~30 newer paths, not the core API.

## Auth model

Two methods, both HTTPS-only. Unchanged from 6.x through 8.5.

1. **HTTP Basic** — username/password. Works on all `/rest/*`; required for
   some DELETEs *(docs)*.
2. **Automation token** — header `ph-auth-token: <token>`. Preferred for
   tooling. Tokens belong to automation-type users, support per-user
   allowed-IP restrictions, and can be regenerated (old token dies
   immediately). No `/rest/token` endpoint exists (404) — tokens are minted
   in the UI or via `POST /rest/ph_user/<id>` *(unverified)*.

Error text distinguishes causes: bad token → `"Invalid automation token"`;
no auth → `"No supported auth information provided in request"`.

User types seen live: `normal`, `automation`, `onprem_integration`. The
system `automation` user is **hidden** from the default `/rest/ph_user`
list; reachable via direct id GET or `_filter_type="automation"`.

## Query semantics

General form:

```
GET /rest/<type>?page=0&page_size=10&sort=<field>&order=asc|desc
    &_filter_<field>__<op>=<value>&_exclude_<field>=<value>
    &pretty&include_expensive
```

- **Pagination**: `page` (0-based) + `page_size`; response envelope is
  `{"count": N, "num_pages": M, "data": [...]}`. Exception: `/rest/audit`
  returns a **bare JSON array** — special-case it.
- **Sorting**: `sort=<field>&order=asc|desc`.
- **Filters** (Django-style, ANDed; **no OR**):
  - Exact string match needs **double quotes**: `_filter_name="DNS"`.
  - Operators after `__`: `contains`, `icontains`, `iexact`,
    `startswith`/`istartswith`, `endswith`/`iendswith`, `gt`, `gte`, `lt`,
    `lte`, `in` (URL-encoded JSON list), `range`, `regex`/`iregex`,
    `isnull`, plus timestamp parts (`day`, `month`, `year`, `hour`, ...).
  - Booleans must be **Python-style** `True`/`False` — lowercase silently
    fails (`{"failed": true}`). `__exact` on booleans also fails; use bare
    `_filter_disabled=False`.
  - Related-record traversal works: `_filter_container__name__icontains="x"`;
    nested JSON too: `_filter_custom_fields__snowid__regex="^SIR.*"`.
  - `_exclude_<field>=` inverts (e.g. `_exclude_install_status="staged"`
    yields only installed apps).
- **Extras**: `pretty` adds `_pretty_*` human-relative times;
  `include_expensive` adds expensive computed fields (e.g.
  `artifact_count`) *(docs — no visible effect on empty lab data)*.
- **Status filtering uses numeric ids**, not names — resolve via
  `/rest/container_status` first.
- Pseudo-fields as sub-resources: `/rest/container/<id>/artifacts`,
  `/actions`, `/notes`, `/audit`, `/approvals`, `/permitted_users`.

## Endpoint inventory

All verified live (HTTP 200) unless noted. "Count" is the lab instance.

### Core data

| Endpoint | Methods | Notes |
|---|---|---|
| `/rest/container` | GET, POST; id: GET, POST, DELETE | Events/cases. Key fields: `name`*, `label`*, `status`, `severity`, `sensitivity` (TLP), `source_data_identifier`, `owner_id`, `tags[]`, `custom_fields{}`, `data{}`, `container_type` ("default"/"case"), `artifacts[]` inline, `run_automation` (default **false**), `due_time`, `current_phase_id`, `in_case` |
| `/rest/artifact` | GET, POST; id: GET, POST, DELETE | `container_id`*, `cef{}` payload, `cef_types{}`, `data{}`, `severity`, `source_data_identifier`, `type`, `tags[]`, `kill_chain`, `run_automation` (default **true**) |
| `/rest/container_options` | GET | Valid statuses/severities/sensitivities/**labels**/tags — labels have no standalone list endpoint |
| `/rest/container_status` | GET, POST, DELETE *(docs)* | Custom statuses grouped by `status_type` new/open/resolved |
| `/rest/severity` | GET, POST, DELETE *(docs)* | high / medium (default) / low + custom |
| `/rest/cef` | GET | 150 standard CEF field definitions |
| `/rest/container_comment` | GET, POST *(docs)* | `container_id`, `comment` |
| `/rest/container_attachment` | POST *(docs)* | Vault upload: `container_id`, `file_name`, `file_content` (base64, ~32 MB nginx default cap), `metadata` |
| `/rest/container_pin` | GET, POST *(docs)* | HUD cards |
| `/rest/note` | GET, POST *(docs)* | Container/task notes |
| `/rest/vault_document` | GET; id: GET, DELETE *(docs)* | Hash, names, size, contains, sources |
| `/rest/evidence` | GET, POST, DELETE *(docs)* | Evidence linked to containers |
| `/rest/indicator` | GET | Auto-extracted IOCs from CEF (POST/DELETE unverified) |
| `/rest/decided_list` | GET, POST; id: GET, POST, DELETE *(docs)* | Custom lists (allow/blocklists); stored as JSON rows |

### Automation

| Endpoint | Methods | Notes |
|---|---|---|
| `/rest/playbook` | GET, POST *(docs)* | Metadata: id, name, scm, active, trigger |
| `/rest/playbook_run` | POST *(unverified fields)*; id: GET, POST | Trigger: `{container_id, playbook_id, scope: "all"\|"new", run: true}` → `playbook_run_id`. Poll id: `status` pending/running/success/failed, `message`, `inputs`, `outputs`. Cancel: POST `{"cancel": true}` |
| `/rest/action_run` | POST *(docs)*; id: GET, POST | Trigger: `{action, container_id, name, targets: [{app_id, assets[], parameters[{}]}], type}` → `action_run_id`. Poll/cancel like playbook_run |
| `/rest/action_run/<id>/app_runs` | GET *(docs)* | Per-asset results: `app_name`, `status`, `message`, timings |
| `/rest/app_run` | GET | Raw app-run records |
| `/rest/app` | GET, POST *(docs)* | 46 fields; `install_status` "staged" vs "installed" (lab: 196 bundled, 5 installed) |
| `/rest/asset` | GET, POST *(docs)* | Configured app instances; `configuration{}`, `action_whitelist`, `token` |
| `/rest/scm` | GET, POST *(docs)*; `<id>/sync` POST *(docs)* | Playbook git repos; lab has 1 local repo |
| `/rest/custom_function` | GET | Shared playbook code blocks |
| `/rest/playbook_resource_usage/<id>` | GET *(docs)* | Per-block run stats |

### Case management

| Endpoint | Methods | Notes |
|---|---|---|
| `/rest/workbook_template` | GET, POST *(docs)* | 10 preloaded; NIST 800-61 default |
| `/rest/workbook_phase_template` | GET, POST *(docs)* | Phases with nested task arrays |
| `/rest/workbook_task_template` | GET, POST *(docs)* | Flat task templates |
| `/rest/workbook_phase`, `/rest/workbook_task` | GET, POST *(docs)* | Live phases/tasks on containers |
| `/rest/approval` | GET *(docs)* | Approval workflow |

`/rest/case` is **gone** in 8.x (404) — a case is a container with
`container_type: "case"` (+ optional workbook/template).

### Admin & platform

| Endpoint | Methods | Notes |
|---|---|---|
| `/rest/version` | GET | `{"version": "8.5.0.248"}` |
| `/rest/system_info` | GET | `base_url`, `time_zone`, `machine_id` |
| `/rest/license` | GET | `license_info.maximum_actions_per_day`, `current_usage`, `status` |
| `/rest/health` | GET | Time-series samples per daemon (pid, rss, cpu) |
| `/rest/system_settings` | GET, POST *(docs)* | 37 top-level config keys |
| `/rest/feature_flag` | GET | 70 flags (replaced `system_settings/features` in 6.2.1) |
| `/rest/ph_user` | GET, POST *(docs)* | Automation user hidden from list (see Auth) |
| `/rest/role` | GET, POST *(docs)* | 7 built-in immutable roles; per-category view/edit/execute/delete perms |
| `/rest/user_settings` | GET | Settings of the **authenticated** user |
| `/rest/audit` | GET | **Bare array**, not the paginated envelope; per-object routes: `/rest/ph_user/<id>/audit`, `/rest/playbook/<id>/audit`, `/rest/container/<id>/audit` |
| `/rest/tenant` | GET | Single `_default_` tenant when multi-tenant off |
| `/rest/cluster_node` | GET | Empty when unclustered |
| `/rest/search` | GET | `?query=` required, `categories=` optional (container, artifact, asset, app, action, playbook, docs); 400 without query |

### Dead ends (verified)

`/rest/case`, `/rest/status`, `/rest/label(s)`, `/rest/tag`, `/rest/event`,
`/rest/token`, `/rest/dashboard`, `/rest/automation_broker` → 404.
`/rest/action`, `/rest/widget` → `{"failed": true}` (not collections).
`/rest/broker` → 400 `Missing PsaasImpersonationToken header` (cloud-only).

## Recipes

### Ingest (container + artifacts)

1. Dedup check: `GET /rest/container?_filter_source_data_identifier="X"`
   (`count: 0` → safe). Creating a duplicate returns
   `{"existing_container_id": N, "failed": true}` — same idea for artifacts
   (`existing_artifact_id`).
2. `POST /rest/container` with `run_automation: false`.
3. `POST /rest/artifact` for each, `run_automation: false` except the
   **last** one `true` (triggers playbooks once fully populated).
   Alternative: embed `artifacts[]` in the container POST — SOAR handles
   the last-artifact flag itself *(docs)*.

### Run & poll

- Playbook: `POST /rest/playbook_run` → poll `GET /rest/playbook_run/<id>`
  until `status` ∈ {success, failed}; `message` is JSON-encoded per-action
  detail. Cancel with POST `{"cancel": true}`.
- Action: `POST /rest/action_run` → poll `GET /rest/action_run/<id>`;
  per-asset detail at `/app_runs`. Cancel identically.

## Prior art

- **No official SOAR ops CLI exists.** `soarapps` (from the official
  `splunk-soar-sdk`, PyPI, ≥ SOAR 6.4) is for *developing connector apps*,
  not operations. Community `soarsdk` REST wrapper is stale (2023). The
  Splunk App for SOAR bridges from inside Splunk Enterprise only.

## Version notes (6.x → 8.5)

- 7.x → 8.4.0 was a **version realignment** with Enterprise Security, not a
  breaking API change; 8.5.0 ≈ April 2026 release. REST surface stable
  since Phantom 4.x except `system_settings/features` → `feature_flag`
  (6.2.1) and the `/rest/case` removal.
- Automations run on Python 3.13 (7.0+); classic playbook editor removed
  (6.4.0); automation isolation default-on for new deployments (7.0+).
