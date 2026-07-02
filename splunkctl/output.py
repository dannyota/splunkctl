"""Dual output — TTY gets tables, pipes get JSON."""

import csv
import io
import json
import sys
from pathlib import Path
from typing import Any

import click
from tabulate import tabulate

type Rows = list[dict[str, Any]]


def render(
    ctx: click.Context,
    data: Rows | dict[str, Any],
    *,
    empty: str | None = None,
) -> None:
    """Format and output data according to global flags.

    Args:
        ctx: Click context carrying format flags.
        data: Single dict or list of dicts to render.
        empty: Human message for empty results (table mode only, stderr).
            Data formats always emit a valid payload (``[]`` for JSON,
            nothing for csv/jsonl) so pipelines never break.
    """
    rows: Rows = [data] if isinstance(data, dict) else list(data)
    obj: dict[str, Any] = ctx.obj or {}

    fields: str | None = obj.get("fields")
    if fields:
        keep = [f.strip() for f in fields.split(",")]
        rows = [{k: row.get(k) for k in keep} for row in rows]

    if not rows:
        _render_empty(obj, empty)
        return

    fmt: str | None = obj.get("format")
    use_json: bool = obj.get("json", False)

    if use_json or fmt == "json":
        text = json.dumps(rows, indent=2, default=str)
    elif fmt == "jsonl":
        text = "\n".join(json.dumps(r, default=str) for r in rows)
    elif fmt == "csv":
        text = _csv(rows)
    elif fmt == "table" or sys.stdout.isatty():
        text = tabulate(rows, headers="keys", tablefmt="simple")
    else:
        text = json.dumps(rows, indent=2, default=str)

    out_path: str | None = obj.get("out")
    if out_path:
        Path(out_path).write_text(text + "\n")
        click.echo(f"Written to {out_path}", err=True)
    else:
        click.echo(text)


def _render_empty(obj: dict[str, Any], empty: str | None) -> None:
    """Emit the empty-result payload for the resolved format."""
    if _resolve_table(obj):
        click.echo(empty or "No results.", err=True)
        return

    fmt: str | None = obj.get("format")
    use_json: bool = obj.get("json", False)
    is_json = use_json or fmt == "json" or fmt is None
    text = "[]" if is_json else ""

    out_path: str | None = obj.get("out")
    if out_path:
        Path(out_path).write_text(text + "\n" if text else "")
        click.echo(f"Written to {out_path}", err=True)
    elif text:
        click.echo(text)


def is_table(ctx: click.Context) -> bool:
    """True when output resolves to a human-readable table."""
    obj: dict[str, Any] = ctx.obj or {}
    return _resolve_table(obj)


def _resolve_table(obj: dict[str, Any]) -> bool:
    if obj.get("json") or obj.get("format") in ("json", "jsonl", "csv"):
        return False
    return obj.get("format") == "table" or sys.stdout.isatty()


def error(msg: str) -> None:
    """Print error to stderr."""
    click.echo(f"Error: {msg}", err=True)


def info(msg: str) -> None:
    """Print info to stderr (keeps stdout clean for piping)."""
    click.echo(msg, err=True)


def _csv(rows: Rows) -> str:
    if not rows:
        return ""
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames, restval="")
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue().rstrip("\n")
