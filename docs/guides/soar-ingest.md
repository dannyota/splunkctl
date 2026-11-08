<!-- summary: Turn Splunk search results into Splunk SOAR containers and artifacts with an idempotent, previewable ingest command. -->

# Ingest SIEM results into SOAR

When to use: you have Splunk search results (ES notables, firewall hits, a hunting query) and want them in SOAR as containers and CEF artifacts so playbooks can act on them, with the official CIM-to-CEF mapping, deduplication, and a preview before anything is sent.

## Prerequisites

- A Splunk profile that passes `splunkctl doctor` and SOAR credentials that pass `splunkctl soar test` (see [Configure](configure.md) and [Set up and check SOAR](soar.md)).
- A label that exists on the SOAR instance (`splunkctl soar meta labels`); the default is `events`.
- Either an SPL query (`--spl`) or the sid of a finished search job (`--sid`, from `splunkctl search jobs`); the two are mutually exclusive.

## Synopsis

```text
splunkctl soar ingest (--spl <SPL> | --sid <SID>) [--earliest TIME] [--latest TIME] [--app APP] [--label LABEL] [--severity NAME] [--sensitivity NAME] [--sdi-field FIELD] [--container-name TEXT] [--container-name-field FIELD] [--grouping] [--map CEF_KEY=SPLUNK_FIELD]... [--map-file FILE.yaml] [--include-unmapped] [--no-automation] [--yes]
```

Defaults: `--label events`, `--sensitivity amber`, `--sdi-field event_id`, severity derived from the row, one container per row.

## Workflow

### Preview an ingest

```bash
splunkctl soar ingest --spl '| makeresults count=2 | eval src="10.0.0.1"'
splunkctl soar ingest --spl 'index=firewall src=10.0.0.1' --earliest -24h
```

Expected result: the dry run shows the container count and artifacts per container, the active CIM-to-CEF mapping table (first 10 entries), and a sample CEF payload from the first result row. No data is sent to SOAR. The search runs through the same machinery as `splunkctl search run`; `--earliest`, `--latest`, and `--app` scope it.

### Apply the ingest

> **Safety:** Target is the SOAR host in the active profile, with results read from the Splunk host in the same profile. Impact: new containers and artifacts are created and playbooks fire on the last artifact of each container. Preview with `splunkctl soar ingest --spl 'index=firewall src=10.0.0.1' --earliest -24h`, apply by adding `--yes`, and verify with `splunkctl soar containers list --label events --since <today>`.

```bash
splunkctl soar ingest --spl '| makeresults count=2 | eval src="10.0.0.1"' --yes
splunkctl soar ingest --sid 1720000000.42 --yes
splunkctl soar ingest --spl 'index=firewall' --label notable --severity high --sensitivity green --yes
```

Expected result: one container per result row (or one container for all rows with `--grouping`), each with CEF artifacts, and a summary of containers and artifacts created and skipped.

### Control the field mapping

> **Safety:** Target is the SOAR host in the active profile. Impact: containers and artifacts are created with the mapped CEF keys. Preview by dropping `--yes` and reading the mapping table and sample CEF payload, apply by adding it back, and verify with `splunkctl soar artifacts list --container <CONTAINER_ID>`.

```bash
splunkctl soar ingest --spl 'index=firewall' --map sourceAddress=my_src --yes
splunkctl soar ingest --spl 'index=firewall' --map-file ~/.splunkctl/cim_cef_map.yaml --yes
splunkctl soar ingest --spl 'index=firewall' --include-unmapped --yes
```

Expected result: the built-in `CIM_CEF_MAP` mirrors the official Splunk SOAR Connector for Splunk mapping (with the upstream `butesIn` typo fixed to `bytesIn`). CEF keys get automatic `cef_types` from the built-in `CEF_CONTAINS_MAP` (for example `sourceAddress` becomes `["ip", "host name"]`), which makes artifact fields actionable as playbook inputs. `--map` overrides one key per flag; `--map-file` loads a YAML file:

```yaml
mappings:
  src: {cef: sourceAddress, contains: [ip]}
  custom_score: {cef: riskScore}
unmapped: drop   # or "pass" to keep unmapped fields as custom CEF keys
```

Fields not in the map are dropped by default. `--include-unmapped` (or `unmapped: pass`) passes them through as custom CEF keys; underscore-prefixed internal fields such as `_raw` and `_time` are always excluded.

### Group rows into one container

> **Safety:** Target is the SOAR host in the active profile. Impact: one container with every row as an artifact is created. Preview by dropping `--yes`, apply by adding it back, and verify with `splunkctl soar containers list --label events --since <today>`.

```bash
splunkctl soar ingest --spl 'index=firewall src=10.0.0.1' --grouping --yes
```

Expected result: a single container with one artifact per row instead of one container per row.

