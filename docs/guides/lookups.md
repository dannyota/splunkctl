# Lookups

Lookups turn raw events into actionable intelligence. SecOps teams use
them for threat intel enrichment (IoC feeds correlated at search time),
asset/identity lists (mapping IPs to owners for triage), and GeoIP
databases (flagging logins from unexpected regions). Keeping these tables
current is the difference between a detection that fires and one that
misses.

## Commands

```bash
splunkctl lookups list                    # list lookup files
splunkctl lookups list --app search       # filter by app
splunkctl lookups get <name>              # get lookup metadata
splunkctl lookups upload <name> --file data.csv --app search --yes
splunkctl lookups update <name> --file updated.csv --app search --yes
splunkctl lookups download <name> --app search
splunkctl lookups download <name> --app search --out local.csv
splunkctl lookups delete <name> --app search --yes

splunkctl lookups define <defname> --file <file.csv> --yes       # transforms.conf
splunkctl lookups define <defname> --collection <coll> --yes     # kvstore-backed
splunkctl lookups auto <defname> --sourcetype <st> \
    --input <field> --output <field> --yes                       # props.conf LOOKUP-*
splunkctl lookups definitions                                    # list transforms.conf lookup stanzas
```

## Lookup definitions & automatic lookups

Uploading a CSV makes a table file that exists on the server, but Splunk
doesn't know it's a *lookup* until two more things are wired up:

1. A **lookup definition** (`transforms.conf`) binds a name to the table
   file (or, for a KV store collection, to `external_type=kvstore` +
   `collection=<name>`) -- this is what `| lookup <defname> ...` and
   `| inputlookup <defname>` reference.
2. An **automatic lookup** (`props.conf` `LOOKUP-*`) wires that
   definition onto a sourcetype so every matching event gets enriched
   at search time, with no `| lookup` needed in the SPL at all.

`lookups define` writes the first; `lookups auto` writes the second.
Both are guarded (dry-run by default, `--yes` to apply) and both
delegate the actual conf write to the same `conf_ops` core `conf`/
`parsers`/`macros` use -- there's exactly one implementation of the SDK
plumbing.

```bash
# 1. Define: bind a name to the uploaded table
splunkctl lookups define threat_intel --file threat_indicators.csv --yes

# KV store collection instead of a table file (G3-created collections
# aren't queryable via `| inputlookup` until they have a definition):
splunkctl lookups define asset_intel --collection assets --yes

# Optional tuning: how strict the match is, and what to do when it misses
splunkctl lookups define threat_intel --file threat_indicators.csv \
    --max-matches 1 --case-sensitive --default-match unknown --yes

# 2. Auto: wire the definition onto a sourcetype
splunkctl lookups auto threat_intel --sourcetype firewall_logs \
    --input dest_ip:ip --output threat_level --output threat_category --yes

# 3. Enrich: events of that sourcetype now carry threat_level/
# threat_category automatically, no `| lookup` required
splunkctl search oneshot 'sourcetype=firewall_logs | table dest_ip threat_level threat_category'

# Read side: what lookup definitions already exist
splunkctl lookups definitions
splunkctl lookups definitions --app SA-ThreatIntelligence
```

`--input`/`--output` are repeatable (at least one of each is required,
else a usage error/exit 2) and take an optional `FIELD:RENAME` form:
`--input` is `event_field[:lookup_table_field]` (the field you already
have, then the lookup table's column name only if it differs);
`--output` is `lookup_table_field[:event_field]` (the column you're
pulling in, then what to call it on the event). `--overwrite`
(default) emits `OUTPUT` (always overwrite); `--no-overwrite` emits
`OUTPUTNEW` (only fill fields the event doesn't already have).
`lookups define` requires exactly one of `--file`/`--collection` (else
exit 2), and warns -- without blocking -- if `--file` names a table that
doesn't exist yet in that app.

## Remote upload

Upload works from your laptop -- no SSH, no SCP, no server filesystem
access. The CLI uploads through the Splunk Web UI form handler (same
mechanism the browser uses), so you can push files to a remote instance
across the network. Supports CSV and mmdb (GeoIP) files.

```bash
# Push a threat intel feed update
splunkctl lookups upload threat_indicators.csv \
    --file threat_indicators.csv --app SA-ThreatIntelligence --yes

# Refresh the asset/identity list
splunkctl lookups update asset_lookup.csv \
    --file asset_lookup.csv --app SA-IdentityManagement --yes

# Update a GeoIP database
splunkctl lookups upload GeoIP2-City.mmdb --file GeoIP2-City.mmdb --yes

# Download the current lookup for diff before updating
splunkctl lookups download threat_indicators.csv \
    --app SA-ThreatIntelligence --out current_threats.csv
```

## Automating threat feed updates

Combine with standard tools to build a lightweight feed pipeline:

```bash
# Fetch a fresh STIX/CSV feed, then push it
curl -sO https://feeds.example.com/iocs_latest.csv
splunkctl lookups update threat_indicators.csv \
    --file iocs_latest.csv --app SA-ThreatIntelligence --yes
```

## Implementation notes

Uses `LookupTableFile`/`LookupTableFiles` entity classes from the SDK
fork for metadata and download. Upload goes through the `client.py` Web
UI workaround (the REST API requires a server-side path). `define`/
`auto`/`definitions` go through `conf_ops` against `transforms.conf`/
`props.conf` instead -- no dedicated SDK entity class for either, since
`conf_ops`'s generic stanza get/set already covers it.
