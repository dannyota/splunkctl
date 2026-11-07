<!-- summary: Inspect CIM data model definitions and acceleration health so tstats-based detections run on complete data. -->

# Check data model acceleration

When to use: your detections run on accelerated CIM data models through `| tstats` and you need to know which models exist, whether acceleration is healthy and complete, and how to trigger a rebuild when a summary is stale or broken.

## Prerequisites

- A profile that passes `splunkctl doctor` (see [Configure](configure.md)).
- Read access to data models for `list`, `get`, and `acceleration`; write access to the model's app (for example `Splunk_SA_CIM`) for `rebuild`.
- No SDK fork is needed: every command is a thin, typed wrapper around the `datamodel/model` and `admin/summarization` REST collections.

## Synopsis

```text
splunkctl datamodels list [--app APP] [--filter SUBSTRING] [--limit N] [--offset N]
splunkctl datamodels get <NAME> [--app APP] [--definition]
splunkctl datamodels acceleration [NAME]
splunkctl datamodels rebuild <NAME> [--app APP] [--yes]
```

## Workflow

### List the models

```bash
splunkctl datamodels list
splunkctl datamodels list --app Splunk_SA_CIM
splunkctl datamodels list --filter auth
```

Expected result: `name`, `app`, `accelerated` (bool), and `disabled` (bool), read straight off the collection listing with no per-model follow-up call. `--app` defaults to all apps. `--filter` forces a full fetch with client-side case-insensitive name matching; without it, `--limit` and `--offset` pass straight through to the REST call as `count` and `offset`.

### Inspect one model

```bash
splunkctl datamodels get Authentication
splunkctl datamodels get Authentication --app Splunk_SA_CIM
splunkctl datamodels get Authentication --definition
```

Expected result: a detection-engineering summary rather than the full blob. A model's raw definition is a JSON-encoded string that can run past 250 KB for a CIM model with dozens of objects; `get` parses it once and surfaces:

- `name`, `app`, `displayName`, `disabled`
- `acceleration_enabled`, `acceleration_earliest_time`, `acceleration_cron_schedule`: the acceleration configuration, not build status
- `object_count`, `objects` (comma-joined object names)
- `root_search`: the base object's first constraint search, which is the raw index, sourcetype, or tag the whole model covers

`--definition` prints the raw, pretty-printed objects, fields, and calculations JSON instead, the same shape as `dashboards get --definition` but for a model's object hierarchy.

### Check acceleration health

```bash
splunkctl datamodels acceleration
splunkctl datamodels acceleration Authentication
```

Expected result: without a name, one row per model whose acceleration configuration is enabled; with a name, that model whether or not it is accelerated. Each row carries:

- `enabled`: acceleration configuration state
- `has_summary`: whether `admin/summarization` has an entity yet; a freshly enabled model whose cron has not fired is `enabled: true, has_summary: false`, accelerated but nothing built
- `is_complete` and `percent_complete`: from `summary.complete`, a 0 to 1 fraction server side, rendered as a 0 to 100 percentage rounded to one decimal place
- `size`, `earliest_summarized`, `latest_summarized`: raw `summary.size`, `summary.earliest_time`, and `summary.latest_time`, unmodified (epoch seconds)
- `last_error`: `summary.last_error` (a list server side, one entry per distributed peer) joined with `; `; empty when clean

Two REST resources are involved because `datamodel/model`'s `acceleration` field holds only the configuration (`enabled`, `earliest_time`, `cron_schedule`) and never build progress. Percent complete, the summarized range, size, and the last build error live on a separate `admin/summarization` entity per accelerated model, named `tstats:DM_<app>_<model>`, the same source Splunk Web's Data Model Manager page reads. If nothing is accelerated, the command renders an empty result, never an error, and skips the `admin/summarization` fetch. `acceleration <name>` on a non-accelerated model returns `enabled: false` with the other fields blank or `null`; that is a valid answer to "is this model accelerated at all", so an agent auditing coverage does not need a special case. Only a model that does not exist is an error (`not_found`).

### Rebuild a stale summary

> **Safety:** Target is the Splunk host in the active profile and the named model's app. Impact: the existing tsidx summary is dropped and historical data is re-summarized from scratch for the same `earliest_time` window; `| tstats` searches run on incomplete data until the rebuild finishes. Preview with `splunkctl datamodels rebuild Authentication`, apply by adding `--yes`, and verify with `splunkctl datamodels acceleration Authentication` until `percent_complete` reaches 100.

```bash
splunkctl datamodels rebuild Authentication
splunkctl datamodels rebuild Authentication --yes
splunkctl datamodels acceleration Authentication
```

Expected result: the preview names the model, its app, the preserved `earliest_time` window, and states that this re-summarizes historical data from scratch; there is no partial or incremental rebuild. There is no dedicated rebuild REST verb, so `rebuild` does what Splunk Web's own Rebuild button does (confirmed against the installed Data Model Manager JS): it POSTs `datamodel/model/<name>` twice, first `acceleration=0` (disable), then `acceleration=1` with the same `acceleration.earliest_time` re-sent explicitly (re-enable).

`rebuild` is only meaningful for an already-accelerated model. If the model's acceleration configuration is disabled, it exits 1 with a clear message before the dry-run or `--yes` guard runs; `--yes` against a non-accelerated model prints no preview and touches nothing.

Because a rebuild is two separate POSTs, a failure between them (for example a permission or connectivity error on the second call) can leave the model disabled without the summary restarting. Splunk Web's Rebuild button carries the same risk; there is no atomic rebuild to fall back to. Run `splunkctl datamodels get <name>` afterwards to confirm `acceleration_enabled` is `true` again.

## Troubleshooting

- `http` with status 503 from `list`: the instance is down or starting; the error envelope carries `kind`, `http_status`, and `message`, never a traceback.
- `not_found` from `get`, `acceleration NAME`, or `rebuild`: the model name is case-sensitive and may live in another app; run `splunkctl datamodels list --filter <text>` and pass `--app`.
- `Data model 'NAME' is not accelerated`: `rebuild` exits 1 and does nothing; enable acceleration in Splunk Web first.
- `percent_complete` stays below 100 after a rebuild: the summarization cron has not caught up; check `last_error` for a peer-level failure before rebuilding again.
- `acceleration_enabled` is `false` after a failed `rebuild --yes`: the second POST failed; fix the `permission` or `connection` error and run `rebuild --yes` again once acceleration is re-enabled in Splunk Web.
- `has_summary: false` with `enabled: true`: acceleration was just enabled; wait for the first cron run.

## See also

- [Manage detection rules](rules.md)
- [Run searches](search.md)
- [Manage macros, eventtypes, tags](knowledge.md)
- [Command reference: datamodels](../commands/datamodels.md)
