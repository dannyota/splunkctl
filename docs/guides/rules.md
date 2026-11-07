<!-- summary: Export detection rules to YAML, review them in version control, and import them on another Splunk instance with a preview. -->

# Manage detection rules

When to use: you maintain scheduled saved searches (detections) and want to create or tune them from the terminal, keep them in git, review changes in a pull request, and promote them from staging to production with a preview of every change.

## Prerequisites

- A Splunk account that can create and schedule saved searches in the target app (for example the `power` or `admin` role).
- For `--actions notable` or `risk`, Enterprise Security installed on the target.
- For `import`: a YAML file produced by `rules export` or written in the shape shown under "Export to YAML".

## Synopsis

```text
splunkctl rules list [--app APP] [--owner USER] [--scheduled] [--filter SUBSTRING] [--limit N] [--offset N]
splunkctl rules get <NAME> [--app APP] [--owner USER]
splunkctl rules history <NAME>
splunkctl rules schedule [--app APP] [--owner USER] [--filter SUBSTRING] [--limit N] [--offset N]
splunkctl rules test <NAME> [--earliest TIME] [--latest TIME] [--limit N]
splunkctl rules create --name <NAME> --search <SPL> [--cron EXPR] [--app APP] [--description TEXT] [--actions LIST] [--disabled] [--earliest TIME] [--latest TIME] [--alert-type TYPE] [--alert-comparator CMP] [--alert-threshold N] [--severity 1-6] [--throttle SECONDS] [--throttle-fields LIST] [--track|--no-track] [--schedule-window N|auto] [--email-to LIST] [--email-subject TEXT] [--webhook-url URL] [--set KEY=VALUE]... [--yes]
splunkctl rules update <NAME> [same flags as create except --name, plus --enabled|--disabled] [--yes]
splunkctl rules enable <NAME> [--yes]
splunkctl rules disable <NAME> [--yes]
splunkctl rules share <NAME> --sharing <user|app|global> [--owner USER] [--yes]
splunkctl rules delete <NAME> [--yes]
splunkctl rules export --path <FILE.yml> [--name NAME]... [--app APP]
splunkctl rules import --path <FILE.yml> [--update|--no-update] [--yes]
```

## Workflow

### List and inspect rules

```bash
splunkctl rules list
splunkctl rules list --scheduled
splunkctl rules get 'Brute Force - Multiple Failed Logins'
splunkctl rules history 'Brute Force - Multiple Failed Logins'
splunkctl rules list --json | jq '.[] | select(.is_scheduled == "0")'
```

Expected result: one row per saved search; `get` adds the SPL and every saved-search field; `history` lists past runs. `--json` gives structured output for scripts and agents.

`list` and `get` default to the current namespace, which does not include saved searches private to a specific app (for example rules shipped by an add-on such as Splunk_Security_Essentials). Pass `--app` to scope into that namespace; the owner is wildcarded automatically, so app-private rules owned by any user are included. Add `--owner` only to narrow to one user's rules:

```bash
splunkctl rules list --app Splunk_Security_Essentials
splunkctl rules get 'Generate MITRE Detections Lookup' --app Splunk_Security_Essentials
```

### Check scheduler health

```bash
splunkctl rules schedule
splunkctl rules schedule --json
splunkctl rules schedule --app search
```

Expected result: a table with `name`, `cron`, `next_run`, `window`, and `enabled` for every scheduled saved search. JSON output adds `cron_schedule`, `next_scheduled_time`, `dispatch.earliest_time`, `dispatch.latest_time`, `is_scheduled`, `disabled`, and `qualifiedSearch`.

### Create a rule

> **Safety:** Target is the Splunk host and app in the active profile. Impact: a new scheduled search that starts running on its cron and fires its alert actions. Preview with `splunkctl rules create --name 'Lateral Movement - PsExec' --search 'index=win EventCode=7045 ServiceName="PSEXESVC"' --cron '*/5 * * * *' --actions notable`, apply by adding `--yes`, and verify with `splunkctl rules get 'Lateral Movement - PsExec'`.

