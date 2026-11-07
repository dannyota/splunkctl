<!-- summary: Review fired alerts, inspect alert actions, and manage alert suppression on a Splunk instance from the terminal. -->

# Review fired alerts

When to use: an incident is under way and you need to see which rules fired, when, and at what severity; a maintenance window is coming and noisy rules must be throttled before they flood the on-call channel; or an auditor asks which alerts fired and which were suppressed.

## Prerequisites

- A profile that passes `splunkctl doctor` (see [Configure](configure.md)).
- Read access to fired alerts for `list`, `get`, and `actions`.
- Write access to the saved search that owns the rule for `suppress` and `unsuppress`.

## Synopsis

```text
splunkctl alerts list [--filter SUBSTRING] [--limit N] [--offset N]
splunkctl alerts get <NAME>
splunkctl alerts actions
splunkctl alerts suppress <NAME> [--duration SECONDS] [--yes]
splunkctl alerts unsuppress <NAME> [--yes]
```

`NAME` is the rule's saved search name, matched exactly and case-sensitively.

## Workflow

### Triage during an incident

```bash
splunkctl alerts list
splunkctl alerts list --filter brute
splunkctl alerts get 'Brute Force Login Attempts'
```

Expected result: one row per firing with `rule`, `triggered`, `severity`, `sid`, and `actions`. `--filter` matches the rule name; `--limit` and `--offset` page the firing rows client side, so a row is one firing, not one rule. `get` prints every firing of one rule and the firing count.

### Check alert action types

```bash
splunkctl alerts actions
```

Expected result: the action types (email, webhook, script, and app-provided actions) configured on the instance. Check this before creating or changing saved searches that fire alerts.

### Suppress during a maintenance window

> **Safety:** Target is the Splunk host in the active profile. Impact: `alert.suppress=1` and `alert.suppress.period=<SECONDS>s` are written to the rule's saved search, so repeat firings are throttled for that window. Preview with `splunkctl alerts suppress 'Brute Force Login Attempts' --duration 7200`, apply by adding `--yes`, and verify with `splunkctl conf get savedsearches 'Brute Force Login Attempts' --key alert.suppress`.

```bash
splunkctl alerts suppress 'Brute Force Login Attempts' --duration 7200
splunkctl alerts suppress 'Brute Force Login Attempts' --duration 7200 --yes
```

Expected result: the preview prints `[DRY RUN] Throttle alerts for rule (profile: NAME @ HOST:8089)` and the settings it will write; the apply prints `Throttled 'Brute Force Login Attempts' for 7200s.`. `--duration` is in seconds and defaults to 3600. Splunk's fired-alerts endpoint cannot be edited; throttling is a property of the underlying saved search.

Suppress several rules during a planned outage:

```bash
for rule in 'Brute Force Login Attempts' 'Failed VPN Auth' 'DNS Exfil'; do
  splunkctl alerts suppress "$rule" --duration 14400 --yes
done
```

### Remove suppression after the window

> **Safety:** Target is the Splunk host in the active profile. Impact: `alert.suppress=0` is written to the rule's saved search and it alerts normally again. Preview with `splunkctl alerts unsuppress 'Brute Force Login Attempts'`, apply by adding `--yes`, and verify with `splunkctl conf get savedsearches 'Brute Force Login Attempts' --key alert.suppress`.

```bash
splunkctl alerts unsuppress 'Brute Force Login Attempts'
splunkctl alerts unsuppress 'Brute Force Login Attempts' --yes
```

Expected result: `Removed throttling from 'Brute Force Login Attempts'.`. The throttle setting stays on the saved search until you remove it; it does not expire on its own.

### Produce JSON for scripts and agents

```bash
splunkctl alerts list --json
splunkctl alerts list --json | jq '.[] | select((.severity | tonumber) >= 5)'
splunkctl alerts get 'Brute Force Login Attempts' --json > alert_detail.json
```

Expected result: a JSON array of firing rows, suitable for `jq`, an agent, or audit evidence. `--format table|json|csv|jsonl` picks another output format. An agent can consume the JSON directly to correlate fired alerts with a change calendar or file tickets for high-severity triggers.

## Troubleshooting

- `not_found` from `alerts get`: the name must match the rule exactly; run `splunkctl alerts list --filter <text>` to find the spelling.
- `not_found` from `suppress` or `unsuppress`: no saved search with that name is visible to your account; check `splunkctl rules list --filter <text>`.
- `permission` from `suppress` or `unsuppress`: your role cannot edit the saved search in its owning app.
- `No fired alerts.`: nothing has fired within Splunk's fired-alert retention; this is not an error.
- A rule keeps firing after `suppress --yes`: throttling suppresses repeat firings for the period after a trigger; it does not disable the search. Disable the rule itself with the commands in [Manage detection rules](rules.md).

## See also

- [Manage detection rules](rules.md)
- [Triage ES notables](es.md)
- [Edit any conf file](conf.md)
- [Command reference: alerts](../commands/alerts.md)
