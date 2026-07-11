# SOAR Approvals

Manage approval requests from SOAR playbook prompt blocks. A playbook
pauses at a prompt action and waits for an external approve/deny response
before continuing. This command group lets an operator review and respond
to those prompts from the terminal, unblocking automation without opening
the SOAR UI.

## How approvals arise

1. A playbook author adds a **prompt** block (manual or automated prompt
   action) to a playbook.
2. When the playbook runs and reaches that block, it creates an approval
   request tied to the container and pauses execution.
3. The approval stays in `pending` status until someone responds via the
   UI or the REST API (`/rest/external_prompt/<id>`).
4. Once approved or denied, the playbook resumes along the corresponding
   branch.

Without active playbooks that contain prompt blocks, the approval list
will be empty -- this is normal on a fresh or lab instance.

## List

```bash
splunkctl soar approvals list                          # all approvals
splunkctl soar approvals list --pending                # only unanswered
splunkctl soar approvals list --container 42           # by container
splunkctl soar approvals list --container 42 --pending # combined
splunkctl soar approvals list --json
```

`--pending` adds a `_filter_status="pending"` filter so only unanswered
approvals are returned. `--container` queries the per-container
pseudo-field endpoint (`/rest/container/<id>/approvals`) instead of the
global collection. Both flags compose.

An empty result exits 0 with clean output (`[]` in JSON mode, a human
message in table mode).

## Get

```bash
splunkctl soar approvals get 5
splunkctl soar approvals get 5 --json
```

Fetches the detail summary view for a single approval
(`/rest/approval/<id>?_detail=detail_summary_view`). Returns the full
approval object including message, status, and response history.

## Respond

```bash
splunkctl soar approvals respond 5 approve             # dry-run preview
splunkctl --yes soar approvals respond 5 approve       # apply
splunkctl --yes soar approvals respond 5 deny --message "Insufficient evidence"
```

Posts to `/rest/external_prompt/<id>` with `{status: "approve"|"deny"}`.
`--message` attaches a freeform response message to the decision.

**Guarded**: dry-run by default. The preview shows the approval ID,
action, and message. Pass `--yes` to apply. The guard banner includes the
SOAR host so you never accidentally respond on the wrong instance.

The action argument accepts only `approve` or `deny` (case-insensitive).
Any other value is rejected as a usage error before any API call.

## Workflow example

A typical prompt-response cycle from the terminal:

```bash
# 1. Check for pending approvals
splunkctl soar approvals list --pending

# 2. Inspect a specific approval
splunkctl soar approvals get 5

# 3. Approve it (or deny)
splunkctl --yes soar approvals respond 5 approve --message "Verified IOC"

# 4. Confirm the playbook resumed
splunkctl soar containers get 42 --playbook-runs
```

## Error handling

All commands produce typed error envelopes on failure:

```bash
splunkctl soar approvals get 999 --json
# stderr: {"error": {"kind": "not_found", "http_status": 404, ...}}
# exit 1
```

Responding to an already-answered approval typically returns a conflict
error from the server.
