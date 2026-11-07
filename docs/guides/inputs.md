<!-- summary: Manage monitor, TCP, UDP, scripted, and HTTP data inputs on a Splunk instance. -->

# Manage data inputs

When to use: you are onboarding a new log source, routing it to a dedicated index and sourcetype, pausing an input for maintenance, or removing a decommissioned source, all over the REST API without filesystem access to the Splunk server.

## Prerequisites

- A profile that passes `splunkctl doctor` with the `list_inputs`, `edit_monitor` (file inputs), and `edit_tcp` (network inputs) capabilities it reports.
- The target index already exists (see [Manage indexes](indexes.md)); events for a missing index are dropped or sent to the last-chance index.
- For `tcp` and `udp` inputs: the port is free on the Splunk server.

## Synopsis

```text
splunkctl inputs list [--kind monitor|tcp|udp|script|http] [--filter SUBSTRING] [--limit N] [--offset N]
splunkctl inputs get <NAME>
splunkctl inputs create --name <NAME> --kind <monitor|tcp|udp|script|http> [--index INDEX] [--sourcetype SOURCETYPE] [--disabled] [--yes]
splunkctl inputs update <NAME> [--index INDEX] [--sourcetype SOURCETYPE] [--enabled|--disabled] [--yes]
splunkctl inputs enable <NAME> [--yes]
splunkctl inputs disable <NAME> [--yes]
splunkctl inputs delete <NAME> [--yes]
```

`NAME` is the input's path for `monitor` and `script` inputs (`/var/log/syslog`) and the port for `tcp` and `udp` inputs (`5514`). `http` inputs are HEC tokens; manage them with [Manage HEC tokens](hec.md).

## Workflow

### Audit existing inputs

```bash
splunkctl inputs list
splunkctl inputs list --kind monitor
splunkctl inputs get /var/log/syslog
splunkctl inputs list --kind monitor --json | jq '.[] | {name, index, sourcetype, disabled}'
```

Expected result: one row per input with `name`, `kind`, `index`, `sourcetype`, and `disabled`. `--filter`, `--limit`, and `--offset` apply client side after `--kind`. The SDK's union collection pages each kind with a 30-per-kind default limit, so an instance with more than 30 inputs of one kind may list incompletely; verify completeness for a kind with:

```bash
splunkctl search oneshot '| rest /services/data/inputs/monitor' --limit 10000
```

### Onboard a new log source

> **Safety:** Target is the Splunk host in the active profile. Impact: Splunk starts reading the file or listening on the port and indexing into the named index immediately. Preview with `splunkctl inputs create --name /var/log/webapp/access.log --kind monitor --index security_logs --sourcetype access_combined`, apply by adding `--yes`, and verify with `splunkctl inputs get /var/log/webapp/access.log`.

```bash
splunkctl inputs create --name /var/log/webapp/access.log --kind monitor --index security_logs --sourcetype access_combined
splunkctl inputs create --name /var/log/webapp/access.log --kind monitor --index security_logs --sourcetype access_combined --yes
splunkctl inputs create --name 5514 --kind tcp --index security_logs --sourcetype syslog --yes
splunkctl inputs create --name /var/log/staged.log --kind monitor --index main --disabled --yes
```

Expected result: `Created input: NAME (KIND)`. The preview lists `kind`, `index`, and `sourcetype`. `--disabled` creates the input paused so you can review it before data flows. TCP and UDP inputs bind a port on the Splunk server, so confirm it is not already in use.

### Verify data is arriving

```bash
splunkctl search run 'index=security_logs sourcetype=access_combined | head 5' --earliest -15m
```

Expected result: recent events from the new input. An empty result after several minutes usually means a wrong path or port, a missing index, or a disabled input.

### Change index or sourcetype

> **Safety:** Target is the Splunk host in the active profile. Impact: new events from the input are parsed and stored differently from now on; existing events are unchanged. Preview with `splunkctl inputs update /var/log/app.log --sourcetype json`, apply by adding `--yes`, and verify with `splunkctl inputs get /var/log/app.log`.

```bash
splunkctl inputs update /var/log/app.log --sourcetype json
splunkctl inputs update /var/log/app.log --sourcetype json --yes
splunkctl inputs update /var/log/app.log --index security_logs --enabled --yes
```

### Pause an input for maintenance

> **Safety:** Target is the Splunk host in the active profile. Impact: ingestion stops while the input is disabled; the configuration is kept, and file inputs resume from where they left off when re-enabled. Preview with `splunkctl inputs disable /var/log/old_app.log`, apply by adding `--yes`, and verify with `splunkctl inputs get /var/log/old_app.log --json` (check `disabled`).

```bash
splunkctl inputs disable /var/log/old_app.log --yes
splunkctl inputs enable /var/log/old_app.log --yes
```

Use disable for maintenance windows instead of deleting the input.

### Remove a decommissioned source

> **Safety:** Target is the Splunk host in the active profile. Impact: the input definition is removed; indexed events remain searchable. Preview with `splunkctl inputs delete /var/log/retired_app.log`, apply by adding `--yes`, and verify with `splunkctl inputs list --filter retired_app`.

```bash
splunkctl inputs delete /var/log/retired_app.log
splunkctl inputs delete /var/log/retired_app.log --yes
```

## Troubleshooting

- `Input not found: NAME`: the name must match exactly (full path for files, bare port for TCP and UDP); find it with `splunkctl inputs list --filter <text>`, and remember the 30-per-kind listing limit.
- `conflict` or a create error naming an existing input: the path or port is already configured; `update` it instead.
- `permission` from `create`, `update`, or `delete`: the account lacks `edit_monitor` or `edit_tcp`; check `splunkctl doctor`.
- No events after `create --yes`: the input was created `--disabled`, the index does not exist, or the file path is not readable by the Splunk process on the server.
- `--kind http` behaves differently: those are HEC tokens; use `splunkctl hec` for the full token lifecycle.

## See also

- [Manage indexes](indexes.md)
- [Manage HEC tokens](hec.md)
- [Manage source types and extractions](parsers.md)
- [Run searches](search.md)
- [Command reference: inputs](../commands/inputs.md)
