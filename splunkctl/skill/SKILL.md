# splunkctl — Agent Skill Guide

You are operating a Splunk Enterprise instance via `splunkctl`. This guide
tells you how to authenticate, run commands, and handle common workflows.

## Scope

`splunkctl` targets Splunk Enterprise core over the REST API. There is no
dedicated `es` command group yet (planned for a later phase). Enterprise
Security capabilities — notables, risk, correlation-search actions,
asset/identity lookups — are reachable today through the generic search,
rules, and lookups commands documented below; see **ES recipes** under
Workflow patterns.

## Auth

Set up credentials once — all commands inherit them automatically.

```bash
# Interactive (human use):
splunkctl config init

# Non-interactive (agent use):
splunkctl config init --host localhost --port 8089 \
    --username admin --password changeme --scheme https --no-verify

# Verify:
splunkctl config test
splunkctl config show                  # secrets redacted
```

Credentials resolve in order: CLI flags > env vars > config file
(`~/.splunkctl/config.yaml`). Env vars: `SPLUNK_HOST`, `SPLUNK_PORT`,
`SPLUNK_USER`, `SPLUNK_PASS`, `SPLUNK_TOKEN`, `SPLUNK_SCHEME`.

Token auth: set `SPLUNK_TOKEN` for service-account access without a password.

## Global flags

| Flag | Purpose |
|---|---|
| `--json` | Force JSON output |
| `--format table\|json\|csv\|jsonl` | Output format |
| `--fields f1,f2` | Project specific fields |
| `-o, --out file` | Write output to file |
| `-y, --yes` | Apply mutations (skip dry-run) |
| `--timeout N` | Request timeout in seconds (default 30) |
| `-c, --config path` | Config file path override |
| `--debug` | HTTP request/response logging |

**Dry-run by default.** Every mutation previews what would change. Only
`--yes` applies it.

## Output behavior

- **stdout**: data payload only (table, JSON, CSV, JSONL)
- **stderr**: info messages, errors, dry-run previews
- **JSON format**: always a JSON array of objects, even for single items
- **Exit codes**: 0 = success, 1 = application error (not found, server
  rejected the request, etc.), 2 = usage error (missing/invalid flags or
  arguments — Click rejects before any request is made). Dry-run exits 0.

## Commands

### Doctor

```bash
splunkctl doctor                         # check connection, auth, health, permissions
splunkctl doctor --json                  # machine-readable output
splunkctl doctor --strict                # treat warnings as failures (exit 1)
```

### Search

```bash
splunkctl search run 'index=main error | head 10'
splunkctl search run 'index=main' --earliest -24h --latest now --limit 50
splunkctl search run 'index=main' --detach           # start job, return SID, don't wait
splunkctl search export 'index=main | stats count by sourcetype'
splunkctl search oneshot '| makeresults count=5 | eval x=random()'
splunkctl search jobs                    # list recent jobs (with owner, SPL preview)
splunkctl search job <sid>               # get job results
splunkctl search job <sid> --offset 100 --count 50   # paged results
splunkctl search job <sid> --events      # raw events instead of results
splunkctl search job <sid> --status-only # job status without results
splunkctl search cancel <sid> --yes      # cancel a running job
splunkctl search upload --path threats.csv --index threat_intel --yes
```

