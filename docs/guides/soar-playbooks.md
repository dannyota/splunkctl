<!-- summary: Export, import, run, and monitor Splunk SOAR playbooks and keep them as code in version control. -->

# Run playbooks

When to use: you want to run a playbook against a container and watch it finish, enable or disable playbooks and set their triggers, or keep playbooks as code: export the bundle, edit the Python in git, and import it back.

## Prerequisites

- SOAR credentials in the active profile and a passing `splunkctl soar test` (see [Set up and check SOAR](soar.md)).
- Username and password credentials for `delete`; SOAR 8.5 exposes no working REST deletion, so the CLI logs in through the Web UI, which refuses automation tokens.
- A container id for `run` (`splunkctl soar containers list`).
- For `import`: a playbook bundle, either a `.tgz` or a directory with `<name>.json` (metadata, COA graph, labels, trigger config) and `<name>.py` (Python code with `@phantom.playbook_block()` functions).

## Synopsis

```text
splunkctl soar playbooks list [--active] [--label LABEL] [--repo NAME]
splunkctl soar playbooks get <PLAYBOOK_ID>
splunkctl soar playbooks enable <PLAYBOOK_ID> [--yes]
splunkctl soar playbooks disable <PLAYBOOK_ID> [--cancel-runs] [--yes]
splunkctl soar playbooks trigger <PLAYBOOK_ID> --on <artifact_created|container_resolved> [--yes]
splunkctl soar playbooks run <PLAYBOOK_ID_OR_NAME> --container <CONTAINER_ID> [--scope all|new] [--input KEY=VALUE]... [--wait] [--timeout SECONDS] [--yes]
splunkctl soar playbooks runs list [--container CONTAINER_ID] [--status pending|running|success|failed] [--limit N]
splunkctl soar playbooks runs get <RUN_ID> [--blocks]
splunkctl soar playbooks runs cancel <RUN_ID> [--yes]
splunkctl soar playbooks export <PLAYBOOK_ID_OR_NAME> [--out DIR] [--unpack]
splunkctl soar playbooks import <PATH.tgz | DIR/> [--scm NAME] [--force|--no-force] [--yes]
splunkctl soar playbooks delete <PLAYBOOK_ID_OR_NAME>... [--yes]
splunkctl soar playbooks repos
splunkctl soar playbooks sync <REPO_ID> [--yes]
```

## Workflow

### List and inspect playbooks

```bash
splunkctl soar playbooks list
splunkctl soar playbooks list --active
splunkctl soar playbooks list --label events
splunkctl soar playbooks list --repo local
splunkctl soar playbooks get 10 --json
```

Expected result: filters combine with AND. `--active` uses the SOAR boolean filter (`_filter_active=True`), `--label` matches the playbook's `labels[]` array, `--repo` filters by SCM repo name. `get` returns the full object including the `coa` graph, labels, trigger configuration, and `draft_mode`.

### Run a playbook against a container

> **Safety:** Target is the SOAR host in the active profile. Impact: the playbook's blocks execute against the container's artifacts, including any containment actions it contains. Preview with `splunkctl soar playbooks run my_playbook --container 42` and read the POST body, apply by adding `--yes`, and verify with `splunkctl soar playbooks runs list --container 42`.

```bash
splunkctl soar playbooks run my_playbook --container 42 --yes
splunkctl soar playbooks run 7 --container 42 --yes
splunkctl soar playbooks run my_playbook --container 42 \
  --scope new --input ip=1.2.3.4 --input domain=evil.com --yes
splunkctl soar playbooks run my_playbook --container 42 \
  --wait --timeout 120 --yes
```

Expected result: a `POST /rest/playbook_run` with `{playbook_id, container_id, scope, run: true, inputs?}` and the run id. A name is resolved through `GET /rest/playbook?_filter_name=...`. `--scope all` (default) runs against every artifact in the container; `new` limits to artifacts not yet processed. `--wait` polls `GET /rest/playbook_run/<id>` until the status reaches `success`, `failed`, or `cancelled` (default timeout 300 seconds); when the `message` field parses as JSON it is pretty-printed. A bogus playbook id returns 404 `"Playbook \"N\" not found"`; the server validates the id before creating a run.

