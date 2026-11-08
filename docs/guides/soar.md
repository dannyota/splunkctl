<!-- summary: Configure SOAR credentials in a splunkctl profile, confirm connectivity, and read SOAR version, health, license, settings, metrics, and vocabularies. -->

# Set up and check SOAR

When to use: you are connecting splunkctl to a Splunk SOAR instance for the first time, or you need a quick read of its health, license usage, settings, or SOC metrics before doing incident work.

## Prerequisites

- A Splunk SOAR instance (on-premises or cloud) reachable on its REST port (default 8443).
- An automation token, or a username and password. Username and password are required for `delete` commands, because SOAR refuses automation tokens on DELETE; custom lists are the exception and accept a token.
- splunkctl installed (see [Install](install.md)).

## Synopsis

```text
splunkctl config init --soar [--profile NAME]
splunkctl soar test
splunkctl soar info
splunkctl soar health
splunkctl soar license
splunkctl soar settings [--section NAME]
splunkctl soar stats [--widget NAME] [--list]
splunkctl soar meta <severities|statuses|labels|tags|cef|features>
splunkctl soar search <TEXT> [--categories LIST] [--page-size N] [--page N]
```

## Workflow

### Add SOAR credentials to the profile

```bash
splunkctl config init --soar
splunkctl --profile uat config init --soar
```

The prompts ask for host, port, and either a token or a username and password. Values are saved as a `soar:` map inside the profile, next to the SIEM settings. Environment variables (`SOAR_HOST`, `SOAR_PORT`, `SOAR_TOKEN`, `SOAR_USER`, `SOAR_PASS`) override the profile for one run. Resolution order: environment variables, then the profile `soar:` section, then defaults (port 8443, TLS verification on).

This writes a local file and is not guarded.

### Verify connectivity

```bash
splunkctl soar test
splunkctl soar test --json
```

Expected result: `status: ok` and the SOAR version. On failure the command prints a typed error envelope (`kind: auth`, `connection`, or `timeout`) and exits 1.

### Read version and system info

```bash
splunkctl soar info
```

Merges `/rest/version` and `/rest/system_info` into one row: version, FQDN, and system details.

### Check health

```bash
splunkctl soar health
splunkctl soar health --json
```

Rolls up three endpoints into rows tagged by `type`:

- `daemon` rows from `/rest/health`: the latest state per daemon (decided, nginx, postgres, uwsgi, and others).
- `warm_standby` from `/rest/warm_standby`: `off` on most installs; errors are reported as `unavailable`.
- `cluster_node` from `/rest/cluster_node`: errors are reported as `unclustered` on single-node installs.

### Check license usage

```bash
splunkctl soar license
```

Shows license type (community or enterprise), the daily action cap (`max_allowed_actions_per_day`), expiry, and today's action count. A community license caps at 100 actions per day, which matters before a bulk `soar actions run`.

### Read settings and SOC metrics

```bash
splunkctl soar settings
splunkctl soar settings --section debug_settings
splunkctl soar stats
splunkctl soar stats --widget roi_summary
splunkctl soar stats --list
```

`settings` is a read-only dump of `/rest/system_settings`, one row per section (`auth_settings`, `response_settings`, `debug_settings`, `email_settings`, and the rest). `stats` reads `/rest/widget_data/<name>`; without `--widget` it fetches `container_stats`, `containers_workload`, `sla_stats`, and `pending_approvals`. `--list` prints the widget names without calling the API.

### Look up vocabularies

```bash
splunkctl soar meta severities
splunkctl soar meta statuses
splunkctl soar meta labels
splunkctl soar meta tags
splunkctl soar meta cef
splunkctl soar meta features
```

`severities`, `statuses`, `cef`, and `features` fetch every result page. `labels` and `tags` read the complete arrays from `/rest/container_options`.

`statuses` shows the name-to-id map; container updates take the status name, not the id. `labels` cannot be created through the REST API, only in the UI. `features` lists feature flags with their enabled state.

### Search across objects

```bash
splunkctl soar search dns
splunkctl soar search dns --categories app,container
splunkctl soar search dns --page-size 5 --page 2
```

Free-text search across apps, containers, artifacts, assets, and other object types through `/rest/search`. Each hit carries `category`, `name`, `id`, and `url`. Pagination here is 1-based, unlike other SOAR endpoints.

## Troubleshooting

- `kind: auth` from `soar test`: the token or password is wrong, or the token lacks REST access. Rerun `splunkctl config init --soar`.
- `kind: connection`: check host, port (8443 by default), and TLS. Set `--no-verify` in `config init` only for lab instances with self-signed certificates.
- `kind: auth` on a delete command while reads work: the profile is token-only. Add a username and password.
- `health` shows `unavailable` or `unclustered`: expected on single-node installs without warm standby.

Error kinds match the SIEM taxonomy: `auth`, `connection`, `timeout`, `not_found`, `permission`, `usage`, `error`. See [Exit codes](exit-codes.md).

## See also

- [Work SOAR incidents](soar-incidents.md)
- [Configure](configure.md)
- [Install SOAR apps](soar-apps.md)
- [Administer SOAR users and roles](soar-admin.md)
- [Command reference: soar](../commands/soar.md)
