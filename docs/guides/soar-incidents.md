<!-- summary: Find, create, update, assign, and close Splunk SOAR containers, and manage their artifacts, vault files, notes, and comments from the terminal. -->

# Work SOAR incidents

When to use: you are handling an event or case in Splunk SOAR and want to list the queue, pull one container's detail, add evidence (artifacts, files, notes), reassign it, or close it, alone or in bulk.

## Prerequisites

- SOAR credentials in the active profile and a passing `splunkctl soar test` (see [Set up and check SOAR](soar.md)).
- Username and password credentials for any `delete` command; SOAR refuses automation tokens on DELETE.
- Status names from `splunkctl soar meta statuses` and label names from `splunkctl soar meta labels`.

## Synopsis

```text
splunkctl soar containers list [--label TEXT] [--status NAME] [--severity NAME] [--owner USER] [--since DATE] [--type event|case] [--filter DJANGO_FILTER] [--limit N] [--offset N]
splunkctl soar containers get <CONTAINER_ID> [--artifacts|--notes|--comments|--audit|--activity|--playbook-runs|--phases]
splunkctl soar containers create --name <NAME> --label <LABEL> [--severity NAME] [--sensitivity NAME] [--sdi TEXT] [--description TEXT] [--tag TAG]... [--field KEY=VALUE]... [--yes]
splunkctl soar containers update <IDS>... [--status NAME] [--severity NAME] [--owner USER] [--role ROLE] [--tag TAG]... [--field KEY=VALUE]... [--yes]
splunkctl soar containers close <IDS>... [--yes]
splunkctl soar containers assign <IDS>... (--owner USER | --role ROLE) [--yes]
splunkctl soar containers delete <IDS>... [--yes]

splunkctl soar artifacts list --container <CONTAINER_ID> [--limit N] [--offset N]
splunkctl soar artifacts get <ARTIFACT_ID>
splunkctl soar artifacts create --container <CONTAINER_ID> --name <NAME> [--cef KEY=VALUE]... [--cef-file FILE.json] [--cef-type FIELD=TYPE]... [--sdi TEXT] [--severity NAME] [--type TEXT] [--no-automation] [--yes]
splunkctl soar artifacts update <ARTIFACT_ID> [--cef KEY=VALUE]... [--cef-file FILE.json] [--replace-cef] [--name TEXT] [--severity NAME] [--type TEXT] [--yes]
splunkctl soar artifacts delete <ARTIFACT_ID> [--yes]

splunkctl soar vault list [--container CONTAINER_ID]
splunkctl soar vault get <VAULT_ID>
splunkctl soar vault upload --container <CONTAINER_ID> <FILE_PATH> [--yes]
splunkctl soar vault download <VAULT_ID> [--out FILE]
splunkctl soar vault delete <ATTACHMENT_ID> [--yes]

splunkctl soar notes list --container <CONTAINER_ID> [--task TASK_ID]
splunkctl soar notes add --container <CONTAINER_ID> --title <TITLE> [CONTENT] [--file FILE] [--task-id TASK_ID] [--yes]
splunkctl soar notes delete <NOTE_ID> [--yes]
splunkctl soar notes comment <CONTAINER_ID> <TEXT> [--yes]
```

## Workflow

### Find the containers you need

```bash
splunkctl soar containers list --status open --severity high
splunkctl soar containers list --label events --since 2026-07-01
splunkctl soar containers list --owner admin --type case
splunkctl soar containers list --filter '_filter_name__icontains="dns"'
splunkctl soar containers list --limit 10 --offset 20 --json
```

Filters combine with AND. `--status` is validated against `/rest/container_status` before the query; an unknown name exits 1. `--type event` maps to `container_type=default`. `--since` maps to `_filter_create_time__gt`. `--filter` passes a raw Django-style filter. `--offset` requires `--limit` and must be a multiple of it, because the API pages by page number.

### Read one container

```bash
splunkctl soar containers get 42
splunkctl soar containers get 42 --artifacts
splunkctl soar containers get 42 --playbook-runs
splunkctl soar containers get 42 --audit --json
```

Without a flag you get the full container object. Each flag fetches one sub-view from `/rest/container/<id>/<suffix>`; if you pass several, the last one wins.

### Create a container

> **Safety:** Target is the SOAR host in the active profile. Impact: a new container is created with `run_automation: false`, so playbooks do not fire. Preview with `splunkctl soar containers create --name "DNS Alert" --label events`, apply by adding `--yes`, and verify with `splunkctl soar containers list --label events --since <today>`.

```bash
splunkctl soar containers create --name "DNS Alert" --label events
splunkctl soar containers create --name "DNS Alert" --label events \
  --severity high --sensitivity white --sdi "SDI-001" \
  --description "Probe" --tag malware --field priority=P1 --yes
```

When `--sdi` is given, the CLI first looks for an existing container with that source data identifier and exits 1 with `kind: conflict` and the existing id if one is found.

### Update, assign, or close containers

> **Safety:** Target is the SOAR host in the active profile. Impact: status, severity, owner, tags, or fields change on every id you pass, in one bulk request. Preview with `splunkctl soar containers update 42 --severity critical`, apply by adding `--yes`, and verify with `splunkctl soar containers get 42`.

```bash
splunkctl soar containers update 42 --severity critical --yes
splunkctl soar containers update 1 2 3 --severity low --yes
splunkctl soar containers update 42 --tag new_tag --yes
splunkctl soar containers assign 42 --owner analyst --yes
splunkctl soar containers assign 1 2 --role analyst --yes
splunkctl soar containers close 42 --yes
```

