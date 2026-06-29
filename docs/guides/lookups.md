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
```

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
UI workaround (the REST API requires a server-side path).
