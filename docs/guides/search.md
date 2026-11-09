<!-- summary: Run SPL searches, export results, upload files, and manage search jobs on a remote Splunk instance. -->

# Run searches

When to use: you want to run SPL against a remote Splunk instance from your terminal for hunting, incident response, or detection tuning, pull large result sets to a file, push a local file into an index, or check on and cancel long-running jobs.

## Prerequisites

- A profile that passes `splunkctl doctor` (see [Configure](configure.md)).
- A role with search access to the indexes you query. `upload` needs permission to post data to the `receivers/simple` endpoint.
- Always scope `--earliest`; unscoped searches scan all time.

## Synopsis

```text
splunkctl search run <SPL> [--earliest TIME] [--latest TIME] [--limit N] [--app APP] [--detach] [--yes]
splunkctl search export <SPL> [--earliest TIME] [--latest TIME] [--app APP] [--yes]
splunkctl search oneshot <SPL> [--earliest TIME] [--latest TIME] [--limit N] [--app APP] [--yes]
splunkctl search jobs [--filter SID_SUBSTRING] [--limit N] [--offset N]
splunkctl search job <SID> [--offset N] [--count N] [--events] [--status-only]
splunkctl search cancel <SID> [--yes]
splunkctl search upload --path <FILE> [--index INDEX] [--sourcetype TYPE] [--source TEXT] [--host HOST] [--yes]
splunkctl search metrics --index <INDEX> [--metric NAME] [--filter PREFIX] [--app APP]
```

## Workflow

### Run an interactive search

```bash
splunkctl search run \
    'index=auth sourcetype=linux_secure "Failed password" | stats count by src_ip | where count > 20' \
    --earliest -24h
splunkctl search run \
    'index=wineventlog EventCode=4625 | stats count by Account_Name, src_ip | where count > 10' \
    --earliest -1d --limit 500
```

Expected result: `run` creates a normal job, polls until it finishes, and prints up to `--limit` rows (default 100). Use it for most interactive work: detection tuning, hunting, triage queries. When more rows exist the output names the sid and the `search job <SID> --offset N` command that fetches the next page.

| Flag | Default | Notes |
|---|---|---|
| `--earliest` | none | Splunk time syntax: `-1h`, `-7d@d`, `2025-01-15T00:00:00` |
| `--latest` | `now` | Use `@d` to snap to midnight boundaries |
| `--limit` | 100 | Max rows returned (`run` and `oneshot` only; `export` has no cap) |
| `--app` | none | App namespace context (for example `SplunkEnterpriseSecuritySuite`) |

Time-range tips: snap-to modifiers reduce bucket scanning (`-1d@d` is yesterday midnight, `-1h@h` the top of the previous hour). For exports over days or weeks, break the range into daily chunks to avoid timeouts on heavy indexes.

Bare keywords get `search` prepended automatically. Pipe-leading queries and generating commands (`makeresults`, `inputlookup`, `tstats`, and others) pass through unchanged.

### Export a large result set

```bash
splunkctl search export \
    'index=dns query="*.evil-domain.com" | table _time src_ip query answer' \
    --earliest -7d | jq . > dns_hits.json
```

Expected result: results stream to stdout without a job artifact and without a row cap. Use it for bulk extraction, for example a week of firewall logs for offline analysis.

### Get a quick count

```bash
splunkctl search oneshot 'index=main | stats count' --earliest '@d'
```

Expected result: the fastest path for small, read-only queries: no job object and no poll loop. Good for counts, stats, and quick checks.

### Run SPL that writes

> **Safety:** Target is the Splunk host in the active profile. Impact: write commands such as `outputlookup` and `collect` change lookups or indexes on the instance. Preview by running the command without `--yes` and reading the refusal, apply by adding `--yes`, and verify with a read search (for example `| inputlookup suspicious_ips.csv`).

```bash
splunkctl search run 'index=auth action=failure | stats count by src_ip | outputlookup suspicious_ips.csv' --earliest -24h
splunkctl search run 'index=auth action=failure | stats count by src_ip | outputlookup suspicious_ips.csv' --earliest -24h --yes
```

