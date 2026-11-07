<!-- summary: Promote Splunk SOAR containers to cases, apply workbook templates, and work phases and tasks. -->

# Manage cases and workbooks

When to use: an event needs formal incident handling, so you promote its container to a case with a workbook template, then work the phases and tasks (assign owners, mark progress, add closing notes) and maintain the templates themselves.

## Prerequisites

- SOAR credentials in the active profile and a passing `splunkctl soar test` (see [Set up and check SOAR](soar.md)).
- Username and password credentials for `workbook-templates delete`; SOAR refuses automation tokens on most DELETE endpoints.
- A container id (`splunkctl soar containers list`). Cases are containers with `container_type=case` and an attached workbook of phases and tasks.

## Synopsis

```text
splunkctl soar cases promote <CONTAINER_ID> [--template NAME_OR_ID] [--yes]
splunkctl soar cases workbook <CONTAINER_ID>
splunkctl soar cases phase add --container <CONTAINER_ID> --name <NAME> [--order N] [--yes]
splunkctl soar cases task add --phase-id <PHASE_ID> --name <NAME> [--description TEXT] [--order N] [--yes]
splunkctl soar cases task update <TASK_ID> [--status incomplete|in_progress|complete] [--owner USER] [--note TEXT] [--yes]

splunkctl soar workbook-templates list [--limit N]
splunkctl soar workbook-templates get <NAME_OR_ID>
splunkctl soar workbook-templates create --name <NAME> --phases <"P1,P2,P3"> [--yes]
splunkctl soar workbook-templates update <NAME_OR_ID> --add-phase <NAME>... [--yes]
splunkctl soar workbook-templates delete <NAME_OR_ID> [--yes]
```

## Workflow

### Pick a workbook template

```bash
splunkctl soar workbook-templates list
splunkctl soar workbook-templates list --limit 5 --json
splunkctl soar workbook-templates get "NIST 800-61"
splunkctl soar workbook-templates get 1 --json
```

Expected result: the preloaded templates with their phases. The default on most instances is NIST 800-61 (5 phases, 19 tasks). Numeric arguments are treated as ids; non-numeric arguments trigger a case-sensitive name lookup.

### Promote a container to a case

> **Safety:** Target is the SOAR host in the active profile. Impact: the container's type becomes `case` and every phase and task from the template is instantiated on it in one atomic POST to `/rest/container/<id>`. Preview with `splunkctl soar cases promote 42 --template "NIST 800-61"`, apply by adding `--yes`, and verify with `splunkctl soar cases workbook 42`.

```bash
splunkctl soar cases promote 42 --yes
splunkctl soar cases promote 42 --template "NIST 800-61" --yes
splunkctl soar cases promote 42 --template 3 --yes
```

Expected result: without `--template` the server's default template (`is_default=true`) is used; if no default exists the command errors and lists the available templates. `--template` accepts a case-sensitive name or a numeric id.

### View the workbook

```bash
splunkctl soar cases workbook 42
splunkctl soar cases workbook 42 --json
```

Expected result: all phases (`/rest/container/<id>/phases`) with their nested tasks. Each task shows `status` (0 incomplete, 1 in_progress, 2 complete), owner, description, and notes.

### Add a phase or a task

> **Safety:** Target is the SOAR host in the active profile. Impact: a new phase or task appears on the case's workbook for every analyst. Preview with `splunkctl soar cases phase add --container 42 --name "Recovery"`, apply by adding `--yes`, and verify with `splunkctl soar cases workbook 42`.

```bash
splunkctl soar cases phase add --container 42 --name "Recovery" --yes
splunkctl soar cases phase add --container 42 --name "Recovery" --order 3 --yes
splunkctl soar cases task add --phase-id 13 --name "Review logs" --yes
splunkctl soar cases task add --phase-id 13 --name "Review logs" \
    --description "Check all relevant logs" --order 5 --yes
```

Expected result: `phase add` posts `container_id`, `name`, and optional `order` to `/rest/workbook_phase`; `task add` posts to `/rest/workbook_task` with `phase_id` (the field is `phase_id`, not `phase`). Take the phase id from `cases workbook`.

