# splunkctl — Agent Skill Guide

You are operating a Splunk Enterprise instance via `splunkctl`. This guide
tells you how to authenticate, run commands, and handle common workflows.

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
- **Exit codes**: 0 = success, 1 = error. Dry-run exits 0.

## Commands

### Doctor

```bash
splunkctl doctor                         # check connection, auth, health, permissions
splunkctl doctor --json                  # machine-readable output
```

### Search

```bash
splunkctl search run 'index=main error | head 10'
splunkctl search run 'index=main' --earliest -24h --latest now --limit 50
splunkctl search run 'index=main' --earliest -7d --app search
splunkctl search export 'index=main | stats count by sourcetype'
splunkctl search oneshot '| makeresults count=5 | eval x=random()'
splunkctl search jobs                    # list recent jobs
splunkctl search job <sid>               # get job status/results
splunkctl search cancel <sid> --yes      # cancel a running job
splunkctl search upload --path threats.csv --index threat_intel --yes
```

SPL is auto-normalized: bare keywords get `search` prepended; pipe-leading
and generating commands (`makeresults`, `inputlookup`, `tstats`, etc.) are
passed through unchanged. Use `--app` to scope searches to a specific app.

### Rules (saved searches)

```bash
splunkctl rules list
splunkctl rules get 'My Rule'
splunkctl rules create --name 'New Rule' --search 'index=main error' \
    --cron '*/5 * * * *' --actions email --description 'Alert on errors' --yes
splunkctl rules update 'My Rule' --search 'index=main fail' --yes
splunkctl rules update 'My Rule' --enabled --yes
splunkctl rules delete 'My Rule' --yes
splunkctl rules enable 'My Rule' --yes
splunkctl rules disable 'My Rule' --yes
splunkctl rules history 'My Rule'
splunkctl rules export --path detections.yml
splunkctl rules export --path detections.yml --name 'My Rule'
splunkctl rules import --path detections.yml --yes
splunkctl rules import --path detections.yml --no-update --yes
```

### Alerts

```bash
splunkctl alerts list
splunkctl alerts get 'Alert Name'
splunkctl alerts actions               # list alert action types
splunkctl alerts suppress 'Alert Name' --duration 7200 --yes
```

### Dashboards

```bash
splunkctl dashboards list
splunkctl dashboards list --app search
splunkctl dashboards get my_dashboard
splunkctl dashboards create --name new_dash --file dash.xml --app search --yes
splunkctl dashboards update my_dash --file updated.xml --app search --yes
splunkctl dashboards delete my_dash --app search --yes
splunkctl dashboards export my_dash --out dash.xml
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
splunkctl hec create --name my_token --index main \
    --indexes 'main,_internal' --sourcetype json --yes
splunkctl hec delete my_token --yes
splunkctl hec enable my_token --yes
splunkctl hec disable my_token --yes
```

### Parsers (sourcetypes & extractions)

```bash
splunkctl parsers sourcetypes           # list all sourcetypes
splunkctl parsers get syslog            # get sourcetype config
splunkctl parsers extractions           # list field extractions
splunkctl parsers create --sourcetype mysource --category Custom --yes
splunkctl parsers create --sourcetype mysource \
    --category Custom --transforms my_extraction --yes
splunkctl parsers update mysource --category Operating_System --yes
splunkctl parsers delete mysource --yes
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
splunkctl users roles                   # list all roles
splunkctl users create --name newuser --password 'pass' \
    --roles user --email user@example.com --yes
splunkctl users update newuser --roles 'user,power' --yes
splunkctl users delete newuser --yes
```

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

```bash
splunkctl alerts list
splunkctl rules get 'Alert Rule Name'
splunkctl search run 'index=main error' --earliest -7d --limit 1000
```

### Audit detection coverage

```bash
splunkctl rules list --json | jq '[.[] | select(.is_scheduled == "1")]'
splunkctl rules list --json | jq '[.[] | select(.disabled == "1")]'
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
