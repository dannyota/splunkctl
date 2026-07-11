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

## Settings

```bash
splunkctl soar settings                   # all 37 sections
splunkctl soar settings --section debug_settings
splunkctl soar settings --json
```

Read-only dump of `/rest/system_settings`. Each row is
`{section, settings}` where `settings` is the section's key-value map.
Sections include `auth_settings`, `response_settings`, `debug_settings`,
`email_settings`, `decided_runner_settings`, and 32 more.

## Stats

```bash
splunkctl soar stats                      # default 4 SOC widgets
splunkctl soar stats --widget roi_summary # single widget
splunkctl soar stats --list               # all 17 widget names
splunkctl soar stats --json
```

SOC metrics from `/rest/widget_data/<name>`. Defaults fetch
`container_stats`, `containers_workload`, `sla_stats`, and
`pending_approvals`. Use `--widget NAME` for any of the 17 widgets;
unknown names return an error envelope. `--list` prints the catalog
without hitting the API.

## Meta (Vocabularies)

```bash
splunkctl soar meta severities            # high/medium/low + colors
splunkctl soar meta statuses              # new/open/closed + status_type
splunkctl soar meta labels                # container labels (UI-only creation)
splunkctl soar meta tags                  # container tags
splunkctl soar meta cef                   # CEF field vocabulary
splunkctl soar meta features              # feature flags (enabled/disabled)
```

Read-only vocabulary lookups. `statuses` shows the name-to-id map needed
for container updates (use the string name, not numeric id). `labels`
notes that label creation has no REST endpoint (UI-only). `features`
lists feature flags with their enabled state.

## Containers

### List

```bash
splunkctl soar containers list                          # all containers
splunkctl soar containers list --label events            # by label
splunkctl soar containers list --status open              # by status name
splunkctl soar containers list --severity high            # by severity
splunkctl soar containers list --owner admin              # by owner
splunkctl soar containers list --since 2026-07-01         # created after date
splunkctl soar containers list --type event               # events only
splunkctl soar containers list --type case                # cases only
splunkctl soar containers list --limit 10 --offset 20     # pagination
splunkctl soar containers list --filter '_filter_name__icontains="dns"'
splunkctl soar containers list --json
```

Filters compose (AND). `--status` validates the name against
`/rest/container_status` before querying; unknown names exit 1 with a
usage error (if the lookup itself fails, a warning is printed and the
name passes through to the server). `--type event` maps to API
`container_type=default`. `--since` maps to `_filter_create_time__gt`.
`--filter` passes a raw Django-style filter for advanced queries.
`--offset` requires `--limit` and must be a multiple of it (the API
pages by page number: `page = offset / limit`).

### Get

```bash
splunkctl soar containers get 42                        # full container
splunkctl soar containers get 42 --artifacts             # artifacts
splunkctl soar containers get 42 --notes                 # notes
splunkctl soar containers get 42 --comments              # comments
splunkctl soar containers get 42 --audit                 # audit log
splunkctl soar containers get 42 --activity              # activity feed
splunkctl soar containers get 42 --playbook-runs         # playbook runs
splunkctl soar containers get 42 --phases                # case phases
splunkctl soar containers get 42 --json
```

Without a sub-view flag, returns the full container object. Each flag
fetches the corresponding pseudo-field endpoint
(`/rest/container/<id>/<suffix>`). Sub-view flags are mutually exclusive
(last wins).

### Create

```bash
splunkctl soar containers create --name "DNS Alert" --label events --yes
splunkctl soar containers create --name "Alert" --label events \
  --severity high --sensitivity white --sdi "SDI-001" \
  --description "Probe" --tag malware --field priority=P1 --yes
```

Creates a container with `run_automation: false`. When `--sdi` is given,
the CLI queries for an existing container with that SDI first; if found,
it exits 1 with `kind: conflict` and the existing container id. The
server also returns `existing_container_id` on a 400 duplicate, which the
CLI surfaces. Tags and custom fields are passed inline. All mutations are
dry-run by default (pass `--yes` to apply); the guard banner shows the
SOAR host.

### Update

```bash
splunkctl soar containers update 42 --severity critical --yes
splunkctl soar containers update 42 --status closed --yes
splunkctl soar containers update 42 --owner analyst --role analyst --yes
splunkctl soar containers update 1 2 3 --severity low --yes   # bulk
splunkctl soar containers update 42 --tag new_tag --yes       # read-modify-write
```

