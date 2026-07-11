# soar functions -- custom function management

Manage SOAR custom functions: list, inspect, import, export, update, and
delete. Custom functions are reusable Python snippets called from playbook
blocks. Each function is a paired `<name>.json` (metadata) + `<name>.py`
(source) stored in the SOAR SCM repository.

## List custom functions

```bash
splunkctl soar functions list
splunkctl soar functions list --limit 10 --offset 0
```

## Get a custom function

```bash
splunkctl soar functions get 42          # by numeric id
splunkctl soar functions get 42 --json   # includes python source
```

## Import a custom function

Accept a `.tgz` archive (same format as SOAR export) or a directory
containing the paired `.json` + `.py` files. Directories are packed
into a tgz automatically.

```bash
# From a tgz archive
splunkctl soar functions import ./my_function.tgz
splunkctl --yes soar functions import ./my_function.tgz

# From a directory
splunkctl --yes soar functions import ./my_function/
```

The archive is base64-encoded and posted to `/rest/import_custom_function`
with `scm: "local"` and `force: true`. Imported functions that fail
validation are saved as drafts.

## Export a custom function

```bash
splunkctl soar functions export 42 --out function.tgz
splunkctl soar functions export 42 > function.tgz
```

Exports via `GET /rest/custom_function/<id>/export` (returns
`application/x-gzip`). The archive contains the paired `.json` +
`.py` files.

## Update a custom function

Replace the Python source of an existing function. Requires `--python`
(path to the new source file) and `--message` (SCM commit message).
The command resolves the SCM repo id automatically via `GET /rest/scm`,
fetches the existing record, and posts only the changed fields.

```bash
splunkctl --yes soar functions update 42 \
    --python ./updated_logic.py \
    --message "Fix edge case in IP formatting"
```

Quirks:

- **SCM required**: the SOAR instance must have at least one SCM
  repository configured (the lab has a `local` repo by default).
- **Python version upgrade**: functions imported as Python 2.7 are
  automatically upgraded to Python 3 on update (SOAR 8.x refuses to
  edit Python 2.7 functions).
- **Draft mode**: functions that fail validation on import are saved as
  drafts; updating the source may resolve validation and clear draft
  mode, depending on the function signature.

## Delete a custom function

```bash
splunkctl --yes soar functions delete 42
```

DELETE requires Basic auth credentials (SOAR refuses automation tokens
on DELETE endpoints).

## Pair anatomy

A custom function is stored as two files in the SCM repo:

- `<name>.json` -- metadata (name, module, description, parameters,
  outputs, python_version)
- `<name>.py` -- Python source (the function body)

This is the same pair shape used by playbooks under
`custom_functions/`. The export bundle is a tgz of this pair.
