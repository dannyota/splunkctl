"""Raw Splunk REST calls with guarded writes and faithful JSON envelopes."""

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import click
from splunklib.binding import UrlEncoded

from splunkctl import guard, output
from splunkctl.api_paths import validate_path
from splunkctl.client import get_client
from splunkctl.errors import WebSessionError


@click.group("api")
def api_group() -> None:
    """Call Splunk REST endpoints."""


def _params(values: tuple[str, ...]) -> list[tuple[str, str]]:
    pairs = []
    for value in values:
        key, sep, val = value.partition("=")
        if not sep or not key:
            raise click.BadParameter("--param requires KEY=VALUE")
        if key.lower() == "output_mode":
            raise click.BadParameter("output_mode is reserved as json")
        pairs.append((key, val))
    return pairs


def _render(ctx: click.Context, data: Any) -> None:
    obj = ctx.ensure_object(dict)
    if obj.get("format") is None:
        obj["format"] = "json"
    if data is None:
        data = []
    if not isinstance(data, (dict, list)) or (
        isinstance(data, list) and any(not isinstance(row, dict) for row in data)
    ):
        raise WebSessionError(
            "API response must be a JSON object or object array", kind="http"
        )
    output.render(ctx, data)


def _request(
    ctx: click.Context,
    method: str,
    path: str,
    params: list[tuple[str, str]],
    *,
    body: str | None = None,
    content_type: str | None = None,
) -> Any:
    query = params if method != "POST" or body is not None else []
    headers = []
    if method == "POST":
        if body is None:
            body = urlencode(params)
            content_type = content_type or "application/x-www-form-urlencoded"
        if content_type:
            headers.append(("Content-Type", content_type))
    target = UrlEncoded(
        path + "?" + urlencode([*query, ("output_mode", "json")]), skip_encode=True
    )
    service = get_client(ctx).service
    if method == "POST":
        response = service.post(
            target, headers=headers, body=(body or "").encode("utf-8")
        )
    else:
        response = service.request(target, method=method, headers=headers)
    raw = response.body.read()
    try:
        return json.loads(raw) if raw else None
    except (ValueError, UnicodeDecodeError) as exc:
        raise WebSessionError("API response is not JSON", kind="http") from exc


def _describe(data: Any) -> list[dict[str, Any]]:
    # JSON discovery uses entry.fields; eai:attributes is XML-only.
    entries = data.get("entry") if isinstance(data, dict) else None
    rows: list[dict[str, Any]] = []
    found = False
    if isinstance(entries, list):
        for entry in entries:
            attrs = entry.get("fields") if isinstance(entry, dict) else None
            if not isinstance(attrs, dict):
                continue
            for key in ("required", "optional", "wildcard"):
                fields = attrs.get(key)
                if not isinstance(fields, list) or any(
                    not isinstance(f, str) for f in fields
                ):
                    raise WebSessionError(
                        "Endpoint field discovery returned unsupported attributes",
                        kind="http",
                    )
                found = True
                rows.extend({"field": field, "kind": key} for field in fields)
    if not found:
        raise WebSessionError("Endpoint does not support field discovery", kind="http")
    return rows


@api_group.command("get")
@click.argument("path")
@click.option("--param", multiple=True, help="Add a request parameter.")
@click.option(
    "--describe",
    is_flag=True,
    help="List required, optional and wildcard fields from PATH/_new.",
)
@click.pass_context
def api_get(
    ctx: click.Context, path: str, param: tuple[str, ...], *, describe: bool
) -> None:
    """Read a REST endpoint."""
    path = validate_path(path)
    params = _params(param)
    data = _request(
        ctx, "GET", path.rstrip("/") + "/_new" if describe else path, params
    )
    _render(ctx, _describe(data) if describe else data)


@api_group.command("post")
@guard.guarded
@click.argument("path")
@click.option("--param", multiple=True, help="Add a request parameter.")
@click.option("--body", default=None, help="Send a raw request body.")
@click.option(
    "--body-file",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Read the request body from a file.",
)
@click.option("--content-type", default=None, help="Set the request content type.")
@click.pass_context
def api_post(
    ctx: click.Context,
    path: str,
    param: tuple[str, ...],
    body: str | None,
    body_file: Path | None,
    content_type: str | None,
) -> None:
    """Preview a REST POST; --yes executes."""
    path = validate_path(path)
    params = _params(param)
    if body is not None and body_file is not None:
        raise click.UsageError("--body and --body-file are mutually exclusive")
    if body_file is not None:
        body = body_file.read_text()
    if guard.check(ctx, f"POST {path}"):
        _render(
            ctx,
            _request(ctx, "POST", path, params, body=body, content_type=content_type),
        )


@api_group.command("delete")
@guard.guarded
@click.argument("path")
@click.option("--param", multiple=True, help="Add a request parameter.")
@click.pass_context
def api_delete(ctx: click.Context, path: str, param: tuple[str, ...]) -> None:
    """Preview a REST DELETE; --yes executes."""
    path = validate_path(path)
    params = _params(param)
    if guard.check(ctx, f"DELETE {path}"):
        _render(ctx, _request(ctx, "DELETE", path, params))
