"""SOAR playbooks — list, get, enable/disable, trigger, export, import."""

from __future__ import annotations

import base64
import io
import json
import tarfile
from pathlib import Path, PurePosixPath
from typing import Any

import click

from splunkctl import guard, output
from splunkctl.commands.soar._client import get_soar_client
from splunkctl.soar.client import SOARError


@click.group("playbooks")
def playbooks_group() -> None:
    """Playbook lifecycle — list, export, import, enable/disable."""


# ─── list ─────────────────────────────────────────────────────────────


@playbooks_group.command("list")
@click.option("--active", is_flag=True, default=False, help="Only active playbooks.")
@click.option("--label", default=None, help="Filter by label.")
@click.option("--repo", default=None, help="Filter by SCM repo name.")
@click.pass_context
def list_cmd(
    ctx: click.Context,
    *,
    active: bool,
    label: str | None,
    repo: str | None,
) -> None:
    """List playbooks with optional filters."""
    client = get_soar_client(ctx)
    params: dict[str, Any] = {}

    if active:
        params["_filter_active"] = "True"
    if label is not None:
        params["_filter_labels__contains"] = json.dumps(label)

    try:
        if repo is not None:
            # The scm filter is id-typed — a name string 400s.
            params["_filter_scm"] = str(_resolve_repo_id(client, repo))
        result = client.get("playbook", params=params)
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return

    data = result.get("data", []) if isinstance(result, dict) else []
    output.render(ctx, data, empty="No playbooks found.")


def _as_id(value: str) -> int | None:
    """Parse a strict ASCII-decimal id, else None.

    ``str.isdigit`` alone is unsafe: it accepts Unicode digits like
    ``"²"`` that ``int()`` rejects with a ValueError.
    """
    return int(value) if value.isascii() and value.isdigit() else None


def _resolve_repo_id(client: Any, repo: str) -> int:
    """Resolve an SCM repo name to its numeric id (numeric passes through)."""
    repo_id = _as_id(repo)
    if repo_id is not None:
        return repo_id
    result = client.get("scm", params={"_filter_name": json.dumps(repo)})
    data = result.get("data", []) if isinstance(result, dict) else []
    if not data:
        raise SOARError(f"SCM repo '{repo}' not found.", kind="not_found")
    return int(data[0]["id"])


# ─── get ──────────────────────────────────────────────────────────────


@playbooks_group.command("get")
@click.argument("playbook_id", type=int)
@click.pass_context
def get_cmd(ctx: click.Context, *, playbook_id: int) -> None:
    """Get a playbook by ID."""
    client = get_soar_client(ctx)
    try:
        result = client.get(f"playbook/{playbook_id}", params={})
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return

    output.render(ctx, result, empty=f"Playbook {playbook_id} not found.")


# ─── enable / disable ────────────────────────────────────────────────


