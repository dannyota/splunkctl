# Alerts

Fired alerts are the SOC's incoming work queue. During an incident, you
need to see what triggered, when, and at what severity. During planned
maintenance, you need to suppress noisy rules before they flood the
on-call channel. After the fact, auditors ask which alerts fired and
which were suppressed. These commands cover all three workflows.

## Commands

```bash
splunkctl alerts list                         # list fired alerts
splunkctl alerts get 'Alert Name'             # details for one alert group
splunkctl alerts actions                      # list alert action types
splunkctl alerts suppress 'Alert Name' \
    --duration 7200 --yes                     # suppress for 2 hours
```

## Triage during an incident

List all currently fired alerts to see what the environment is telling you.
Output includes name, trigger count, triggered time, and severity.

```bash
splunkctl alerts list
splunkctl alerts get 'Brute Force Login Attempts'
```

## Check alert action types

See which action types (email, webhook, script, etc.) are configured on
the instance. Useful before creating or modifying saved searches that
fire alerts.

```bash
splunkctl alerts actions
```

## Suppress during a maintenance window

Suppression is guarded -- dry-run by default. The first command below
previews the change; the second applies it. Duration is in seconds.

```bash
splunkctl alerts suppress 'Brute Force Login Attempts' --duration 7200
splunkctl alerts suppress 'Brute Force Login Attempts' --duration 7200 --yes
```

Suppress multiple alerts in a loop during a planned outage:

```bash
for rule in 'Brute Force Login Attempts' 'Failed VPN Auth' 'DNS Exfil'; do
  splunkctl alerts suppress "$rule" --duration 14400 --yes
done
```

## JSON output for scripts and agents

Pass `--json` to get structured output suitable for piping into `jq`,
feeding into an LLM agent, or storing as audit evidence.

```bash
splunkctl alerts list --json                          # all fired alerts
splunkctl alerts list --json | jq '.[] | select(.severity >= 6)'
splunkctl alerts get 'Brute Force Login Attempts' --json > alert_detail.json
```

An LLM agent can consume the JSON directly to decide next steps --
for example, correlating fired alerts with a change window calendar
or auto-filing tickets for high-severity triggers.

## Options

| Flag | Applies to | Description |
|------|-----------|-------------|
| `--duration` | `suppress` | Suppression length in seconds (default 3600) |
| `--json` | all | Force JSON output regardless of TTY |
| `--format` | all | Output format: `table`, `json`, `csv`, `jsonl` |
| `--yes` | `suppress` | Apply the mutation (skip dry-run preview) |
