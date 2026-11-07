<!-- summary: List, approve, and deny approval requests raised by Splunk SOAR playbook prompt blocks. -->

# Handle approvals

When to use: a playbook has paused at a prompt block and is waiting for a human decision, and you want to review and approve or deny it from the terminal instead of the SOAR UI, so automation can continue.

## Prerequisites

- SOAR credentials in the active profile and a passing `splunkctl soar test` (see [Set up and check SOAR](soar.md)).
- A playbook that contains a prompt block (a manual or automated prompt action). When such a playbook runs and reaches that block it creates an approval request tied to the container and pauses; the approval stays `pending` until someone responds through the UI or the REST API (`/rest/external_prompt/<id>`), then the playbook resumes along the approve or deny branch.
- Without active playbooks that contain prompt blocks the approval list is empty; that is normal on a fresh or lab instance.

## Synopsis

```text
splunkctl soar approvals list [--pending] [--container CONTAINER_ID]
splunkctl soar approvals get <APPROVAL_ID>
splunkctl soar approvals respond <APPROVAL_ID> <approve|deny> [--message TEXT] [--yes]
```

## Workflow

### Find pending approvals

```bash
splunkctl soar approvals list
splunkctl soar approvals list --pending
splunkctl soar approvals list --container 42
splunkctl soar approvals list --container 42 --pending
splunkctl soar approvals list --json
```

Expected result: one row per approval. `--pending` adds a `_filter_status="pending"` filter so only unanswered approvals return. `--container` queries the per-container endpoint (`/rest/container/<id>/approvals`) instead of the global collection. Both flags compose. An empty result exits 0 with clean output (`[]` in JSON mode, `No approvals found.` in table mode).

### Read one approval

```bash
splunkctl soar approvals get 5
splunkctl soar approvals get 5 --json
```

Expected result: the detail summary view (`/rest/approval/<id>?_detail=detail_summary_view`): the full approval object including message, status, and response history.

### Approve or deny

> **Safety:** Target is the SOAR host in the active profile; the dry-run banner names it so you never answer a prompt on the wrong instance. Impact: the paused playbook resumes along the chosen branch, which may run containment actions. Preview with `splunkctl soar approvals respond 5 approve --message "Verified IOC"` (the preview shows the approval id, action, and message), apply by adding `--yes`, and verify with `splunkctl soar containers get 42 --playbook-runs`.

```bash
splunkctl soar approvals respond 5 approve
splunkctl soar approvals respond 5 approve --message "Verified IOC" --yes
splunkctl soar approvals respond 5 deny --message "Insufficient evidence" --yes
```

Expected result: a POST to `/rest/external_prompt/<id>` with `{status: "approve"|"deny"}` and the optional message, and the playbook run moves past the prompt. The action argument accepts only `approve` or `deny` (case-insensitive); any other value is a usage error before any API call.

### Run the full cycle

> **Safety:** Target is the SOAR host in the active profile. Impact: step 3 resumes the paused playbook. Preview with `splunkctl soar approvals respond 5 approve --message "Verified IOC"`, apply by adding `--yes`, and verify with step 4.

```bash
splunkctl soar approvals list --pending
splunkctl soar approvals get 5
splunkctl soar approvals respond 5 approve --message "Verified IOC" --yes
splunkctl soar containers get 42 --playbook-runs
```

Expected result: the approval leaves the pending list and the container's playbook run shows progress past the prompt block.

## Troubleshooting

- `not_found` on `get` or `respond` (`{"error": {"kind": "not_found", "http_status": 404, ...}}`, exit 1): the approval id is wrong or was deleted with its container; list again with `--pending`.
- `conflict` on `respond`: the approval was already answered in the UI or by someone else; `get` shows the recorded decision.
- Usage error (exit 2) on `respond`: the action must be `approve` or `deny`.
- `permission` on `respond` while `list` works: the account's role cannot answer prompts; respond with a user whose role may.
- The playbook did not resume after approval: check `splunkctl soar playbooks runs list --container 42 --status failed`; a failure in the next block looks like a stuck approval from the queue.

## See also

- [Run playbooks](soar-playbooks.md)
- [Work SOAR incidents](soar-incidents.md)
- [Set up and check SOAR](soar.md)
- [Command reference: soar](../commands/soar.md)