@playbooks_group.command("enable")
@guard.guarded
@click.argument("playbook_id", type=int)
@click.pass_context
def enable_cmd(ctx: click.Context, *, playbook_id: int) -> None:
    """Activate a playbook. draft_mode playbooks cannot be activated."""
    body: dict[str, Any] = {"active": True}
    if not guard.soar_check(ctx, f"Enable playbook {playbook_id}"):
        return

    client = get_soar_client(ctx)
    try:
        client.post(f"playbook/{playbook_id}", body=body)
    except SOARError as exc:
        msg = exc.message
        if "draft" in msg.lower():
            msg += (
                " (hint: playbooks in draft_mode cannot be activated; "
                "re-import without draft_mode or edit in the VPE)"
            )
        output.error(msg, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return

    output.info(f"Playbook {playbook_id} enabled.")


@playbooks_group.command("disable")
@guard.guarded
@click.argument("playbook_id", type=int)
@click.option(
    "--cancel-runs",
    is_flag=True,
    default=False,
    help="Cancel running instances.",
)
@click.pass_context
def disable_cmd(
    ctx: click.Context,
    *,
    playbook_id: int,
    cancel_runs: bool,
) -> None:
    """Deactivate a playbook. --cancel-runs stops running instances."""
    body: dict[str, Any] = {"active": False}
    action = f"Disable playbook {playbook_id}"
    if cancel_runs:
        # The destructive side effect must be visible in the preview.
        body["cancel_runs"] = True
        action += " (cancel in-flight runs)"
    if not guard.soar_check(ctx, action):
        return

    client = get_soar_client(ctx)
    try:
        client.post(f"playbook/{playbook_id}", body=body)
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return

    output.info(f"Playbook {playbook_id} disabled.")


# ─── trigger ──────────────────────────────────────────────────────────


@playbooks_group.command("trigger")
@guard.guarded
@click.argument("playbook_id", type=int)
@click.option(
    "--on",
    "trigger_type",
    required=True,
    type=click.Choice(["artifact_created", "container_resolved"]),
    help=(
        "Trigger type. ('label' is import-metadata only — the REST "
        "endpoint rejects setting it.)"
    ),
)
@click.pass_context
def trigger_cmd(
    ctx: click.Context,
    *,
    playbook_id: int,
    trigger_type: str,
) -> None:
    """Set the automation trigger for a playbook."""
    body: dict[str, Any] = {"playbook_trigger": trigger_type}
    if not guard.soar_check(
        ctx, f"Set trigger '{trigger_type}' for playbook {playbook_id}"
    ):
        return

    client = get_soar_client(ctx)
    try:
        client.post(f"playbook/{playbook_id}", body=body)
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return

    output.info(f"Playbook {playbook_id} trigger set to '{trigger_type}'.")


# ─── export ───────────────────────────────────────────────────────────


def _resolve_playbook_id(
    client: Any,
    identifier: str,
    ctx: click.Context,
    *,
    suffix_retry: bool = True,
) -> int | None:
    """Resolve a playbook name to its numeric id.

    Playbook names are scoped ``<dir>/<module>``; a bare module name is
    retried as a suffix match unless *suffix_retry* is off (irreversible
    commands demand the exact name so the name→id mapping is never
    guessed — a suffix hit becomes a did-you-mean error instead).

    Returns None and emits an error if not found.
    """
    try:
        result = client.get(
            "playbook",
            params={"_filter_name": json.dumps(identifier), "page_size": 2},
        )
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return None

    data = result.get("data", []) if isinstance(result, dict) else []
    if not data:
        try:
            result = client.get(
                "playbook",
                params={
                    "_filter_name__endswith": json.dumps(f"/{identifier}"),
                    "page_size": 2,
                },
            )
        except SOARError as exc:
            output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
            ctx.exit(1)
            return None
        suffix_data = result.get("data", []) if isinstance(result, dict) else []
        if suffix_data and not suffix_retry:
            hints = ", ".join(
                f"'{d.get('name')}' (id {d.get('id')})" for d in suffix_data
            )
            output.error(
                f"Playbook '{identifier}' not found by exact name. "
                f"Did you mean {hints}? Pass the exact scoped name or "
                "the numeric id.",
                kind="not_found",
            )
            ctx.exit(1)
            return None
        data = suffix_data
    if not data:
        output.error(
            f"Playbook '{identifier}' not found.",
            kind="not_found",
        )
        ctx.exit(1)
        return None
    if len(data) >= 2:
        output.error(
            f"Ambiguous: multiple playbooks named '{identifier}'",
            kind="ambiguous",
        )
        ctx.exit(1)
        return None
    return int(data[0]["id"])


@playbooks_group.command("export")
@click.argument("identifier")
@click.option("--out", default=None, help="Output directory.")
@click.option("--unpack", is_flag=True, default=False, help="Extract json+py files.")
@click.pass_context
def export_cmd(
    ctx: click.Context,
    *,
    identifier: str,
    out: str | None,
    unpack: bool,
) -> None:
    """Export a playbook as tgz (by id or name). --unpack extracts files."""
    client = get_soar_client(ctx)

    # Resolve name → id if not numeric.
    pb_id = _as_id(identifier)
    if pb_id is None:
        resolved = _resolve_playbook_id(client, identifier, ctx)
        if resolved is None:
            return
        pb_id = resolved

    try:
        tgz_bytes = client.get_bytes(f"playbook/{pb_id}/export", params={})
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return

    if unpack:
        _unpack_tgz(tgz_bytes, out, ctx)
    elif out:
        out_path = Path(out)
        if out_path.is_dir():
            out_path = out_path / f"playbook_{pb_id}.tgz"
        out_path.write_bytes(tgz_bytes)
        output.info(f"Exported to {out_path}")
    else:
        # Raw tgz to stdout.
        click.get_binary_stream("stdout").write(tgz_bytes)


def _unpack_tgz(tgz_bytes: bytes, out_dir: str | None, ctx: click.Context) -> None:
    """Extract a playbook tgz to *out_dir* (or cwd)."""
    dest = Path(out_dir) if out_dir else Path.cwd()
    try:
        with tarfile.open(fileobj=io.BytesIO(tgz_bytes), mode="r:gz") as tar:
            tar.extractall(path=dest, filter="data")
    except (tarfile.TarError, OSError) as exc:
        output.error(f"Failed to unpack: {exc}", kind="error")
        ctx.exit(1)
        return
    output.info(f"Unpacked to {dest}")


# ─── import ───────────────────────────────────────────────────────────


def _dir_to_tgz(directory: Path) -> bytes:
    """Pack a playbook directory into a tgz archive."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for child in sorted(directory.iterdir()):
            if child.is_file():
                tar.add(str(child), arcname=f"{directory.name}/{child.name}")
    return buf.getvalue()


def _scoped_name(tgz_bytes: bytes) -> str | None:
    """Best-effort SOAR-side scoped name (``<dir>/<module>``) from a tgz."""
    try:
        with tarfile.open(fileobj=io.BytesIO(tgz_bytes), mode="r:gz") as tar:
            for member in tar.getmembers():
                if member.name.endswith(".py"):
                    p = PurePosixPath(member.name)
                    parent = p.parent.name
                    return f"{parent}/{p.stem}" if parent else p.stem
    except tarfile.TarError:
        return None
    return None


@playbooks_group.command("import")
@guard.guarded
@click.argument("path", type=click.Path())
@click.option("--scm", default="local", help="SCM repo name (default: local).")
@click.option(
    "--force/--no-force",
    default=True,
    help="Force overwrite (default: true).",
)
@click.pass_context
def import_cmd(
    ctx: click.Context,
    *,
    path: str,
    scm: str,
    force: bool,
) -> None:
    """Import a playbook from a directory or tgz file."""
    src = Path(path)
    if not src.exists():
        output.error(f"Path does not exist: {path}", kind="usage")
        ctx.exit(1)
        return

    if src.is_dir():
        tgz_bytes = _dir_to_tgz(src)
        label = src.name
    elif src.is_file():
        tgz_bytes = src.read_bytes()
        label = src.name
    else:
        output.error(f"Unsupported path type: {path}", kind="usage")
        ctx.exit(1)
        return

    encoded = base64.b64encode(tgz_bytes).decode()
    body: dict[str, Any] = {
        "playbook": encoded,
        "scm": scm,
        "force": force,
    }

    details = f"Import '{label}' (scm={scm}, force={force})"
    scoped = _scoped_name(tgz_bytes)
    if scoped is not None:
        details += f"\nplaybook name after import: {scoped}"
    if not guard.soar_check(ctx, details):
        return

    client = get_soar_client(ctx)
    try:
        result = client.post("import_playbook", body=body)
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return

    new_id = result.get("id", "?") if isinstance(result, dict) else "?"
    output.info(f"Playbook imported: id={new_id}")
    if isinstance(result, dict):
        output.render(ctx, result)


# ─── repos ────────────────────────────────────────────────────────────


@playbooks_group.command("repos")
@click.pass_context
def repos_cmd(ctx: click.Context) -> None:
    """List SCM repositories."""
    client = get_soar_client(ctx)
    try:
        result = client.get("scm", params={})
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return

    data = result.get("data", []) if isinstance(result, dict) else []
    output.render(ctx, data, empty="No SCM repositories found.")


# ─── sync ─────────────────────────────────────────────────────────────


@playbooks_group.command("sync")
@guard.guarded
@click.argument("repo_id", type=int)
@click.pass_context
def sync_cmd(ctx: click.Context, *, repo_id: int) -> None:
    """Sync an external SCM repo (pull + force)."""
    body: dict[str, Any] = {"pull": True, "force": True}
    details = json.dumps(body, indent=2)
    if not guard.soar_check(ctx, f"Sync SCM repo {repo_id}", details=details):
        return

    client = get_soar_client(ctx)
    try:
        client.post(f"scm/{repo_id}", body=body)
    except SOARError as exc:
        msg = exc.message
        if "not supported" in msg.lower():
            msg += (
                " (hint: the built-in local repo (file://) has no remote "
                "to pull from; use 'splunkctl soar playbooks import' for "
                "local deployment, or add an external HTTPS/SSH repo)"
            )
        output.error(msg, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return

    output.info(f"SCM repo {repo_id} synced.")
