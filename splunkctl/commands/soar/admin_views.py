"""SOAR admin visibility — settings, stats, meta vocabularies."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import click

from splunkctl import output
from splunkctl.commands.soar._client import get_soar_client
from splunkctl.soar.client import SOARClient, SOARError

type _VocabHandler = Callable[[click.Context, SOARClient], None]

# -- Widget catalog (17 known widgets on SOAR 8.5.0.248) -------------------

_ALL_WIDGETS: list[str] = [
    "container_stats",
    "containers_workload",
    "sla_stats",
    "pending_approvals",
    "top_playbooks_actions",
    "roi_summary",
    "containers_by_label",
    "containers_by_severity",
    "containers_by_status",
    "containers_by_type",
    "top_artifacts",
    "top_indicators",
    "top_responders",
    "new_artifacts",
    "event_overview",
    "indicator_overview",
    "mean_time_to_resolve",
]

_DEFAULT_WIDGETS: list[str] = [
    "container_stats",
    "containers_workload",
    "sla_stats",
    "pending_approvals",
]

_VOCAB_CHOICES: list[str] = [
    "severities",
    "statuses",
    "labels",
    "tags",
    "cef",
    "features",
]


# -- settings ---------------------------------------------------------------


@click.command("settings")
@click.option(
    "--section",
    default=None,
    help="Filter to a single section (e.g. auth_settings, debug_settings).",
)
@click.pass_context
def settings(ctx: click.Context, *, section: str | None) -> None:
    """Read-only dump of SOAR system settings (37 sections)."""
    client = get_soar_client(ctx)
    data = client.get("system_settings")

    if not isinstance(data, dict):
        output.render(ctx, [], empty="No settings available.")
        return

    if section:
        value = data.get(section)
        if value is None:
            output.render(ctx, [], empty=f"Section '{section}' not found.")
            return
        output.render(ctx, {"section": section, "settings": value})
        return

    rows: list[dict[str, Any]] = []
    for key in sorted(data):
        rows.append({"section": key, "settings": data[key]})
    output.render(ctx, rows, empty="No settings available.")


# -- stats ------------------------------------------------------------------


@click.command("stats")
@click.option("--widget", default=None, help="Fetch a single widget by name.")
@click.option("--list", "list_widgets", is_flag=True, help="List all known widgets.")
@click.pass_context
def stats(ctx: click.Context, *, widget: str | None, list_widgets: bool) -> None:
    """SOC metrics from widget_data endpoints."""
    if list_widgets:
        catalog = [{"name": w} for w in _ALL_WIDGETS]
        output.render(ctx, catalog)
        return

    client = get_soar_client(ctx)

    if widget:
        _fetch_widget(ctx, client, widget)
        return

    # Default: fetch the four summary widgets
    rows: list[dict[str, Any]] = []
    for name in _DEFAULT_WIDGETS:
        try:
            data = client.get(f"widget_data/{name}")
        except Exception:
            data = {"error": "unavailable"}
        rows.append({"widget": name, "data": data})
    output.render(ctx, rows)


def _fetch_widget(ctx: click.Context, client: SOARClient, name: str) -> None:
    """Fetch a single widget; raises SOARError on not-found."""
    try:
        data = client.get(f"widget_data/{name}")
    except SOARError as exc:
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return
    output.render(ctx, {"widget": name, "data": data})


# -- meta -------------------------------------------------------------------


@click.command("meta")
@click.argument("vocabulary", type=click.Choice(_VOCAB_CHOICES))
@click.pass_context
def meta(ctx: click.Context, *, vocabulary: str) -> None:
    """Vocabulary lookups — severities, statuses, labels, tags, cef, features."""
    client = get_soar_client(ctx)

    handler = _VOCAB_HANDLERS.get(vocabulary)
    if handler is None:
        output.error(f"Unknown vocabulary: {vocabulary}", kind="usage")
        ctx.exit(1)
        return
    handler(ctx, client)


def _meta_severities(ctx: click.Context, client: SOARClient) -> None:
    data = client.get("severity")
    rows: list[dict[str, Any]] = data.get("data", []) if isinstance(data, dict) else []
    output.render(ctx, rows, empty="No severities found.")


def _meta_statuses(ctx: click.Context, client: SOARClient) -> None:
    data = client.get("container_status")
    rows: list[dict[str, Any]] = data.get("data", []) if isinstance(data, dict) else []
    output.render(ctx, rows, empty="No statuses found.")


def _meta_labels(ctx: click.Context, client: SOARClient) -> None:
    data = client.get("container_options")
    labels: list[str] = data.get("label", []) if isinstance(data, dict) else []
    rows = [{"label": lb} for lb in labels]
    output.render(ctx, rows, empty="No labels found.")
    if rows and output.is_table(ctx):
        output.info("Note: label creation is UI-only (no REST endpoint).")


def _meta_tags(ctx: click.Context, client: SOARClient) -> None:
    data = client.get("container_options")
    tags: list[str] = data.get("tags", []) if isinstance(data, dict) else []
    rows = [{"tag": t} for t in tags]
    output.render(ctx, rows, empty="No tags found.")


def _meta_cef(ctx: click.Context, client: SOARClient) -> None:
    data = client.get("cef")
    rows: list[dict[str, Any]] = data.get("data", []) if isinstance(data, dict) else []
    output.render(ctx, rows, empty="No CEF fields found.")


def _meta_features(ctx: click.Context, client: SOARClient) -> None:
    data = client.get("feature_flag")
    rows: list[dict[str, Any]] = data.get("data", []) if isinstance(data, dict) else []
    output.render(ctx, rows, empty="No feature flags found.")


_VOCAB_HANDLERS: dict[str, _VocabHandler] = {
    "severities": _meta_severities,
    "statuses": _meta_statuses,
    "labels": _meta_labels,
    "tags": _meta_tags,
    "cef": _meta_cef,
    "features": _meta_features,
}
