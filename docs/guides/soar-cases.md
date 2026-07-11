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

# Mark in_progress (requires a closing note)
splunkctl --yes soar cases task update 100 --status in_progress \
    --note "Starting active investigation"

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
the integer codes the SOAR API expects. The `in_progress` transition
requires a closing note -- the SOAR server rejects it with "Closing
note content is required". The CLI enforces this client-side with a
clear error message before making any API call.

### Closing notes

When `--note` is provided, the CLI posts a note to `/rest/note` with
`task_id` set, linking the note to the specific task. The task's
`container_id` is resolved automatically via a GET on the task.

## Workbook templates

SOAR ships with 10 preloaded workbook templates. The default is
NIST 800-61 (5 phases, 19 tasks). Templates are listed at
`/rest/workbook_template`. The `promote` command resolves template
names via this endpoint.

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