### Name containers and set severity

> **Safety:** Target is the SOAR host in the active profile. Impact: containers are created with the chosen names and severity, which drives SOAR queue sorting. Preview by dropping `--yes` and reading the container list in the dry run, apply by adding it back, and verify with `splunkctl soar containers list --severity high`.

```bash
splunkctl soar ingest --spl 'index=notable' --container-name-field rule_name --yes
splunkctl soar ingest --spl 'index=firewall' --container-name "Firewall sweep" --yes
splunkctl soar ingest --spl 'index=firewall' --severity high --yes
```

Expected result: the name is chosen in this order: `--container-name-field` (that row field's value), `--container-name` (a literal or template), the `rule_name` field (ES notable convention), then the fallback `"Splunk Log Entry on <_time>: <source>"`. Severity checks the row's `severity` first, then `urgency`, and defaults to `medium`; multivalue fields take the highest value, and `--severity` overrides:

| Splunk severity or urgency | SOAR severity |
|---|---|
| informational, low | low |
| medium | medium |
| high, critical | high |

### Rerun safely with deduplication

> **Safety:** Target is the SOAR host in the active profile. Impact: only rows whose SDI is new become containers or artifacts; changing `--sdi-field` can make every row look new and duplicate the queue. Preview by dropping `--yes` and reading the skipped counts, apply by adding it back, and verify with `splunkctl soar containers list --filter '_filter_source_data_identifier="<SDI>"'`.

```bash
splunkctl soar ingest --spl 'index=notable | head 10' --yes
splunkctl soar ingest --spl 'index=notable | head 10' --yes
splunkctl soar ingest --spl 'index=firewall' --sdi-field event_hash --yes
```

Expected result: the second run reports the existing containers and artifacts and skips creating them. The source data identifier (SDI) is the `event_id` field when present, otherwise a SHA-256 hash of the full row; `--sdi-field` picks another field. Containers are prechecked client-side with `_filter_source_data_identifier`, and the server-side fallback returns `existing_container_id`. Artifacts are prechecked client-side only, because the server does not deduplicate artifacts.

### Control playbook automation

> **Safety:** Target is the SOAR host in the active profile. Impact: with `--no-automation` no playbook fires for the new artifacts; without it the last artifact per container triggers active playbooks. Preview by dropping `--yes`, apply by adding it back, and verify with `splunkctl soar playbooks runs list --container <CONTAINER_ID>`.

```bash
splunkctl soar ingest --spl 'index=firewall' --no-automation --yes
```

Expected result: by default every artifact is created with `run_automation: false` except the last artifact actually created in each container, which gets `run_automation: true`, so playbooks fire once the container is fully populated. `--no-automation` suppresses automation on all artifacts.

### Ingest ES notables

> **Safety:** Target is the SOAR host in the active profile, reading notables from the Splunk host in the same profile. Impact: one container per notable with its context fields as CEF keys, and playbooks fire on each. Preview by dropping `--yes`, apply by adding it back, and verify with `splunkctl soar containers list --label events --since <today>`.

```bash
splunkctl soar ingest \
    --spl 'index=notable | head 10' \
    --include-unmapped --yes
```

Expected result: notables with their native fields: SDI from `event_id` (the default `--sdi-field`), the container name from `rule_name`, severity mapped from the notable's `severity` or `urgency`, and `--include-unmapped` preserving `event_id`, `risk_score`, `security_domain`, and other context fields as custom CEF keys for playbook use.

## Troubleshooting

- Usage error "No SOAR host configured": run `splunkctl config init --soar`.
- `confirmation_required` from the SIEM search: the SPL contains a write command; remove it, the ingest only reads results.
- `auth` or `connection` naming the Splunk host: the SIEM side failed; run `splunkctl doctor`. Naming the SOAR host: run `splunkctl soar test`.
- `not_found` on `--sid`: the job expired; rerun with `--spl`, or create a fresh job with `splunkctl search run ... --detach`.
- `http` error on container creation: the server rejected a field; check that `--label` exists (`splunkctl soar meta labels`) and `--severity` and `--sensitivity` are valid names (`splunkctl soar meta severities`).
- Everything is skipped on rerun: deduplication by SDI is working; change `--sdi-field` only if the rows are genuinely new.
- Playbooks did not fire: `--no-automation` was set, or the playbook's trigger and label do not match (see [Run playbooks](soar-playbooks.md)).

## See also

- [Run searches](search.md)
- [Triage ES notables](es.md)
- [Work SOAR incidents](soar-incidents.md)
- [Run playbooks](soar-playbooks.md)
- [Configure assets and monitor ingestion](soar-assets.md)
- [Command reference: soar](../commands/soar.md)
- [SIEM to SOAR field map](../design/soar-ingest-map.md), the rationale behind the built-in mapping
