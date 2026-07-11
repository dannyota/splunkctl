# SOAR actions

Run, monitor, and inspect action runs on Splunk SOAR assets.

## Commands

```bash
splunkctl soar actions list                         # list all action runs
splunkctl soar actions list --container 42           # scoped to a container
splunkctl soar actions status 999                    # poll one action run
splunkctl soar actions results 999                   # per-asset app_runs detail
splunkctl soar actions cancel 999 --yes              # cancel a running action

splunkctl soar actions run \
    --action "lookup domain" \
    --asset google_dns \
    --container 42 \
    --param domain=example.com \
    --wait --yes                                     # run and wait for result
```

## Running actions

`run` is a guarded mutation (dry-run by default). It builds the
`/rest/action_run` payload, resolves each asset's `app_id` from the
asset record (or accepts `--app` to skip the lookup), and POSTs it.

```bash
# Dry-run preview — shows the exact JSON payload
splunkctl soar actions run \
    --action "lookup domain" \
    --asset google_dns \
    --container 42 \
    --param domain=example.com

# Apply
splunkctl soar actions run \
    --action "lookup domain" \
    --asset google_dns \
    --container 42 \
    --param domain=example.com --yes
```

### Multiple assets and parameters

Repeat `--asset` and `--param` as needed. Assets sharing an `app_id`
are grouped into a single target entry.

```bash
splunkctl soar actions run \
    --action "lookup domain" \
    --asset google_dns --asset custom_dns \
    --container 42 \
    --param domain=example.com --param type=A --yes
```

### Explicit app id

Skip the asset lookup when you already know the app id:

```bash
splunkctl soar actions run \
    --action "lookup domain" \
    --asset google_dns --app 55 \
    --container 42 \
    --param domain=example.com --yes
```

### Wait for completion

`--wait` polls `GET /rest/action_run/<id>` until the status reaches
`success` or `failed`, then fetches per-asset results (`app_runs`).
Default timeout is 300 seconds; override with `--timeout`.

```bash
splunkctl soar actions run \
    --action "lookup domain" \
    --asset google_dns \
    --container 42 \
    --param domain=example.com \
    --wait --timeout 120 --yes
```

On success (exit 0) the app_runs detail is rendered. On failure or
timeout, exit 1 with diagnostics.

## Inspecting results

```bash
# Status of a specific action run
splunkctl soar actions status 999

# Per-asset detail (app_runs) — contains result_data with outputs
splunkctl soar actions results 999

# Pipe to jq for scripted extraction
splunkctl soar actions results 999 --json \
    | jq '.[].result_data[].data'
```

## Cancelling

Cancel is a guarded mutation:

```bash
splunkctl soar actions cancel 999        # dry-run
splunkctl soar actions cancel 999 --yes  # apply
```

## Options

| Flag | Applies to | Description |
|---|---|---|
| `--action` | `run` | Action name (e.g. "lookup domain") |
| `--asset` | `run` | Asset name (repeatable) |
| `--app` | `run` | Explicit app id (skips asset lookup) |
| `--container` | `run`, `list` | Container id |
| `--param` | `run` | Action parameter key=value (repeatable) |
| `--type` | `run` | Action type (default: investigate) |
| `--name` | `run` | Run name (defaults to action name) |
| `--wait` | `run` | Poll until completion |
| `--timeout` | `run` | Wait timeout in seconds (default: 300) |
| `--limit` | `list` | Max results |
| `--offset` | `list` | Paging offset |
| `--yes` | `run`, `cancel` | Apply mutation (skip dry-run) |

## Budget note

The community license allows 100 action runs per day. Budget live
tests accordingly.
