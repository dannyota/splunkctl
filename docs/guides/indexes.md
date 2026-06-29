# Indexes

Create, configure, and manage Splunk indexes.

## Why it matters

Indexes are the storage layer for all Splunk data. Getting them right
determines retention compliance, search performance, and storage cost.
Separate indexes let you apply different retention periods (e.g. 90 days
for threat intel, 1 year for security logs), control access via roles,
and size capacity per data tier.

## Commands

```bash
splunkctl indexes list                        # list all indexes
splunkctl indexes get main                    # full index details
splunkctl indexes create --name my_index --yes
splunkctl indexes create --name metrics_idx \
    --datatype metric --max-size 500 \
    --frozen-period 604800 --yes              # metrics index
splunkctl indexes update my_index \
    --max-size 1000 --yes                     # resize
splunkctl indexes update my_index \
    --frozen-period 2592000 --yes             # change retention
splunkctl indexes delete my_index --yes       # delete
splunkctl indexes clean my_index --yes        # remove all events
splunkctl indexes reload --yes                # reload configs
```

## Practical examples

### Separate indexes for security workloads

```bash
# Threat intel -- short retention, small volume
splunkctl indexes create --name threat_intel \
    --max-size 100 --frozen-period 7776000 --yes   # 90 days

# Security event logs -- long retention, large volume
splunkctl indexes create --name security_logs \
    --max-size 5000 --frozen-period 31536000 --yes # 365 days
```

### Capacity planning

```bash
# Current size and event counts across all indexes
splunkctl indexes list --json \
    | jq '.[] | {name, totalEventCount, currentDBSizeMB, maxTotalDataSizeMB}'

# Find indexes approaching their size limit (over 80% full)
splunkctl indexes list --json \
    | jq '.[] | select(.currentDBSizeMB / .maxTotalDataSizeMB > 0.8)
          | {name, pct_used: (100 * .currentDBSizeMB / .maxTotalDataSizeMB)}'
```

### Health checks

```bash
# Indexes with zero events (possibly misconfigured)
splunkctl indexes list --json \
    | jq '[.[] | select(.totalEventCount == "0")] | .[].name'

# Verify retention settings match compliance requirements
splunkctl indexes get security_logs --json \
    | jq '{frozenTimePeriodInSecs, maxTotalDataSizeMB}'
```

## Notes

- `--frozen-period` is in seconds (86400 = 1 day, 2592000 = 30 days).
- `maxTotalDataSizeMB` is a high-water mark; Splunk freezes buckets when
  the index reaches this limit. Plan for headroom.
- Deleting an index does not free disk immediately; frozen buckets remain
  on the filesystem until manually removed from the Splunk server.