SPL is auto-normalized: bare keywords get `search` prepended; pipe-leading
and generating commands (`makeresults`, `inputlookup`, `tstats`, etc.) are
passed through unchanged. Use `--app` to scope searches to a specific app.
The `owner` column in `search jobs` is the real submitting user (job ACL,
not the job's internal `author` field, which is always blank).

### Rules (saved searches)

```bash
splunkctl rules list
splunkctl rules list --app Splunk_Security_Essentials  # include app-private rules
splunkctl rules get 'My Rule'
splunkctl rules get 'My Rule' --app Splunk_Security_Essentials --owner nobody
splunkctl rules create --name 'New Rule' --search 'index=main error' \
    --cron '*/5 * * * *' --actions email --description 'Alert on errors' --yes
splunkctl rules update 'My Rule' --search 'index=main fail' --yes
splunkctl rules update 'My Rule' --enabled --yes
splunkctl rules delete 'My Rule' --yes
splunkctl rules enable 'My Rule' --yes
splunkctl rules disable 'My Rule' --yes
splunkctl rules share 'My Rule' --sharing app --yes
splunkctl rules history 'My Rule'
splunkctl rules list --filter 'disabled=1'   # filter by key=value
splunkctl rules export --path detections.yml
splunkctl rules export --path detections.yml --name 'My Rule'
splunkctl rules import --path detections.yml --yes
splunkctl rules import --path detections.yml --no-update --yes
```

`list`/`get` default to the current namespace, which misses saved
searches private to another app — e.g. detections shipped inside
Splunk_Security_Essentials are invisible to a plain `rules list`. Always
pass `--app` (and `--owner` if needed) when auditing detection coverage,
or the audit has a blind spot. `get` also surfaces every enabled action's
non-empty `action.<name>.*` params (e.g. `action.notable.param.severity`,
`action.risk.param._risk_score`) inline — no export needed just to see
what a correlation search's actions are configured to do.

`create`/`update --actions email` or `--actions webhook` warn on stderr
during dry-run if the action's required companion field is missing
(`action.email.to` for email, `action.webhook.param.url` for webhook) —
the server otherwise 400s on `--yes`. Supply it with `--set`:

```bash
splunkctl rules create --name 'New Rule' --search 'index=main error' \
    --actions email --set action.email.to=soc@bank.example --yes
```

`--set KEY=VALUE` (repeatable, `create`/`update` only) sets any raw
saved-search REST field — the generic escape hatch for anything without
a first-class flag, including ES action params:

```bash
splunkctl rules update 'ES Correlation Search' \
    --set action.notable.param.severity=high \
    --set action.notable.param.security_domain=access \
    --set action.risk.param._risk_score=80 \
    --set action.risk.param._risk_object_type=user \
    --yes
```

### Alerts

```bash
splunkctl alerts list
splunkctl alerts get 'Alert Name'
splunkctl alerts actions               # list alert action types
splunkctl alerts suppress 'Alert Name' --duration 7200 --yes
splunkctl alerts unsuppress 'Alert Name' --yes
```

### Dashboards

```bash
splunkctl dashboards list                # includes type column (classic/studio)
splunkctl dashboards list --app search
splunkctl dashboards get my_dashboard
splunkctl dashboards get my_dashboard --definition  # Studio JSON only
splunkctl dashboards create --name new_dash --file dash.xml --yes
splunkctl dashboards create --name studio_dash --file viz.json --type studio --yes
splunkctl dashboards create --name dash --file d.xml --sharing app --yes
splunkctl dashboards update my_dash --file updated.xml --yes   # shows diff preview
splunkctl dashboards delete my_dash --yes
splunkctl dashboards export my_dash --out dash.xml
splunkctl dashboards export my_dash --definition     # Studio JSON definition
splunkctl dashboards export --all --dir ./dashboards # bulk export all
splunkctl dashboards share my_dash --sharing app --yes
```

### Indexes

```bash
splunkctl indexes list
splunkctl indexes get main
splunkctl indexes create --name my_index --yes
splunkctl indexes create --name metrics_idx --datatype metric \
    --max-size 500 --frozen-period 604800 --yes
splunkctl indexes update my_index --max-size 1000 --yes
splunkctl indexes update my_index --frozen-period 2592000 --yes
splunkctl indexes delete my_index --yes
splunkctl indexes clean my_index --yes   # remove all events
splunkctl indexes reload --yes
```

### Inputs

```bash
splunkctl inputs list
splunkctl inputs list --kind monitor
splunkctl inputs get /var/log/syslog
splunkctl inputs create --name /var/log/app.log --kind monitor \
    --index main --sourcetype syslog --yes
splunkctl inputs update /var/log/app.log --sourcetype json --yes
splunkctl inputs update /var/log/app.log --disabled --yes
splunkctl inputs delete /var/log/app.log --yes
splunkctl inputs enable /var/log/app.log --yes
splunkctl inputs disable /var/log/app.log --yes
```

### Lookups

```bash
splunkctl lookups list
splunkctl lookups list --app Splunk_Security_Essentials
splunkctl lookups get my_lookup.csv
splunkctl lookups upload my_lookup.csv --file data.csv --app search --yes
splunkctl lookups update my_lookup.csv --file updated.csv --app search --yes
splunkctl lookups download my_lookup.csv --app search
splunkctl lookups download my_lookup.csv --app search --out local.csv
splunkctl lookups delete my_lookup.csv --app search --yes
```

### HEC (HTTP Event Collector)

```bash
splunkctl hec list                      # list all HEC tokens
splunkctl hec get my_token              # get token details
splunkctl hec create --name my_token --index main --yes
splunkctl hec create --name my_token --index main --set useACK=1 --yes
splunkctl hec delete my_token --yes
splunkctl hec enable my_token --yes
splunkctl hec disable my_token --yes
splunkctl hec settings                  # show global HEC state (port, SSL)
splunkctl hec settings --enable --yes   # enable global HEC
splunkctl hec settings --disable --yes  # disable global HEC
splunkctl hec send my_token 'test event data' --yes  # send event via HEC
```

### Parsers (sourcetypes & extractions)

```bash
splunkctl parsers sourcetypes           # list all sourcetypes
splunkctl parsers get syslog            # get sourcetype config
splunkctl parsers get syslog --key TIME_FORMAT  # get one key
splunkctl parsers extractions           # list field extractions
splunkctl parsers set syslog TIME_FORMAT '%Y-%m-%d' --yes  # set config key
splunkctl parsers unset syslog TIME_FORMAT --yes           # remove key
splunkctl parsers create --sourcetype mysource --category Custom --yes
splunkctl parsers update mysource --category Operating_System --yes
splunkctl parsers delete mysource --yes
splunkctl parsers reload --yes
splunkctl parsers export --path parsers.yml          # export props/transforms
splunkctl parsers import --path parsers.yml --yes    # import from YAML
```

### Apps

```bash
splunkctl apps list
splunkctl apps get SplunkForwarder
splunkctl apps install --path ./my_app.spl --yes
splunkctl apps install --path ./my_app.tar.gz --force --yes
splunkctl apps uninstall my_app --yes
splunkctl apps update my_app --enabled --visible --yes
splunkctl apps update my_app --disabled --hidden --yes
splunkctl apps reload --yes
```

`apps install --path` uploads a local .spl/.tar.gz to the remote Splunk
instance via the Web UI (no server filesystem access needed).

### Users

```bash
splunkctl users list
splunkctl users get admin
splunkctl users create --name newuser --password 'pass' \
    --roles user --email user@example.com --yes
splunkctl users update newuser --roles 'user,power' --yes
splunkctl users update newuser --password 'newpass' --yes
splunkctl users delete newuser --yes
splunkctl users roles                   # list all roles
splunkctl users roles get admin         # role details
splunkctl users roles create --name myrole --imported-roles user \
    --capabilities 'search,list_inputs' --yes
splunkctl users roles update myrole --search-filter 'index=main' --yes
splunkctl users roles delete myrole --yes
```

### Server

```bash
splunkctl server messages               # list system messages
splunkctl server messages --dismiss warn_disk --yes  # dismiss a message
splunkctl server license                # license pool usage
splunkctl server kvstore                # KV store status
```

`kvstore` always reports an explicit status word (`ready`, `failed`,
`starting`, `unknown`, ...) — never a blank field, so a down KV store
can't be mistaken for a healthy empty result.

### Config

```bash
splunkctl config init                   # interactive setup
splunkctl config init --host h --port 8089 --username u --password p
splunkctl config show                   # display config (redacted)
splunkctl config test                   # verify connectivity
```

### Info & version

```bash
splunkctl info                          # server info
splunkctl --version                     # CLI version
```

### Agent discovery

```bash
splunkctl commands                      # JSON command tree
splunkctl skill                         # print this guide
splunkctl skill install                 # install to ~/.claude/skills/
```

## Workflow patterns

### Investigate an alert

Pivot on the firing's `sid` to pull the exact triggering events — don't
re-run the detection's SPL broadly, that returns whatever matches now,
not what actually fired.

```bash
splunkctl alerts list                    # each firing has a sid
splunkctl alerts get 'Alert Rule Name'    # all firings for one rule, with sid
splunkctl search job <sid>                # the exact triggering results
splunkctl search job <sid> --events       # raw events instead of stats/table rows
```

Fallback only: if the job's TTL has expired (`search job <sid>` errors
not-found), recover the SPL from the rule and re-run it over the firing's
time window instead:

```bash
splunkctl rules get 'Alert Rule Name'                # recover the SPL
splunkctl search run '<SPL from rules get>' \
    --earliest -7d --latest now --limit 1000
```

### Audit detection coverage

```bash
splunkctl rules list --json | jq '[.[] | select(.is_scheduled == "1")]'
splunkctl rules list --json | jq '[.[] | select(.disabled == "1")]'
# Repeat with --app for every app that ships detections, or app-private
# rules (e.g. Splunk_Security_Essentials) are silently excluded:
splunkctl rules list --app Splunk_Security_Essentials --json | jq '[.[] | select(.disabled == "1")]'
```

### ES recipes

No dedicated `es` command group yet (see Scope) — these generic
recipes cover the common Enterprise Security workflows in the meantime.

```bash
# Read notables
splunkctl search run 'index=notable' --earliest -24h --latest now --limit 100
splunkctl search run 'index=notable status_label!=Closed' --earliest -7d --limit 200

# Read risk — aggregate risk score per object
splunkctl search run 'index=risk | stats sum(risk_score) by risk_object' \
    --earliest -24h --latest now

# Author/tune a correlation search's notable + risk actions via --set
splunkctl rules update 'ES Correlation Search Name' \
    --set action.notable.param.severity=high \
    --set action.notable.param.security_domain=access \
    --set action.risk.param._risk_score=80 \
    --set action.risk.param._risk_object=user \
    --set action.risk.param._risk_object_type=user \
    --yes
# Audit what a correlation search's actions are already set to:
splunkctl rules get 'ES Correlation Search Name'   # inlines action.notable.*/action.risk.* params

# Asset/identity CSVs — managed like any other lookup table (exact
# filename/app vary by ES version, e.g. assets_by_str.csv /
# identities_lookup_by_str.csv under SplunkEnterpriseSecuritySuite):
splunkctl lookups list --app SplunkEnterpriseSecuritySuite
splunkctl lookups download assets_by_str.csv --app SplunkEnterpriseSecuritySuite
splunkctl lookups update assets_by_str.csv --file assets.csv \
    --app SplunkEnterpriseSecuritySuite --yes
```

