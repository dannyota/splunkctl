<!-- summary: Read Splunk server health, license, KV store status, topology, deployment, authentication, tokens, and workload settings. -->

# Check server health and topology

When to use: a detection returned nothing and you need to know whether the search ran against a healthy platform, or you are auditing license usage, KV store state, authentication providers, auth tokens, deployment server classes, or workload management on a Splunk instance.

## Prerequisites

- A profile that passes `splunkctl doctor` (see [Configure](configure.md)).
- A role that can read `server/` and `cluster/` endpoints; most reads work with `admin`, and the health, license, and KV store views need no cluster membership.
- `tokens` needs Splunk 7.3 or later; `workloads` needs Splunk 8.1 or later with workload management enabled; `serverclasses` and `deployment` need the deployment server enabled.

## Synopsis

```text
splunkctl server health
splunkctl server messages [--dismiss NAME] [--yes]
splunkctl server license [--usage]
splunkctl server kvstore
splunkctl server cluster
splunkctl server shcluster
splunkctl server deployment
splunkctl server search-peers
splunkctl server serverclasses list
splunkctl server serverclasses get <NAME>
splunkctl server serverclasses reload <NAME> [--yes]
splunkctl server tokens list [--user USER]
splunkctl server tokens create --user <USER> [--audience TEXT] [--expires-in DAYS] [--yes]
splunkctl server tokens revoke <TOKEN_ID> [--yes]
splunkctl server auth show
splunkctl server auth ldap
splunkctl server auth saml
splunkctl server auth role-mapping
splunkctl server workloads pools
splunkctl server workloads rules
splunkctl server workloads status
```

Every command accepts the global `--json` flag for machine-readable output.

## Workflow

### Read the splunkd health report

```bash
splunkctl server health
splunkctl server health --json
```

Expected result: Splunk's health-report tree (search scheduler, disk space, KV store, ingestion latency, and more) flattened to one row per component. Nested feature names join with `/`, and unhealthy components carry their reason text in a `reasons` column. The command reports, it does not gate: red components still exit 0. It complements `doctor` (connectivity-oriented) with splunkd's own self-diagnosis.

### Triage an empty detection result

```bash
splunkctl server cluster --json
splunkctl server shcluster --json
splunkctl server deployment --json
splunkctl server search-peers
```

Expected result: enough to tell "no threat" (the search ran correctly and nothing matched) from "infrastructure degraded" (an indexer peer is down, the cluster bundle failed to replicate, a forwarder stopped checking in). On a non-clustered instance each command reports a clean disabled or no-clients state and exits 0; that is not an error.

- `cluster`: an overview row (`mode`, `label`, `replication_factor_met`, `search_factor_met`, `rolling_restart`, `maintenance_mode`) followed by one row per peer (`label`, `status`, `site`, `search_state`, `replication_count`, `bucket_count`). When disabled, a single row with `mode: disabled`. Prefers `cluster/manager` (Splunk 9+) and falls back to `cluster/master` on older instances.
- `shcluster`: a captain row (`captain`, `captain_id`, `dynamic_captain`, `elected_captain`) followed by one row per member (`label`, `status`, `site`, `out_of_sync`). When disabled, `mode: disabled`.
- `deployment`: one row per client (`client`, `hostname`, `ip`, `last_phone_home`, `phone_home_interval`), or `status: no_clients, total: 0`.
- `search-peers`: one row per distributed-search peer (`peer`, `status`, `replication_status`, `version`). Empty on a standalone instance.

Genuine REST errors (401, or 503 for reasons other than "not enabled") exit 1 with a classified error envelope.

### Check license and KV store

```bash
splunkctl server license
splunkctl server license --usage
splunkctl server kvstore
```

