# Search

Run SPL queries against a remote Splunk instance from your laptop.
This is the primary interface for threat hunting, incident response,
and ad-hoc log analysis without opening Splunk Web.

## Commands

```
splunkctl search run '<SPL>'              # sync search, wait for results
splunkctl search export '<SPL>'           # streaming export (large result sets)
splunkctl search oneshot '<SPL>'          # fire-and-forget, small queries
splunkctl search jobs                     # list running/recent search jobs
splunkctl search job <sid>                # check status + fetch results by SID
splunkctl search cancel <sid> --yes       # kill a running search
splunkctl search upload --path file --yes # ingest a local file into Splunk
```

**run** creates a normal job, polls until done, returns results. Use for
most interactive work -- detection tuning, hunting, triage queries.

**export** streams results without creating a job artifact. Use for bulk
extraction (e.g. pulling a week of firewall logs into a local file for
offline analysis). No result-count cap.

**oneshot** is the fastest path for small, read-only queries. No job
object, no poll loop. Good for counts, stats, and quick checks.

## Common options

| Flag | Default | Notes |
|---|---|---|
| `--earliest` | none | Splunk time syntax: `-1h`, `-7d@d`, `2025-01-15T00:00:00` |
| `--latest` | `now` | Use `@d` to snap to midnight boundaries |
| `--limit` | 100 | Max rows returned (run/oneshot only; export has no cap) |
| `--app` | none | App namespace context (e.g. `SplunkEnterpriseSecuritySuite`) |

## Practical examples

Threat hunting -- find brute-force SSH attempts in the last 24 hours:

```bash
splunkctl search run \
    'index=auth sourcetype=linux_secure "Failed password" | stats count by src_ip | where count > 20' \
    --earliest -24h
```

Incident response -- pull all DNS queries to a suspect domain:

```bash
splunkctl search export \
    'index=dns query="*.evil-domain.com" | table _time src_ip query answer' \
    --earliest -7d | jq . > dns_hits.json
```

Detection tuning -- test a correlation search before saving it:

```bash
splunkctl search run \
    'index=wineventlog EventCode=4625 | stats count by Account_Name, src_ip | where count > 10' \
    --earliest -1d --limit 500
```

Quick count -- how many events hit an index today:

```bash
splunkctl search oneshot 'index=main | stats count' --earliest '@d'
```

## Time-range tips

- Always scope `--earliest`. Unscoped searches scan all time and are slow.
- Use snap-to modifiers: `-1d@d` = yesterday midnight, `-1h@h` = top of
  the previous hour. Reduces bucket scanning.
- For exports over days/weeks, break into daily chunks to avoid timeouts
  on heavy indexes.

## Job management

Long-running searches (stats over weeks, large tstats) run async. Check
on them or kill stragglers:

```bash
splunkctl search jobs                     # see all active/recent jobs
splunkctl search job 1719648000.12345     # poll a specific SID
splunkctl search cancel 1719648000.12345 --yes
```

## Upload -- ingest local files into remote Splunk

Your laptop has a CSV of threat intel IOCs or sample logs from a vendor.
Splunk is remote. `upload` reads the local file and pushes it to the
remote instance via the `receivers/simple` REST endpoint -- no SSH, no
shared filesystem, no server-side path needed.

Use cases:
- Push a threat-intel CSV (STIX export, OSINT feed) into a `threat_intel`
  index for correlation searches.
- Ingest sample logs from a new data source to build parsing rules
  (props/transforms) before onboarding the real feed.
- Replay captured traffic or pcap summaries into Splunk for analysis.

```bash
splunkctl search upload --path iocs.csv --index threat_intel --sourcetype csv --yes
splunkctl search upload --path sample_paloalto.log --index sandbox --sourcetype pan:traffic --yes
splunkctl search upload --path captured.json --index main --host web-prod-03 --yes
```

Options: `--index` (default `main`), `--sourcetype` (auto if omitted),
`--source` (defaults to filename), `--host` (host metadata override).
Dry-run by default; add `--yes` to execute.

## Metrics catalog

Explore metrics indexes without writing raw `| mcatalog` SPL. List all
metric names in an index, optionally filter by prefix, or drill into the
dimensions available for a specific metric.

List all metric names in a metrics index:

```bash
splunkctl search metrics --index my_metrics
```

Filter to metrics starting with `cpu`:

```bash
splunkctl search metrics --index my_metrics --filter cpu
```

Show dimensions for a specific metric:

```bash
splunkctl search metrics --index my_metrics --metric cpu.idle
```

The command runs `| mcatalog` under the hood via `oneshot` -- no special
permissions beyond search access to the metrics index.

## SPL normalization

Bare keywords get `search` prepended automatically. Pipe-leading queries
and generating commands (`makeresults`, `inputlookup`, `tstats`, etc.)
pass through unchanged.
