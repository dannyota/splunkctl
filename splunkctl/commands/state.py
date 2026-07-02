"""`state` — unified config-as-code: pull / diff / push (Task I1).

The bank change-management workflow: pull a versioned snapshot of
rules/parsers/macros/lookups/dashboards, edit it, diff it against the
live instance, then push. ``push --report <file>`` writes a savable
before→after JSON artifact a change ticket can reference — written on
both a dry-run (``applied: false``, the plan for approval) and a
``--yes`` apply (``applied: true``, the record of what happened).

This module is pure orchestration: every read, diff, and apply is
delegated to ``state_io.py``, which itself reuses the existing
``rules_io``/``parsers_io``/``conf_ops``/``client.upload_lookup`` paths.
No object serialization or apply logic is re-implemented here.

**push never deletes.** An instance object with no on-disk counterpart
is classified ``removed`` and reported, but push only ever creates or
updates what is represented on disk.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import click

from splunkctl import guard, output
from splunkctl.client import get_client
from splunkctl.commands import state_io

_TYPES_HELP = ", ".join(state_io.TYPES)


def _parse_types(types_csv: str | None) -> tuple[str, ...]:
    if not types_csv:
        return state_io.TYPES
    requested = tuple(t.strip() for t in types_csv.split(",") if t.strip())
    unknown = [t for t in requested if t not in state_io.TYPES]
    if unknown:
        raise click.BadParameter(
            f"unknown type(s): {', '.join(unknown)} (valid: {_TYPES_HELP})"
        )
    return requested


def _types_option[F: Any](f: F) -> F:
    return click.option(
        "--types",
        "types_csv",
        default=None,
        help=f"Comma-separated object types to include (default: all — {_TYPES_HELP}).",
    )(f)


def _app_option[F: Any](f: F) -> F:
    return click.option(
        "--app", default=None, help="Only objects in this app (default: all apps)."
    )(f)


@click.group("state")
def state_group() -> None:
    """Unified config-as-code across rules, parsers, macros, lookups, dashboards.

    The change-ticket workflow: `state pull` a snapshot, edit it, `state
    diff` to see exactly what changed, `state push --yes --report <file>`
    to apply it and save the before→after evidence. Dashboards are
    pull+diff only — no import path exists yet, so `push` reports
    dashboard drift as apply-unsupported without writing anything. push
    never deletes: an instance object missing from the directory is
    reported as `removed` drift, never applied.
    """


@state_group.command("pull")
@click.option(
    "--dir",
    "dir_path",
    required=True,
    type=click.Path(file_okay=False),
    help="Target directory — owned by this snapshot (pull overwrites the "
    "pulled types' files).",
)
@_app_option
@_types_option
@click.pass_context
def state_pull(
    ctx: click.Context, dir_path: str, app: str | None, types_csv: str | None
) -> None:
    """Snapshot the live instance to a versioned directory tree.

    Writes ``<dir>/rules.yml``, ``parsers.yml``, ``macros.yml``,
    ``lookups/<name>``, ``dashboards/<name>.xml`` (per selected
    ``--types``) plus a top-level ``manifest.json`` (tool version, host,
    per-type object counts). Read-only against the instance.
    """
    types = _parse_types(types_csv)
    client = get_client(ctx)
    target = Path(dir_path)
    target.mkdir(parents=True, exist_ok=True)

    counts: dict[str, int] = {}
    for t in types:
        counts[t] = state_io.PULL_FNS[t](client, target, app)

    state_io.write_manifest(target, host=state_io.resolve_host(client), counts=counts)
    total = sum(counts.values())
    summary = ", ".join(f"{k}={v}" for k, v in counts.items())
    output.info(f"Pulled {total} object(s) to {target}: {summary}.")


@state_group.command("diff")
@click.option(
    "--dir",
    "dir_path",
    required=True,
    type=click.Path(exists=True, file_okay=False),
    help="Directory previously written by `state pull`.",
)
@_app_option
@_types_option
@click.pass_context
def state_diff(
    ctx: click.Context, dir_path: str, app: str | None, types_csv: str | None
) -> None:
    """Structured drift report: on-disk snapshot vs the live instance.

    One row per object: ``{type, name, change, fields?}`` where
    ``change`` is ``added`` (on disk only — push would create it),
    ``removed`` (live only — push does NOT delete it), ``modified``, or
    ``unchanged``. Exit code is always 0 — diff is a report, not a gate.
    """
    types = _parse_types(types_csv)
    client = get_client(ctx)
    target = Path(dir_path)

    rows: list[dict[str, Any]] = [
        {"type": t, **entry}
        for t in types
        for entry in state_io.DIFF_FNS[t](client, target, app)
    ]
    output.render(ctx, rows, empty="No objects found for the selected type(s).")


def _plan(
    client: Any, target: Path, app: str | None, types: tuple[str, ...]
) -> tuple[dict[str, list[state_io.DriftEntry]], dict[str, int]]:
    """Full diff per type, split into the apply plan and the removed counts."""
    plan: dict[str, list[state_io.DriftEntry]] = {}
    removed: dict[str, int] = {}
    for t in types:
        entries = state_io.DIFF_FNS[t](client, target, app)
        removed[t] = sum(1 for e in entries if e["change"] == "removed")
        plan[t] = [e for e in entries if e["change"] in ("added", "modified")]
    return plan, removed


def _preview_lines(
    types: tuple[str, ...], plan: dict[str, list[state_io.DriftEntry]]
) -> tuple[list[str], int]:
    """Per-object create/update preview lines for the guard's dry-run detail."""
    lines: list[str] = []
    total = 0
    for t in types:
        if t == "dashboards":
            continue
        for e in plan[t]:
            total += 1
            lines.append(f"  {e['change']}: {t}/{e['name']}")
    return lines, total