```bash
splunkctl rules create --name 'Lateral Movement - PsExec' \
    --search 'index=win EventCode=7045 ServiceName="PSEXESVC"' \
    --cron '*/5 * * * *' --actions notable --yes
splunkctl rules create --name 'Rule' --search '<SPL>' \
    --cron '*/5 * * * *' --actions email --email-to soc@bank.example --yes
splunkctl rules create --name 'Rule' --search '<SPL>' --cron '*/5 * * * *' \
    --alert-comparator 'greater than' --alert-threshold 10 --severity 4 \
    --throttle 3600 --throttle-fields src --disabled --yes
```

Expected result: the rule exists; with `--disabled` it is created but not scheduled until you `enable` it.

`--email-to`, `--email-subject`, and `--webhook-url` are shortcuts for the most common alert-action fields, on both `create` and `update`:

| Flag | Field | Requires |
|---|---|---|
| `--email-to` | `action.email.to` | `--actions email` to enable |
| `--email-subject` | `action.email.subject` | `--actions email` to enable |
| `--webhook-url` | `action.webhook.param.url` | `--actions webhook` to enable |

Setting a flag does not enable its action; Splunk keeps `action.*` params inert until the action is named in `--actions`. Passing a flag whose action is not enabled prints a non-blocking advisory (`--email-to is set but 'email' is not in --actions`) and still applies. On `update` the advisory is based on the current invocation's `--actions`, so it can fire even when the action is already enabled server-side (for example when rotating an email recipient without repeating `--actions email`). A flag and an equivalent `--set` for the same field is a usage error (exit 2), not a silent pick:

```bash
splunkctl rules create --name 'Rule' --search '<SPL>' \
    --email-to soc@bank.example --set action.email.to=other@bank.example
```

`--set action.*` is the escape hatch for any action field without a flag (ES notable and risk params, `action.webhook.param.method`, and so on).

### Update, enable, or disable a rule

> **Safety:** Target is the Splunk host and app in the active profile. Impact: the SPL, schedule, or actions change for the next run; `disable` stops the detection from firing. Preview with `splunkctl rules update 'Rule' --search '<SPL>'`, apply by adding `--yes`, and verify with `splunkctl rules get 'Rule'`.

```bash
splunkctl rules update 'Rule' --search '<SPL>' --yes
splunkctl rules update 'Rule' --cron '*/10 * * * *' --earliest -15m --latest now --yes
splunkctl rules enable 'Rule' --yes
splunkctl rules disable 'Rule' --yes
```

Expected result: `get` shows the new field values; `enable` and `disable` flip `disabled`.

### Test a rule without firing actions

```bash
splunkctl rules test 'Rule'
splunkctl rules test 'Rule' --earliest -7d --latest now --limit 500
```

Expected result: the saved search is dispatched now over its window (or the override) and the results print, without triggering alert actions. Use it to backfill or to tune a threshold before enabling.

### Change sharing

> **Safety:** Target is the Splunk host and app in the active profile. Impact: who can see and run the rule changes; `global` exposes it from every app. Preview with `splunkctl rules share 'Rule' --sharing app`, apply by adding `--yes`, and verify with `splunkctl rules get 'Rule' --json` (check the ACL).

```bash
splunkctl rules share 'Rule' --sharing app --yes
splunkctl rules share 'Rule' --sharing global --owner admin --yes
```

### Delete a rule

> **Safety:** Target is the Splunk host and app in the active profile. Impact: the saved search is removed and its detection stops; only an export can restore it. Preview with `splunkctl rules delete 'Rule'`, apply by adding `--yes`, and verify with `splunkctl rules list --filter 'Rule'`.

```bash
splunkctl rules export --path backup.yml --name 'Rule'
splunkctl rules delete 'Rule' --yes
```

### Export to YAML

```bash
splunkctl rules export --path detections.yml
splunkctl rules export --path ess.yml --app SplunkEnterpriseSecuritySuite
splunkctl rules export --path brute.yml --name 'Brute Force' --name 'Credential Stuffing'
```

Expected result: a YAML list, one document per rule. `--name` is repeatable; `--app` filters by app context. The file looks like this:

```yaml
- name: "Brute Force - Multiple Failed Logins"
  search: >
    index=auth sourcetype=linux_secure action=failure
    | bin _time span=5m
    | stats count dc(user) as users values(user) as targets by src
    | where count > 20 AND users > 3
  description: "Distributed brute force across multiple accounts"
  cron_schedule: "*/10 * * * *"
  is_scheduled: "1"
  actions: "email,notable"
  alert.severity: "4"
  alert.suppress: "1"
  alert.suppress.period: "1h"
  alert.suppress.fields: "src"
  dispatch.earliest_time: "-15m"
  dispatch.latest_time: "now"
```

