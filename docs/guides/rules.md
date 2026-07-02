# Detection rules

`splunkctl rules` manages saved searches (detections) over the REST API
so they can live in git, pass through CI, and deploy across instances.

## Why detection-as-code

- **Version control** -- every SPL change is a commit with author and diff.
- **Code review** -- detections go through PR review before production.
- **CI/CD** -- lint and validate in a pipeline before import.
- **Cross-instance** -- export from prod, import to staging with one command.
- **Reproducibility** -- rebuild a detection library from a YAML file.

## Commands

```bash
splunkctl rules list                      # list all saved searches
splunkctl rules get <name>                # get rule details + SPL
splunkctl rules create --name 'Rule' --search '<SPL>' \
    --cron '*/5 * * * *' --actions email --yes
splunkctl rules update <name> --search '<SPL>' --yes
splunkctl rules delete <name> --yes
splunkctl rules enable <name> --yes
splunkctl rules disable <name> --yes
splunkctl rules history <name>            # run history
```

### App-private rules

`list`/`get` default to the current namespace, which does not include
saved searches private to a specific app (for example, rules shipped by
an add-on like Splunk_Security_Essentials). Pass `--app`/`--owner` to
scope into that namespace:

```bash
splunkctl rules list --app Splunk_Security_Essentials
splunkctl rules get 'Generate MITRE Detections Lookup' --app Splunk_Security_Essentials
```

## Detection-as-code workflow

Export from prod, edit in git, import to staging, promote.

```bash
# 1. Export production detections
splunkctl rules export --path detections.yml
# 2. Edit in git -- tune SPL, adjust thresholds, commit, open PR.
# 3. Import to staging (dry-run first -- always)
splunkctl rules import --path detections.yml            # preview
splunkctl rules import --path detections.yml --yes      # apply
# 4. Promote to prod (same file, different SPLUNK_HOST)
SPLUNK_HOST=prod.corp splunkctl rules import --path detections.yml --yes
```

### Filtering and safe imports

```bash
splunkctl rules export --path ess.yml --app SplunkEnterpriseSecuritySuite
splunkctl rules export --path brute.yml --name 'Brute Force' --name 'Credential Stuffing'
splunkctl rules import --path detections.yml --no-update --yes  # new rules only
```

`--no-update` seeds a fresh instance without clobbering rules analysts
have tuned in-place. `--name` is repeatable; `--app` filters by app context.

## YAML format reference

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

### Supported fields

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
| `dispatch.earliest_time` | no | Search window start (e.g. `"-1h"`) |
| `dispatch.latest_time` | no | Search window end (e.g. `"now"`) |
| `app` | no | App context (omitted defaults to `search`) |

Any `SavedSearch` REST API attribute can be included -- unknown keys pass
through as-is.

## Agent usage

LLM agents can drive these commands for detection engineering:

```bash
# Audit: find unscheduled rules
splunkctl rules list --json | jq '.[] | select(.is_scheduled == "0")'
# Export-edit-reimport cycle
splunkctl rules export --path /tmp/rules.yml
# (agent edits YAML programmatically)
splunkctl rules import --path /tmp/rules.yml --yes
# Create a detection inline
splunkctl rules create --name 'Lateral Movement - PsExec' \
    --search 'index=win EventCode=7045 ServiceName="PSEXESVC"' \
    --cron '*/5 * * * *' --actions notable --yes
```

`--json` on `list`/`get` gives structured output for parsing. Dry-run
default prevents accidental mutations -- `--yes` is required to apply.
