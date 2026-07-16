# soar cases -- case management, workbook phases & tasks

Promote containers to cases with workbook templates, view phase/task
structure, and manage individual phases and tasks. Cases are containers
with `container_type=case` and an attached workbook (phases and tasks).

## Promote a container to a case

Promote an existing container (event) to a case with a workbook template.
The promotion is a single atomic POST that sets `container_type` and
instantiates all phases/tasks from the template.

```bash
# Use the server's default template (NIST 800-61 on most instances)
splunkctl --yes soar cases promote 42

# Specify a template by name
splunkctl --yes soar cases promote 42 --template "NIST 800-61"

# Specify a template by numeric id
splunkctl --yes soar cases promote 42 --template 3
```

Template resolution: `--template` accepts a name (case-sensitive) or
numeric id. Without `--template`, the server's default template
(`is_default=true`) is used. If no default exists, the command errors
with the list of available templates.

## View workbook phases and tasks

```bash
splunkctl soar cases workbook 42
splunkctl --json soar cases workbook 42
```

Returns all phases with their nested tasks. Each task shows `status`
(0=incomplete, 1=in_progress, 2=complete), owner, description, and
notes.

## Add a phase

```bash
splunkctl --yes soar cases phase add --container 42 --name "Recovery"
splunkctl --yes soar cases phase add --container 42 --name "Recovery" --order 3
```

Posts to `/rest/workbook_phase` with `container_id`, `name`, and
optional `order`.

## Add a task

```bash
splunkctl --yes soar cases task add --phase-id 13 --name "Review logs"
splunkctl --yes soar cases task add --phase-id 13 --name "Review logs" \
    --description "Check all relevant logs" --order 5
```

Posts to `/rest/workbook_task`. The field name is `phase_id` (not
`phase`).

## Update a task

```bash
# Mark complete (0 -> 2, no note required)
splunkctl --yes soar cases task update 100 --status complete

# Mark incomplete
splunkctl --yes soar cases task update 100 --status incomplete

# Mark in_progress (requires a closing note; only allowed FROM
# complete — the server rejects 0 -> 1, so complete the task first)
splunkctl --yes soar cases task update 100 --status in_progress \
    --note "Reopening for active investigation"

# Assign owner
splunkctl --yes soar cases task update 100 --owner analyst

# Combine status + owner + note
splunkctl --yes soar cases task update 100 --status in_progress \
    --owner analyst --note "Taking over investigation"
```

### Task status codes

| Name | Integer | Note required |
|---|---|---|
| `incomplete` | 0 | No |
| `in_progress` | 1 | Yes |
| `complete` | 2 | No |

The `--status` flag accepts human-readable names; the CLI maps them to
the integer codes the SOAR API expects. The server only allows the
transitions 0 -> 2 (complete) and 2 -> 1 (reopen as in-progress);
0 -> 1 is rejected with "Invalid status transition". The `in_progress`
transition also requires a closing note -- the CLI enforces this
client-side with a clear error message before making any API call.

### Closing notes

When `--note` accompanies `--status`, the note is sent INLINE in the
task POST (field `note`) -- the server rejects note-requiring
transitions otherwise, and the inline note still lands as a regular
task note. A `--note` without `--status` posts to `/rest/note` with
`task_id` set; the task's `container_id` is resolved automatically via
a GET on the task.

## Workbook templates

SOAR ships with 10 preloaded workbook templates. The default is
NIST 800-61 (5 phases, 19 tasks). Templates are managed via the
`soar workbook-templates` subgroup.

### List templates

```bash
splunkctl soar workbook-templates list
splunkctl --json soar workbook-templates list --limit 5
```

### Get a template by name or id

```bash
splunkctl soar workbook-templates get "NIST 800-61"
splunkctl --json soar workbook-templates get 1
```

Name resolution is case-sensitive. Numeric arguments are treated
as ids directly; non-numeric arguments trigger a name lookup.

### Create a template

```bash
splunkctl --yes soar workbook-templates create \
    --name "IR Workflow" --phases "Detect,Contain,Eradicate,Recover"
```

Phases are created in the order given, numbered starting at 1.
At least one phase is required.

### Update a template (add phases)

```bash
splunkctl --yes soar workbook-templates update "NIST 800-61" \
    --add-phase "Lessons Learned"

# Multiple phases
splunkctl --yes soar workbook-templates update 2 \
    --add-phase Eradicate --add-phase Recover
```

New phases are appended after the highest existing order value.

### Delete a template

```bash
splunkctl --yes soar workbook-templates delete "Custom Investigation"
splunkctl --yes soar workbook-templates delete 3
```

DELETE on `workbook_template` requires Basic auth (username/password
credentials) -- SOAR refuses token auth on most DELETE endpoints.
Ensure your profile has `username` and `password` configured.

## API endpoints used

| Operation | Method | Endpoint |
|---|---|---|
| Promote | POST | `/rest/container/<id>` |
| Workbook view | GET | `/rest/container/<id>/phases` |
| Phase add | POST | `/rest/workbook_phase` |
| Task add | POST | `/rest/workbook_task` |
| Task update | POST | `/rest/workbook_task/<id>` |
| Closing note | POST | `/rest/note` |
| Template list | GET | `/rest/workbook_template` |
| Template get | GET | `/rest/workbook_template/<id>` |
| Template create | POST | `/rest/workbook_template` |
| Template update | POST | `/rest/workbook_template/<id>` |
| Template delete | DELETE | `/rest/workbook_template/<id>` |
