# Parsers

Manage source types (`props.conf`) and field extractions
(`transforms.conf`) via the REST API.

## Why this matters

Every new data source that lands in Splunk needs a source type to tell
the indexer how to break events and a set of field extractions to make
the data searchable. When you onboard a custom appliance, a SaaS
webhook, or a home-grown app, the parser config is what turns raw text
into structured, queryable fields. Managing this as code means
repeatable onboarding across environments and auditable change history.

## Commands

```bash
splunkctl parsers sourcetypes                 # list source types
splunkctl parsers get syslog                  # full sourcetype config
splunkctl parsers extractions                 # list field extractions
splunkctl parsers create --sourcetype mysource \
    --category Custom --yes                   # create sourcetype
splunkctl parsers create --sourcetype mysource \
    --category Custom \
    --transforms my_extraction --yes          # with extraction
splunkctl parsers update mysource \
    --category Operating_System --yes         # update category
splunkctl parsers delete mysource --yes       # delete sourcetype
```

## Recipes

### Onboard a custom log source

Create a source type for a new appliance and verify it exists:

```bash
splunkctl parsers create --sourcetype firewall_appliance_v2 \
    --category Network_Security --yes
splunkctl parsers get firewall_appliance_v2
```

### Audit all field extractions

Dump every extraction to JSON for review or diffing between instances:

```bash
splunkctl parsers extractions --json \
  | jq '[.[] | {name, type, stanza}]' > extractions.json
```

### Check a source type before editing

Preview the full config to confirm the current state:

```bash
splunkctl parsers get mysource --json | jq .
```

## Tips

- Changes to `props.conf` / `transforms.conf` may require a Splunk
  restart to take effect.
- Use `--json` output to diff parser configs across dev and prod
  instances.
- Source type names are case-sensitive. Match the exact casing from the
  data input configuration.
