<!-- summary: Manage source types, props, and transforms, and keep field extractions in YAML for review and deployment. -->

# Manage source types and extractions

When to use: you are onboarding a new data source and need a source type in `props.conf`, field extractions in `transforms.conf`, or want those stanzas exported to YAML so they can be reviewed and deployed to another instance.

## Prerequisites

- A Splunk account that can write to the target app (for example the `admin` role, or a role with write access to `search`).
- Source type names are case-sensitive; take the exact spelling from the data input configuration.
- For `import`: a YAML file produced by `parsers export` or written in the same shape.

## Synopsis

```text
splunkctl parsers sourcetypes [--filter SUBSTRING] [--limit N] [--offset N]
splunkctl parsers extractions [--sourcetype SUBSTRING] [--filter SUBSTRING] [--limit N] [--offset N]
splunkctl parsers get <SOURCETYPE> [--conf props|transforms] [--explicit] [--app APP]
splunkctl parsers create --sourcetype <NAME> [--category TEXT] [--transforms TEXT] [--yes]
splunkctl parsers update <SOURCETYPE> [--category TEXT] [--transforms TEXT] [--yes]
splunkctl parsers delete <SOURCETYPE> [--yes]
splunkctl parsers set <STANZA> <KEY=VALUE>... [--conf props|transforms] [--sharing user|app|global] [--create|--no-create] [--yes]
splunkctl parsers unset <STANZA> <KEY>... [--conf props|transforms] [--yes]
splunkctl parsers export --path <FILE.yml> [--conf props|transforms|all] [--filter SUBSTRING]
splunkctl parsers import --path <FILE.yml> [--yes]
splunkctl parsers reload [--conf props|transforms|all] [--yes]
```

## Workflow

### List source types and extractions

```bash
splunkctl parsers sourcetypes
splunkctl parsers sourcetypes --filter firewall
splunkctl parsers extractions
splunkctl parsers extractions --sourcetype firewall
```

Expected result: one row per `props.conf` stanza with its `category`, or one row per `transforms.conf` stanza. `--filter` is a case-insensitive name substring; `--limit` and `--offset` apply after filtering.

### Inspect one source type

```bash
splunkctl parsers get syslog
splunkctl parsers get syslog --explicit --app search
splunkctl parsers get my_extraction --conf transforms
splunkctl parsers get mysource --json | jq .
```

Expected result: the merged view of the stanza by default; `--explicit` shows only the keys set in that stanza within `--app` (default `search`). Use `--json` output to diff a source type between dev and prod.

### Audit every extraction

```bash
splunkctl parsers extractions --json > extractions.json
```

Expected result: a JSON array of every `transforms.conf` stanza with its keys, ready to diff against another instance.

### Create a source type

> **Safety:** Target is the Splunk host in the active profile. Impact: a new `props.conf` stanza that the indexer uses for events arriving with that source type. Preview with `splunkctl parsers create --sourcetype firewall_appliance_v2 --category Network_Security`, apply by adding `--yes`, and verify with `splunkctl parsers get firewall_appliance_v2`.

```bash
splunkctl parsers create --sourcetype firewall_appliance_v2 --category Network_Security
splunkctl parsers create --sourcetype firewall_appliance_v2 --category Network_Security --yes
splunkctl parsers create --sourcetype mysource --category Custom --transforms my_extraction --yes
splunkctl parsers get firewall_appliance_v2
```

Expected result: the stanza exists with the category and, when given, a `TRANSFORMS` reference to the extraction.

### Set or clear parsing keys

> **Safety:** Target is the Splunk host in the active profile. Impact: parsing keys such as `TIME_FORMAT` or `LINE_BREAKER` change how new events are broken and parsed; a wrong `LINE_BREAKER` merges or splits events. Preview with `splunkctl parsers set mysource TIME_FORMAT=%Y-%m-%dT%H:%M:%S`, apply by adding `--yes`, and verify with `splunkctl parsers get mysource --explicit`.

```bash
splunkctl parsers set mysource TIME_FORMAT=%Y-%m-%dT%H:%M:%S SHOULD_LINEMERGE=false --yes
splunkctl parsers set my_extraction 'REGEX=user=(?<user>\S+)' 'FORMAT=user::$1' --conf transforms --yes
splunkctl parsers set mysource EXTRACT-ip='(?<ip>\d+\.\d+\.\d+\.\d+)' --sharing global --yes
splunkctl parsers unset mysource SHOULD_LINEMERGE --yes
```

Expected result: the keys appear in `get --explicit`. New stanzas are created when missing (`--no-create` turns that off) and are app-shared by default, because user-private parsing stanzas do not apply at index time. The REST API cannot remove a key, so `unset` sets it to the empty string, which disables most parsing keys.

### Update or delete a source type

> **Safety:** Target is the Splunk host in the active profile. Impact: `update` changes the category or transforms reference; `delete` removes the stanza and events for that source type fall back to default parsing. Preview with `splunkctl parsers delete mysource`, apply by adding `--yes`, and verify with `splunkctl parsers sourcetypes --filter mysource`.

```bash
splunkctl parsers update mysource --category Operating_System --yes
splunkctl parsers delete mysource
splunkctl parsers delete mysource --yes
```

Export the stanza first (next step) so you can import it again if needed.

### Export stanzas to YAML

```bash
splunkctl parsers export --path parsers.yml
splunkctl parsers export --path props.yml --conf props --filter firewall
```

Expected result: a YAML file of explicitly set keys only (merged defaults are left out), suitable for version control.

### Import stanzas from YAML

> **Safety:** Target is the Splunk host in the active profile. Impact: stanzas in the file are created or updated; nothing is deleted. Preview with `splunkctl parsers import --path parsers.yml` and read the per-stanza create, update, or unchanged lines with their key-level diffs, apply by adding `--yes`, and verify with `splunkctl parsers get <SOURCETYPE> --explicit`.

```bash
splunkctl parsers import --path parsers.yml
splunkctl parsers import --path parsers.yml --yes
```

Expected result: each stanza reports `create`, `update`, or `unchanged`. The command exits non-zero when any stanza is skipped or fails, so CI cannot silently pass a broken file.

### Reload props and transforms

> **Safety:** Target is the Splunk host in the active profile. Impact: splunkd re-reads `props.conf` and `transforms.conf`, so index-time changes start applying to new data. Preview with `splunkctl parsers reload`, apply with `splunkctl parsers reload --yes`, and verify by searching a few new events for the expected fields.

```bash
splunkctl parsers reload --yes
splunkctl parsers reload --conf transforms --yes
```

Expected result: index-time keys take effect for data indexed after the reload. Already indexed events are not reparsed.

## Troubleshooting

- `not_found` on `get`, `update`, or `delete`: the name is case-sensitive; copy it from `splunkctl parsers sourcetypes --filter <part>`.
- `permission` on `create`, `set`, or `import`: the account cannot write to the app; use a role with write access, or pass `--sharing app` with an app you own.
- `import` exits 1 while most stanzas applied: at least one stanza was skipped or failed; fix the reported stanza and rerun, the others are idempotent.
- A new `TIME_FORMAT` or `LINE_BREAKER` has no effect: run `splunkctl parsers reload --yes`, then check only events indexed after the reload.
- An `EXTRACT-*` key set by a user-private stanza never fires at index time: promote it with `--sharing app` or `--sharing global`.

## See also

- [Manage configuration as code](state.md), which pulls and pushes `parsers.yml`
- [Edit any conf file](conf.md)
- [Manage lookups](lookups.md)
- [Run searches](search.md)
- [Command reference: parsers](../commands/parsers.md)
