# SOAR Operations

Platform reads, containers, artifacts, playbooks, and actions on Splunk
SOAR (on-premises or cloud) via the REST API.

## Prerequisites

Configure SOAR credentials in the active profile:

```bash
splunkctl config init --soar          # interactive: host, port, token/user/pass
```

Or set environment variables (`SOAR_HOST`, `SOAR_TOKEN`, etc.) for
ephemeral overrides. The CLI resolves: env vars > profile `soar:` section >
defaults (port 8443, verify off).

## Connectivity Test

```bash
splunkctl soar test                   # version + auth check
splunkctl soar test --json            # machine-readable
```

Reports `status: ok` with the SOAR version on success. On failure, a
typed error envelope (kind: `auth`, `connection`, `timeout`, ...) exits 1.

## System Info

```bash
splunkctl soar info                   # version, FQDN, system details
splunkctl soar info --json
```

Merges `/rest/version` and `/rest/system_info` into a single row.

## Health

```bash
splunkctl soar health                 # daemon status, standby, cluster
splunkctl soar health --json
```

Rolls up three endpoints:

- `/rest/health` -- per-daemon time-series; the latest state per daemon
  (decided, nginx, postgres, uwsgi, ...) is reported.
- `/rest/warm_standby` -- standby mode (`off` on most installs). Errors
  are swallowed with status `unavailable`.
- `/rest/cluster_node` -- cluster node list. Errors are swallowed with
  status `unclustered` (lab is single-node).

Each row carries a `type` column (`daemon`, `warm_standby`,
`cluster_node`) for easy filtering.

## License

```bash
splunkctl soar license                # type, action quota, usage
splunkctl soar license --json
```

Surfaces `/rest/license`: license type (community/enterprise), daily
action cap (`max_allowed_actions_per_day`), expiry, and today's action
count. Community license caps at 100 actions/day.

## Error Handling

All SOAR commands produce typed error envelopes on failure:

```bash
SOAR_TOKEN=bogus splunkctl soar test --json
# stderr: {"error": {"kind": "auth", "http_status": 401, "message": "..."}}
# exit 1
```

Error kinds match the SIEM taxonomy: `auth`, `connection`, `timeout`,
`not_found`, `permission`, `usage`, `error`.
