<!-- summary: Look up indicators of compromise across Splunk SOAR and manage evidence items on containers. -->

# Look up indicators and evidence

When to use: you have an IP, domain, hash, or URL and want to know where SOAR has seen it before, or you are building a case and need to tag artifacts, notes, or action runs on a container as formal evidence.

## Prerequisites

- SOAR credentials in the active profile and a passing `splunkctl soar test` (see [Set up and check SOAR](soar.md)).
- For the `indicators` commands (`list`, `get`, `pivot`, `stats`): the `use_indicators` feature flag enabled on the instance. It is off by default on new installs; enable it in Administration > Product Settings > Feature Toggles, or `POST /rest/feature_flag` with `name='use_indicators'` and `value=true`.
- Username and password credentials for `evidence remove`; SOAR refuses automation tokens on DELETE.
- The `evidence` commands work regardless of the indicators flag.

## Synopsis

```text
splunkctl soar indicators list [--type ip|domain|hash|url|email|file|process|vault_id] [--limit N]
splunkctl soar indicators get <VALUE>
splunkctl soar indicators pivot <VALUE>
splunkctl soar indicators stats

splunkctl soar evidence list --container <CONTAINER_ID>
splunkctl soar evidence add <CONTAINER_ID> --object <artifact|note|action_run> --id <OBJECT_ID> [--yes]
splunkctl soar evidence remove <EVIDENCE_ID> [--yes]
```

## Workflow

### Confirm the indicators feature is on

```bash
splunkctl soar indicators stats
```

Expected result: aggregated breakdowns by type and severity (`indicator_stats_type` and `indicator_stats_severity`). Every indicator command first checks `/rest/feature_flag` for `use_indicators=true`; if the flag is off or the endpoint is unreachable the command exits 1 with:

```text
Error: Indicators feature is disabled on this SOAR instance.
Enable it in Administration > Product Settings > Feature Toggles,
or POST /rest/feature_flag with name='use_indicators' and value=true.
```

### List indicators

```bash
splunkctl soar indicators list
splunkctl soar indicators list --type ip
splunkctl soar indicators list --limit 20
splunkctl soar indicators list --json
```

Expected result: one row per indicator from `GET /rest/indicator`, optionally filtered to one `--type` (`ip`, `domain`, `hash`, `url`, `email`, `file`, `process`, `vault_id`).

### Look up one value

```bash
splunkctl soar indicators get 8.8.8.8
splunkctl soar indicators get evil.com --json
```

Expected result: the indicator record for that exact value, through `GET /rest/indicator_by_value`.

### Pivot to every container that saw it

```bash
splunkctl soar indicators pivot evil.com
splunkctl soar indicators pivot 8.8.8.8 --json
```

Expected result: every container where the IOC has appeared (`GET /rest/indicator_common_container`), answering "where else have we seen this IP?" for cross-case correlation.

### List evidence on a container

```bash
splunkctl soar evidence list --container 100
splunkctl soar evidence list --container 100 --json
```

Expected result: the evidence items (`GET /rest/evidence`) linking artifacts, notes, or action runs to the container as formally tagged proof. `--container` is required.

### Add evidence

> **Safety:** Target is the SOAR host in the active profile; the dry-run banner shows the host and the payload. Impact: the object is tagged as evidence on the container and appears in case reports. Preview with `splunkctl soar evidence add 100 --object artifact --id 42`, apply by adding `--yes`, and verify with `splunkctl soar evidence list --container 100`.

```bash
splunkctl soar evidence add 100 --object artifact --id 42
splunkctl soar evidence add 100 --object artifact --id 42 --yes
splunkctl soar evidence add 100 --object note --id 7 --yes
splunkctl soar evidence add 100 --object action_run --id 999 --yes
```

Expected result: a `POST /rest/evidence` and a new evidence id. `--object` accepts `artifact`, `note`, or `action_run`; `--id` is that object's id, not the container id.

### Remove evidence

> **Safety:** Target is the SOAR host in the active profile. Impact: the evidence tag is removed; the underlying artifact, note, or action run stays. Preview with `splunkctl soar evidence remove 5`, apply by adding `--yes`, and verify with `splunkctl soar evidence list --container 100`.

```bash
splunkctl soar evidence remove 5
splunkctl soar evidence remove 5 --yes
```

Expected result: a `DELETE /rest/evidence/<id>`, which needs username and password credentials; a token-only profile gets a clear `auth` error.

## Troubleshooting

- "Indicators feature is disabled" (exit 1): enable `use_indicators` as shown above, then rerun; the check runs before every indicators command.
- `not_found` on `indicators get`: the value must match exactly (no wildcards, no trailing dot on domains); list with `--type` to find the stored form.
- `auth` on `evidence remove` while `add` works: the profile is token-only; add a username and password with `splunkctl config init --soar`.
- `not_found` on `evidence add`: `--id` must be an existing artifact, note, or action run id, and it must belong to the container you name.
- `evidence remove` needs the evidence id, not the artifact id: take it from the `id` column of `evidence list`.

## See also

- [Work SOAR incidents](soar-incidents.md)
- [Manage cases and workbooks](soar-cases.md)
- [Run actions](soar-actions.md)
- [Set up and check SOAR](soar.md)
- [Command reference: soar](../commands/soar.md)
