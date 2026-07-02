"""KV store — collections and document CRUD via the raw REST data API.

Every command addresses ``servicesNS/nobody/<app>/storage/collections/
{config|data}/...`` — collection ownership is always ``nobody`` (KV store
convention), scoped by app with ``--app`` (default ``search``). REST calls
are left to raise on failure (HTTPError, connection errors, ...); the
top-level CLI error handler (``splunkctl.errors.classify``) turns any of
those into a clean, typed error envelope, so a down KV store never returns
blank output or a raw traceback.
"""

import json
import urllib.parse
from collections.abc import Callable
from pathlib import Path
from typing import Any

import click

from splunkctl import guard, output
from splunkctl.client import get_client, rest_get_json, rest_post_json

_OWNER = "nobody"
_CHUNK_SIZE = 500


def _seg(value: str) -> str:
    """URL-escape a REST API path segment (collection, key, name).

    Escapes all special characters including '/' so CIDR keys like
    '10.0.0.0/24' are properly addressed as single segments.
    """
    return urllib.parse.quote(value, safe="")


def _app_option[F: Callable[..., Any]](f: F) -> F:
    """Attach the uniform ``--app`` option (default: search)."""
    return click.option(
        "--app", default="search", help="Splunk app context (default: search)."
    )(f)


def _parse_json(raw: str, *, param_hint: str) -> Any:
    """Parse a JSON string, raising a usage error (exit 2) when invalid."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise click.BadParameter(f"invalid JSON: {exc}", param_hint=param_hint) from exc


def _load_doc(data: str | None, file_path: str | None) -> dict[str, Any]:
    """Load a single JSON document from ``--data`` or ``--file``.

    Raises:
        click.UsageError: Neither or both of ``data``/``file_path`` given.
        click.BadParameter: The source isn't valid JSON, or isn't a single
            JSON object.
    """
    if data is not None and file_path is not None:
        raise click.UsageError("exactly one of --data or --file is required")
    if file_path is not None:
        raw = Path(file_path).read_text(encoding="utf-8")
        hint = "--file"
    elif data is not None:
        raw = data
        hint = "--data"
    else:
        raise click.UsageError("exactly one of --data or --file is required")
    doc = _parse_json(raw, param_hint=hint)
    if not isinstance(doc, dict):
        raise click.BadParameter(
            "document must be a single JSON object", param_hint=hint
        )
    return doc


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Parse a JSONL file (one JSON object per line, blank lines skipped).

    Raises:
        click.BadParameter: A non-blank line isn't valid JSON, or isn't a
            single JSON object.
    """
    docs: list[dict[str, Any]] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise click.BadParameter(
                f"line {lineno}: invalid JSON: {exc}", param_hint="--file"
            ) from exc
        if not isinstance(parsed, dict):
            raise click.BadParameter(
                f"line {lineno}: document must be a single JSON object",
                param_hint="--file",
            )
        docs.append(parsed)
    return docs


@click.group("kvstore")
def kvstore_group() -> None:
    """KV store — collections and document CRUD (allowlists, threat intel)."""


@kvstore_group.command("collections")
@_app_option
@click.pass_context
def list_collections(ctx: click.Context, *, app: str) -> None:
    """List KV store collection names in an app."""
    client = get_client(ctx)
    body = rest_get_json(
        client.service, "storage/collections/config", owner=_OWNER, app=app
    )
    rows: list[dict[str, Any]] = []
    for entry in body.get("entry", []):
        acl: dict[str, Any] = entry.get("acl", {})
        content: dict[str, Any] = entry.get("content", {})
        rows.append(
            {
                "name": entry.get("name", ""),
                "app": acl.get("app", ""),
                "owner": acl.get("owner", ""),
                "disabled": content.get("disabled", False),
            }
        )
    output.render(ctx, rows, empty=f"No KV store collections in app '{app}'.")


@kvstore_group.command("create")
@guard.guarded
@click.argument("name")
@_app_option
@click.pass_context
def create_collection(ctx: click.Context, name: str, *, app: str) -> None:
    """Create a new, empty KV store collection."""
    if not guard.check(ctx, f"Create KV store collection '{name}' in app '{app}'"):
        return
    client = get_client(ctx)
    client.service.post("storage/collections/config", owner=_OWNER, app=app, name=name)
    output.info(f"KV store collection '{name}' created in app '{app}'.")


