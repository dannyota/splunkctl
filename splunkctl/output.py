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
) -> None:
    """Format and output data according to global flags.

    Args:
        ctx: Click context carrying format flags.
        data: Single dict or list of dicts to render.
    """
    rows: Rows = [data] if isinstance(data, dict) else list(data)
    obj: dict[str, Any] = ctx.obj or {}

    fields: str | None = obj.get("fields")
    if fields:
        keep = [f.strip() for f in fields.split(",")]
        rows = [{k: row.get(k) for k in keep} for row in rows]

    fmt: str | None = obj.get("format")
    use_json: bool = obj.get("json", False)

    if use_json or fmt == "json":
        text = json.dumps(rows, indent=2, default=str)
    elif fmt == "jsonl":
        text = "\n".join(json.dumps(r, default=str) for r in rows)
    elif fmt == "csv":
        text = _csv(rows)
    elif fmt == "table" or sys.stdout.isatty():
        text = (
            tabulate(rows, headers="keys", tablefmt="simple") if rows else "No results."
        )
    else:
        text = json.dumps(rows, indent=2, default=str)

    out_path: str | None = obj.get("out")
    if out_path:
        Path(out_path).write_text(text + "\n")
        click.echo(f"Written to {out_path}", err=True)
    else:
        click.echo(text)


def error(msg: str) -> None:
    """Print error to stderr."""
    click.echo(f"Error: {msg}", err=True)


def info(msg: str) -> None:
    """Print info to stderr (keeps stdout clean for piping)."""
    click.echo(msg, err=True)


def _csv(rows: Rows) -> str:
    if not rows:
        return ""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()), extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue().rstrip("\n")