Expected result: `license` lists pool usage (used versus quota per pool). `--usage` reports one row with `used`, `quota`, `pct_used` (today's indexed volume against the licensed daily quota), `licenses_valid`, and `soonest_expiry` (earliest expiring non-perpetual license, or `never`). `kvstore` shows status, port, version, and storage engine, with an explicit status word (`ready`, `failed`, `starting`, `unknown`) so a down KV store is never mistaken for a healthy result.

### Read and dismiss system messages

> **Safety:** Target is the Splunk host in the active profile. Impact: the message disappears from Splunk Web for every user. Preview with `splunkctl server messages --dismiss warn_disk`, apply by adding `--yes`, and verify with `splunkctl server messages`.

```bash
splunkctl server messages
splunkctl server messages --dismiss warn_disk --yes
```

Expected result: the list of system messages, then the list without `warn_disk`.

### Inspect the authentication provider

```bash
splunkctl server auth show
splunkctl server auth ldap
splunkctl server auth saml
splunkctl server auth role-mapping
```

Expected result (all read-only):

- `show`: one row per provider-services entry with `name`, `auth_type` (detected: `Splunk`, `LDAP`, or `SAML`), and `active_authmodule`.
- `ldap`: feature-detects the active auth type first. When LDAP is not configured it returns `{"status": "not_configured", "active_auth": "..."}` and exits 0. When configured it shows `name`, `host`, `port`, `SSLEnabled`, `userBaseDN`, `groupBaseDN`, `bindDN`, `userNameAttribute`, `groupMemberAttribute`.
- `saml`: same detection; when configured it shows `name` (group name) and `roles` (mapped Splunk roles, comma-separated).
- `role-mapping`: every role with `name`, `imported_roles`, `srchFilter`, `srchIndexesAllowed`, `defaultApp`, for auditing which external groups map to which Splunk roles.

### Manage auth tokens

> **Safety:** Target is the Splunk host in the active profile. Impact: `create` issues a bearer token that authenticates as `--user` until it expires; `revoke` permanently deletes a token and breaks any automation using it. Preview with `splunkctl server tokens create --user svc --audience my-app --expires-in 30`, apply by adding `--yes`, and verify with `splunkctl server tokens list --user svc`.

```bash
splunkctl server tokens list
splunkctl server tokens list --user admin
splunkctl server tokens create --user admin --yes
splunkctl server tokens create --user svc --audience my-app --expires-in 30 --yes
splunkctl server tokens revoke <TOKEN_ID> --yes
```

Expected result: `list` shows `id`, `user`, `audience`, `status`, `last_used`, `expires`; tokens that never expire show `never`, unused tokens show `last_used: never`. `create` prints the token value once; save it immediately, it cannot be retrieved later. Omit `--expires-in` for a non-expiring token. Tokens are an alternative to password auth for service accounts and automation.

### Push apps with deployment server classes

> **Safety:** Target is the deployment server in the active profile. Impact: `reload` pushes the serverclass's current app configuration to every matching forwarder, which may restart splunkd on them when `restartSplunkd` is set. Preview with `splunkctl server serverclasses reload linux_forwarders`, apply by adding `--yes`, and verify with `splunkctl server deployment` (check `last_phone_home`).

```bash
splunkctl server serverclasses list
splunkctl server serverclasses get linux_forwarders
splunkctl server serverclasses reload linux_forwarders --yes
```

Expected result: `list` shows `name`, `restartSplunkd`, `stateOnClient`, `whitelist`, `blacklist`. `get` adds `repositoryLocation`, `targetRepositoryLocation`, `endpoint`, `filterType`, and an `apps` list (each with `app`, `restartSplunkd`, `stateOnClient`). When the deployment server is not enabled, `list` reports a clean disabled status and exits 0.

### Review workload management

```bash
splunkctl server workloads pools
splunkctl server workloads rules
splunkctl server workloads status
```

Expected result (read-only): `pools` gives one row per pool (`name`, `cpu_weight`, `mem_weight`, `default_category`, `category`); `rules` one row per admission rule (`name`, `predicate`, `workload_pool`, `action`, `order`, `schedule`); `status` reports `status` (enabled or disabled) and `admission_rules_enabled`, plus a nested `pools` list with `cpu_usage`, `mem_usage`, and `search_count` when pool-level utilisation is available. On older or unconfigured instances each reports a clean not-available status and exits 0.

## Troubleshooting

- `auth` error on every command: credentials are wrong or expired; run `splunkctl doctor`.
- `permission` on `cluster`, `tokens`, or `serverclasses`: the role cannot read that endpoint; use `admin` or add the matching capability.
- `http` 503 on `cluster` or `shcluster` with a reason other than "not enabled": the cluster manager or captain is down; treat detection results from that window as unreliable.
- `not_found` on `tokens revoke`: use the `id` column from `tokens list`, not the token value.
- `not_found` on `messages --dismiss`: the message name is the `name` column from `splunkctl server messages`, not its text.
- `connection` or `timeout`: the management port is unreachable; raise the global `--timeout` or check the network path.

## See also

- [Diagnose a connection](doctor.md)
- [Run searches](search.md)
- [Manage users and roles](users.md)
- [Log in through browser SAML](auth.md)
- [Manage KV store collections](kvstore.md)
- [Command reference: server](../commands/server.md)
