# soar lists -- Custom Lists (decided_list)

Manage SOAR custom lists (the `decided_list` API). Custom lists are
simple tabular data structures stored as an array of rows, where each
row is an array of string values.

## Quick reference

```bash
# List all custom lists
splunkctl soar lists list
splunkctl soar lists list --limit 10

# Get a list by name or ID (shows metadata + content)
splunkctl soar lists get blocklist
splunkctl soar lists get 42

# Create with initial content from a JSON file
# JSON format: [["col1","col2"],["a","b"],["c","d"]]
splunkctl soar lists create --name my_list --file rows.json

# Create from CSV (parsed client-side into array-of-rows)
splunkctl soar lists create --name my_list --file data.csv

# Update (FULL REPLACE -- all existing rows are overwritten)
splunkctl soar lists update my_list --file new_rows.json

# Add a single row (fetch-modify-replace)
splunkctl soar lists add-row my_list --values "val1,val2,val3"

# Add a row with values that contain commas (JSON array form)
splunkctl soar lists add-row my_list --values '["val, with comma","val2"]'

# Remove a row by 0-based index (fetch-modify-replace)
splunkctl soar lists remove-row my_list --index 2

# Delete a list by name or ID (token auth is allowed for this endpoint)
splunkctl soar lists delete 42
splunkctl soar lists delete blocklist

# Export as JSON (content array only)
splunkctl soar lists export my_list
splunkctl soar lists export my_list --out backup.json

# Export as CSV (uses the formatted_content API route)
splunkctl soar lists export my_list --format csv
splunkctl soar lists export my_list --format csv --out backup.csv

# Import: creates if new, updates (full-replace) if exists
splunkctl soar lists import --name my_list --file rows.json
splunkctl soar lists import --name my_list --file data.csv
```

## Concepts

### Content format

The SOAR `decided_list` API stores content as a JSON array of arrays
(rows of string values). The server rejects `text/csv` -- all content
is sent as JSON. The CLI handles CSV-to-JSON conversion client-side
when you pass a `.csv` file to `--file`.

### Full-replace semantics

The `update` command replaces **all** content in the list. There is no
partial merge. The dry-run preview states this explicitly. Use
`add-row` and `remove-row` for incremental edits -- they fetch the
current content, modify it, and POST the full replacement.

### Name resolution

The `get`, `update`, `add-row`, `remove-row`, `delete`, and `export`
commands accept either a numeric ID or a list name. Names are resolved via a
`_filter_name` query against the API.

### Token auth on DELETE

Unlike most SOAR endpoints, `decided_list` DELETE accepts automation
token auth (no Basic auth required). This is the only SOAR DELETE
endpoint with this exception.

## File formats

### JSON input (--file)

Array of arrays, each inner array is one row:

```json
[
  ["header1", "header2"],
  ["value1", "value2"],
  ["value3", "value4"]
]
```

### CSV input (--file)

Standard CSV. The header row becomes the first element of the content
array (SOAR custom lists do not distinguish headers from data):

```csv
header1,header2
value1,value2
value3,value4
```

## Mutations

All mutations are dry-run by default. Pass `--yes` to apply. The
dry-run preview shows the SOAR host and the operation details.
