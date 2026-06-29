# HEC tokens

HEC (HTTP Event Collector) is Splunk's HTTP/JSON ingestion endpoint.
SecOps teams use it to push data into Splunk from sources that do not
have a forwarder: SOAR playbooks sending enrichment results back to
Splunk, custom scripts forwarding threat intel, CI/CD pipelines logging
deploy events, and cloud services that can only webhook out. Managing
HEC tokens programmatically means you can provision, rotate, and revoke
ingestion credentials without touching the Web UI.

## Commands

```bash
splunkctl hec list                            # list all HEC tokens
splunkctl hec get my_token                    # get token details
splunkctl hec create --name my_token \
    --index main --yes                        # create token
splunkctl hec create --name my_token \
    --index main --indexes 'main,_internal' \
    --sourcetype json --yes                   # with allowed indexes
splunkctl hec delete my_token --yes           # delete token
splunkctl hec enable my_token --yes           # enable token
splunkctl hec disable my_token --yes          # disable token
```

## Practical examples

```bash
# Provision a token for a SOAR integration (scoped to one index)
splunkctl hec create --name soar_enrichment \
    --index notable_enrichments --sourcetype json --yes

# Provision a token for a custom threat feed ingester
splunkctl hec create --name threat_feed_ingest \
    --index threat_intel --indexes 'threat_intel' \
    --sourcetype stix_ioc --yes

# Rotate a compromised token: disable old, create replacement
splunkctl hec disable old_webhook_token --yes
splunkctl hec create --name new_webhook_token \
    --index webhook_events --sourcetype json --yes

# Audit all HEC tokens -- find enabled tokens and their indexes
splunkctl hec list --json | jq '.[] | {name, index, disabled}'

# Revoke a decommissioned integration
splunkctl hec delete legacy_siem_bridge --yes
```

## Note on naming

Splunk prefixes HEC token names with `http://` internally. Creating
`my_token` results in a token named `http://my_token`. The CLI handles
this transparently -- you always use the short name.

## Implementation notes

Uses `HECToken`/`HECTokens` entity classes from the SDK fork. Token
CRUD goes through the REST API (no Web UI workaround needed).
