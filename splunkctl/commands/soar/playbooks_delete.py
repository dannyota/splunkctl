"""SOAR playbook deletion — Web-UI-backed, strict-name, guarded."""

from __future__ import annotations

import click

from splunkctl import guard, output
from splunkctl.commands.soar._client import get_soar_client
from splunkctl.commands.soar.playbooks import (
    _as_id,
    _resolve_playbook_id,
    playbooks_group,
)
from splunkctl.soar.client import SOARError


@playbooks_group.command("delete")
@guard.guarded
@click.argument("identifiers", nargs=-1, required=True)
@click.pass_context
def delete_cmd(ctx: click.Context, *, identifiers: tuple[str, ...]) -> None:
    """Delete playbooks by ID or exact name (requires username/password).

    Deletion is irreversible, so names never suffix-match: pass the
    exact scoped name (``<dir>/<module>``) or the numeric id.
    """
    # Guard BEFORE any network I/O — name→id resolution happens at
    # apply time, so the dry-run preview needs no connectivity.
    listing = "\n".join(
        f"  {ident}"
        if _as_id(ident) is not None
        else f"  {ident} (name — resolved to id at apply time, exact match)"
        for ident in identifiers
    )
    details = f"Playbooks to delete:\n{listing}"
    if not guard.soar_check(
        ctx, f"Delete {len(identifiers)} playbook(s)", details=details
    ):
        return

    client = get_soar_client(ctx)
    ids: list[int] = []
    for ident in identifiers:
        pb_id = _as_id(ident)
        if pb_id is None:
            pb_id = _resolve_playbook_id(client, ident, ctx, suffix_retry=False)
            if pb_id is None:
                return
            output.info(f"Resolved '{ident}' to playbook id {pb_id}")
        ids.append(pb_id)

    try:
        result = client.web_delete_playbooks(ids)
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return

    done = result.get("done_count", 0)
    fail = result.get("fail_count", 0)
    changes: list[str] = result.get("changes", [])
    errors: list[str] = result.get("errors", [])

    for change in changes:
        output.info(change)
    for err in errors:
        output.error(err, kind="error")

    id_str = ", ".join(str(i) for i in ids)
    if fail:
        output.error(
            f"{fail} playbook(s) failed to delete.",
            kind="error",
        )
        ctx.exit(1)
    elif done == 0:
        output.warning(f"No playbooks deleted (IDs may not exist: {id_str}).")
    else:
        output.info(f"Deleted {done} playbook(s).")
