# Data models (CIM/tstats acceleration)

Mature SOC detections run on accelerated CIM data models via `| tstats`
— this group answers "which models exist," "is acceleration healthy,"
and "trigger a rebuild when stale." No SDK entity for data models
(unlike dashboards/lookups/HEC tokens) — every command is a thin, typed
wrapper around the raw `datamodel/model` and `admin/summarization` REST
collections, same pattern as `kvstore`/`server`.

## Why two REST resources

`datamodel/model`'s `content["acceleration"]` field is only the
**configuration** — `enabled`, `earliest_time` (the summarization
window), `cron_schedule`. It does **not** carry build progress. Percent
complete, the actual summarized earliest/latest range, size, and the
last build error live on a separate `admin/summarization` entity, one
per accelerated model, named `tstats:DM_<app>_<model>`.

This shape was confirmed against this project's own Splunk 10.4 install,
not guessed from REST trial and error alone: the installed
`splunk.models.summarization.Summarization` REST model class
(`$SPLUNK_HOME/lib/python3.13/site-packages/splunk/models/summarization.py`)
declares every `summary.*` field this group reads, and the bundled Data
Model Manager JS (`data_model_manager.js`) builds the exact
`tstats:DM_<app>_<model>` id when it fetches a model's acceleration
info in the Splunk Web UI. Both ship with splunkd itself, so they
describe exactly what this REST API version does — the same UI page an
admin would open to check acceleration health.

## Commands

```bash
splunkctl datamodels list                              # name, app, accelerated, disabled
splunkctl datamodels list --app Splunk_SA_CIM
splunkctl datamodels list --filter auth

splunkctl datamodels get Authentication                 # detection-engineering summary
splunkctl datamodels get Authentication --definition    # raw objects/fields/calculations JSON
splunkctl datamodels get Authentication --app Splunk_SA_CIM

splunkctl datamodels acceleration                       # every accelerated model's build status
splunkctl datamodels acceleration Authentication         # one model (accelerated or not)

splunkctl datamodels rebuild Authentication --yes        # re-summarize from scratch (guarded)
```

## `list`: cheap collection fields only

Columns: `name`, `app`, `accelerated` (bool), `disabled` (bool) — all
read straight off the collection listing, no per-model follow-up call.
`--app` (default: all apps), plus the uniform `--limit`/`--offset`/
`--filter` paging (F2): `--filter` forces a full fetch with client-side
case-insensitive name matching; without it, `--limit`/`--offset` pass
straight through to the REST call as `count`/`offset`.

## `get`: detection-engineering summary, not the full blob

A data model's raw definition (`content["description"]`) is a
JSON-encoded string that can run past 250KB for a CIM model with dozens
of objects — `get` parses it once and surfaces only what a detection
engineer actually needs:

- `name`, `app`, `displayName`, `disabled`
- `acceleration_enabled`, `acceleration_earliest_time`,
  `acceleration_cron_schedule` — the acceleration *config* (not status;
  use `acceleration` for that)
- `object_count`, `objects` (comma-joined object names)
- `root_search` — the base object's first constraint search, i.e. what
  raw index/sourcetype/tag the whole model actually covers

Pass `--definition` to get the raw, pretty-printed objects/fields/
calculations JSON instead — same shape as `dashboards get --definition`,
just for a data model's object hierarchy instead of a Studio dashboard's
visualization JSON.

## `acceleration`: the money command

`datamodels acceleration` (no argument) lists every model whose
acceleration config is enabled, with its build status:

- `enabled` — acceleration config state (should always be `true` here)
- `has_summary` — whether `admin/summarization` has an entity yet (a
  freshly-enabled model with a cron that hasn't fired yet is
  `enabled: true, has_summary: false` — accelerated, but nothing built)
- `is_complete` / `percent_complete` — from `summary.complete` (a 0–1
  fraction server-side; rendered here as a 0–100 percentage, rounded to
  1 decimal place: `round(float(complete) * 100, 1)`)
- `size`, `earliest_summarized`, `latest_summarized` — raw
  `summary.size`/`summary.earliest_time`/`summary.latest_time`,
  unmodified (epoch seconds, not reformatted)
- `last_error` — `summary.last_error` (a list server-side, one entry
  per distributed peer) joined with `; `; empty string when clean

If nothing is accelerated, this cleanly renders an empty result — never
an error — and skips the `admin/summarization` fetch entirely (no
accelerated models means nothing to look up).

`datamodels acceleration <name>` shows one model regardless of whether
it's accelerated: `enabled: false` (with every other field blank/`null`)
is a valid, non-error answer to "is this model accelerated at all" — an
agent auditing acceleration coverage across many models shouldn't have
to special-case the read path for the ones that aren't accelerated yet.
Only a model that doesn't exist at all is an error (`kind: "not_found"`).

## `rebuild`: guarded, disable-then-re-enable

There is no dedicated "rebuild" REST verb for data model acceleration.
Splunk Web's own "Rebuild" button (confirmed from the installed Data
Model Manager JS) works by POSTing `datamodel/model/<name>` twice:
first `acceleration=0` (disable), then `acceleration=1` with the same
`acceleration.earliest_time` re-sent explicitly (re-enable) — this drops
the existing tsidx summary and re-summarizes historical data for the
same window from scratch. `datamodels rebuild <name>` does exactly this,
behind the standard dry-run guard:

```bash
splunkctl datamodels rebuild Authentication            # [DRY RUN] preview, no changes
splunkctl datamodels rebuild Authentication --yes       # applies: disable, then re-enable
```

The dry-run preview names the model, its app, the preserved
`earliest_time` window, and states plainly that this re-summarizes
historical data from scratch — there is no partial/incremental rebuild.

**Only meaningful for an already-accelerated model.** If the named
model's acceleration config is disabled, `rebuild` exits 1 with a clear
message *before* the dry-run/`--yes` guard even runs — passing `--yes`
against a non-accelerated model does not print a preview and does not
touch anything, it just fails the same way the bare dry-run would.

**Known caveat (inherent to the underlying REST API, not this CLI):**
because a rebuild is two separate POSTs, a failure between them (e.g. a
permission or connectivity error on the second call) can leave the
model disabled without the summary having restarted. This is exactly
the same risk Splunk Web's own Rebuild button carries — there is no
atomic rebuild operation to fall back to. A rebuild failure surfaces
through the normal F1 classified envelope; re-running `datamodels get
<name>` afterward shows whether acceleration ended up enabled again.

## Errors

REST failures are never caught locally — they flow straight through the
CLI's F1 error-envelope classification (`splunkctl.errors.classify`), so
a down or misconfigured instance always surfaces a clean `kind`/
`http_status`/`message`, never blank output or a raw traceback:

```bash
$ splunkctl --json datamodels list
{"error": {"kind": "http", "http_status": 503, "message": "..."}}
```

## Live-verified status

`list`/`get`/`acceleration` (read paths) and `rebuild`'s dry-run preview
and not-accelerated rejection are live-verified against the local dev
instance. The instance ships Splunk Security Essentials (sample content
and CIM-aware detections) but not the `Splunk_SA_CIM` add-on itself, so
no data model on it is actually accelerated — `acceleration`'s populated
build-status row (non-zero percent complete, a real summarized range)
and `rebuild --yes`'s two-POST apply path are unit-tested against the
REST shape above (verified via the installed Splunk source, not
guessed) rather than live-verified end-to-end; live verification of a
populated, real acceleration build is pending an instance with an
actually-accelerated CIM model.
