<!-- summary: List, inspect, and bulk-triage Enterprise Security notable events by status, owner, urgency, disposition, and comment from the terminal. -->

# Triage ES notables

When to use: you work the Enterprise Security incident review queue and want to see what is open, pull the full detail of one notable, then assign it, change its status or urgency, set a disposition, or leave a comment, alone or in bulk.

## Prerequisites

- Splunk Enterprise Security installed on the target instance. Every `es` subcommand first checks for the `SplunkEnterpriseSecuritySuite` app and exits 1 with a `not_found` error when it is missing.
- A Splunk account that can search `index=notable` and call the `notable_update` endpoint (the ES analyst role or equivalent).
- Live verification against a real ES instance is still pending for this group. The read and update logic is unit-tested against a mocked REST layer; the feature-detection path is the only part verified live. Test on a non-production ES instance before scripting production triage.

## Synopsis

```text
splunkctl es notables list [--since TIME] [--until TIME] [--status NAME_OR_INT] [--owner USER] [--rule SUBSTRING] [--limit N]
splunkctl es notables get <EVENT_ID>
splunkctl es notables update <EVENT_IDS>... [--status NAME_OR_INT] [--owner USER] [--urgency informational|low|medium|high|critical] [--disposition ID] [--comment TEXT] [--yes]
```

## Workflow

### See the queue

```bash
splunkctl es notables list
splunkctl es notables list --since -7d --status new
splunkctl es notables list --owner unassigned
splunkctl es notables list --rule beacon --limit 20
splunkctl es notables list --json
```

The default window is the last 24 hours, up to 100 rows. `--since` and `--until` become the search time range; `--status`, `--owner`, and `--rule` fold into the SPL (`index=notable status=1 owner="analyst1" rule_name="*beacon*"`) so filtering happens server side. Expected columns: `time`, `rule`, `security_domain`, `urgency`, `status`, `owner`, `event_id`. Pass `event_id` straight to `get` or `update`.

### Read one notable

```bash
splunkctl es notables get <EVENT_ID>
splunkctl es notables get <EVENT_ID> --json
```

Returns the full field set of the notable event.

### Triage one or many notables

> **Safety:** Target is the Splunk host in the active profile. Impact: status, owner, urgency, disposition, or comment changes on every event id you pass, in one `notable_update` call. Preview with `splunkctl es notables update <EVENT_ID> --status closed --comment 'false positive'`, apply by adding `--yes`, and verify with `splunkctl es notables get <EVENT_ID>`.

```bash
splunkctl es notables update <EVENT_ID> --status closed \
  --comment 'false positive, ticket CHG-123'
splunkctl es notables update <EVENT_ID> --status closed \
  --comment 'false positive, ticket CHG-123' --yes
splunkctl es notables update <ID1> <ID2> <ID3> --owner analyst1 --urgency high --yes
splunkctl es notables update <ID1> <ID2> --status closed --comment 'duplicate of INC-4471' --yes
```

The preview looks like this:

```text
$ splunkctl es notables update evt-1 evt-2 --status closed --comment 'fp'
[DRY RUN] Update 2 notable(s) (profile: default @ splunk.example.com:8089)
  event_ids: evt-1, evt-2
  changes: status=5, comment=fp
Pass --yes to apply.
```

At least one of `--status`, `--owner`, `--urgency`, `--disposition`, or `--comment` is required; `update` with no change is a usage error (exit 2). The preview is local only; the ES feature check runs when `--yes` is passed.

### Status names and integers

`--status` on `list` and `update` accepts the name or the integer ES stores:

| Name | Integer |
|---|---|
| `unassigned` | 0 |
| `new` | 1 |
| `in progress` | 2 |
| `pending` | 3 |
| `resolved` | 4 |
| `closed` | 5 |

Custom statuses from `reviewstatuses.conf` are integers above 5; pass the number, for example `--status 6`.

### Dispositions

`--disposition` is passed through as given. ES ships `disposition:1` (true positive), `disposition:2` (benign positive), `disposition:3` (false positive), and more, but installations customize the list, so check your instance's Incident Review disposition dropdown or `reviewstatuses.conf` before scripting against an id.

## Troubleshooting

- `{"error": {"kind": "not_found", ...}}` naming `SplunkEnterpriseSecuritySuite`: ES is not installed on this instance, or the account cannot see the app.
- Exit 2 on `update`: no change flag was given.
- `list` returns nothing: widen `--since` (for example `--since -7d`) or drop `--status`.
- A custom status name is rejected: use its integer.

## See also

- [Manage ES correlations and threat intel](es-detections.md)
- [Run searches](search.md)
- [Review fired alerts](alerts.md)
- [Ingest SIEM results into SOAR](soar-ingest.md)
- [Command reference: es](../commands/es.md)