### Detection rule lifecycle

```bash
# Create, test, enable:
splunkctl rules create --name 'Failed Logins' \
    --search 'index=main sourcetype=auth action=failure | stats count by user' \
    --cron '*/15 * * * *' --actions email --yes
splunkctl search run 'index=main sourcetype=auth action=failure | stats count by user'
splunkctl rules enable 'Failed Logins' --yes
splunkctl rules history 'Failed Logins'
```

### Export a dashboard for version control

```bash
splunkctl dashboards export my_dashboard --out dashboards/my_dashboard.xml
```

### Detection-as-code

```bash
# Export all rules to YAML, version control them
splunkctl rules export --path detections.yml
# Export specific rules
splunkctl rules export --path detections.yml --name 'Brute Force' --name 'C2 Beacon'
# Import into another instance (dry-run first)
splunkctl rules import --path detections.yml
splunkctl rules import --path detections.yml --yes
# Import without updating existing rules
splunkctl rules import --path detections.yml --no-update --yes
# Machine-readable dry-run diff, to verify programmatically before --yes
splunkctl rules import --path detections.yml --json
```

`import --json` (dry-run only, apply path is unaffected) emits a full,
untruncated diff array on stdout instead of applying anything: one
object per rule, `{"name", "action", "changes": [{"field", "old",
"new"}], "reason"}`. `action` is `create` | `update` | `unchanged` |
`skip`; `reason` is present only when `action` is `skip`; `old` is
`null` for `create`; `changes` is `[]` for `unchanged` and `skip`.