def _notes(
    types: tuple[str, ...],
    plan: dict[str, list[state_io.DriftEntry]],
    removed: dict[str, int],
) -> list[str]:
    """Informational notes printed unconditionally, dry-run and --yes alike.

    Dashboard drift is never applied (no import path), and a `removed`
    object is never applied either (push never deletes) -- both need to
    surface regardless of whether the guard actually applies anything.
    """
    notes: list[str] = []
    dash_plan = plan.get("dashboards", [])
    if dash_plan:
        notes.append(
            f"dashboards: {len(dash_plan)} drifted object(s) — "
            "apply not supported (export-only, no import path)"
        )
    for t, n in removed.items():
        if n:
            notes.append(
                f"{t}: {n} object(s) on the instance only — "
                "not deleted (push never deletes)"
            )
    return notes


@state_group.command("push")
@guard.guarded
@click.option(
    "--dir",
    "dir_path",
    required=True,
    type=click.Path(exists=True, file_okay=False),
    help="Directory previously written by `state pull`.",
)
@_app_option
@_types_option
@click.option(
    "--report",
    "report_path",
    type=click.Path(dir_okay=False),
    default=None,
    help="Write the before→after change-ticket evidence artifact (JSON).",
)
@click.pass_context
def state_push(
    ctx: click.Context,
    dir_path: str,
    app: str | None,
    types_csv: str | None,
    report_path: str | None,
) -> None:
    """Apply the on-disk snapshot to the instance (guarded; never deletes).

    Dry-run previews exactly what `--yes` would create/update — added and
    modified objects only; a `removed` object (live but absent from disk)
    is noted but never touched. Dashboards have no apply path: drifted
    dashboards are reported as apply-unsupported and skipped, never
    erroring. `--report <file>` writes `{host, types, changes, applied}`
    on both the dry-run (`applied: false`, the plan) and `--yes`
    (`applied: true`, the record) — attach the former to the ticket for
    approval, the latter as the change evidence.
    """
    types = _parse_types(types_csv)
    client = get_client(ctx)
    target = Path(dir_path)

    plan, removed = _plan(client, target, app, types)
    lines, total = _preview_lines(types, plan)
    detail = "\n".join(lines) if lines else "  (no drift)"

    for note in _notes(types, plan, removed):
        output.info(f"note: {note}")

    applied = guard.check(ctx, f"Push {total} change(s) from {target}", details=detail)

    changes: list[state_io.ChangeRecord] = []
    applicable = [t for t in types if t in state_io.APPLICABLE_TYPES]
    if applied:
        for t in applicable:
            if plan[t]:
                changes.extend(state_io.APPLY_FNS[t](client, target, app))
    else:
        for t in applicable:
            changes.extend(state_io.change_record(t, e) for e in plan[t])
        obj: dict[str, Any] = ctx.obj or {}
        if obj.get("json") or obj.get("format") == "json":
            output.render(ctx, [dict(c) for c in changes])

    if report_path is not None:
        state_io.write_report(
            Path(report_path),
            host=state_io.resolve_host(client),
            types=list(types),
            changes=changes,
            applied=applied,
        )
        output.info(f"Report written to {report_path} (applied={applied}).")

    if applied:
        output.info(f"Applied {len(changes)} change(s).")
