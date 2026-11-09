"""Runtime logger levels, reset when splunkd restarts."""

import json
from typing import Any

import click

from splunkctl import guard, output
from splunkctl.client import get_client
from splunkctl.rest_adapters import _segment

_PATH = "/services/server/logger"


def _rows(service: Any, component: str | None) -> list[dict[str, Any]]:
    path = _PATH + "/" + _segment(component) if component is not None else _PATH
    kwargs: dict[str, Any] = {"output_mode": "json"}
    if component is None:
        kwargs["count"] = 0
    response = service.get(path, **kwargs)
    body: dict[str, Any] = json.loads(response.body.read())
    return [
        {"component": entry.get("name"), "level": entry.get("content", {}).get("level")}
        for entry in body.get("entry", [])
    ]


@click.group("log-level")
def log_level_group() -> None:
    """Manage runtime logging levels. Restarting splunkd resets changes."""


@log_level_group.command("get")
@click.argument("component", required=False)
@click.pass_context
def get_level(ctx: click.Context, component: str | None) -> None:
    """Show runtime logging levels for one component or every component."""
    output.render(ctx, _rows(get_client(ctx).service, component))


@log_level_group.command("set")
@guard.guarded
@click.argument("component")
@click.argument(
    "level", type=click.Choice(["DEBUG", "INFO", "WARN", "ERROR"], case_sensitive=False)
)
@click.pass_context
def set_level(ctx: click.Context, component: str, level: str) -> None:
    """Preview or set a runtime logging level. Restarting splunkd resets it."""
    service = get_client(ctx).service
    before = _rows(service, component)
    if not before:
        output.error(f"Logger '{component}' not found.", kind="not_found")
        ctx.exit(1)
    if before[0]["level"] == level:
        output.render(ctx, before)
        output.info("Logging level unchanged.")
        return
    details = (
        f"  level: {before[0]['level']} -> {level}\n"
        "  Runtime only: restarting splunkd resets this change."
    )
    if not guard.check(ctx, f"Set logger '{component}'", details=details):
        return
    service.post(_PATH + "/" + _segment(component), output_mode="json", level=level)
    after = _rows(service, component)
    if not after or after[0]["level"] != level:
        output.error(f"Logger '{component}' read-back did not confirm level {level}.")
        ctx.exit(1)
    output.render(ctx, after)
