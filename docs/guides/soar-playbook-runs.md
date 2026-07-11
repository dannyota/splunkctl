# Playbook runs

Run playbooks against containers, poll to completion, inspect run history
and block results, cancel in-progress runs.

## Run a playbook

```bash
# By name (resolved via GET /rest/playbook)
splunkctl soar playbooks run my_playbook --container 42 --yes

# By numeric id
splunkctl soar playbooks run 7 --container 42 --yes

# With scope and inputs
splunkctl soar playbooks run my_playbook --container 42 \
  --scope new --input ip=1.2.3.4 --input domain=evil.com --yes

# Wait for completion (polls until terminal status)
splunkctl soar playbooks run my_playbook --container 42 \
  --wait --timeout 120 --yes
```

The `run` command is a guarded mutation: without `--yes` it previews the
POST body and exits. The `--wait` flag polls `GET /rest/playbook_run/<id>`
until the status reaches `success`, `failed`, or `cancelled`. When the
`message` field parses as JSON it is pretty-printed.

**Scope**: `all` (default) runs the playbook against all artifacts in the
container; `new` limits to artifacts not yet processed.

## List playbook runs

```bash
# All runs
splunkctl soar playbooks runs list

# Filter by container and/or status
splunkctl soar playbooks runs list --container 42 --status failed
```

## Get a playbook run

```bash
# Run detail
splunkctl soar playbooks runs get 101

# Block-level results
splunkctl soar playbooks runs get 101 --blocks
```

## Cancel a run

```bash
# Guarded — dry-run by default
splunkctl soar playbooks runs cancel 101 --yes
```

## API reference

| Operation | Endpoint | Notes |
|---|---|---|
| Run | `POST /rest/playbook_run` | `{playbook_id, container_id, scope, run: true, inputs?}` |
| Poll | `GET /rest/playbook_run/<id>` | Terminal: success, failed, cancelled |
| Block results | `GET /rest/playbook_run/<id>/block_results` | Per-block status and output |
| Cancel | `POST /rest/playbook_run/<id>` | `{cancel: true}` |
| Resolve name | `GET /rest/playbook?_filter_name="<name>"` | Returns playbook metadata with id |

Bogus `playbook_id` returns HTTP 404 with `"Playbook \"N\" not found"` --
the server validates the id before creating a run.
