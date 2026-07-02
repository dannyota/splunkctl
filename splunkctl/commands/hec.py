"""HEC (HTTP Event Collector) token management via SDK."""

import json as json_mod
from typing import Any

import click
import requests as req

from splunkctl import guard, output
from splunkctl.client import get_client
from splunkctl.commands.common import fetch_page, list_options, parse_set


@click.group("hec")
def hec_group() -> None:
    """Manage HTTP Event Collector tokens."""


@hec_group.command("list")
@list_options
@click.pass_context
def list_hec(
    ctx: click.Context,
    *,
    limit: int | None,
    offset: int,
    name_filter: str | None,
) -> None:
    """List HEC tokens."""
    client = get_client(ctx)
    items = fetch_page(
        client.service.hec_tokens.list,
        limit=limit,
        offset=offset,
        name_filter=name_filter,
    )
    rows: list[dict[str, Any]] = [
        {
            "name": t.name,
            "token": t.content.get("token", ""),
            "index": t.content.get("index", ""),
            "disabled": t.content.get("disabled", ""),
            "sourcetype": t.content.get("sourcetype", ""),
        }
        for t in items
    ]
    output.render(ctx, rows, empty="No HEC tokens found.")


@hec_group.command("get")
@click.argument("name")
@click.pass_context
def get_hec(ctx: click.Context, name: str) -> None:
    """Get HEC token details."""
    client = get_client(ctx)
    try:
        token = client.service.hec_tokens[name]
    except KeyError:
        output.error(f"HEC token '{name}' not found.")
        ctx.exit(1)
        return
    row: dict[str, Any] = {
        "name": token.name,
        "token": token.content.get("token", ""),
        "index": token.content.get("index", ""),
        "indexes": token.content.get("indexes", ""),
        "sourcetype": token.content.get("sourcetype", ""),
        "disabled": token.content.get("disabled", ""),
        "useACK": token.content.get("useACK", ""),
    }
    output.render(ctx, row)


@hec_group.command("create")
@guard.guarded
@click.option("--name", required=True, help="Token name.")
@click.option("--index", default=None, help="Default index.")
@click.option("--indexes", default=None, help="Allowed indexes (comma-separated).")
@click.option("--sourcetype", default=None, help="Default source type.")
@click.option("--set", "set_pairs", multiple=True, help="KEY=VALUE (e.g. useACK=1).")
@click.pass_context
def create_hec(
    ctx: click.Context,
    name: str,
    set_pairs: tuple[str, ...],
    *,
    index: str | None,
    indexes: str | None,
    sourcetype: str | None,
) -> None:
    """Create a new HEC token."""
    kwargs: dict[str, str] = {}
    if set_pairs:
        kwargs.update(parse_set(set_pairs))
    if index:
        kwargs["index"] = index
    if indexes:
        kwargs["indexes"] = indexes
    if sourcetype:
        kwargs["sourcetype"] = sourcetype
    details = f"  name: {name}"
    for k, v in kwargs.items():
        details += f"\n  {k}: {v}"
    if not guard.check(ctx, f"Create HEC token '{name}'", details=details):
        return
    client = get_client(ctx)
    try:
        client.service.hec_tokens.create(name, **kwargs)
    except Exception as exc:
        output.error(f"Create failed: {exc}")
        ctx.exit(1)
        return
    output.info(f"HEC token '{name}' created.")


@hec_group.command("delete")
@guard.guarded
@click.argument("name")
@click.pass_context
def delete_hec(ctx: click.Context, name: str) -> None:
    """Delete a HEC token."""
    if not guard.check(ctx, f"Delete HEC token '{name}'"):
        return
    client = get_client(ctx)
    try:
        client.service.hec_tokens[name].delete()
    except KeyError:
        output.error(f"HEC token '{name}' not found.")
        ctx.exit(1)
        return
    except Exception as exc:
        output.error(f"Delete failed: {exc}")
        ctx.exit(1)
        return
    output.info(f"HEC token '{name}' deleted.")


