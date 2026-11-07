<!-- summary: Run app actions on Splunk SOAR assets, wait for results, and inspect past action runs. -->

# Run actions

When to use: you want to run one app action (for example `lookup domain` or `block ip`) on one or more SOAR assets inside a container, wait for the result, read the per-asset output of a past run, or cancel a run that is stuck.

## Prerequisites

- SOAR credentials in the active profile and a passing `splunkctl soar test` (see [Set up and check SOAR](soar.md)).
- A configured asset for the app whose action you want to run (`splunkctl soar assets list`, see [Configure assets and monitor ingestion](soar-assets.md)).
- A container id to attach the run to (`splunkctl soar containers list`).
- A community license caps action runs at 100 per day; check `splunkctl soar license` (`max_allowed_actions_per_day`) before a bulk run.

## Synopsis

```text
splunkctl soar actions list [--container CONTAINER_ID] [--limit N] [--offset N]
splunkctl soar actions status <ACTION_RUN_ID>
splunkctl soar actions results <ACTION_RUN_ID>
splunkctl soar actions run --action <NAME> --asset <ASSET>... --container <CONTAINER_ID> [--param KEY=VALUE]... [--app APP_ID] [--type TYPE] [--name TEXT] [--wait] [--timeout SECONDS] [--yes]
splunkctl soar actions cancel <ACTION_RUN_ID> [--yes]
```

## Workflow

### List past action runs

```bash
splunkctl soar actions list
splunkctl soar actions list --container 42
splunkctl soar actions list --limit 20 --offset 20
```

Expected result: one row per action run, newest first. `--offset` requires `--limit` and must be a multiple of it.

### Run an action

> **Safety:** Target is the SOAR host in the active profile. Impact: the app contacts the external system behind the asset (a DNS resolver, a firewall, an EDR) and the result lands on the container; a containment action changes that system. Preview with `splunkctl soar actions run --action "lookup domain" --asset google_dns --container 42 --param domain=example.com` and read the exact `/rest/action_run` JSON payload, apply by adding `--yes`, and verify with `splunkctl soar actions status <ACTION_RUN_ID>`.

```bash
splunkctl soar actions run \
    --action "lookup domain" \
    --asset google_dns \
    --container 42 \
    --param domain=example.com
splunkctl soar actions run \
    --action "lookup domain" \
    --asset google_dns \
    --container 42 \
    --param domain=example.com --yes
```

Expected result: the dry run prints the payload; with `--yes` the run is created and its id printed. The CLI resolves each asset's `app_id` from the asset record and groups assets that share an `app_id` into one target entry. `--type` defaults to `investigate`; `--name` defaults to the action name.

### Target several assets or pass several parameters

> **Safety:** Target is the SOAR host in the active profile. Impact: the action runs on every asset listed, so a containment action reaches several systems at once. Preview by dropping `--yes`, apply by adding it back, and verify with `splunkctl soar actions results <ACTION_RUN_ID>`.

```bash
splunkctl soar actions run \
    --action "lookup domain" \
    --asset google_dns --asset custom_dns \
    --container 42 \
    --param domain=example.com --param type=A --yes
```

Expected result: one action run with both assets. Repeat `--asset` and `--param` as needed.

### Skip the asset lookup with an explicit app id

> **Safety:** Target is the SOAR host in the active profile. Impact: the action runs under the app id you pass with no check that it matches the asset. Preview by dropping `--yes`, apply by adding it back, and verify with `splunkctl soar actions status <ACTION_RUN_ID>`.

```bash
splunkctl soar actions run \
    --action "lookup domain" \
    --asset google_dns --app 55 \
    --container 42 \
    --param domain=example.com --yes
```

Expected result: the same run without the `/rest/asset` lookup; use it when you already know the app id.

### Wait for completion

> **Safety:** Target is the SOAR host in the active profile. Impact: the same action run as above; `--wait` only changes when the command returns. Preview by dropping `--yes`, apply by adding it back, and verify from the rendered `app_runs` detail or `splunkctl soar actions results <ACTION_RUN_ID>`.

```bash
splunkctl soar actions run \
    --action "lookup domain" \
    --asset google_dns \
    --container 42 \
    --param domain=example.com \
    --wait --timeout 120 --yes
```

Expected result: `--wait` polls `GET /rest/action_run/<id>` until the status reaches `success`, `failed`, or `cancelled`, then fetches the per-asset results (`app_runs`). The default timeout is 300 seconds. On success the command exits 0 and renders the `app_runs` detail; on failure or timeout it exits 1 with diagnostics.

### Inspect a run

```bash
splunkctl soar actions status 999
splunkctl soar actions results 999
splunkctl soar actions results 999 --json | jq '.[].result_data[].data'
```

Expected result: `status` shows the run's state; `results` shows the `app_runs` detail, whose `result_data` holds the action output per asset, ready for `jq`.

### Cancel a run

> **Safety:** Target is the SOAR host in the active profile. Impact: the running action is stopped and its result never lands. Preview with `splunkctl soar actions cancel 999`, apply with `splunkctl soar actions cancel 999 --yes`, and verify with `splunkctl soar actions status 999` (expect `cancelled`).

```bash
splunkctl soar actions cancel 999
splunkctl soar actions cancel 999 --yes
```

## Troubleshooting

- `not_found` for an asset name on `run`: the name must match `splunkctl soar assets list` exactly, or pass `--app <APP_ID>` to skip the lookup.
- `not_found` on `status` or `results`: the action run id does not exist; find it with `splunkctl soar actions list --container <ID>`.
- Exit 1 after `--wait`: the run finished `failed` or the timeout elapsed; read `splunkctl soar actions results <ID>` for the app's message, or raise `--timeout`.
- `run` is rejected after many runs in one day: the community license limit of 100 action runs per day may be spent; check `splunkctl soar license`.
- `--offset` rejected on `list`: it must be a multiple of `--limit`.
- `auth` or `permission` on `run` while `list` works: the credential's role cannot run actions; check its roles with `splunkctl soar users get <USER_ID>`.

## See also

- [Set up and check SOAR](soar.md)
- [Configure assets and monitor ingestion](soar-assets.md)
- [Work SOAR incidents](soar-incidents.md)
- [Run playbooks](soar-playbooks.md)
- [Look up indicators and evidence](soar-indicators.md)
- [Command reference: soar](../commands/soar.md)
