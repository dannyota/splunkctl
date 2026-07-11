# SOAR Indicators & Evidence

IOC indicator lookups and evidence management on Splunk SOAR.

## Prerequisites

SOAR credentials configured (see `splunkctl config init --soar`).

Indicator commands (`list`, `get`, `pivot`, `stats`) require the
`use_indicators` feature flag to be enabled on the SOAR instance. When
the flag is off (the default on new installs), commands exit 1 with an
actionable message explaining how to enable it.

Evidence commands (`list`, `add`, `remove`) work regardless of the
indicators flag.

## Indicators

### Feature flag detection

Every indicator command checks `/rest/feature_flag` for
`use_indicators=true` before proceeding. If the flag is off or the
endpoint is unreachable, you get:

```
Error: Indicators feature is disabled on this SOAR instance.
Enable it in Administration > Product Settings > Feature Toggles,
or POST /rest/feature_flag with name='use_indicators' and value=true.
```

### List indicators

```bash
splunkctl soar indicators list                  # all indicators
splunkctl soar indicators list --type ip        # filter by type
splunkctl soar indicators list --limit 20       # page size
splunkctl soar indicators list --json           # machine-readable
```

Supported `--type` values: `ip`, `domain`, `hash`, `url`, `email`,
`file`, `process`, `vault_id`.

### Get indicator by value

```bash
splunkctl soar indicators get 8.8.8.8
splunkctl soar indicators get evil.com --json
```

Looks up an indicator by its exact value via `indicator_by_value`.

### Pivot — common containers

```bash
splunkctl soar indicators pivot evil.com
splunkctl soar indicators pivot 8.8.8.8 --json
```

Shows every container where the IOC has appeared
(`indicator_common_container`). Useful for cross-case correlation:
"where else have we seen this IP?"

### Indicator stats

```bash
splunkctl soar indicators stats
splunkctl soar indicators stats --json
```

Aggregated breakdowns from `indicator_stats_type` and
`indicator_stats_severity`.

## Evidence

Evidence links artifacts, notes, or action runs to a container as
formally tagged proof items.

### List evidence

```bash
splunkctl soar evidence list --container 100
splunkctl soar evidence list --container 100 --json
```

`--container` is required.

### Add evidence (guarded)

```bash
# Dry-run preview (default):
splunkctl soar evidence add 100 --object artifact --id 42

# Apply:
splunkctl soar evidence add 100 --object artifact --id 42 --yes
```

Supported `--object` types: `artifact`, `note`, `action_run`.

The guard banner shows the SOAR host and previews the payload before
any mutation. Pass `--yes` to apply.

### Remove evidence (guarded)

```bash
splunkctl soar evidence remove 5              # dry-run
splunkctl soar evidence remove 5 --yes        # apply (Basic auth)
```

DELETE requires Basic auth credentials (SOAR refuses automation tokens
on DELETE). If your profile only has a token, the CLI will error with a
clear auth message.

## API endpoints

| Command | REST endpoint |
|---|---|
| `indicators list` | `GET /rest/indicator` |
| `indicators get` | `GET /rest/indicator_by_value` |
| `indicators pivot` | `GET /rest/indicator_common_container` |
| `indicators stats` | `GET /rest/indicator_stats_type`, `indicator_stats_severity` |
| `evidence list` | `GET /rest/evidence` |
| `evidence add` | `POST /rest/evidence` |
| `evidence remove` | `DELETE /rest/evidence/<id>` |
