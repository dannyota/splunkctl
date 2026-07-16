"""Auth-token management — list, create, revoke (Splunk 7.3+)."""

import json
from datetime import UTC, datetime
from typing import Any

import click

from splunkctl import guard, output
from splunkctl.client import get_client

_TOKENS_PATH = "/services/authorization/tokens"


def _parse_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """Flatten a token entry into a display row."""
    c: dict[str, Any] = entry.get("content", {})
    claims: dict[str, Any] = c.get("claims", {})
    # claims may arrive as a JSON string or a dict
    if isinstance(claims, str):
        try:
            claims = json.loads(claims)
        except (json.JSONDecodeError, ValueError):
            claims = {}

    exp = claims.get("exp")
    expires = (
        datetime.fromtimestamp(int(exp), tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        if exp
        else "never"
    )

    last_used = c.get("lastUsedTime")
    last_used_str = (
        datetime.fromtimestamp(int(last_used), tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        if last_used and str(last_used) != "0"
        else "never"
    )

    return {
        "id": c.get("id", entry.get("name", "")),
        "user": claims.get("sub", c.get("userName", "")),
        "audience": claims.get("aud", ""),
        "status": c.get("status", ""),
        "last_used": last_used_str,
        "expires": expires,
    }


@click.group("tokens")
def tokens_group() -> None:
    """Manage Splunk auth tokens (Splunk 7.3+)."""


@tokens_group.command("list")
@click.option("--user", default=None, help="Filter by username.")
@click.pass_context
def list_tokens(ctx: click.Context, user: str | None) -> None:
    """List auth tokens, optionally filtered by user."""
    client = get_client(ctx)
    kwargs: dict[str, Any] = {"output_mode": "json"}
    if user:
        kwargs["userName"] = user
    resp = client.service.get(_TOKENS_PATH, **kwargs)
    body: dict[str, Any] = json.loads(resp.body.read())

    rows = [_parse_entry(e) for e in body.get("entry", [])]
    output.render(ctx, rows, empty="No auth tokens found.")


@tokens_group.command("create")
@guard.guarded
@click.option("--user", required=True, help="Username to issue the token for.")
@click.option("--audience", default=None, help="Token audience claim.")
@click.option(
    "--expires-in",
    type=int,
    default=None,
    help="Token lifetime in days (omit for non-expiring).",
)
@click.pass_context
def create_token(
    ctx: click.Context,
    user: str,
    audience: str | None,
    expires_in: int | None,
) -> None:
    """Create an auth token. The token value is shown ONCE."""
    details = f"  user: {user}"
    if audience:
        details += f"\n  audience: {audience}"
    if expires_in is not None:
        details += f"\n  expires_in: {expires_in}d"

    if not guard.check(ctx, f"Create auth token for '{user}'", details=details):
        return

    client = get_client(ctx)
    kwargs: dict[str, Any] = {"output_mode": "json", "name": user}
    if audience:
        kwargs["audience"] = audience
    if expires_in is not None:
        kwargs["expires_on"] = f"+{expires_in}d"
    resp = client.service.post(_TOKENS_PATH, **kwargs)
    body: dict[str, Any] = json.loads(resp.body.read())

    entries: list[dict[str, Any]] = body.get("entry", [])
    if not entries:
        output.error("Token created but no entry returned.", kind="error")
        ctx.exit(1)
        return

    c: dict[str, Any] = entries[0].get("content", {})
    token_value: str = c.get("token", "")

    row: dict[str, Any] = {
        "id": c.get("id", ""),
        "user": user,
        "token": token_value,
    }
    output.render(ctx, row)
    output.warning("Save this token now — it cannot be retrieved again.")


@tokens_group.command("revoke")
@guard.guarded
@click.argument("token_id")
@click.pass_context
def revoke_token(ctx: click.Context, token_id: str) -> None:
    """Revoke (delete) an auth token by its ID."""
    if not guard.check(ctx, f"Revoke auth token '{token_id}'"):
        return

    client = get_client(ctx)
    client.service.delete(
        f"{_TOKENS_PATH}/{token_id}",
        output_mode="json",
    )
    output.info(f"Token '{token_id}' revoked.")