### Monitor and cancel runs

> **Safety:** Target is the SOAR host in the active profile. Impact: `runs cancel` stops an in-progress run part way through its blocks. Preview with `splunkctl soar playbooks runs cancel 101`, apply by adding `--yes`, and verify with `splunkctl soar playbooks runs get 101`.

```bash
splunkctl soar playbooks runs list
splunkctl soar playbooks runs list --container 42 --status failed
splunkctl soar playbooks runs get 101
splunkctl soar playbooks runs get 101 --blocks
splunkctl soar playbooks runs cancel 101 --yes
```

Expected result: `runs get` shows the run detail; `--blocks` adds per-block status and output from `/rest/playbook_run/<id>/block_results`; `cancel` posts `{cancel: true}` to the run.

### Enable, disable, or set the trigger

> **Safety:** Target is the SOAR host in the active profile. Impact: `enable` makes the playbook fire on its trigger for every matching container; `disable --cancel-runs` also stops running instances; `trigger` changes when it fires. Preview with `splunkctl soar playbooks enable 10`, apply by adding `--yes`, and verify with `splunkctl soar playbooks get 10 --json`.

```bash
splunkctl soar playbooks enable 10 --yes
splunkctl soar playbooks disable 10 --yes
splunkctl soar playbooks disable 10 --cancel-runs --yes
splunkctl soar playbooks trigger 10 --on artifact_created --yes
splunkctl soar playbooks trigger 10 --on container_resolved --yes
```

Expected result: `enable` sets `active: true`, `disable` sets `active: false`. Playbooks in `draft_mode: true` cannot be activated; the CLI adds a hint when the server rejects the enable. Re-import without `draft_mode` or finalize it in the Visual Playbook Editor first. `artifact_created` fires when an artifact is added, `container_resolved` on resolution. The `label` trigger seen in playbook metadata is import-only; the REST endpoint rejects setting it ("playbook_trigger is set to an invalid enum"), so it is not an accepted `--on` value.

### Export a playbook

```bash
splunkctl soar playbooks export 10 > playbook.tgz
splunkctl soar playbooks export 10 --out ./exports/
splunkctl soar playbooks export 10 --unpack --out ./pb/
splunkctl soar playbooks export my_playbook --unpack --out ./pb/
```

Expected result: the bundle from `GET /rest/playbook/<id>/export`, written raw to stdout or as a tgz under `--out`; `--unpack` extracts `<name>.json` and `<name>.py` into the directory. A non-numeric identifier is looked up by exact scoped name (`<dir>/<module>`) first, then as a suffix match on the bare module name (`export my_playbook` finds `my-repo-dir/my_playbook`). Ambiguous or missing names return an error.

### Import a playbook

> **Safety:** Target is the SOAR host in the active profile. Impact: the playbook is created in `--scm` (default `local`) or, with the default `--force`, overwrites the existing one of the same name. Preview with `splunkctl soar playbooks import ./my_playbook/`, apply by adding `--yes`, and verify with `splunkctl soar playbooks list --json | jq '.[] | select(.name=="my_playbook")'`.

```bash
splunkctl soar playbooks import ./my_playbook/ --yes
splunkctl soar playbooks import ./my_playbook.tgz --yes
splunkctl soar playbooks import ./pb/ --scm my_repo --yes
splunkctl soar playbooks import ./pb/ --no-force --yes
```

Expected result: a directory is packed into a tgz on the fly; the payload is base64-encoded and posted to `/rest/import_playbook` as `{playbook, scm, force}`. `--no-force` refuses to overwrite.

### Keep playbooks as code

> **Safety:** Target is the SOAR host in the active profile. Impact: step 5 overwrites the playbook on the instance with the edited bundle. Preview with step 4 (no `--yes`), apply with step 5, and verify with step 6.

