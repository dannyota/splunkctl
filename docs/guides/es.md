# ES notable-event triage and correlation-search admin

The SOC daily loop: see what's queued, pull the full detail on one
notable, then assign, set status/urgency/disposition, or leave a comment
— alone or in bulk. Reading notables already works through the generic
`search` command (`index=notable`); this group adds the incident-review
mutation ES's `notable_update` endpoint provides, plus normalized reads
that don't require hand-writing SPL.

The `correlations` subgroup adds admin operations over correlation
searches — the saved searches scoped to the ES app that generate
notables. List, inspect, enable, and disable them without touching
Splunk Web.

> **Requires Enterprise Security.** Every `es` subcommand checks for the
> `SplunkEnterpriseSecuritySuite` app first (one cheap entity fetch, not a
> full apps dump). Without ES installed, every subcommand exits 1 with a
> `not_found` envelope naming the app — see **Feature detection** below.
>
> **Live-verified against ES: pending.** The local dev instance ships
> Splunk Security Essentials, not Enterprise Security, so only the
> feature-detection negative path has been verified against a real
> instance. The read/update logic is unit-tested against a mocked REST
> layer; verify against a real ES instance before relying on it in
> production triage.

## Commands

```bash
splunkctl es notables list                              # last 24h, up to 100
splunkctl es notables list --since -7d --status new      # open in the last week
splunkctl es notables list --owner unassigned             # unclaimed queue
splunkctl es notables list --rule beacon --limit 20       # by correlation search
splunkctl es notables get <event_id>                      # full field set
splunkctl es notables update <event_id> --status closed \
    --comment 'false positive, ticket CHG-123' --yes
splunkctl es notables update <id1> <id2> <id3> \
    --owner analyst1 --urgency high --yes                # bulk triage
```

## Feature detection

`es` is a feature-detected group: it exists in `commands --json` and
`--help` regardless of what's installed, but every subcommand's first
move is a single entity fetch for `SplunkEnterpriseSecuritySuite`. On an
instance without ES:

```bash
$ splunkctl --json es notables list
{"error": {"kind": "not_found", "http_status": null, "message": "App 'SplunkEnterpriseSecuritySuite' is not installed on this instance. The 'es' command group requires Splunk Enterprise Security."}}
$ echo $?
1
```

`update`'s dry-run preview never triggers this check — like every guarded
command, the preview is local-only (config + banner, no network call).
The ES check runs once `--yes` is passed and the mutation is about to
apply.

## List filters compose server-side

`--since`/`--until` become the search's time range; `--status`, `--owner`,
and `--rule` fold into the SPL itself (`index=notable status=1
owner="analyst1" rule_name="*beacon*"`) rather than filtering client-side
after a full fetch — the same "filters first" contract as every other
list surface (see SKILL.md). Output columns are normalized: `time`,
`rule`, `security_domain`, `urgency`, `status`, `owner`, `event_id`.
`event_id` is the notable's unique id — pass it straight to `get` or
`update`.

## Status names and integers

`--status` (on both `list` and `update`) accepts either the canonical
name or the raw integer ES uses internally:

| Name | Integer |
|---|---|
| `unassigned` | 0 |
| `new` | 1 |
| `in progress` | 2 |
| `pending` | 3 |
| `resolved` | 4 |
| `closed` | 5 |

Custom statuses configured on an instance (via `reviewstatuses.conf`) are
integers outside 0-5 — pass the number directly, e.g. `--status 6`.

## Bulk triage

`update` accepts one or more `EVENT_ID` arguments; all of them go into a
single `notable_update` call (`ruleUIDs`), so a bulk status change or
reassignment is one request, not N:

```bash
splunkctl es notables update <id1> <id2> <id3> --status closed \
    --comment 'duplicate of INC-4471' --yes
```

At least one of `--status`/`--owner`/`--urgency`/`--disposition`/
`--comment` is required — `update` with no fields is a usage error
(exit 2), not a silent no-op.

## Dry-run preview

Like every mutation, `update` previews before applying:

```bash
$ splunkctl es notables update evt-1 evt-2 --status closed --comment 'fp'
[DRY RUN] Update 2 notable(s) (profile: default @ splunk.example.com:8089)
  event_ids: evt-1, evt-2
  changes: status=5, comment=fp
Pass --yes to apply.
```

## Disposition

`--disposition` is passed through exactly as given — ES ships a default
set (`disposition:1` true positive, `disposition:2` benign positive,
`disposition:3` false positive, ...) but installations customize this
list, so the CLI doesn't invent a name mapping. Check your instance's
configured dispositions (Incident Review > disposition dropdown, or
`reviewstatuses.conf`) before scripting against specific ids.

## Options

| Flag | Applies to | Description |
|------|-----------|-------------|
| `--since` | `list` | Earliest time (default `-24h`) |
| `--until` | `list` | Latest time (default `now`) |
| `--status` | `list`, `update` | Status name or integer (see table above) |
| `--owner` | `list` | Filter by assigned owner |
| `--rule` | `list` | Correlation search name substring |
| `--limit` | `list` | Max results (default 100) |
| `--owner` | `update` | New assignee |
| `--urgency` | `update` | `informational`/`low`/`medium`/`high`/`critical` |
| `--disposition` | `update` | ES disposition id, passed through as-is |
| `--comment` | `update` | Analyst comment |
| `--yes` | `update` | Apply the mutation (skip dry-run preview) |

## Correlation searches

Correlation searches are saved searches scoped to the
`SplunkEnterpriseSecuritySuite` app. They generate notable events when
their SPL triggers. The `es correlations` subgroup provides admin
operations over them using `service.saved_searches` with ES app scoping.

```bash
splunkctl es correlations list                              # all correlation searches
splunkctl es correlations list --enabled                    # only enabled
splunkctl es correlations list --disabled                   # only disabled
splunkctl es correlations list --security-domain access     # filter by domain
splunkctl es correlations get "Brute Force Access Behavior" # full detail
splunkctl es correlations enable "Brute Force" --yes        # enable one
splunkctl es correlations enable "Rule A" "Rule B" --yes    # enable multiple
splunkctl es correlations disable "DNS Exfil" --yes         # disable one
```

### Correlation-search fields

The summary view (`list`) surfaces: `name`, `security_domain`,
`severity`, `enabled`, `cron_schedule`, `next_scheduled_time`. The
detail view (`get`) adds: `search`, `description`, `is_scheduled`,
`actions`, `dispatch.earliest_time`, `dispatch.latest_time`, `app`,
`owner`, `sharing`.

### Enable / disable

Both `enable` and `disable` are guarded mutations — they preview in
dry-run mode and require `--yes` to apply. They accept one or more
correlation search names:

```bash
splunkctl es correlations enable "Rule A" "Rule B" --yes
splunkctl es correlations disable "Rule A" --yes
```

## Implementation notes

`list`/`get` (notables) run over the existing oneshot-search
infrastructure against `index=notable` (no SDK entity class — ES ships
no REST collection for notables, just the raw index and the
`notable_update` action endpoint). `update` POSTs to
`/services/notable_update` through the SDK's `service.post` via
`client.py`'s existing request plumbing — no new HTTP stack.

Correlation searches use `service.saved_searches` with
`app=SplunkEnterpriseSecuritySuite` and `owner="-"` to fetch across all
owners. The `security_domain` is read from the
`action.correlationsearch.label` content key (the standard ES field for
this), falling back to `security_domain` if absent.
