"""Shared helpers for command groups."""

from collections.abc import Callable
from typing import Any

import click

from splunkctl import output

_ALERT_TYPES = (
    "custom",
    "number of events",
    "number of hosts",
    "number of sources",
)
_COMPARATORS = (
    "greater than",
    "less than",
    "equal to",
    "not equal to",
    "drops by",
    "rises by",
)


def parse_set(pairs: tuple[str, ...]) -> dict[str, str]:
    """Parse repeatable ``--set KEY=VALUE`` options into a dict.

    Values may contain ``=``; the split happens on the first one.

    Raises:
        click.BadParameter: On a pair without ``=`` or a read-only key.
    """
    out: dict[str, str] = {}
    for pair in pairs:
        key, sep, value = pair.partition("=")
        key = key.strip()
        if not sep or not key:
            raise click.BadParameter(f"expected KEY=VALUE, got '{pair}'")
        if key.startswith("eai:"):
            raise click.BadParameter(f"'{key}' is read-only")
        out[key] = value
    return out


def read_results(stream: Any) -> list[dict[str, Any]]:
    """Parse a Splunk JSON results stream into a list of dicts."""
    from splunklib.results import JSONResultsReader

    reader: Any = JSONResultsReader(stream)
    return [item for item in reader if isinstance(item, dict)]


def alert_options[F: Callable[..., Any]](f: F) -> F:
    """Attach the alert-semantics options shared by rules create/update."""
    opts = [
        click.option(
            "--earliest", default=None, help="dispatch.earliest_time (e.g. -24h)."
        ),
        click.option("--latest", default=None, help="dispatch.latest_time (e.g. now)."),
        click.option(
            "--alert-type",
            type=click.Choice(_ALERT_TYPES),
            default=None,
            help="Alert trigger type (defaults to 'number of events' "
            "when a comparator is set).",
        ),
        click.option(
            "--alert-comparator",
            type=click.Choice(_COMPARATORS),
            default=None,
            help="Trigger comparator (requires --alert-threshold).",
        ),
        click.option(
            "--alert-threshold",
            default=None,
            help="Trigger threshold (number or percentage).",
        ),
        click.option(
            "--severity",
            type=click.IntRange(1, 6),
            default=None,
            help="Alert severity 1 (info) to 6 (fatal).",
        ),
        click.option(
            "--throttle", type=int, default=None, help="Throttle window in seconds."
        ),
        click.option(
            "--throttle-fields",
            default=None,
            help="Comma-separated fields to throttle by.",
        ),
        click.option(
            "--track/--no-track",
            "track",
            default=None,
            help="List firings under triggered alerts.",
        ),
        click.option(
            "--schedule-window",
            default=None,
            help="Scheduler window in minutes, or 'auto'.",
        ),
        click.option(
            "--set",
            "set_pairs",
            multiple=True,
            help="Raw saved-search field KEY=VALUE (repeatable); "
            "explicit flags win over --set.",
        ),
    ]
    for opt in reversed(opts):
        f = opt(f)
    return f


def alert_kwargs(
    *,
    earliest: str | None,
    latest: str | None,
    alert_type: str | None,
    alert_comparator: str | None,
    alert_threshold: str | None,
    severity: int | None,
    throttle: int | None,
    throttle_fields: str | None,
    track: bool | None,
    schedule_window: str | None,
    set_pairs: tuple[str, ...],
) -> dict[str, str]:
    """Translate alert flags into saved-search REST fields.

    Starts from ``--set`` pairs; explicit flags overwrite them.
    """
    if (alert_comparator is None) != (alert_threshold is None):
        raise click.BadParameter(
            "--alert-comparator and --alert-threshold must be used together"
        )
    kwargs: dict[str, str] = parse_set(set_pairs)
    if earliest is not None:
        kwargs["dispatch.earliest_time"] = earliest
    if latest is not None:
        kwargs["dispatch.latest_time"] = latest
    if alert_comparator is not None and alert_type is None:
        alert_type = "number of events"
    if alert_type is not None:
        kwargs["alert_type"] = alert_type
    if alert_comparator is not None:
        kwargs["alert_comparator"] = alert_comparator
    if alert_threshold is not None:
        kwargs["alert_threshold"] = str(alert_threshold)
    if severity is not None:
        kwargs["alert.severity"] = str(severity)
    if throttle is not None:
        kwargs["alert.suppress"] = "1"
        kwargs["alert.suppress.period"] = f"{throttle}s"
    if throttle_fields is not None:
        kwargs["alert.suppress.fields"] = throttle_fields
    if track is not None:
        kwargs["alert.track"] = "1" if track else "0"
    if schedule_window is not None:
        kwargs["schedule_window"] = schedule_window
    return kwargs


# Known alert actions and the companion field Splunk rejects --yes without.
# One-line adds only — this is advisory, not exhaustive.
_REQUIRED_ACTION_FIELDS: dict[str, str] = {
    "email": "action.email.to",
    "webhook": "action.webhook.param.url",
}


def warn_missing_action_fields(
    actions: str,
    kwargs: dict[str, Any],
    existing: dict[str, Any] | None = None,
) -> None:
    """Warn on stderr for enabled actions missing a known-required field.

    Advisory only — the server remains the authority. Checks ``kwargs``
    (explicit flags plus ``--set`` pairs) for the companion field; for
    updates, ``existing`` (the saved search's current server-side content)
    also satisfies the check. Actions outside ``_REQUIRED_ACTION_FIELDS``
    are silently skipped.
    """
    for act in (a.strip() for a in actions.split(",") if a.strip()):
        field = _REQUIRED_ACTION_FIELDS.get(act)
        if field is None or kwargs.get(field):
            continue
        if existing is not None and existing.get(field):
            continue
        output.warning(
            f"action '{act}' requires {field} — the server will reject "
            "--yes without it."
        )
