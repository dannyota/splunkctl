<!-- summary: List, inspect, import, export, and update Splunk SOAR custom functions. -->

# Manage custom functions

When to use: your playbooks call a SOAR custom function (a reusable Python snippet) and you want to back it up, deploy it from a repository, replace its source with a reviewed change, or remove it.

## Prerequisites

- SOAR credentials in the active profile and a passing `splunkctl soar test` (see [Set up and check SOAR](soar.md)).
- At least one SCM repository on the instance (`splunkctl soar playbooks repos`); the lab ships a `local` repo. `update` needs it to resolve the repo id through `GET /rest/scm`.
- Username and password credentials for `delete`; SOAR refuses automation tokens on DELETE endpoints.
- For `import`: a `.tgz` in SOAR's export format, or a directory holding the paired `<name>.json` (metadata: name, module, description, parameters, outputs, python_version) and `<name>.py` (the function body). This is the same pair shape playbooks use under `custom_functions/`.

## Synopsis

```text
splunkctl soar functions list [--limit N] [--offset N]
splunkctl soar functions get <FUNCTION_ID>
splunkctl soar functions export <FUNCTION_ID> [--out FILE.tgz]
splunkctl soar functions import <PATH.tgz | DIR/> [--yes]
splunkctl soar functions update <FUNCTION_ID> --python <FILE.py> --message <TEXT> [--yes]
splunkctl soar functions delete <FUNCTION_ID> [--yes]
```

## Workflow

### List and inspect functions

```bash
splunkctl soar functions list
splunkctl soar functions list --limit 10 --offset 0
splunkctl soar functions get 42
splunkctl soar functions get 42 --json
```

Expected result: one row per custom function; `get --json` includes the Python source.

### Back up a function

```bash
splunkctl soar functions export 42 --out function.tgz
splunkctl soar functions export 42 > function.tgz
```

Expected result: a tgz (`GET /rest/custom_function/<id>/export`, served as `application/x-gzip`) containing the paired `.json` and `.py` files. Export before `update` or `delete` so you can import the previous version.

### Import a function

> **Safety:** Target is the SOAR host in the active profile. Impact: the function is created, or overwritten when one with the same name exists, because the import posts with `force: true`; playbooks pick up the new code on their next run. Preview with `splunkctl soar functions import ./my_function.tgz`, apply by adding `--yes`, and verify with `splunkctl soar functions list`.

```bash
splunkctl soar functions import ./my_function.tgz
splunkctl soar functions import ./my_function.tgz --yes
splunkctl soar functions import ./my_function/ --yes
```

Expected result: a directory is packed into a tgz automatically; the archive is base64-encoded and posted to `/rest/import_custom_function` with `scm: "local"` and `force: true`. Functions that fail validation are saved as drafts.

### Replace the Python source

> **Safety:** Target is the SOAR host in the active profile. Impact: the function body changes for every playbook that calls it; there is no server-side rollback except your export. Preview with `splunkctl soar functions update 42 --python ./updated_logic.py --message "Fix edge case in IP formatting"`, apply by adding `--yes`, and verify with `splunkctl soar functions get 42 --json`.

```bash
splunkctl soar functions export 42 --out before.tgz
splunkctl soar functions update 42 \
    --python ./updated_logic.py \
    --message "Fix edge case in IP formatting" --yes
```

Expected result: the CLI resolves the SCM repo id through `GET /rest/scm`, fetches the existing record, and posts only the changed fields (`python`, `commit_message`, `scm_id`). Functions imported as Python 2.7 are upgraded to Python 3 on update, because SOAR 8.x refuses to edit Python 2.7 functions. A function saved as a draft on import may leave draft mode once the new source passes validation, depending on its signature.

### Delete a function

> **Safety:** Target is the SOAR host in the active profile. Impact: the function is removed and playbooks that call it fail on their next run. Preview with `splunkctl soar functions delete 42`, apply by adding `--yes`, and verify with `splunkctl soar functions list`.

```bash
splunkctl soar functions export 42 --out before.tgz
splunkctl soar functions delete 42 --yes
```

Expected result: a DELETE that succeeds only with username and password credentials in the profile.

## Troubleshooting

- `not_found` on `get`, `export`, `update`, or `delete`: commands take the numeric id from `splunkctl soar functions list`, not the name.
- `update` exits 1 before posting with a message about SCM: the instance has no SCM repository; add one in the SOAR UI or check `splunkctl soar playbooks repos`.
- `auth` on `delete` while reads work: the profile is token-only; add a username and password with `splunkctl config init --soar`.
- `import` reports the function as a draft: validation failed; fix the `.json` metadata or the source and import again with `--yes`.
- `http` error on `import` about the archive: check that the directory or tgz holds the paired `<name>.json` and `<name>.py` with matching names.

## See also

- [Run playbooks](soar-playbooks.md)
- [Maintain custom lists](soar-lists.md)
- [Set up and check SOAR](soar.md)
- [Command reference: soar](../commands/soar.md)