`--status` takes a name (`closed`), never a numeric id. Tags are read-modify-write: existing tags are fetched at apply time and merged. `assign` takes an owner or a role, not both; names resolve to ids at apply time and every container is read back to confirm the change. `close` is shorthand for `update --status closed`.

### Delete containers

> **Safety:** Target is the SOAR host in the active profile. Impact: the container and all artifacts, vault files, comments, notes, phases, and tasks in it are removed; there is no undo. Preview with `splunkctl soar containers delete 42`, apply with `splunkctl soar containers delete 42 --yes`, and verify with `splunkctl soar containers get 42` (expect `not_found`).

```bash
splunkctl soar containers delete 42
splunkctl soar containers delete 42 --yes
```

Requires username and password credentials.

### Add and update artifacts

> **Safety:** Target is the SOAR host in the active profile. Impact: a new artifact on the container, which can trigger playbooks unless you pass `--no-automation`. Preview with `splunkctl soar artifacts create --container 42 --name "Suspicious IP" --cef sourceAddress=10.0.0.5`, apply by adding `--yes`, and verify with `splunkctl soar artifacts list --container 42`.

```bash
splunkctl soar artifacts list --container 42
splunkctl soar artifacts create --container 42 --name "Suspicious IP" \
  --cef sourceAddress=10.0.0.5 --yes
splunkctl soar artifacts create --container 42 --name "DNS hit" \
  --cef destinationDnsDomain=evil.example --severity high --type network \
  --sdi "SDI-001" --no-automation --yes
splunkctl soar artifacts update 77 --cef sourceAddress=9.9.9.9 --yes
splunkctl soar artifacts update 77 --cef sourceAddress=9.9.9.9 --replace-cef --yes
```

CEF fields come from `--cef` (repeatable) and/or `--cef-file`; `--cef` wins on conflict. Contains types are filled in from a built-in CEF map (for example `sourceAddress` becomes `ip` and `host name`); `--cef-type field=type` overrides one entry. SOAR does not deduplicate artifacts by SDI, so when `--sdi` is given the CLI checks for an existing match in the same container and warns. `update` merges CEF keys by default; `--replace-cef` replaces the whole CEF map.

### Delete an artifact

> **Safety:** Target is the SOAR host in the active profile. Impact: the artifact is removed from its container. Preview with `splunkctl soar artifacts delete 77`, apply with `splunkctl soar artifacts delete 77 --yes`, and verify with `splunkctl soar artifacts list --container 42`.

```bash
splunkctl soar artifacts delete 77 --yes
```

### Attach and retrieve vault files

> **Safety:** Target is the SOAR host in the active profile. Impact: the file is stored in the vault and attached to the container. Preview with `splunkctl soar vault upload --container 42 ./sample.pcap`, apply by adding `--yes`, and verify with `splunkctl soar vault list --container 42`.

```bash
splunkctl soar vault upload --container 42 ./sample.pcap --yes
splunkctl soar vault list --container 42
splunkctl soar vault get <VAULT_ID>
splunkctl soar vault download <VAULT_ID> --out ./sample.pcap
```

Upload base64-encodes the file and posts to `/rest/container_attachment`; files over 30 MB trigger a warning because SOAR's proxy caps requests near 32 MB. `get` and `download` take the vault id (SHA1 hash). `download` without `--out` writes raw bytes to stdout; `--out` overwrites the target without prompting.

### Delete a vault file

> **Safety:** Target is the SOAR host in the active profile. Impact: the attachment is removed from the container. Preview with `splunkctl soar vault delete <ATTACHMENT_ID>`, apply by adding `--yes`, and verify with `splunkctl soar vault list --container 42`.

```bash
splunkctl soar vault delete <ATTACHMENT_ID> --yes
```

Use the attachment id (the `id` column of `vault list`), not the vault id hash. Requires username and password credentials.

### Record notes and comments

> **Safety:** Target is the SOAR host in the active profile. Impact: a note is added to the container; comments are immutable once posted and cannot be deleted through the API. Preview with `splunkctl soar notes add --container 42 --title "Summary" "Findings"`, apply by adding `--yes`, and verify with `splunkctl soar notes list --container 42`.

```bash
splunkctl soar notes list --container 42
splunkctl soar notes list --container 42 --task 7
splunkctl soar notes add --container 42 --title "Summary" "Investigation findings" --yes
splunkctl soar notes add --container 42 --title "Report" --file ./report.md --yes
splunkctl soar notes add --container 42 --title "Task note" --task-id 7 "Task analysis" --yes
splunkctl soar notes delete 10 --yes
splunkctl soar notes comment 42 "Investigation complete" --yes
```

Note content comes from the positional argument or `--file`; `--file` wins when both are given. `--task-id` makes it a task note. `notes comment-delete` exists only to explain that SOAR comments are immutable; it makes no API call.

## Troubleshooting

- `usage` error on `--status`: pass the status name from `splunkctl soar meta statuses`, not a number.
- `kind: conflict` on create: a container with that `--sdi` already exists; the message includes its id.
- `kind: auth` on a delete while reads work: the profile is token-only. Add a username and password with `splunkctl config init --soar`.
- `--offset` rejected: it must be a multiple of `--limit`.
- `assign` exits 1 after a 200 response: the server accepted but ignored the write; the read-back check caught it. Confirm the owner or role exists with `splunkctl soar users list` or `splunkctl soar roles list`.
- Vault delete returns 405: you passed the vault id hash; use the attachment id from `vault list`.

## See also

- [Set up and check SOAR](soar.md)
- [Run playbooks](soar-playbooks.md)
- [Run actions](soar-actions.md)
- [Manage cases and workbooks](soar-cases.md)
- [Ingest SIEM results into SOAR](soar-ingest.md)
- [Command reference: soar](../commands/soar.md)