### Parsers-as-code

```bash
# Export props/transforms for version control
splunkctl parsers export --path parsers.yml
# Import into another instance (dry-run shows diff)
splunkctl parsers import --path parsers.yml
splunkctl parsers import --path parsers.yml --yes
```

### Upload data from laptop

```bash
# Ingest threat intel, logs, or sample data remotely
splunkctl search upload --path threats.csv --index threat_intel \
    --sourcetype csv --yes
splunkctl search upload --path firewall.log --yes
```

### Bulk lookup update

```bash
splunkctl lookups download hosts.csv --app search --out hosts.csv
# Edit hosts.csv locally...
splunkctl lookups update hosts.csv --file hosts.csv --app search --yes
```

### Check index health

```bash
splunkctl indexes list --json \
    | jq '.[] | {name, totalEventCount, currentDBSizeMB}'
```

### User and role audit

```bash
splunkctl users list --json | jq '.[] | {name, roles, email}'
splunkctl users roles --json | jq '.[] | {name, capabilities}'
```

### Discover data sources

```bash
splunkctl search oneshot '| metadata type=sourcetypes index=*' --limit 500
splunkctl search oneshot '| metadata type=sources index=main' --limit 100
```

## SPL tips

| Pattern | Example |
|---|---|
| Time range | `--earliest -24h --latest now` |
| Stats | `index=main \| stats count by sourcetype` |
| Table | `index=main \| table _time host source message` |
| Dedup | `index=main \| dedup host` |
| Where | `index=main \| where count > 10` |
| Eval | `index=main \| eval dur=end-start` |
| Timechart | `index=main \| timechart span=1h count by source` |
| Lookup | `\| inputlookup my_lookup.csv` |
| Generate | `\| makeresults count=10 \| eval x=random()` |
| REST | `\| rest /services/server/info` |
| Metadata | `\| metadata type=sources index=main` |
| Tstats | `\| tstats count where index=main by sourcetype` |
| Rex | `\| rex field=_raw "code=(?<code>\d+)"` |

## Error handling

- **Diagnostics**: run `splunkctl doctor` to check everything at once
- **Connection errors**: run `splunkctl config test` to verify auth
- **Timeout**: increase with `--timeout 120`
- **SSL errors**: SSL verification is off by default. Use `--verify` during
  `config init` to enable certificate validation for production.
- **Not found**: commands print `Error: ...` to stderr and exit 1
- **Dry-run block**: add `--yes` to apply mutations
- **Permission denied**: check user roles with `splunkctl users get <name>`
- **Debug**: add `--debug` to see full HTTP request/response logs

## Output piping

```bash
# JSON to jq
splunkctl rules list --json | jq '.[] | .name'

# CSV to file
splunkctl indexes list --format csv --out indexes.csv

# JSONL for streaming
splunkctl search export 'index=main' --format jsonl > events.jsonl

# Field projection
splunkctl users list --fields name,roles

# Alternate config
splunkctl -c /path/to/other.yaml config test
```
