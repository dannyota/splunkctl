# SOAR Automation

Apps, assets, connectivity testing, and ingestion monitoring on Splunk
SOAR. Companion to [soar.md](soar.md) (platform reads, containers,
artifacts, vault, notes).

## Apps

### List

```bash
splunkctl soar apps list                            # all apps
splunkctl soar apps list --installed                # exclude staged (uninstalled)
splunkctl soar apps list --category Information     # by category
splunkctl soar apps list --limit 10                 # paginate
splunkctl soar apps list --json
```

`--installed` adds `_exclude_install_status="staged"` to show only
installed apps. `--category` filters by app category string.

### Get

```bash
splunkctl soar apps get 5                           # app config schema
splunkctl soar apps get 5 --actions                 # include supported actions
splunkctl soar apps get 5 --json
```

Returns the app object including `configuration` -- a per-key schema
with `data_type` (string/password/numeric/boolean), `required`, and
`default` values. Use this to understand what keys an asset for this app
expects.

`--actions` appends the list of supported actions (from
`/rest/app/<id>/actions`) into the output under an `actions` key.

## Assets

### List

```bash
splunkctl soar assets list                          # all assets
splunkctl soar assets list --limit 20               # paginate
splunkctl soar assets list --json
```

### Get

```bash
splunkctl soar assets get 1                         # by asset ID
splunkctl soar assets get 1 --json
```

### Create

```bash
splunkctl soar assets create --name "my_dns" --app-id 5 --yes
splunkctl soar assets create --name "my_dns" --app-id 5 \
  --set dns_server=8.8.8.8 --description "Google DNS" --yes
splunkctl soar assets create --name "enrichment" --app-id 10 \
  --file config.json --yes
```

Config keys come from `--set key=value` (repeatable) and/or `--file`
(JSON object). When both are given, `--set` values override `--file`.
Get the expected keys from `soar apps get <app_id>` (the `configuration`
schema).

Password-type config values (per the app schema) are masked as `****`
in dry-run previews. The real value is sent on `--yes`.

### Update

```bash
splunkctl soar assets update 1 --set dns_server=1.1.1.1 --yes
splunkctl soar assets update 1 --name "renamed" --description "new" --yes
splunkctl soar assets update 1 --file config.json --yes
splunkctl soar assets update 1 --replace --set only_key=value --yes
```

**Fetch-merge-post by default.** The SOAR API treats asset POST as a
full replace -- the CLI fetches the existing asset, merges new config
keys into the existing configuration, and posts the merged result. This
prevents accidental config wipe.

`--replace` skips the merge and sends only the provided configuration
(full replace). Use with care.

Password-type values are masked in dry-run previews.

### Delete

```bash
splunkctl --yes soar assets delete 1
```

Deletes an asset by ID. Requires Basic auth (SOAR refuses token auth on
DELETE). Guarded: dry-run by default.

### Test Connectivity

```bash
splunkctl --yes soar assets test 1
splunkctl --yes soar assets test 1 --timeout 60
```

Posts to `/rest/asset/<id>/test`, which triggers an async connectivity
test on the SOAR server. The CLI then polls `/rest/app_status` for the
result (up to `--timeout` seconds, default 30).

**Async caveat:** The test runs in the SOAR backend with no visible
action_run. If polling times out, the test may still complete
server-side -- check the SOAR UI (asset configuration page) for the
final result.

Reports `success`, `failed`, or timeout with a warning.

## Ingestion Status

```bash
splunkctl soar ingest-status                        # poller health
splunkctl soar ingest-status --json
```

Rolls up `/rest/ingestion_status` (per-poller records: asset, app,
status, message, container_label) with `/rest/app_status` (app health).
Each row carries the ingestion record enriched with `app_status` and
`app_message` from the app_status lookup.

Use this to verify that polling-based ingestion assets are active and
healthy.
