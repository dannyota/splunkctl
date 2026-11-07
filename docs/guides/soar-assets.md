<!-- summary: Create, update, test, and delete Splunk SOAR assets, then confirm that polling-based ingestion assets are healthy with ingest-status. -->

# Configure assets and monitor ingestion

When to use: you are wiring a SOAR app to a real service (a DNS resolver, a threat-intel feed, a SIEM poller) and need to create or change its asset, prove it can connect, and confirm ingestion keeps running.

## Prerequisites

- SOAR credentials in the active profile (`splunkctl config init --soar`) and a passing `splunkctl soar test`.
- The app id and its configuration keys, from `splunkctl soar apps get <APP_ID>` (see [Install SOAR apps](soar-apps.md)).
- `delete` requires username and password credentials; SOAR refuses automation tokens on DELETE.

## Synopsis

```text
splunkctl soar assets list [--limit N]
splunkctl soar assets get <ASSET_ID>
splunkctl soar assets create --name <NAME> --app-id <APP_ID> [--set KEY=VALUE]... [--file CONFIG.json] [--description TEXT] [--yes]
splunkctl soar assets update <ASSET_ID> [--set KEY=VALUE]... [--file CONFIG.json] [--name TEXT] [--description TEXT] [--replace] [--yes]
splunkctl soar assets test <ASSET_ID> [--timeout SECONDS] [--yes]
splunkctl soar assets delete <ASSET_ID> [--yes]
splunkctl soar ingest-status
```

## Workflow

### Inspect existing assets

```bash
splunkctl soar assets list
splunkctl soar assets get 1 --json
```

Expected result: one row per asset with id, name, app, and whether it is configured for ingestion.

### Create an asset

> **Safety:** Target is the SOAR host in the active profile. Impact: a new asset is created and, if the app polls, may start ingesting containers. Preview with `splunkctl soar assets create --name my_dns --app-id 5 --set dns_server=8.8.8.8`, apply by adding `--yes`, and verify with `splunkctl soar assets get <ASSET_ID>`.

```bash
splunkctl soar assets create --name my_dns --app-id 5 \
  --set dns_server=8.8.8.8 --description "Google DNS"
splunkctl soar assets create --name my_dns --app-id 5 \
  --set dns_server=8.8.8.8 --description "Google DNS" --yes
splunkctl soar assets create --name enrichment --app-id 10 --file config.json --yes
```

Configuration comes from `--set key=value` (repeatable) and/or `--file` (a JSON object). When both are given, `--set` wins. Values whose schema type is `password` are shown as `****` in the preview; the real value is sent on `--yes`.

### Update an asset

> **Safety:** Target is the SOAR host in the active profile. Impact: the asset's configuration changes; with `--replace`, every key you do not pass is removed. Preview with `splunkctl soar assets update 1 --set dns_server=1.1.1.1`, apply by adding `--yes`, and verify with `splunkctl soar assets get 1`.

```bash
splunkctl soar assets update 1 --set dns_server=1.1.1.1
splunkctl soar assets update 1 --set dns_server=1.1.1.1 --yes
splunkctl soar assets update 1 --name renamed --description "new" --yes
splunkctl soar assets update 1 --replace --set only_key=value --yes
```

The SOAR API treats asset POST as a full replace. By default the CLI fetches the current asset, merges your keys into its configuration, and posts the result, so an update cannot wipe keys by accident. `--replace` skips the merge and sends only what you pass.

### Test connectivity

> **Safety:** Target is the SOAR host in the active profile. Impact: SOAR runs the app's test-connectivity action against the asset's configured service. Preview with `splunkctl soar assets test 1`, apply with `splunkctl soar assets test 1 --yes`, and verify the result in the command output or on the asset page in the SOAR UI.

```bash
splunkctl soar assets test 1 --yes
splunkctl soar assets test 1 --timeout 60 --yes
```

The command posts to `/rest/asset/<id>/test` and polls `/rest/app_status` for up to `--timeout` seconds (default 30). Expected result: `success` or `failed`. The test runs in the SOAR backend with no visible action run; if polling times out, it may still finish server side, so check the asset page in the SOAR UI.

### Delete an asset

> **Safety:** Target is the SOAR host in the active profile. Impact: the asset is removed and any ingestion or playbook action that used it stops. Preview with `splunkctl soar assets delete 1`, apply with `splunkctl soar assets delete 1 --yes`, and verify with `splunkctl soar assets list`.

```bash
splunkctl soar assets delete 1
splunkctl soar assets delete 1 --yes
```

### Monitor ingestion

```bash
splunkctl soar ingest-status
splunkctl soar ingest-status --json
```

Each row is a poller record from `/rest/ingestion_status` (asset, app, status, message, container label) enriched with `app_status` and `app_message` from `/rest/app_status`. Expected result: every ingestion asset you rely on shows an active status with no error message.

## Troubleshooting

- `kind: auth` on delete: add username and password to the SOAR profile with `splunkctl config init --soar`.
- Test reports a timeout: raise `--timeout`, then check the asset page in the SOAR UI for the final result.
- Keys you set are rejected: compare them with `splunkctl soar apps get <APP_ID>`; names and types must match the app schema.
- A poller shows an error in `ingest-status`: fix the asset configuration with `soar assets update`, rerun `soar assets test`, then check `ingest-status` again.

## See also

- [Install SOAR apps](soar-apps.md)
- [Run actions](soar-actions.md)
- [Ingest SIEM results into SOAR](soar-ingest.md)
- [Command reference: soar](../commands/soar.md)
