<!-- summary: List, inspect, enable, and disable Enterprise Security correlation searches, and upload or remove threat-intelligence items. -->

# Manage ES correlations and threat intel

When to use: you maintain the detections that generate Enterprise Security notables and the threat-intelligence collections they match against, and you want to enable, disable, or inspect them without opening Splunk Web.

## Prerequisites

- Splunk Enterprise Security installed on the target instance. Every `es` subcommand checks for the `SplunkEnterpriseSecuritySuite` app and exits 1 with a `not_found` error when it is missing.
- A Splunk account that can read and edit saved searches in the `SplunkEnterpriseSecuritySuite` app and call the `/services/data/threat_intel/*` endpoints.
- Live verification against a real ES instance is still pending for this group; the logic is unit-tested against a mocked REST layer. Test on a non-production ES instance first.

## Synopsis

```text
splunkctl es correlations list [--enabled | --disabled] [--security-domain NAME]
splunkctl es correlations get <NAME>
splunkctl es correlations enable <NAMES>... [--yes]
splunkctl es correlations disable <NAMES>... [--yes]
splunkctl es threat-intel list [--type COLLECTION] [--limit N]
splunkctl es threat-intel upload --type <COLLECTION> --file <FILE> [--yes]
splunkctl es threat-intel delete <KEY> [--yes]
```

Collection types: `ip_intel`, `domain_intel`, `file_intel`, `email_intel`, `http_intel`, `certificate_intel`, `registry_intel`, `service_intel`, `user_intel`, `process_intel`.

## Workflow

### Review correlation searches

```bash
splunkctl es correlations list
splunkctl es correlations list --enabled
splunkctl es correlations list --disabled
splunkctl es correlations list --security-domain access
splunkctl es correlations get "Brute Force Access Behavior"
```

Correlation searches are saved searches scoped to the `SplunkEnterpriseSecuritySuite` app; the CLI fetches across all owners. `list` shows `name`, `security_domain`, `severity`, `enabled`, `cron_schedule`, and `next_scheduled_time`. `get` adds `search`, `description`, `is_scheduled`, `actions`, `dispatch.earliest_time`, `dispatch.latest_time`, `app`, `owner`, and `sharing`. The security domain is read from `action.correlationsearch.label`, falling back to `security_domain`.

### Enable or disable correlation searches

> **Safety:** Target is the Splunk host in the active profile. Impact: the named searches start or stop generating notables on their next schedule. Preview with `splunkctl es correlations disable "DNS Exfil"`, apply with `splunkctl es correlations disable "DNS Exfil" --yes`, and verify with `splunkctl es correlations get "DNS Exfil"` (check `enabled`).

```bash
splunkctl es correlations enable "Brute Force Access Behavior"
splunkctl es correlations enable "Rule A" "Rule B" --yes
splunkctl es correlations disable "DNS Exfil" --yes
```

### List threat-intelligence items

```bash
splunkctl es threat-intel list
splunkctl es threat-intel list --type ip_intel
splunkctl es threat-intel list --type domain_intel --limit 25
```

Reads `/services/data/threat_intel/item`, up to 100 rows by default. The `name` column is the key you pass to `delete`.

### Upload indicators

> **Safety:** Target is the Splunk host in the active profile. Impact: every row in the file becomes a threat-intel item in the chosen collection and can match against live events. Preview with `splunkctl es threat-intel upload --type ip_intel --file iocs.csv`, apply by adding `--yes`, and verify with `splunkctl es threat-intel list --type ip_intel`.

```bash
splunkctl es threat-intel upload --type ip_intel --file iocs.csv
splunkctl es threat-intel upload --type ip_intel --file iocs.csv --yes
```

`--file` takes a local CSV or JSON file. A CSV needs a header row that matches the fields of the collection type, for example `ip`, `description`, and `weight` for `ip_intel`:

```csv
ip,description,weight
203.0.113.10,known C2,80
```

### Delete an indicator

> **Safety:** Target is the Splunk host in the active profile. Impact: the item stops matching. Preview with `splunkctl es threat-intel delete <KEY>`, apply with `splunkctl es threat-intel delete <KEY> --yes`, and verify with `splunkctl es threat-intel list --type <COLLECTION>`.

```bash
splunkctl es threat-intel delete <KEY> --yes
```

`KEY` is the `name` value from `threat-intel list`.

## Troubleshooting

- `{"error": {"kind": "not_found", ...}}` naming `SplunkEnterpriseSecuritySuite`: ES is not installed or not visible to this account.
- A correlation search is not listed: it may be owned by another app; `es correlations` only covers the ES app. Use `splunkctl rules list` for other saved searches.
- Upload is accepted but items do not appear: check that the CSV header matches the collection's field names.

## See also

- [Triage ES notables](es.md)
- [Manage detection rules](rules.md)
- [Manage lookups](lookups.md)
- [Command reference: es](../commands/es.md)
