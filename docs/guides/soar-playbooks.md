# SOAR Playbooks

Playbook lifecycle and playbooks-as-code workflow on Splunk SOAR via the
REST API. Export, edit in git, import back -- the first programmatic
playbook management loop.

## List

```bash
splunkctl soar playbooks list                     # all playbooks
splunkctl soar playbooks list --active            # only active
splunkctl soar playbooks list --label events      # by label
splunkctl soar playbooks list --repo local        # by SCM repo
splunkctl soar playbooks list --json
```

Filters compose (AND). `--active` uses the SOAR boolean filter
(`_filter_active=True`). `--label` matches against the playbook's
`labels[]` array. `--repo` filters by the SCM repo name.

## Get

```bash
splunkctl soar playbooks get 10                   # by numeric ID
splunkctl soar playbooks get 10 --json
```

Returns the full playbook object including `coa` graph, labels, trigger
configuration, and `draft_mode` status.

## Enable / Disable

```bash
splunkctl soar playbooks enable 10 --yes
splunkctl soar playbooks disable 10 --yes
splunkctl soar playbooks disable 10 --cancel-runs --yes
```

Enable sets `active: true`; disable sets `active: false`. Pass
`--cancel-runs` to stop any running instances when disabling.

**draft_mode caveat**: playbooks in `draft_mode: true` cannot be
activated. The CLI surfaces this with a hint if the server rejects the
enable. Re-import the playbook without `draft_mode` or finalize it in
the Visual Playbook Editor first.

Guarded: dry-run by default, `--yes` to apply.

## Trigger

```bash
splunkctl soar playbooks trigger 10 --on label --yes
splunkctl soar playbooks trigger 10 --on artifact_created --yes
splunkctl soar playbooks trigger 10 --on container_resolved --yes
```

Sets the automation trigger type. `label` triggers on container ingest
(label match). `artifact_created` triggers when an artifact is added.
`container_resolved` triggers on resolution.

Guarded: dry-run by default, `--yes` to apply.

## Export

```bash
splunkctl soar playbooks export 10 > playbook.tgz       # raw tgz
splunkctl soar playbooks export 10 --out ./exports/      # write tgz file
splunkctl soar playbooks export 10 --unpack --out ./pb/  # extract json+py
splunkctl soar playbooks export my_playbook              # by name
```

Downloads the playbook bundle via `GET /rest/playbook/<id>/export`.
Without `--unpack`, writes raw tgz (to stdout or `--out`). With
`--unpack`, extracts the `<name>.json` metadata and `<name>.py` code
into the output directory.

Non-numeric identifiers trigger a name lookup first; if the name is
ambiguous or not found, an error is returned.

## Import

```bash
splunkctl soar playbooks import ./my_playbook/ --yes     # from directory
splunkctl soar playbooks import ./my_playbook.tgz --yes  # from tgz
splunkctl soar playbooks import ./pb/ --scm my_repo --yes
splunkctl soar playbooks import ./pb/ --no-force --yes   # no overwrite
```

Imports a playbook bundle via `POST /rest/import_playbook`. Accepts a
directory (packed into tgz on the fly) or an existing tgz file. The
payload is base64-encoded and posted with `{playbook, scm, force}`.

- `--scm` (default: `local`) sets the target SCM repository.
- `--force/--no-force` (default: force) controls overwrite behavior.

Guarded: dry-run by default, `--yes` to apply.

## Playbooks-as-Code Workflow

The export/import pair enables a full as-code loop:

```bash
# 1. Export the playbook
splunkctl soar playbooks export my_playbook --unpack --out ./pb/

# 2. Edit the Python code (between Custom Code markers)
$EDITOR ./pb/my_playbook/my_playbook.py

# 3. Commit to git
cd ./pb && git add . && git commit -m "Update playbook logic"

# 4. Re-import
splunkctl soar playbooks import ./pb/my_playbook/ --yes

# 5. Verify
splunkctl soar playbooks list --json | jq '.[] | select(.name=="my_playbook")'
```

A playbook bundle consists of a `<name>.json` (metadata, COA graph,
labels, trigger config) paired with a `<name>.py` (Python code with
`@phantom.playbook_block()` functions). Hand-edits to the Python code
should stay between the `## Custom Code Start` / `## Custom Code End`
markers.

## SCM Repos

```bash
splunkctl soar playbooks repos                    # list all repos
splunkctl soar playbooks repos --json
```

Lists SCM repositories via `GET /rest/scm`. The lab ships with one
`local` repo (`file:////opt/phantom/scm/git/local`).

## Sync

```bash
splunkctl soar playbooks sync 1 --yes             # sync repo id 1
```

Triggers a pull + force sync on an external SCM repo via
`POST /rest/scm/<id>`. Designed for HTTPS/SSH repos that have a real
remote to pull from.

**Local repo caveat**: the built-in local repo (`file://` URI) returns
500 "Operation not supported" because there is no remote to pull from.
This is expected behavior, not a bug. Use `import` instead for local
playbook deployment.

Guarded: dry-run by default, `--yes` to apply.

## Seed Playbook

The test suite includes a minimal valid playbook bundle at
`tests/soar/fixtures/splunkctl_seed_noop/` -- a no-op start-to-end
automation playbook (`splunkctl_seed_noop.json` + `.py`). It serves as:

- A round-trip test fixture (import then export, compare)
- A seed for the lab (imported and left in place for playbook-run tests)

## Implementation Notes

- Uses `SOARClient.get_bytes()` for export (binary tgz download).
- Import packs directories into tgz with `tarfile`, base64-encodes, and
  POSTs to `import_playbook`.
- Name resolution on export uses a filter query, not a list scan.
- All mutations go through `guard.soar_check()` with the SOAR host
  banner.

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