Updates one or more containers. Multiple ids use a single bulk array POST
to `/rest/container`. Status must be a name (`closed`, not `2`) -- numeric
ids are rejected with a `usage` error. Tags are read-modify-write: each
container's existing tags are fetched at apply time, new tags merged per
container, duplicates removed (dry-run previews the merge without any
API call).

### Close

```bash
splunkctl soar containers close 42 --yes
splunkctl soar containers close 1 2 3 --yes                   # bulk
```

Sugar for `update --status closed`. Multiple ids use one array POST.

### Assign

```bash
splunkctl soar containers assign 42 --owner analyst --yes
splunkctl soar containers assign 1 2 --owner admin --role analyst --yes
```

Sets owner and/or role on containers. Multiple ids use one array POST.

### Delete

```bash
splunkctl soar containers delete 42 --yes
splunkctl soar containers delete 1 2 3 --yes
```

Cascading delete (artifacts, vault, comments, notes, phases, tasks).
Requires Basic auth credentials (username/password in profile); SOAR
refuses automation tokens on DELETE. Token-only profiles get a clear
`kind: auth` error.

## Vault

### List

```bash
splunkctl soar vault list                             # all vault items
splunkctl soar vault list --container 42              # by container
splunkctl soar vault list --json
```

Lists vault attachments via `/rest/container_attachment`. `--container`
filters by container ID.

### Get

```bash
splunkctl soar vault get <vault_id>                   # by SHA1 hash
splunkctl soar vault get <vault_id> --json
```

Queries `/rest/vault_document` by hash. Returns metadata including SHA1,
SHA256, file names, size, and tags.

### Upload

```bash
splunkctl soar vault upload --container 42 ./sample.pcap
splunkctl --yes soar vault upload --container 42 ./sample.pcap
```

Base64-encodes the file and POSTs to `/rest/container_attachment`.
Guarded: dry-run by default, `--yes` to apply. Files over 30 MB emit a
warning (SOAR's nginx proxy caps at ~32 MB).

### Download

```bash
splunkctl soar vault download <vault_id>              # raw bytes to stdout
splunkctl soar vault download <vault_id> --out ./file # write to file
```

Downloads via `GET /rest/download_attachment?vault_id=<sha1>` (the only
working download path). Without `--out`, writes raw bytes to stdout
(pipe-friendly). `--out` overwrites the target file without prompting
(same convention as `lookups download --out` and `dashboards export --out`).

### Delete

```bash
splunkctl --yes soar vault delete <attachment_id>
```

Deletes via `DELETE /rest/container_attachment/<id>`. Use the attachment
ID from `vault list` (the `id` column), not the vault_id hash. SOAR's
`vault_document` DELETE endpoint returns 405 -- the CLI explains this
if encountered. Guarded: dry-run by default, `--yes` to apply.
Requires Basic auth (SOAR refuses token auth on DELETE).

## Notes & Comments

### List

```bash
splunkctl soar notes list --container 42
splunkctl soar notes list --container 42 --task 7   # task-scoped notes
splunkctl soar notes list --container 42 --json
```

Lists notes for a container. `--task` filters to notes attached to a
specific task ID (queries `/rest/note` with container + task_id filters,
since task notes are not visible on the container sub-view endpoint).

### Add

```bash
splunkctl soar notes add --container 42 --title "Summary" "Investigation findings"
splunkctl soar notes add --container 42 --title "Report" --file ./report.md --yes
splunkctl soar notes add --container 42 --title "Task note" --task-id 7 "Task analysis" --yes
```

Content comes from the positional argument or `--file` (mutually
exclusive). `--task-id` makes the note a task note instead of a general
container note. Guarded: dry-run by default, `--yes` to apply.

### Delete

```bash
splunkctl --yes soar notes delete 10
```

Deletes a note by its numeric ID. Guarded.

### Comment

```bash
splunkctl --yes soar notes comment 42 "Investigation complete"
```

Adds a comment to a container. Comments are immutable -- once created,
they cannot be edited or deleted via the API.

### Comment-delete

```bash
splunkctl soar notes comment-delete 50
```

Exits with a usage error explaining that SOAR comments are immutable and
cannot be deleted. Comments are removed only when the parent container is
deleted. No API call is made.

## Error Handling

All SOAR commands produce typed error envelopes on failure:

```bash
SOAR_TOKEN=bogus splunkctl soar test --json
# stderr: {"error": {"kind": "auth", "http_status": 401, "message": "..."}}
# exit 1
```

Error kinds match the SIEM taxonomy: `auth`, `connection`, `timeout`,
`not_found`, `permission`, `usage`, `error`.
