"""Data models — CIM/tstats detection surface: definitions + acceleration.

No SDK entity for data models (unlike dashboards/lookups/HEC tokens) —
every command here is a thin, typed wrapper around the raw
``datamodel/model`` REST collection, mirroring kvstore.py/server.py. REST
calls are left to raise on failure (HTTPError, connection errors, ...); the
top-level CLI error handler (``splunkctl.errors.classify``) turns any of
those into a clean, typed error envelope — no local try/except swallowing.

Acceleration *status* (percent complete, summarized range, last error)
does NOT live on the data model resource itself: ``datamodel/model``'s
``content["acceleration"]`` field is only the *configuration* (enabled,
cron_schedule, earliest_time). Build status lives on a separate
``admin/summarization`` entity, one per accelerated model, named
``tstats:DM_<app>_<model>``. This was confirmed against this project's own
Splunk 10.4 install — not guessed — by reading the installed
``splunk.models.summarization.Summarization`` REST model class and the
Data Model Manager's own bundled JS (both ship with splunkd itself, so
they describe exactly what this REST API version does). See
docs/guides/datamodels.md for the full shape and how it was found.
"""

import json
from typing import Any

import click
from splunklib.binding import UrlEncoded

from splunkctl import guard, output
from splunkctl.client import get_client, rest_get_json
from splunkctl.commands.common import fetch_page, list_options

_OWNER = "nobody"


def _seg(value: str) -> UrlEncoded:
    """Encode one REST path segment (model name), slash included.

    Returns an SDK ``UrlEncoded`` rather than a plain ``str`` so the
    encoding survives untouched through ``Context._abspath``. Paths built
    from this MUST use ``+`` concatenation, not f-strings — see
    ``kvstore._seg`` for the full rationale (same convention, copied here
    to keep every raw-REST command group consistent).
    """
    return UrlEncoded(value, encode_slash=True)


def _parse_acceleration(content: dict[str, Any]) -> dict[str, Any]:
    """Parse a data model's acceleration *config* blob.

    ``content["acceleration"]`` is a JSON-encoded string holding the full
    acceleration configuration (enabled, earliest_time, cron_schedule,
    ...) — distinct from the few flattened ``acceleration.allowed``/
    ``acceleration.hunk.*`` keys Splunk also emits at the top level. This
    is config, not build status — see ``_summary_key``.
    """
    raw = content.get("acceleration") or "{}"
    parsed: Any = json.loads(raw)
    return parsed if isinstance(parsed, dict) else {}


def _summary_key(app: str, model_name: str) -> str:
    """The ``admin/summarization`` entity name for one accelerated model.

    Matches Splunk's own Data Model Manager (confirmed from the installed
    ``data_model_manager.js``): ``tstats:DM_<app>_<model>``.
    """
    return f"tstats:DM_{app}_{model_name}"


def _fetch_models(
    client: Any, *, app: str, limit: int | None, offset: int, name_filter: str | None
) -> list[dict[str, Any]]:
    def _fetch(**kwargs: Any) -> list[dict[str, Any]]:
        body = rest_get_json(
            client.service, "datamodel/model", owner=_OWNER, app=app, **kwargs
        )
        entries: list[dict[str, Any]] = body.get("entry", [])
        return entries

    return fetch_page(
        _fetch,
        limit=limit,
        offset=offset,
        name_filter=name_filter,
        name_of=lambda e: str(e.get("name", "")),
    )


def _resolve(client: Any, name: str, app: str) -> dict[str, Any] | None:
    """Resolve a data model by exact name, scoped to ``app`` (default: any app).

    Splunk's collection ``search=name=<name>`` performs an exact,
    case-insensitive match (confirmed live) — never a substring match —
    so this never needs client-side re-filtering. Returns ``None`` for a
    clean not-found (an empty entry list is a normal 200 response, not an
    exception); an ``--app`` naming an app that doesn't exist at all does
    raise (HTTPError 404), which is left to propagate to the central
    classifier like any other REST failure.
    """
    body = rest_get_json(
        client.service,
        "datamodel/model",
        owner=_OWNER,
        app=app,
        search=f"name={name}",
        count=1,
    )
    entries: list[dict[str, Any]] = body.get("entry", [])
    return entries[0] if entries else None