```bash
splunkctl soar playbooks export my_playbook --unpack --out ./pb/
$EDITOR ./pb/my_playbook/my_playbook.py
cd ./pb && git add . && git commit -m "Update playbook logic" && cd ..
splunkctl soar playbooks import ./pb/my_playbook/
splunkctl soar playbooks import ./pb/my_playbook/ --yes
splunkctl soar playbooks list --json | jq '.[] | select(.name=="my_playbook")'
```

Expected result: the export and import pair gives a full as-code loop. Keep hand edits to the Python between the `## Custom Code Start` and `## Custom Code End` markers so the Visual Playbook Editor keeps them. [Manage configuration as code](state.md) pulls and pushes every playbook as the `soar-playbooks` type.

### Delete playbooks

> **Safety:** Target is the SOAR host in the active profile. Impact: the playbooks are removed irreversibly. Preview with `splunkctl soar playbooks delete local/old_pb` (the preview lists the identifiers as typed and needs no connectivity), apply by adding `--yes`, and verify with `splunkctl soar playbooks list`.

```bash
splunkctl soar playbooks export 10 --out ./backup/
splunkctl soar playbooks delete 10 --yes
splunkctl soar playbooks delete local/old_pb --yes
splunkctl soar playbooks delete 10 11 12 --yes
```

Expected result: `DELETE /rest/playbook/<id>` returns 405 and a POST with `{"delete": true}` reports success without removing anything on SOAR 8.5, so the command uses the browser's route: a Django Web UI login (CSRF cookie) followed by `POST /playbooks` with `{ids, delete: true}`. Because deletion is irreversible, names never suffix-match: pass the exact scoped name (`<dir>/<module>`) or the numeric id; a bare module name that only matches as a suffix returns a did-you-mean error carrying the full name and id. Name resolution happens at apply time. The command prints the server's per-playbook change and error report and exits 1 if any deletion failed.

### List and sync SCM repositories

> **Safety:** Target is the SOAR host in the active profile. Impact: `sync` pulls and force-syncs the repo from its remote, replacing playbooks on the instance with the remote's versions. Preview with `splunkctl soar playbooks sync 1`, apply by adding `--yes`, and verify with `splunkctl soar playbooks list --repo <NAME>`.

```bash
splunkctl soar playbooks repos
splunkctl soar playbooks sync 1 --yes
```

Expected result: `repos` lists SCM repositories from `GET /rest/scm` (the lab ships one `local` repo at `file:////opt/phantom/scm/git/local`). `sync` posts to `/rest/scm/<id>` and is meant for HTTPS or SSH repos with a real remote. The built-in local repo has no remote, so the server rejects the sync with HTTP 400 "Remote named 'origin' didn't exist" on SOAR 8.5 (older versions return 500 "Operation not supported"); that is expected. Use `import` for local deployment.

## Troubleshooting

- `not_found` on `run` or `export` by name: no playbook matches; list with `splunkctl soar playbooks list` and use the id or the scoped `<dir>/<module>` name.
- `http` error on `enable` with the draft_mode hint: the playbook is a draft; re-import it without `draft_mode` or finalize it in the Visual Playbook Editor.
- `auth` on `delete` while everything else works: the profile has only an automation token; add a username and password with `splunkctl config init --soar`.
- Did-you-mean error on `delete`: you passed a bare module name; repeat the command with the full scoped name or id from the message.
- `http` 400 "Remote named 'origin' didn't exist" on `sync`: the repo is the local one; use `import`.
- `run --wait` exits 1: the run ended `failed` or `cancelled`, or `--timeout` elapsed; read `splunkctl soar playbooks runs get <RUN_ID> --blocks`.
- `http` 400 "playbook_trigger is set to an invalid enum": `--on label` is not supported; set the label in the playbook JSON and import it.

## See also

- [Work SOAR incidents](soar-incidents.md)
- [Run actions](soar-actions.md)
- [Manage custom functions](soar-functions.md)
- [Handle approvals](soar-approvals.md)
- [Manage configuration as code](state.md)
- [Set up and check SOAR](soar.md)
- [Command reference: soar](../commands/soar.md)