@kvstore_group.command("delete")
@guard.guarded
@click.argument("name")
@_app_option
@click.pass_context
def delete_collection(ctx: click.Context, name: str, *, app: str) -> None:
    """Delete a KV store collection — removes the collection and ALL its data."""
    details = "  This deletes the entire collection and all documents in it."
    if not guard.check(
        ctx,
        f"Delete KV store collection '{name}' (and all its documents) from app '{app}'",
        details=details,
    ):
        return
    client = get_client(ctx)
    client.service.delete(
        f"storage/collections/config/{_seg(name)}", owner=_OWNER, app=app
    )
    output.info(f"KV store collection '{name}' deleted from app '{app}'.")


@kvstore_group.command("query")
@click.argument("collection")
@click.option(
    "--query",
    "query_json",
    default=None,
    help="Raw JSON filter, passed through unmodified to the API's 'query' param.",
)
@click.option(
    "--limit", type=click.IntRange(min=1), default=None, help="Max documents to return."
)
@click.option(
    "--skip",
    type=click.IntRange(min=0),
    default=None,
    help="Skip the first N documents.",
)
@click.option("--sort", default=None, help="Sort spec, e.g. 'field1,-field2'.")
@_app_option
@click.pass_context
def query_collection(
    ctx: click.Context,
    collection: str,
    *,
    query_json: str | None,
    limit: int | None,
    skip: int | None,
    sort: str | None,
    app: str,
) -> None:
    """Query documents in a collection.

    ``--query``/``--limit``/``--skip``/``--sort`` map straight to the
    KV store data API's own params — filtering and paging happen
    server-side, never re-applied client-side.
    """
    params: dict[str, Any] = {}
    if query_json is not None:
        _parse_json(query_json, param_hint="--query")  # validate only, pass raw through
        params["query"] = query_json
    if limit is not None:
        params["limit"] = limit
    if skip is not None:
        params["skip"] = skip
    if sort is not None:
        params["sort"] = sort

    client = get_client(ctx)
    data = rest_get_json(
        client.service,
        f"storage/collections/data/{_seg(collection)}",
        owner=_OWNER,
        app=app,
        **params,
    )
    rows: list[dict[str, Any]] = data if isinstance(data, list) else []
    output.render(ctx, rows, empty=f"No documents matched in '{collection}'.")


@kvstore_group.command("insert")
@guard.guarded
@click.argument("collection")
@click.option("--data", "data_json", default=None, help="Single JSON document.")
@click.option(
    "--file",
    "file_path",
    type=click.Path(exists=True, dir_okay=False),
    default=None,
    help="Read the JSON document from a file.",
)
@_app_option
@click.pass_context
def insert_document(
    ctx: click.Context,
    collection: str,
    *,
    data_json: str | None,
    file_path: str | None,
    app: str,
) -> None:
    """Insert one document into a collection (exactly one of --data/--file)."""
    doc = _load_doc(data_json, file_path)
    if not guard.check(
        ctx,
        f"Insert 1 document into '{collection}' (app '{app}')",
        details=f"  document: {json.dumps(doc)}",
    ):
        return
    client = get_client(ctx)
    result = rest_post_json(
        client.service,
        f"storage/collections/data/{_seg(collection)}",
        doc,
        owner=_OWNER,
        app=app,
    )
    key = result.get("_key", "") if isinstance(result, dict) else ""
    output.info(f"Inserted document into '{collection}' (_key={key}).")


@kvstore_group.command("update")
@guard.guarded
@click.argument("collection")
@click.argument("key")
@click.option("--data", "data_json", default=None, help="Single JSON document.")
@click.option(
    "--file",
    "file_path",
    type=click.Path(exists=True, dir_okay=False),
    default=None,
    help="Read the JSON document from a file.",
)
@_app_option
@click.pass_context
def update_document(
    ctx: click.Context,
    collection: str,
    key: str,
    *,
    data_json: str | None,
    file_path: str | None,
    app: str,
) -> None:
    """Replace one document by _key (exactly one of --data/--file)."""
    doc = _load_doc(data_json, file_path)
    if not guard.check(
        ctx,
        f"Update document '{key}' in '{collection}' (app '{app}')",
        details=f"  document: {json.dumps(doc)}",
    ):
        return
    client = get_client(ctx)
    rest_post_json(
        client.service,
        f"storage/collections/data/{_seg(collection)}/{_seg(key)}",
        doc,
        owner=_OWNER,
        app=app,
    )
    output.info(f"Updated document '{key}' in '{collection}'.")