### Update a task

> **Safety:** Target is the SOAR host in the active profile. Impact: the task's status, owner, or notes change on the live case. Preview with `splunkctl soar cases task update 100 --status complete`, apply by adding `--yes`, and verify with `splunkctl soar cases workbook 42`.

```bash
splunkctl soar cases task update 100 --status complete --yes
splunkctl soar cases task update 100 --status incomplete --yes
splunkctl soar cases task update 100 --status in_progress \
    --note "Reopening for active investigation" --yes
splunkctl soar cases task update 100 --owner analyst --yes
splunkctl soar cases task update 100 --status in_progress \
    --owner analyst --note "Taking over investigation" --yes
splunkctl soar cases task update 100 --note "Checked proxy logs, nothing found" --yes
```

Expected result: `--status` takes a name and the CLI maps it to the integer code SOAR expects:

| Name | Integer | Note required |
|---|---|---|
| `incomplete` | 0 | No |
| `in_progress` | 1 | Yes |
| `complete` | 2 | No |

The server allows only the transitions 0 to 2 (complete) and 2 to 1 (reopen as in progress); 0 to 1 is rejected with "Invalid status transition", so complete the task first. The `in_progress` transition also requires a closing note, which the CLI enforces client-side with a clear error before any API call. When `--note` accompanies `--status`, the note is sent inline in the task POST (field `note`), because the server rejects note-requiring transitions otherwise; the inline note still lands as a regular task note. A `--note` without `--status` posts to `/rest/note` with `task_id` set, and the task's `container_id` is resolved automatically with a GET on the task.

### Create or extend a template

> **Safety:** Target is the SOAR host in the active profile. Impact: a new or changed template is offered to every future `promote`; existing cases are not touched. Preview with `splunkctl soar workbook-templates create --name "IR Workflow" --phases "Detect,Contain,Eradicate,Recover"`, apply by adding `--yes`, and verify with `splunkctl soar workbook-templates get "IR Workflow"`.

```bash
splunkctl soar workbook-templates create \
    --name "IR Workflow" --phases "Detect,Contain,Eradicate,Recover" --yes
splunkctl soar workbook-templates update "NIST 800-61" --add-phase "Lessons Learned" --yes
splunkctl soar workbook-templates update 2 --add-phase Eradicate --add-phase Recover --yes
```

Expected result: `create` makes phases in the order given, numbered from 1, and needs at least one phase. `update` appends new phases after the highest existing order value.

### Delete a template

> **Safety:** Target is the SOAR host in the active profile. Impact: the template is removed and can no longer be applied; cases already promoted keep their phases. Preview with `splunkctl soar workbook-templates delete "Custom Investigation"`, apply by adding `--yes`, and verify with `splunkctl soar workbook-templates list`.

```bash
splunkctl soar workbook-templates delete "Custom Investigation" --yes
splunkctl soar workbook-templates delete 3 --yes
```

Expected result: a `DELETE /rest/workbook_template/<id>`, which requires username and password credentials in the profile.

## Troubleshooting

- `not_found` on `promote --template` or `workbook-templates get`: names are case-sensitive; copy the exact name from `workbook-templates list` or use the id.
- `promote` fails with a list of templates: the instance has no default template; pass `--template`.
- Usage error "requires a closing note" on `task update --status in_progress`: add `--note "<reason>"`.
- `http` error "Invalid status transition": you tried 0 to 1; run `--status complete` first, then `--status in_progress --note ...`.
- `auth` on `workbook-templates delete` while reads work: the profile is token-only; add a username and password with `splunkctl config init --soar`.
- `not_found` on `task add`: `--phase-id` is the phase id from `cases workbook`, not the container id.

## See also

- [Work SOAR incidents](soar-incidents.md)
- [Run playbooks](soar-playbooks.md)
- [Handle approvals](soar-approvals.md)
- [Set up and check SOAR](soar.md)
- [Command reference: soar](../commands/soar.md)