Expected result: without `--yes` the first command is refused before dispatch, exits 1, and in JSON output mode (including the non-TTY default) emits a `confirmation_required` error envelope. The refusal covers `outputlookup`, `collect`, `mcollect`, `meventcollect`, `sendalert`, `delete`, `outputcsv`, `outputtext`, `sendemail`, `runshellscript`, and `script`, in `run`, `export`, and `oneshot` alike. With `--yes` the search runs.

### Enforce read-only searches

```bash
splunkctl --read-only search run 'index=main | stats count' --earliest -1h
```

Read-only mode refuses writes even with `--yes`. It permits only explicitly classified built-in read commands. Dynamic commands (`map`, `savedsearch`, `dbxquery`, `dbxoutput`, `run`) and unknown commands are refused. Macros and subsearches require successful server parser expansion and classification. Errors name the offending command.

Search jobs and server audit/access logs are exceptions to the guarantee against application-data, configuration and authentication changes. Only jobs created by the current invocation can be cancelled, finalized or deleted under this policy. See [Use read-only access](read-only.md).

### Manage long-running jobs

> **Safety:** Target is the Splunk host in the active profile. Impact: `cancel` kills a running job and discards its results. Preview with `splunkctl search cancel 1719648000.12345`, apply by adding `--yes`, and verify with `splunkctl search jobs --filter 1719648000`.

```bash
splunkctl search run 'index=firewall | tstats count where index=firewall by sourcetype' --earliest -30d --detach
splunkctl search jobs
splunkctl search job 1719648000.12345 --status-only
splunkctl search job 1719648000.12345 --offset 100 --count 100
splunkctl search job 1719648000.12345 --events
splunkctl search cancel 1719648000.12345 --yes
```

Expected result: `--detach` submits the job and prints its sid; `jobs` lists running and recent jobs (`--filter` matches the sid); `job` shows status and pages results (`--count 0` fetches all, `--events` fetches raw events); `cancel` stops it.

### Upload a local file into an index

> **Safety:** Target is the Splunk host in the active profile. Impact: the file's lines are indexed as events in `--index` (default `main`) and cannot be unindexed without `delete` rights. Preview with `splunkctl search upload --path iocs.csv --index threat_intel --sourcetype csv`, apply by adding `--yes`, and verify with `splunkctl search oneshot 'index=threat_intel source="iocs.csv" | stats count'`.

```bash
splunkctl search upload --path iocs.csv --index threat_intel --sourcetype csv --yes
splunkctl search upload --path sample_paloalto.log --index sandbox --sourcetype pan:traffic --yes
splunkctl search upload --path captured.json --index main --host web-prod-03 --yes
```

Expected result: the file is read on your laptop and pushed through the `receivers/simple` REST endpoint; no SSH, shared filesystem, or server-side path is needed. `--sourcetype` is auto-detected when omitted, `--source` defaults to the file name, and `--host` overrides host metadata. Typical uses: a threat-intel CSV (STIX export, OSINT feed) for correlation searches, sample logs from a new vendor to build props and transforms before onboarding the real feed, or captured traffic summaries for analysis.

### Explore a metrics index

```bash
splunkctl search metrics --index my_metrics
splunkctl search metrics --index my_metrics --filter cpu
splunkctl search metrics --index my_metrics --metric cpu.idle
```

Expected result: all metric names in the index, the names starting with `cpu`, or the dimensions of `cpu.idle`. The command runs `| mcatalog` through `oneshot`, so it needs only search access to the metrics index.

## Troubleshooting

- `confirmation_required` (exit 1): the SPL contains a write command. Add `--yes` only if the write is intended.
- `auth` error: credentials are wrong or the session expired; run `splunkctl doctor`.
- `permission` error on `upload`: the role lacks the capability to post to `receivers/simple`.
- `timeout` on `run`: the job is still running; rerun with `--detach` and poll with `search job <SID> --status-only`, or raise the global `--timeout` (seconds).
- `not_found` on `job` or `cancel`: the sid expired or was typed wrong; list current sids with `splunkctl search jobs`.
- Zero results on a known-good search: check the time range first, then confirm the indexers are healthy with [Check server health and topology](server.md).

## See also

- [Configure](configure.md)
- [Manage detection rules](rules.md)
- [Triage ES notables](es.md)
- [Manage lookups](lookups.md)
- [Ingest SIEM results into SOAR](soar-ingest.md)
- [Check server health and topology](server.md)
- [Command reference: search](../commands/search.md)
