"""SOAR cross-object search — ``splunkctl soar search``."""

from __future__ import annotations

from typing import Any

import click

from splunkctl import output
from splunkctl.commands.soar._client import get_soar_client


@click.command("search")
@click.argument("query")
@click.option(
    "--categories",
    default=None,
    help="Comma-separated category filter (e.g. app,container,artifact).",
)
@click.option(
    "--page-size",
    type=int,
    default=None,
    help="Results per page.",
)
@click.option(
    "--page",
    type=int,
    default=None,
    help="Page number (1-based; server default is 1).",
)
@click.pass_context
def search(
    ctx: click.Context,
    query: str,
    categories: str | None,
    page_size: int | None,
    page: int | None,
) -> None:
    """Search across SOAR objects (apps, containers, artifacts, ...).

    QUERY is a free-text search string. Results come from /rest/search
    and may span multiple object types. Use --categories to restrict to
    specific types (comma-separated, e.g. app,container).

    Pagination is 1-based (unlike other SOAR endpoints). Without --page,
    the server defaults to page 1.
    """
    client = get_soar_client(ctx)

    params: dict[str, Any] = {"query": query}
    if categories is not None:
        params["categories"] = categories
    if page_size is not None:
        params["page_size"] = page_size
    if page is not None:
        params["page"] = page

    result = client.get("search", params=params)
    data: list[dict[str, Any]] = result.get("data", [])

    output.render(ctx, data, empty="No results.")
