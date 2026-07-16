# Server Operations

System health, license, KV store status, and topology health reads.

## Messages

```bash
splunkctl server messages                              # list system messages
splunkctl server messages --dismiss warn_disk --yes    # dismiss a message
```

## License

```bash
splunkctl server license             # license pool usage (used vs quota per pool)
splunkctl server license --usage     # today's indexed volume vs quota + expiry
```

`--usage` reports one row: `used`, `quota`, `pct_used` (today's indexed
volume against the licensed daily quota), `licenses_valid`, and
`soonest_expiry` (earliest expiring non-perpetual license, or `never`).

## KV Store

```bash
splunkctl server kvstore     # status, port, version, storage engine
```

Reports an explicit status word (`ready`, `failed`, `starting`,
`unknown`) so a down KV store is never mistaken for a healthy result.

## Auth Tokens

Manage Splunk authentication tokens (Splunk 7.3+). Tokens are an
alternative to password-based auth for service accounts and automation.

```bash
splunkctl server tokens list                      # list all tokens
splunkctl server tokens list --user admin          # filter by user
splunkctl server tokens create --user admin --yes  # create a token
splunkctl server tokens create --user svc \
    --audience my-app --expires-in 30 --yes        # with audience + expiry
splunkctl server tokens revoke <token-id> --yes    # revoke a token
```

`list` shows: `id`, `user`, `audience`, `status`, `last_used`, `expires`.
Tokens that never expire show `never`; unused tokens show `last_used: never`.

`create` returns the token value **once** -- save it immediately. The
token cannot be retrieved after creation. Requires `--yes` (guarded).

`revoke` permanently deletes a token by its ID. Requires `--yes` (guarded).

## Health Report

```bash
splunkctl server health            # component-level splunkd health
splunkctl server health --json
```

Flattens Splunk's health-report tree (search scheduler, disk space, KV
store, ingestion latency...) into one row per component — nested feature
names join with `/`, and unhealthy components carry their reason text in
a `reasons` column. The command reports, it does not gate: red
components still exit 0. Complements `doctor` (connectivity-oriented)
with splunkd's own self-diagnosis.

## Topology Health

Three read-only commands for triage-critical infrastructure health. On a
non-clustered instance, each reports a clean disabled/no-clients state
and exits 0 -- not an error.

### Indexer Cluster

```bash
splunkctl server cluster           # mode, peers, SF/RF met
splunkctl server cluster --json    # machine-readable for agent triage
```

Output (when enabled): cluster overview row (mode, label,
replication_factor_met, search_factor_met, rolling_restart,
maintenance_mode) followed by one row per peer (label, status, site,
search_state, replication_count, bucket_count).

When disabled: single row with `mode: disabled`.

Prefers `cluster/manager` (Splunk 9+); falls back to `cluster/master`
on older instances.

### Search Head Cluster

```bash
splunkctl server shcluster         # captain, members, replication
splunkctl server shcluster --json
```

Output (when enabled): captain row (captain label, captain_id,
dynamic_captain, elected_captain) followed by one row per member (label,
status, site, out_of_sync).

When disabled: single row with `mode: disabled`.

### Deployment Server

```bash
splunkctl server deployment        # clients + last check-in
splunkctl server deployment --json
```

Output (when clients exist): one row per client (client name, hostname,
ip, last_phone_home, phone_home_interval).

When no clients: single row with `status: no_clients, total: 0`.

### Search Peers

```bash
splunkctl server search-peers      # distributed-search peers
splunkctl server search-peers --json
```

Output: one row per peer (peer, status, replication_status, version).
Empty on a standalone instance (exit 0).

## Empty Result vs Infrastructure Down

When a detection search returns nothing, an agent must distinguish:

- **No threat** -- the search ran correctly, nothing matched.
- **Infra degraded** -- an indexer peer is down, the cluster bundle
  failed to replicate, a forwarder stopped checking in.

Use the topology commands to triage:

```bash
splunkctl server cluster --json    # any peers Down? SF/RF not met?
splunkctl server shcluster --json  # any members out of sync?
splunkctl server deployment --json # any forwarders missing check-in?
```

Genuine REST errors (401, 503 for reasons other than "not enabled")
propagate to the central error classifier (F1) and exit 1 with a
classified error envelope.
