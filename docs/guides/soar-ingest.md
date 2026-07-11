# SOAR ingest

Ingest SIEM search results into Splunk SOAR as containers and artifacts,
using the official CIM-to-CEF field mapping and connector conventions.

## Commands

```bash
# Dry-run (default) — preview containers, mapping table, sample CEF
splunkctl soar ingest --spl '| makeresults count=2 | eval src="10.0.0.1"'

# Apply
splunkctl soar ingest --spl '| makeresults count=2 | eval src="10.0.0.1"' --yes

# From an existing search job
splunkctl soar ingest --sid 1720000000.42 --yes

# Custom label, severity, sensitivity
splunkctl soar ingest --spl 'index=firewall' \
    --label notable --severity high --sensitivity green --yes
```

## SIEM search integration

Uses the same SIEM search machinery as `splunkctl search run`. Provide
`--spl` (runs a new search) or `--sid` (fetches results from an existing
job). Time bounds via `--earliest` / `--latest`; app context via `--app`.

## Field mapping (CIM to CEF)

The built-in `CIM_CEF_MAP` mirrors the official Splunk SOAR Connector for
Splunk mapping (with the upstream `butesIn` typo fixed to `bytesIn`).
CEF keys get automatic `cef_types` from the built-in `CEF_CONTAINS_MAP`
(e.g. `sourceAddress` -> `["ip", "host name"]`), making artifact fields
actionable as playbook inputs.

### Override mappings

Per-field overrides:

```bash
splunkctl soar ingest --spl '...' --map sourceAddress=my_src --yes
```

YAML mapping file:

```bash
splunkctl soar ingest --spl '...' --map-file ~/.splunkctl/cim_cef_map.yaml --yes
```

Format:

```yaml
mappings:
  src: {cef: sourceAddress, contains: [ip]}
  custom_score: {cef: riskScore}
unmapped: drop   # or "pass" to keep unmapped fields as custom CEF keys
```

### Include unmapped fields

By default, fields not in the CIM map are dropped. Use `--include-unmapped`
to pass them through as custom CEF keys (underscore-prefixed internal
fields like `_raw`, `_time` are always excluded).

## Grouping

Default: one container per result row. Use `--grouping` to group all rows
into a single container with multiple artifacts.

```bash
splunkctl soar ingest --spl 'index=firewall src=10.0.0.1' --grouping --yes
```

## Container naming

Priority:
1. `--container-name-field` — use that row field's value.
2. `--container-name` — literal name or template.
3. `rule_name` field (ES notable convention).
4. Fallback: `"Splunk Log Entry on <_time>: <source>"`.

## Severity

Checks `severity` first, then `urgency`; defaults to `medium`. Multivalue
fields take the highest value. Override with `--severity`.

| Splunk severity/urgency | SOAR severity |
|---|---|
| informational, low | low |
| medium | medium |
| high, critical | high |

## Dedup (source_data_identifier)

SDI field defaults to `event_id` (if present in the row); otherwise a
SHA-256 hash of the full row. Override with `--sdi-field`.

- **Container-level**: client-side precheck via
  `_filter_source_data_identifier`; server-side fallback returns
  `existing_container_id`.
- **Artifact-level**: client-side precheck only (server does not dedup
  artifacts).

Re-running the same ingest reports existing containers/artifacts and skips
creation.

## Automation batching

All artifacts are created with `run_automation: false` except the last
artifact in each container, which gets `run_automation: true` (playbooks
fire once the container is fully populated). Use `--no-automation` to
suppress automation on all artifacts.

## Notable events (ES)

Ingest ES notables with their native fields:

```bash
splunkctl soar ingest \
    --spl 'index=notable | head 10' \
    --include-unmapped --yes
```

- SDI = `event_id` (default `--sdi-field`).
- Container name from `rule_name`.
- Severity mapped from the notable's `severity` / `urgency`.
- `--include-unmapped` preserves `event_id`, `risk_score`,
  `security_domain`, and other context fields as custom CEF keys for
  playbook use.

## Dry-run preview

Without `--yes`, the command shows:

- Container count and artifacts per container.
- Active CIM-to-CEF mapping table (first 10 entries).
- Sample CEF payload from the first result row.

No data is sent to SOAR in dry-run mode.

## Flags reference

| Flag | Default | Description |
|---|---|---|
| `--spl` | — | SPL search to run on SIEM |
| `--sid` | — | Existing SIEM job SID |
| `--label` | `events` | Container label |
| `--severity` | auto | Override SOAR severity |
| `--sensitivity` | `amber` | Container sensitivity/TLP |
| `--sdi-field` | `event_id` | Row field for SDI (else row hash) |
| `--container-name` | — | Container name (literal or template) |
| `--container-name-field` | — | Row field for container name |
| `--grouping` | off | Group all rows into one container |
| `--map` | — | CEF=splunk_field override (repeatable) |
| `--map-file` | — | YAML custom mapping file |
| `--include-unmapped` | off | Pass unmapped fields as custom CEF |
| `--no-automation` | off | Suppress playbook automation |
| `--earliest` | — | SIEM search earliest time |
| `--latest` | — | SIEM search latest time |
| `--app` | — | SIEM app context |