def _model_row(entry: dict[str, Any]) -> dict[str, Any]:
    content: dict[str, Any] = entry.get("content", {})
    accel = _parse_acceleration(content)
    return {
        "name": entry.get("name", ""),
        "app": entry.get("acl", {}).get("app", ""),
        "accelerated": bool(accel.get("enabled", False)),
        "disabled": bool(content.get("disabled", False)),
    }


def _acceleration_row(
    entry: dict[str, Any], by_name: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    content: dict[str, Any] = entry.get("content", {})
    accel = _parse_acceleration(content)
    app = str(entry.get("acl", {}).get("app", ""))
    model_name = str(entry.get("name", ""))
    summary = by_name.get(_summary_key(app, model_name), {})

    complete_raw = summary.get("summary.complete")
    percent: float | None = None
    if isinstance(complete_raw, (str, int, float)) and complete_raw != "":
        percent = round(float(complete_raw) * 100, 1)

    last_error = summary.get("summary.last_error") or []
    if not isinstance(last_error, list):
        last_error = [last_error]

    return {
        "name": model_name,
        "app": app,
        "enabled": bool(accel.get("enabled", False)),
        "has_summary": bool(summary),
        "is_complete": (percent >= 100.0) if percent is not None else None,
        "percent_complete": percent,
        "size": summary.get("summary.size"),
        "earliest_summarized": summary.get("summary.earliest_time"),
        "latest_summarized": summary.get("summary.latest_time"),
        "last_error": "; ".join(str(e) for e in last_error),
    }


@click.group("datamodels")
def datamodels_group() -> None:
    """CIM/tstats data models — definitions and acceleration health."""


@datamodels_group.command("list")
@click.option(
    "--app", default="-", help="Only data models in this app (default: all apps)."
)
@list_options
@click.pass_context
def list_models(
    ctx: click.Context,
    *,
    app: str,
    limit: int | None,
    offset: int,
    name_filter: str | None,
) -> None:
    """List data models: name, app, accelerated, disabled."""
    client = get_client(ctx)
    entries = _fetch_models(
        client, app=app, limit=limit, offset=offset, name_filter=name_filter
    )
    rows = [_model_row(e) for e in entries]
    output.render(ctx, rows, empty="No data models found.")


@datamodels_group.command("get")
@click.argument("name")
@click.option("--app", default="-", help="Splunk app context.")
@click.option(
    "--definition",
    is_flag=True,
    help="Print the raw model definition (objects/fields/calculations) "
    "instead of the summary row.",
)
@click.pass_context
def get_model(ctx: click.Context, name: str, *, app: str, definition: bool) -> None:
    """Get a data model's detection-engineering summary, or its raw definition."""
    client = get_client(ctx)
    entry = _resolve(client, name, app)
    if entry is None:
        output.error(f"Data model '{name}' not found.", kind="not_found")
        ctx.exit(1)
        return

    content: dict[str, Any] = entry.get("content", {})
    desc_raw = content.get("description") or "{}"
    desc: dict[str, Any] = json.loads(desc_raw)

    if definition:
        click.echo(json.dumps(desc, indent=2))
        return

    objects: list[dict[str, Any]] = desc.get("objects", [])
    object_names = [str(o.get("objectName", "")) for o in objects]
    root_search = ""
    if objects:
        constraints = objects[0].get("constraints") or []
        if constraints:
            root_search = str(constraints[0].get("search", ""))

    accel = _parse_acceleration(content)
    row = {
        "name": entry.get("name", ""),
        "app": entry.get("acl", {}).get("app", ""),
        "displayName": content.get("displayName", ""),
        "disabled": bool(content.get("disabled", False)),
        "acceleration_enabled": bool(accel.get("enabled", False)),
        "acceleration_earliest_time": accel.get("earliest_time", ""),
        "acceleration_cron_schedule": accel.get("cron_schedule", ""),
        "object_count": len(objects),
        "objects": ", ".join(object_names),
        "root_search": root_search,
    }
    output.render(ctx, row)


@datamodels_group.command("acceleration")
@click.argument("name", required=False, default=None)
@click.pass_context
def acceleration_status(ctx: click.Context, name: str | None) -> None:
    """Acceleration build status: percent complete, summarized range, errors.

    Without NAME, shows every accelerated model on the instance (or
    cleanly reports none). With NAME, shows that one model regardless of
    whether it's accelerated — ``enabled: false`` is a valid, non-error
    answer to "is this model accelerated at all".
    """
    client = get_client(ctx)

    if name is not None:
        entry = _resolve(client, name, app="-")
        if entry is None:
            output.error(f"Data model '{name}' not found.", kind="not_found")
            ctx.exit(1)
            return
        candidates = [entry]
    else:
        body = rest_get_json(
            client.service, "datamodel/model", owner=_OWNER, app="-", count=0
        )
        all_entries: list[dict[str, Any]] = body.get("entry", [])
        candidates = [
            e
            for e in all_entries
            if _parse_acceleration(e.get("content", {})).get("enabled")
        ]
        if not candidates:
            output.render(ctx, [], empty="No accelerated data models found.")
            return

    admin_body = rest_get_json(
        client.service, "admin/summarization", owner=_OWNER, app="-", count=0
    )
    by_name: dict[str, dict[str, Any]] = {
        str(e.get("name", "")): e.get("content", {})
        for e in admin_body.get("entry", [])
    }

    rows = [_acceleration_row(e, by_name) for e in candidates]
    output.render(ctx, rows, empty="No accelerated data models found.")


@datamodels_group.command("rebuild")
@guard.guarded
@click.argument("name")
@click.option("--app", default="-", help="Splunk app context.")
@click.pass_context
def rebuild_model(ctx: click.Context, name: str, *, app: str) -> None:
    """Rebuild an accelerated data model's summary (re-summarizes from scratch).

    Only meaningful for an already-accelerated model — there is no
    dedicated rebuild REST verb; this disables then re-enables
    acceleration with the same ``earliest_time`` window, exactly what
    Splunk Web's own "Rebuild" button does (confirmed against the
    installed Data Model Manager JS). A model that isn't accelerated
    exits 1 without touching anything, --yes or not.
    """
    client = get_client(ctx)
    entry = _resolve(client, name, app)
    if entry is None:
        output.error(f"Data model '{name}' not found.", kind="not_found")
        ctx.exit(1)
        return

    content: dict[str, Any] = entry.get("content", {})
    accel = _parse_acceleration(content)
    resolved_app = str(entry.get("acl", {}).get("app", ""))
    resolved_name = str(entry.get("name", name))

    if not accel.get("enabled"):
        output.error(f"Data model '{name}' is not accelerated — nothing to rebuild.")
        ctx.exit(1)
        return

    earliest = accel.get("earliest_time", "")
    details = (
        f"  app: {resolved_app}\n"
        f"  acceleration earliest_time: {earliest or '(all time)'}\n"
        "  Re-summarizes historical data from scratch (disables, then "
        "re-enables acceleration with the same window)."
    )
    if not guard.check(
        ctx, f"Rebuild acceleration for data model '{name}'", details=details
    ):
        return

    client.service.post(
        "datamodel/model/" + _seg(resolved_name),
        owner=_OWNER,
        app=resolved_app,
        acceleration="0",
    )
    client.service.post(
        "datamodel/model/" + _seg(resolved_name),
        owner=_OWNER,
        app=resolved_app,
        acceleration="1",
        **{"acceleration.earliest_time": earliest},
    )
    output.info(
        f"Rebuild triggered for data model '{resolved_name}' (app '{resolved_app}')."
    )
