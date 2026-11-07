<!-- summary: Create, configure, and delete Splunk indexes with a preview before every change. -->

# Manage indexes

When to use: you are onboarding a new data source that needs its own retention or access boundary, resizing an index that is approaching its limit, checking retention against a compliance requirement, or decommissioning an index.

## Prerequisites

- A profile that passes `splunkctl doctor` (see [Configure](configure.md)).
- An account allowed to manage indexes (`indexes_edit`, which the `admin` role has).
- A retention plan: `--frozen-period` is in seconds (86400 = 1 day, 2592000 = 30 days, 31536000 = 365 days) and `--max-size` is in MB.

## Synopsis

```text
splunkctl indexes list [--filter SUBSTRING] [--limit N] [--offset N]
splunkctl indexes get <NAME>
splunkctl indexes create --name <NAME> [--datatype event|metric] [--max-size MB] [--frozen-period SECONDS] [--home-path PATH] [--cold-path PATH] [--yes]
splunkctl indexes update <NAME> [--max-size MB] [--frozen-period SECONDS] [--yes]
splunkctl indexes clean <NAME> [--clean-timeout SECONDS] [--yes]
splunkctl indexes delete <NAME> [--yes]
splunkctl indexes reload [--yes]
```

## Workflow

### List and check capacity

```bash
splunkctl indexes list
splunkctl indexes get main
splunkctl indexes list --json | jq '.[] | {name, totalEventCount, currentDBSizeMB, maxTotalDataSizeMB}'
```

Expected result: one row per index with size and event counts; `get` prints every setting. Field values arrive as strings, so convert before arithmetic in `jq`:

```bash
splunkctl indexes list --json \
  | jq '.[] | select((.currentDBSizeMB | tonumber) / (.maxTotalDataSizeMB | tonumber) > 0.8)
        | {name, pct_used: (100 * (.currentDBSizeMB | tonumber) / (.maxTotalDataSizeMB | tonumber))}'
splunkctl indexes list --json | jq '[.[] | select(.totalEventCount == "0")] | .[].name'
splunkctl indexes get security_logs --json | jq '{frozenTimePeriodInSecs, maxTotalDataSizeMB}'
```

The first query lists indexes over 80 percent full, the second indexes with zero events (possibly misconfigured inputs), and the third verifies retention settings against a compliance requirement.

### Create indexes for security workloads

> **Safety:** Target is the Splunk host in the active profile. Impact: a new index is created and starts accepting events from any input that names it. Preview with `splunkctl indexes create --name threat_intel --max-size 100 --frozen-period 7776000`, apply by adding `--yes`, and verify with `splunkctl indexes get threat_intel`.

```bash
splunkctl indexes create --name threat_intel --max-size 100 --frozen-period 7776000
splunkctl indexes create --name threat_intel --max-size 100 --frozen-period 7776000 --yes
splunkctl indexes create --name security_logs --max-size 5000 --frozen-period 31536000 --yes
splunkctl indexes create --name metrics_idx --datatype metric --max-size 500 --frozen-period 604800 --yes
```

Expected result: the index appears in `splunkctl indexes list`. The first example keeps threat intel for 90 days in a small index; the second keeps security logs for 365 days in a large one; the third creates a metrics index. Separate indexes let you apply different retention per data tier and control access through roles. `--home-path` and `--cold-path` set bucket locations on the server when the defaults do not fit.

### Change size or retention

> **Safety:** Target is the Splunk host in the active profile. Impact: lowering `--max-size` or `--frozen-period` makes Splunk freeze (and by default delete) buckets sooner. Preview with `splunkctl indexes update my_index --frozen-period 2592000`, apply by adding `--yes`, and verify with `splunkctl indexes get my_index --json | jq '{frozenTimePeriodInSecs, maxTotalDataSizeMB}'`.

```bash
splunkctl indexes update my_index --max-size 1000
splunkctl indexes update my_index --max-size 1000 --yes
splunkctl indexes update my_index --frozen-period 2592000 --yes
```

Expected result: the new values read back from `get`. `maxTotalDataSizeMB` is a high-water mark; Splunk freezes buckets when the index reaches it, so plan for headroom. At least one of `--max-size` or `--frozen-period` is required.

### Remove all events from an index

> **Safety:** Target is the Splunk host in the active profile. Impact: every event in the index is deleted; the index itself and its settings remain. Preview with `splunkctl indexes clean my_index`, apply by adding `--yes`, and verify with `splunkctl indexes get my_index --json | jq .totalEventCount`.

```bash
splunkctl indexes clean my_index
splunkctl indexes clean my_index --yes
splunkctl indexes clean big_index --clean-timeout 300 --yes
```

Expected result: `Index 'my_index' cleaned.`. The CLI waits up to `--clean-timeout` seconds (default 60) for the index to empty; a large index needs a longer wait.

### Delete an index

> **Safety:** Target is the Splunk host in the active profile. Impact: the index and its searchable data are removed from Splunk; inputs that still name it will drop events to the last-chance index or fail. Preview with `splunkctl indexes delete my_index`, apply by adding `--yes`, and verify with `splunkctl indexes list --filter my_index`.

```bash
splunkctl indexes delete my_index
splunkctl indexes delete my_index --yes
```

Expected result: the index no longer lists. Deleting an index does not free disk immediately; frozen buckets remain on the filesystem until removed on the Splunk server.

### Reload index configuration

> **Safety:** Target is the Splunk host in the active profile. Impact: splunkd re-reads every index configuration. Preview with `splunkctl indexes reload`, apply with `splunkctl indexes reload --yes`, and verify with `splunkctl indexes list`.

```bash
splunkctl indexes reload --yes
```

## Troubleshooting

- `not_found` from `get`, `update`, `clean`, or `delete`: index names are case-sensitive; check `splunkctl indexes list --filter <text>`.
- `No settings to update`: `update` needs `--max-size` or `--frozen-period`.
- `Clean did not finish ... Retry with a larger --clean-timeout`: the index did not empty in time; the message reports whether the index is enabled and how many events remain. Rerun with `--clean-timeout 300` or more.
- `conflict` from `create`: an index with that name already exists; use `update` instead.
- `permission` from `create`, `update`, `clean`, or `delete`: the account lacks `indexes_edit`; use an `admin` account.
- `jq` errors such as `number and string cannot be divided`: wrap fields in `tonumber` as shown above.

## See also

- [Manage data inputs](inputs.md)
- [Manage HEC tokens](hec.md)
- [Manage users and roles](users.md), for index access per role
- [Command reference: indexes](../commands/indexes.md)