@kvstore_group.command("remove")
@guard.guarded
@click.argument("collection")
@click.argument("key", required=False)
@click.option(
    "--query",
    "query_json",
    default=None,
    help="Delete-by-query JSON (mutually exclusive with KEY).",
)
@_app_option
@click.pass_context
def remove_documents(
    ctx: click.Context,
    collection: str,
    key: str | None,
    *,
    query_json: str | None,
    app: str,
) -> None:
    """Remove one document by _key, or many by --query (exactly one required)."""
    if key is not None and query_json is not None:
        raise click.UsageError("exactly one of KEY or --query is required")

    if key is not None:
        msg = f"Remove document '{key}' from '{collection}' (app '{app}')"
        if not guard.check(ctx, msg):
            return
        client = get_client(ctx)
        client.service.delete(
            f"storage/collections/data/{_seg(collection)}/{_seg(key)}",
            owner=_OWNER,
            app=app,
        )
        output.info(f"Removed document '{key}' from '{collection}'.")
        return

    if query_json is None:
        raise click.UsageError("exactly one of KEY or --query is required")
    _parse_json(query_json, param_hint="--query")  # validate only, pass raw through
    if not guard.check(
        ctx,
        f"Remove documents from '{collection}' matching query (app '{app}')",
        details=f"  query: {query_json}",
    ):
        return
    client = get_client(ctx)
    client.service.delete(
        f"storage/collections/data/{_seg(collection)}",
        owner=_OWNER,
        app=app,
        query=query_json,
    )
    output.info(f"Removed documents from '{collection}' matching query.")


@kvstore_group.command("export")
@click.argument("collection")
@_app_option
@click.pass_context
def export_collection(ctx: click.Context, collection: str, *, app: str) -> None:
    """Export all documents in a collection as JSONL (one doc per line).

    Writes to stdout, or to the file given by the global ``--out``/``-o``
    flag. ``_key`` is preserved on every document, so ``kvstore import``
    can upsert straight back onto the same keys.
    """
    client = get_client(ctx)
    data = rest_get_json(
        client.service,
        f"storage/collections/data/{_seg(collection)}",
        owner=_OWNER,
        app=app,
    )
    docs: list[dict[str, Any]] = data if isinstance(data, list) else []
    lines = "\n".join(json.dumps(doc, default=str) for doc in docs)

    obj: dict[str, Any] = ctx.obj or {}
    out_path = obj.get("out")
    if out_path:
        Path(out_path).write_text(lines + "\n" if lines else "", encoding="utf-8")
        output.info(f"Exported {len(docs)} document(s) to {out_path}")
    else:
        if lines:
            click.echo(lines)
        output.info(f"Exported {len(docs)} document(s).")


@kvstore_group.command("import")
@guard.guarded
@click.argument("collection")
@click.option(
    "--file",
    "file_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False),
    help="JSONL file: one JSON document per line.",
)
@_app_option
@click.pass_context
def import_documents(
    ctx: click.Context, collection: str, file_path: str, *, app: str
) -> None:
    """Bulk-upsert documents from a JSONL file via batch_save.

    A document whose ``_key`` already exists in the collection is
    upserted (overwritten) — that's ``batch_save``'s own semantics, not
    special-cased here. POSTs in chunks of up to 500 documents.
    """
    docs = _read_jsonl(Path(file_path))
    n_chunks = (len(docs) + _CHUNK_SIZE - 1) // _CHUNK_SIZE if docs else 0
    details = (
        f"  {len(docs)} document(s) in {n_chunks} batch(es) of up to {_CHUNK_SIZE}"
    )
    if not guard.check(
        ctx,
        f"Import into '{collection}' from {Path(file_path).name} (app '{app}')",
        details=details,
    ):
        return

    client = get_client(ctx)
    for start in range(0, len(docs), _CHUNK_SIZE):
        chunk = docs[start : start + _CHUNK_SIZE]
        rest_post_json(
            client.service,
            f"storage/collections/data/{_seg(collection)}/batch_save",
            chunk,
            owner=_OWNER,
            app=app,
        )
    output.info(
        f"Imported {len(docs)} document(s) into '{collection}' ({n_chunks} batch(es))."
    )
