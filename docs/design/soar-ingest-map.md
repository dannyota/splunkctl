# SIEM → SOAR ingest conventions

Field-mapping source of truth for `splunkctl soar ingest` (PLAN.md task
P1). Derived 2026-07-11 from the official ecosystem so the CLI matches
convention instead of inventing mappings:

- **Splunk SOAR Connector for Splunk** — `CIM_CEF_MAP` /
  `SPLUNK_SEVERITY_MAP` in
  github.com/splunk-soar-connectors/splunk `src/splunk_consts.py`, and
  ingestion logic in `src/actions/on_poll.py` (v3.0.3).
- **Splunk App for SOAR Export** (Splunkbase 3411) docs — global field
  mappings, grouping, `sendalert sendtophantom` params, adaptive-response
  notable forwarding.
- ES notable field reference (dev.splunk.com) and urgency matrix.

## CIM → CEF map (ship as the built-in default)

| CIM field | CEF key | contains |
|---|---|---|
| action, action_name | act | — |
| app | app | — |
| bytes_in | bytesIn | — |
| bytes_out | bytesOut | — |
| category | cat | — |
| dest | destinationAddress | ip, host name |
| dest_ip | destinationAddress | ip |
| dest_mac | destinationMacAddress | mac address |
| dest_nt_domain | destinationNtDomain | domain |
| dest_port | destinationPort | port |
| dest_translated_ip | destinationTranslatedAddress | ip |
| dest_translated_port | destinationTranslatedPort | port |
| direction | deviceDirection | — |
| dns | destinationDnsDomain | domain |
| dvc | dvc | ip, host name |
| dvc_ip | deviceAddress | ip |
| dvc_mac | deviceMacAddress | mac address |
| file_create_time | fileCreateTime | — |
| file_hash | fileHash | hash |
| file_modify_time | fileModificationTime | — |
| file_name | fileName | file name |
| file_path | filePath | file path |
| file_size | fileSize | — |
| message | message | — |
| protocol, transport | transportProtocol | — |
| request_payload | request | — |
| request_payload_type | requestMethod | — |
| src | sourceAddress | ip, host name |
| src_dns | sourceDnsDomain | domain |
| src_ip | sourceAddress | ip |
| src_mac | sourceMacAddress | mac address |
| src_nt_domain | sourceNtDomain | domain |
| src_port | sourcePort | port |
| src_translated_ip | sourceTranslatedAddress | ip |
| src_translated_port | sourceTranslatedPort | port |
| src_user | sourceUserId | user name |
| url | requestURL | url |
| user | destinationUserName | user name |
| user_id | destinationUserId | user name |

The upstream connector has a `butesIn` typo for `bytes_in` — ship the
corrected `bytesIn`.

## Severity mapping

Check `severity` first, then `urgency`, default `medium`; multivalue →
highest wins (critical > high > medium > low > informational).

| Splunk severity/urgency | SOAR severity |
|---|---|
| informational, low | low |
| medium | medium |
| high, critical | high |

## Dedup (source_data_identifier)

- If `event_id` exists (ES notables), use it as the SDI — mirrors the
  connector's `use_event_id_sdi`.
- Otherwise hash the full result row (connector uses MD5, SHA256 under
  FIPS).
- Container-level SDI dedup is server-side (`existing_container_id`);
  **artifact dedup is NOT** (live-verified) — the CLI prechecks with
  `_filter_source_data_identifier` before posting artifacts.

## Grouping & naming conventions (official app behavior)

- Default: **one container per result row** (connector behavior);
  `--grouping` = all rows into one container with N artifacts
  (`param.grouping=1` equivalent).
- Container name: `"<rule_name|search name>: <field values>"`; connector
  fallback `"Splunk Log Entry on <_time>: <source>"`. Scheduled-search
  alerts use the saved-search name.
- Label default `"events"`; custom labels must pre-exist on SOAR
  (creation is UI-only). Whether `"notable"` exists by default is
  *(unverified)* — feature-detect via `/rest/container_options`.
- Sensitivity default TLP `amber` (official app default).
- Artifact name: `search_name` if present, else `"Field Values"`
  (connector convention).

## run_automation batching

All artifacts `run_automation: false` except the **last** one `true`
(playbooks fire once the container is fully populated). `--no-automation`
parks everything false.

## Notable-specific handling

Notables carry `event_id`, `rule_name`, `severity`, `urgency` (severity ×
asset-priority matrix), `security_domain`, `risk_score`, `owner`,
`status`, `orig_sid`/`orig_rid`, drilldowns. Recommendations:

1. SDI = `event_id`.
2. Container name from `rule_name`.
3. Severity from `urgency` through the map above.
4. Preserve `event_id`, `orig_sid`, `orig_rid`, `security_domain`,
   `risk_score` as CEF/custom fields for playbook context.
5. Lantern warns against `sendtophantom` from correlation searches (no
   notable↔container link) — the CLI ingests from `index=notable` search
   results instead, which keeps `event_id` and sidesteps that limitation.

## Contains types

`cef_types` maps CEF key → list of contains types
(`{"sourceAddress": ["ip"]}`), which is what makes artifact fields
actionable as playbook/action inputs. Ship the contains column above as
the built-in `CEF_CONTAINS_MAP`; the authoritative per-instance list is
`GET /rest/cef` (150 entries) + `GET /rest/cef_metadata`.

## Mapping-file format (user overrides)

```yaml
# --map-file ~/.splunkctl/cim_cef_map.yaml
mappings:
  src: {cef: sourceAddress, contains: [ip]}
  custom_score: {cef: riskScore}
unmapped: drop   # or "pass" -> keep as custom CEF keys
```

`--map cef=splunk_field` overrides single entries without a file.