| Field | Required | Description |
|---|---|---|
| `name` | yes | Saved search name (unique per app) |
| `search` | yes | SPL query |
| `description` | no | Human-readable summary |
| `cron_schedule` | no | Cron expression (auto-sets `is_scheduled`) |
| `is_scheduled` | no | `"1"` to enable scheduling |
| `disabled` | no | `"1"` to create in disabled state |
| `actions` | no | Alert actions, comma-separated (`email`, `notable`) |
| `alert_type` | no | Trigger condition type |
| `alert.severity` | no | `"1"` (info) through `"6"` (critical) |
| `alert.suppress` | no | `"1"` to suppress; set `.period` and `.fields` |
| `alert.track` | no | `"1"` to track triggered alert count |
| `dispatch.earliest_time` | no | Search window start (for example `"-1h"`) |
| `dispatch.latest_time` | no | Search window end (for example `"now"`) |
| `app` | no | App context (omitted defaults to `search`) |

Any `SavedSearch` REST API attribute can be included; unknown keys pass through as-is.

### Import with a preview

> **Safety:** Target is the Splunk host in the active profile (set `SPLUNK_HOST` or `--profile` to pick staging or prod). Impact: rules in the file are created or updated; nothing is deleted. Preview with `splunkctl rules import --path detections.yml` and read the per-rule create, update, or unchanged lines with field-level diffs, apply by adding `--yes`, and verify with `splunkctl rules get <NAME>`.

```bash
splunkctl rules import --path detections.yml
splunkctl rules import --path detections.yml --json
splunkctl rules import --path detections.yml --yes
splunkctl rules import --path detections.yml --no-update --yes
SPLUNK_HOST=prod.corp splunkctl rules import --path detections.yml --yes
```

Expected result: the dry run prints one line per rule on stderr; with `--json` it also prints a full diff array on stdout, one object per rule: `{"name", "action", "changes": [{"field", "old", "new"}], "reason"}` where `action` is `create`, `update`, `unchanged`, or `skip`. The command exits non-zero when any rule is skipped or fails. `--no-update` seeds a fresh instance without clobbering rules analysts have tuned in place.

### Run the detection-as-code loop

> **Safety:** Target is whichever Splunk host `SPLUNK_HOST` or `--profile` selects for each step. Impact: the staging and then the prod instance receive every rule in the file. Preview with `splunkctl rules import --path detections.yml`, apply by adding `--yes`, and verify with `splunkctl rules list --scheduled` on the target.

```bash
splunkctl rules export --path detections.yml
git add detections.yml && git commit -m "Tune brute force threshold"
splunkctl rules import --path detections.yml
splunkctl rules import --path detections.yml --yes
SPLUNK_HOST=prod.corp splunkctl rules import --path detections.yml --yes
```

Expected result: every SPL change is a commit with author and diff, goes through pull-request review, is linted in CI, is previewed on staging, and is promoted to prod from the same file. [Manage configuration as code](state.md) wraps this loop with a change-ticket report.

## Troubleshooting

- `not_found` on `get` or `update`: the rule is app-private; pass `--app <APP>`.
- Usage error (exit 2) on `create` or `update`: you passed both `--email-to` (or `--email-subject`, `--webhook-url`) and the equivalent `--set` field. Keep one.
- `permission` on `create`, `share`, or `import`: the account cannot write saved searches in the app, or `--sharing global` needs the `admin_all_objects` capability.
- `http` error mentioning cron: Splunk rejected `--cron`; use five fields (`*/5 * * * *`).
- `import` exits 1 after applying some rules: at least one rule was skipped; its `reason` is in the `--json` output. Rerun after fixing, the rest is idempotent.
- The email action never sends: `--email-to` alone does not enable it; add `--actions email`.

## See also

- [Manage configuration as code](state.md)
- [Review fired alerts](alerts.md)
- [Manage ES correlations and threat intel](es-detections.md)
- [Run searches](search.md)
- [Command reference: rules](../commands/rules.md)
