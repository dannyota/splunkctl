<!-- summary: Create, export, import, and edit Splunk SOAR custom lists row by row, with the full-replace behaviour of update made explicit before you apply it. -->

# Maintain custom lists

When to use: your playbooks read a SOAR custom list (an allowlist, blocklist, or lookup table) and you need to add or remove rows, replace the whole list from a file, or back it up as JSON or CSV.

## Prerequisites

- SOAR credentials in the active profile and a passing `splunkctl soar test` (see [Set up and check SOAR](soar.md)).
- For `create`, `update`, and `import`: a JSON or CSV file with at least one row (formats below).
- `delete` works with an automation token; `decided_list` is the one SOAR DELETE endpoint that accepts token auth.

## Synopsis

```text
splunkctl soar lists list [--limit N]
splunkctl soar lists get <NAME_OR_ID>
splunkctl soar lists create --name <NAME> --file <ROWS.json|ROWS.csv> [--yes]
splunkctl soar lists update <NAME_OR_ID> --file <ROWS.json|ROWS.csv> [--yes]
splunkctl soar lists add-row <NAME_OR_ID> --values <"a,b,c" | '["a, b","c"]'> [--yes]
splunkctl soar lists remove-row <NAME_OR_ID> --index <N> [--yes]
splunkctl soar lists export <NAME_OR_ID> [--format json|csv] [--out FILE]
splunkctl soar lists import --name <NAME> --file <ROWS.json|ROWS.csv> [--yes]
splunkctl soar lists delete <NAME_OR_ID> [--yes]
```

`get`, `update`, `add-row`, `remove-row`, `export`, and `delete` accept a numeric id or a list name; names are resolved through a `_filter_name` query.

## Workflow

### Read a list

```bash
splunkctl soar lists list
splunkctl soar lists get blocklist
splunkctl soar lists get 42 --json
```

Expected result: list metadata plus its rows. Content is an array of rows, each row an array of strings; SOAR does not distinguish a header row from data.

### Back up a list

```bash
splunkctl soar lists export blocklist --out backup.json
splunkctl soar lists export blocklist --format csv --out backup.csv
```

JSON export writes the content array only. CSV uses SOAR's `formatted_content` route. Export before any `update` or `import` so you can restore the previous rows.

### Create a list from a file

> **Safety:** Target is the SOAR host in the active profile. Impact: a new custom list that playbooks can read immediately. Preview with `splunkctl soar lists create --name my_list --file rows.json`, apply by adding `--yes`, and verify with `splunkctl soar lists get my_list`.

```bash
splunkctl soar lists create --name my_list --file rows.json
splunkctl soar lists create --name my_list --file rows.json --yes
splunkctl soar lists create --name my_list --file data.csv --yes
```

JSON input is an array of arrays:

```json
[
  ["header1", "header2"],
  ["value1", "value2"],
  ["value3", "value4"]
]
```

CSV input is parsed client side into the same shape; the header row becomes the first row:

```csv
header1,header2
value1,value2
value3,value4
```

The SOAR API rejects `text/csv`, so all content is sent as JSON.

### Add or remove one row

> **Safety:** Target is the SOAR host in the active profile. Impact: the CLI fetches the current rows, changes one, and posts the full list back; rows changed in the UI between fetch and post are overwritten. Preview with `splunkctl soar lists add-row my_list --values "val1,val2,val3"`, apply by adding `--yes`, and verify with `splunkctl soar lists get my_list`.

```bash
splunkctl soar lists add-row my_list --values "val1,val2,val3" --yes
splunkctl soar lists add-row my_list --values '["val, with comma","val2"]' --yes
splunkctl soar lists remove-row my_list --index 2 --yes
```

`--values` takes comma-separated values, or a JSON array when a value contains a comma. `--index` is 0-based within the content array, so the header row is index 0.

### Replace a whole list

> **Safety:** Target is the SOAR host in the active profile. Impact: every existing row is overwritten; there is no merge. Preview with `splunkctl soar lists update my_list --file new_rows.json` and read the row count in the preview, apply by adding `--yes`, and verify with `splunkctl soar lists get my_list`.

```bash
splunkctl soar lists export my_list --out before.json
splunkctl soar lists update my_list --file new_rows.json
splunkctl soar lists update my_list --file new_rows.json --yes
```

### Import from a repository

> **Safety:** Target is the SOAR host in the active profile. Impact: the list is created if it does not exist, otherwise fully replaced. Preview with `splunkctl soar lists import --name my_list --file rows.json`, apply by adding `--yes`, and verify with `splunkctl soar lists get my_list`.

```bash
splunkctl soar lists import --name my_list --file rows.json
splunkctl soar lists import --name my_list --file data.csv --yes
```

`import` is the command to use from CI, because it is idempotent for a given file.

### Delete a list

> **Safety:** Target is the SOAR host in the active profile. Impact: the list is removed and playbooks that read it start failing. Preview with `splunkctl soar lists delete blocklist`, apply with `splunkctl soar lists delete blocklist --yes`, and verify with `splunkctl soar lists list`.

```bash
splunkctl soar lists export blocklist --out blocklist.json
splunkctl soar lists delete blocklist
splunkctl soar lists delete 42 --yes
```

## Troubleshooting

- `not_found` by name: run `splunkctl soar lists list` and check the exact name, or use the id.
- `create` rejects the file: it needs at least one row, and JSON must be an array of arrays of strings.
- A value with a comma was split in `add-row`: pass `--values` as a JSON array.
- Rows disappeared after `update`: `update` is a full replace; restore from your export with `splunkctl soar lists update <NAME> --file before.json --yes`.

## See also

- [Run playbooks](soar-playbooks.md)
- [Look up indicators and evidence](soar-indicators.md)
- [Set up and check SOAR](soar.md)
- [Command reference: soar](../commands/soar.md)
