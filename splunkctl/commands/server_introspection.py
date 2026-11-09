"""Live ingestion and filesystem measurements from splunkd."""

import json
from typing import Any

import click

from splunkctl import output
from splunkctl.client import get_client


def number(value: Any) -> int | float | None:
    """Normalize REST numeric strings while retaining missing values."""
    if value is None or value == "":
        return None
    numeric = float(value)
    return int(numeric) if numeric.is_integer() else numeric


def _entries(ctx: click.Context, path: str) -> list[dict[str, Any]]:
    response = get_client(ctx).service.get(path, output_mode="json", count=0)
    body: dict[str, Any] = json.loads(response.body.read())
    return list(body.get("entry", []))


@click.group("introspection")
def introspection_group() -> None:
    """Inspect live ingestion and filesystem usage."""


@introspection_group.command("queues")
@click.pass_context
def queues(ctx: click.Context) -> None:
    """Show ingestion queue occupancy."""
    rows = []
    for entry in _entries(ctx, "/services/server/introspection/queues"):
        content = entry.get("content", {})
        current = number(content.get("current_size_bytes"))
        maximum = number(content.get("max_size_bytes"))
        rows.append(
            {
                "queue": entry.get("name"),
                "current": current,
                "maximum": maximum,
                "unit": "bytes",
                "fill_ratio": current / maximum
                if current is not None and maximum
                else None,
                "blocked": content.get("blocked"),
            }
        )
    output.render(ctx, rows)


@introspection_group.command("indexer")
@click.pass_context
def indexer(ctx: click.Context) -> None:
    """Show indexing status."""
    rows = []
    for entry in _entries(ctx, "/services/server/introspection/indexer"):
        content = entry.get("content", {})
        rows.append(
            {
                "name": entry.get("name"),
                "status": content.get("status"),
                "reason": content.get("reason"),
                "average_KBps": number(content.get("average_KBps")),
            }
        )
    output.render(ctx, rows)


@introspection_group.command("disk")
@click.pass_context
def disk(ctx: click.Context) -> None:
    """Show filesystem usage in MB."""
    rows = []
    for entry in _entries(ctx, "/services/server/status/partitions-space"):
        content = entry.get("content", {})
        capacity = number(content.get("capacity"))
        available = number(content.get("available"))
        free = number(content.get("free"))
        used = capacity - free if capacity is not None and free is not None else None
        rows.append(
            {
                "partition": content.get("mount_point"),
                "capacity": capacity,
                "available": available,
                "used": used,
                "unit": "MB",
                "fill_ratio": used / capacity
                if used is not None and capacity
                else None,
                "fs_type": content.get("fs_type"),
            }
        )
    output.render(ctx, rows)