@hec_group.command("enable")
@guard.guarded
@click.argument("name")
@click.pass_context
def enable_hec(ctx: click.Context, name: str) -> None:
    """Enable a HEC token."""
    if not guard.check(ctx, f"Enable HEC token '{name}'"):
        return
    client = get_client(ctx)
    try:
        client.service.hec_tokens[name].enable()
    except KeyError:
        output.error(f"HEC token '{name}' not found.")
        ctx.exit(1)
        return
    output.info(f"HEC token '{name}' enabled.")


@hec_group.command("disable")
@guard.guarded
@click.argument("name")
@click.pass_context
def disable_hec(ctx: click.Context, name: str) -> None:
    """Disable a HEC token."""
    if not guard.check(ctx, f"Disable HEC token '{name}'"):
        return
    client = get_client(ctx)
    try:
        client.service.hec_tokens[name].disable()
    except KeyError:
        output.error(f"HEC token '{name}' not found.")
        ctx.exit(1)
        return
    output.info(f"HEC token '{name}' disabled.")


_HEC_GLOBAL = "/services/data/inputs/http/http"


@hec_group.command("settings")
@guard.guarded
@click.option("--enable", "action", flag_value="enable", help="Enable HEC globally.")
@click.option("--disable", "action", flag_value="disable", help="Disable HEC globally.")
@click.pass_context
def hec_settings(ctx: click.Context, action: str | None) -> None:
    """Show or toggle global HEC settings."""
    client = get_client(ctx)
    svc = client.service
    if action:
        label = "Enable" if action == "enable" else "Disable"
        if not guard.check(ctx, f"{label} HEC globally"):
            return
        svc.post(_HEC_GLOBAL, disabled="0" if action == "enable" else "1")
        output.info(f"HEC globally {'enabled' if action == 'enable' else 'disabled'}.")
        return
    resp = svc.get(_HEC_GLOBAL, output_mode="json")
    body = json_mod.loads(resp.body.read())
    content: dict[str, Any] = body["entry"][0]["content"]
    row = {
        "disabled": content.get("disabled", ""),
        "port": content.get("port", ""),
        "enableSSL": content.get("enableSSL", ""),
        "dedicatedIoThreads": content.get("dedicatedIoThreads", ""),
    }
    output.render(ctx, row)


@hec_group.command("send")
@guard.guarded
@click.argument("name")
@click.argument("event")
@click.option("--index", default=None, help="Target index.")
@click.option("--sourcetype", default=None, help="Source type.")
@click.pass_context
def hec_send(
    ctx: click.Context,
    name: str,
    event: str,
    *,
    index: str | None,
    sourcetype: str | None,
) -> None:
    """Send one event through a HEC token."""
    details = f"  token: {name}\n  event: {event[:60]}"
    if not guard.check(ctx, "Send HEC event", details=details):
        return
    client = get_client(ctx)
    svc = client.service
    try:
        token_entity = svc.hec_tokens[name]
    except KeyError:
        output.error(f"HEC token '{name}' not found.")
        ctx.exit(1)
        return
    token_val = str(token_entity.content.get("token", ""))
    resp = svc.get(_HEC_GLOBAL, output_mode="json")
    body = json_mod.loads(resp.body.read())
    gcontent: dict[str, Any] = body["entry"][0]["content"]
    port = gcontent.get("port", "8088")
    ssl = str(gcontent.get("enableSSL", "1")) == "1"
    scheme = "https" if ssl else "http"
    host = svc.host
    url = f"{scheme}://{host}:{port}/services/collector/event"
    payload: dict[str, str] = {"event": event}
    if index:
        payload["index"] = index
    if sourcetype:
        payload["sourcetype"] = sourcetype
    timeout: int = ctx.obj.get("timeout", 30)
    verify: bool = getattr(svc, "verify", True)
    try:
        r = req.post(
            url,
            json=payload,
            headers={"Authorization": f"Splunk {token_val}"},
            timeout=timeout,
            verify=verify,
        )
        r.raise_for_status()
    except req.RequestException as exc:
        msg = str(exc)
        try:
            msg = r.json().get("text", msg)  # noqa: F841
        except (ValueError, AttributeError):
            pass
        output.error(f"HEC send failed: {msg}")
        ctx.exit(1)
        return
    output.info("Event sent.")
