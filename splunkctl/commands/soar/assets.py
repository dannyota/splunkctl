"""SOAR asset CRUD + test connectivity + ingest-status."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import click

from splunkctl import guard, output
from splunkctl.commands.soar._client import get_soar_client
from splunkctl.soar.client import SOARError

# Max polls for async test_connectivity result.
_TEST_MAX_POLLS = 12
_TEST_POLL_INTERVAL = 2.5


def _parse_set_pairs(raw: tuple[str, ...]) -> dict[str, str]:
    """Parse ``key=value`` pairs into a config dict."""
    cfg: dict[str, str] = {}
    for pair in raw:
        key, _, value = pair.partition("=")
        if key:
            cfg[key] = value
    return cfg


def _password_keys_from_app(
    client: Any,
    app_id: int,
) -> set[str]:
    """Return config keys with ``data_type: password`` from the app schema."""
    try:
        app = client.get(f"app/{app_id}", params={})
    except SOARError:
        return set()
    if not isinstance(app, dict):
        return set()
    config_schema = app.get("configuration", {})
    if not isinstance(config_schema, dict):
        return set()
    return {
        k
        for k, v in config_schema.items()
        if isinstance(v, dict) and v.get("data_type") == "password"
    }


def _mask_secrets(
    config: dict[str, Any],
    secret_keys: set[str],
) -> dict[str, Any]:
    """Return a copy of *config* with password-type values replaced by ****."""
    masked: dict[str, Any] = {}
    for k, v in config.items():
        masked[k] = "****" if k in secret_keys else v
    return masked


# ---------------------------------------------------------------------------
# Click group
# ---------------------------------------------------------------------------


@click.group("assets")
def assets_group() -> None:
    """Asset CRUD — list, get, create, update, delete, test."""


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


@assets_group.command("list")
@click.option(
    "--limit",
    default=None,
    type=click.IntRange(min=1),
    help="Page size.",
)
@click.pass_context
def list_cmd(ctx: click.Context, *, limit: int | None) -> None:
    """List configured assets."""
    client = get_soar_client(ctx)

    params: dict[str, Any] = {}
    if limit is not None:
        params["page_size"] = limit

    try:
        result = client.get("asset", params=params)
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return

    data = result.get("data", []) if isinstance(result, dict) else []
    output.render(ctx, data, empty="No assets found.")


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------


@assets_group.command("get")
@click.argument("asset_id", type=int)
@click.pass_context
def get_cmd(ctx: click.Context, *, asset_id: int) -> None:
    """Get an asset by ID."""
    client = get_soar_client(ctx)

    try:
        result = client.get(f"asset/{asset_id}", params={})
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return

    if isinstance(result, dict):
        output.render(ctx, result)
    else:
        output.render(ctx, [], empty=f"No asset {asset_id} found.")


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------


@assets_group.command("create")
@guard.guarded
@click.option("--name", required=True, help="Asset name.")
@click.option("--app-id", required=True, type=int, help="App ID.")
@click.option("--description", default=None, help="Description.")
@click.option(
    "--set",
    "set_pairs",
    multiple=True,
    help="Config key=value (repeatable).",
)
@click.option(
    "--file",
    "config_file",
    type=click.Path(exists=True),
    default=None,
    help="JSON file with configuration.",
)
@click.pass_context
def create_cmd(
    ctx: click.Context,
    *,
    name: str,
    app_id: int,
    description: str | None,
    set_pairs: tuple[str, ...],
    config_file: str | None,
) -> None:
    """Create an asset. Config from --set key=value or --file JSON."""
    config: dict[str, Any] = {}
    if config_file is not None:
        config = json.loads(Path(config_file).read_text())
    config.update(_parse_set_pairs(set_pairs))

    body: dict[str, Any] = {"name": name, "app_id": app_id}
    if config:
        body["configuration"] = config
    if description is not None:
        body["description"] = description

    # Mask secrets in preview
    secret_keys = (
        _password_keys_from_app(get_soar_client(ctx), app_id) if config else set()
    )
    preview_body = dict(body)
    if config and secret_keys:
        preview_body["configuration"] = _mask_secrets(config, secret_keys)

    details = json.dumps(preview_body, indent=2)
    if not guard.soar_check(ctx, f"Create asset '{name}'", details=details):
        return

    client = get_soar_client(ctx)
    try:
        result = client.post("asset", body=body)
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return

    new_id = result.get("id", "?") if isinstance(result, dict) else "?"
    output.info(f"Asset created: id={new_id}")
    if isinstance(result, dict):
        output.render(ctx, result)


# ---------------------------------------------------------------------------
# update
# ---------------------------------------------------------------------------


@assets_group.command("update")
@guard.guarded
@click.argument("asset_id", type=int)
@click.option("--name", default=None, help="New asset name.")
@click.option("--description", default=None, help="New description.")
@click.option(
    "--set",
    "set_pairs",
    multiple=True,
    help="Config key=value to merge (repeatable).",
)
@click.option(
    "--file",
    "config_file",
    type=click.Path(exists=True),
    default=None,
    help="JSON file with configuration to merge.",
)
@click.option(
    "--replace",
    is_flag=True,
    default=False,
    help="Full-replace configuration instead of merge.",
)
@click.pass_context
def update_cmd(
    ctx: click.Context,
    *,
    asset_id: int,
    name: str | None,
    description: str | None,
    set_pairs: tuple[str, ...],
    config_file: str | None,
    replace: bool,
) -> None:
    """Update an asset. Fetch-merge-post by default; --replace for full replace."""
    new_config: dict[str, Any] = {}
    if config_file is not None:
        new_config = json.loads(Path(config_file).read_text())
    new_config.update(_parse_set_pairs(set_pairs))

    has_config = bool(new_config)
    has_meta = name is not None or description is not None

    if not has_config and not has_meta:
        output.error(
            "Nothing to update -- provide --set, --file, --name, or --description.",
            kind="usage",
        )
        ctx.exit(1)
        return

    client = get_soar_client(ctx)

    # Fetch existing asset for merge (unless --replace)
    try:
        existing = client.get(f"asset/{asset_id}", params={})
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return

    if not isinstance(existing, dict):
        output.error(f"Asset {asset_id} not found.", kind="not_found")
        ctx.exit(1)
        return

    # Build merged config
    if has_config and not replace:
        old_config: dict[str, Any] = existing.get("configuration", {}) or {}
        merged_config = {**old_config, **new_config}
    elif has_config:
        merged_config = new_config
    else:
        merged_config = existing.get("configuration", {}) or {}

    # Build full payload (POST is full-replace on the asset)
    body: dict[str, Any] = {}
    body["name"] = name if name is not None else existing.get("name", "")
    body["configuration"] = merged_config
    if description is not None:
        body["description"] = description
    elif "description" in existing:
        body["description"] = existing["description"]

    # Mask secrets in dry-run preview
    app_id = existing.get("app") or existing.get("app_id")
    secret_keys: set[str] = set()
    if app_id is not None:
        secret_keys = _password_keys_from_app(client, int(app_id))

    preview_body = dict(body)
    if secret_keys:
        preview_body["configuration"] = _mask_secrets(merged_config, secret_keys)

    details = json.dumps(preview_body, indent=2)
    if not guard.soar_check(ctx, f"Update asset {asset_id}", details=details):
        return

    try:
        result = client.post(f"asset/{asset_id}", body=body)
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return

    output.info(f"Asset {asset_id} updated.")
    if isinstance(result, dict) and result:
        output.render(ctx, result)


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


@assets_group.command("delete")
@guard.guarded
@click.argument("asset_id", type=int)
@click.pass_context
def delete_cmd(ctx: click.Context, *, asset_id: int) -> None:
    """Delete an asset by ID."""
    if not guard.soar_check(ctx, f"Delete asset {asset_id}"):
        return

    client = get_soar_client(ctx)
    try:
        result = client.delete(f"asset/{asset_id}")
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return

    output.render(ctx, result if isinstance(result, dict) else {"id": asset_id})


# ---------------------------------------------------------------------------
# test (connectivity)
# ---------------------------------------------------------------------------


@assets_group.command("test")
@guard.guarded
@click.argument("asset_id", type=int)
@click.option(
    "--timeout",
    default=30,
    type=int,
    help="Max seconds to poll for test result.",
)
@click.pass_context
def test_cmd(ctx: click.Context, *, asset_id: int, timeout: int) -> None:
    """Test asset connectivity. Posts to /rest/asset/<id>/test then polls.

    The test runs asynchronously on the SOAR server. Results appear in
    /rest/app_status and in the SOAR UI under the asset's configuration
    page. If polling times out, the test may still complete on the server.
    """
    if not guard.soar_check(ctx, f"Test asset {asset_id}"):
        return

    client = get_soar_client(ctx)

    try:
        trigger = client.post(f"asset/{asset_id}/test", body={})
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return

    triggered = isinstance(trigger, dict) and trigger.get("success")
    output.info(f"Test triggered for asset {asset_id}; polling for result...")

    deadline = time.monotonic() + timeout
    polls = 0
    while polls < _TEST_MAX_POLLS and time.monotonic() < deadline:
        time.sleep(_TEST_POLL_INTERVAL)
        polls += 1
        try:
            status_resp = client.get(
                "app_status",
                params={"_filter_asset_id": asset_id},
            )
        except SOARError:
            continue

        data = status_resp.get("data", []) if isinstance(status_resp, dict) else []
        for entry in data:
            if not isinstance(entry, dict):
                continue
            st = entry.get("status", "")
            if st in ("success", "failed", "error"):
                output.render(ctx, entry)
                if st != "success":
                    ctx.exit(1)
                return

    if triggered:
        output.render(
            ctx,
            {"asset_id": asset_id, "status": "triggered", "poll": "timed_out"},
        )
        output.warning(
            f"Test triggered successfully but polling timed out after {timeout}s. "
            "Check the SOAR UI for the final result."
        )
    else:
        output.warning(
            f"Timed out after {timeout}s polling for test result. "
            "Check the SOAR UI for the outcome."
        )


# ---------------------------------------------------------------------------
# ingest-status (top-level soar command, not under assets group)
# ---------------------------------------------------------------------------


@click.command("ingest-status")
@click.pass_context
def ingest_status_cmd(ctx: click.Context) -> None:
    """Ingestion health — poller records from /rest/ingestion_status + app_status."""
    client = get_soar_client(ctx)

    try:
        ingest = client.get("ingestion_status", params={})
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return

    ingest_data: list[dict[str, Any]] = (
        ingest.get("data", []) if isinstance(ingest, dict) else []
    )

    # Enrich with app_status where possible.
    try:
        app_status_resp = client.get("app_status", params={})
        app_status_data: list[dict[str, Any]] = (
            app_status_resp.get("data", []) if isinstance(app_status_resp, dict) else []
        )
    except SOARError:
        app_status_data = []

    # Build lookup by asset_id for rollup.
    status_by_asset: dict[int, dict[str, Any]] = {}
    for entry in app_status_data:
        if isinstance(entry, dict) and "asset_id" in entry:
            status_by_asset[int(entry["asset_id"])] = entry

    # Merge app_status into ingestion records.
    rows: list[dict[str, Any]] = []
    for rec in ingest_data:
        if not isinstance(rec, dict):
            continue
        row = dict(rec)
        aid = rec.get("asset_id")
        if aid is not None and int(aid) in status_by_asset:
            st = status_by_asset[int(aid)]
            row["app_status"] = st.get("status", "")
            row["app_message"] = st.get("message", "")
        rows.append(row)

    output.render(ctx, rows, empty="No ingestion records found.")
