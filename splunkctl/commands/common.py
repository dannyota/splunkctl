"""Shared helpers for command groups."""

from collections.abc import Callable, Iterable
from typing import Any

import click

from splunkctl import output


def spl_quote(value: str) -> str:
    """Quote a value for an SPL ``field=value`` search filter.

    Escapes backslashes FIRST, then quotes, to prevent SPL injection.
    A value ending in backslash or containing backslash-quote sequences
    cannot break out of the literal or be reinterpreted by the SPL parser.
    """
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


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


def list_options[F: Callable[..., Any]](f: F) -> F:
    """Attach the uniform list options: ``--limit``, ``--offset``, ``--filter``.

    Defaults leave behavior unchanged: without flags the SDK call is made
    bare and fetches the entire collection.
    """
    opts = [
        click.option(
            "--limit",
            type=click.IntRange(min=1),
            default=None,
            help="Return at most N entries (default: all).",
        ),
        click.option(
            "--offset",
            type=click.IntRange(min=0),
            default=0,
            help="Skip the first N entries.",
        ),
        click.option(
            "--filter",
            "name_filter",
            default=None,
            help="Case-insensitive name substring; --limit/--offset then "
            "apply to the filtered set.",
        ),
    ]
    for opt in reversed(opts):
        f = opt(f)
    return f


def _entity_name(entity: Any) -> str:
    return str(entity.name)


def filter_by_name[T](
    items: Iterable[T],
    name_filter: str | None,
    *,
    name_of: Callable[[Any], str] | None = None,
) -> list[T]:
    """Case-insensitive name-substring filter; pass-through when ``None``."""
    if name_filter is None:
        return list(items)
    key = name_of if name_of is not None else _entity_name
    needle = name_filter.lower()
    return [item for item in items if needle in key(item).lower()]


def page_slice[T](items: list[T], *, limit: int | None, offset: int) -> list[T]:
    """Apply client-side offset then limit to an already-filtered list."""
    if offset:
        items = items[offset:]
    if limit is not None:
        items = items[:limit]
    return items


def fetch_page[T](
    fetch: Callable[..., Iterable[T]],
    *,
    limit: int | None,
    offset: int,
    name_filter: str | None,
    name_of: Callable[[Any], str] | None = None,
) -> list[T]:
    """Fetch one page of entities from an SDK collection ``.list``-style call.

    Without ``--filter`` paging is server-side: ``count``/``offset`` pass
    through to the SDK call, and are omitted entirely when unset so the
    fetch-everything default stays untouched. With ``--filter`` everything
    is fetched, filtered on the entity name, and offset/limit apply
    client-side to the filtered set.
    """
    if name_filter is None:
        kwargs: dict[str, int] = {}
        if limit is not None:
            kwargs["count"] = limit
        if offset:
            kwargs["offset"] = offset
        return list(fetch(**kwargs))
    items = filter_by_name(fetch(), name_filter, name_of=name_of)
    return page_slice(items, limit=limit, offset=offset)


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
            "--email-to",
            default=None,
            help="Email action recipient(s) (action.email.to); does not "
            "enable the action by itself — pass --actions email too. "
            "Conflicts with --set action.email.to.",
        ),
        click.option(
            "--email-subject",
            default=None,
            help="Email action subject (action.email.subject). Conflicts "
            "with --set action.email.subject.",
        ),
        click.option(
            "--webhook-url",
            default=None,
            help="Webhook action URL (action.webhook.param.url); does not "
            "enable the action by itself — pass --actions webhook too. "
            "Conflicts with --set action.webhook.param.url.",
        ),
        click.option(
            "--set",
            "set_pairs",
            multiple=True,
            help="Raw saved-search field KEY=VALUE (repeatable); "
            "--email-to/--email-subject/--webhook-url conflict with their "
            "equivalent --set fields (exit 2), not override.",
        ),
    ]
    for opt in reversed(opts):
        f = opt(f)
    return f


# Friendly action flags, in the order they're merged: (flag, field, action).
_ACTION_FLAGS: tuple[tuple[str, str, str], ...] = (
    ("--email-to", "action.email.to", "email"),
    ("--email-subject", "action.email.subject", "email"),
    ("--webhook-url", "action.webhook.param.url", "webhook"),
)


def _merge_action_flags(
    kwargs: dict[str, str],
    *,
    actions: str | None,
    email_to: str | None,
    email_subject: str | None,
    webhook_url: str | None,
) -> None:
    """Merge --email-to/--email-subject/--webhook-url into ``kwargs``.

    Each flag is sugar for one raw ``action.*`` field. A flag and an
    equivalent ``--set`` for the same field is a usage error (exit 2) —
    two sources of truth for one field must not collide silently. Setting
    a flag does not enable its action (mirrors Splunk semantics: the
    action must still be named in ``--actions``); when it isn't, a
    one-line advisory is printed to stderr, deduplicated per action.

    Raises:
        click.BadParameter: On a flag/--set collision, or an empty value.
    """
    values = {
        "--email-to": email_to,
        "--email-subject": email_subject,
        "--webhook-url": webhook_url,
    }
    enabled = {a.strip() for a in (actions or "").split(",") if a.strip()}
    warned: set[str] = set()
    for flag, field, action in _ACTION_FLAGS:
        value = values[flag]
        if value is None:
            continue
        if not value.strip():
            raise click.BadParameter(f"{flag} must not be empty")
        if field in kwargs:
            raise click.BadParameter(f"{flag} conflicts with --set {field}")
        kwargs[field] = value
        if action not in enabled and action not in warned:
            output.warning(
                f"{flag} is set but '{action}' is not in --actions — "
                "the action stays disabled."
            )
            warned.add(action)


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
    email_to: str | None,
    email_subject: str | None,
    webhook_url: str | None,
    set_pairs: tuple[str, ...],
    actions: str | None = None,
) -> dict[str, str]:
    """Translate alert flags into saved-search REST fields.

    Starts from ``--set`` pairs; explicit flags overwrite them. ``actions``
    is the (not yet applied) ``--actions`` value on this same command, used
    only to advise on friendly action flags whose action isn't enabled.
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
    _merge_action_flags(
        kwargs,
        actions=actions,
        email_to=email_to,
        email_subject=email_subject,
        webhook_url=webhook_url,
    )
    return kwargs


# Known alert actions and the companion field Splunk rejects --yes without.
# One-line adds only — this is advisory, not exhaustive.
_REQUIRED_ACTION_FIELDS: dict[str, str] = {
    "email": "action.email.to",
    "webhook": "action.webhook.param.url",
}


def app_scope(app: str | None) -> dict[str, str]:
    """Build the ``app``/``owner`` kwargs for an app-scoped list call.

    Unscoped by default (the connection's current namespace); ``owner="-"``
    when an app is given so app-private stanzas owned by other users aren't
    silently excluded.
    """
    return {} if app is None else {"app": app, "owner": "-"}


def trunc(value: str, limit: int = 60) -> str:
    """Shorten a long text field for table display.

    Never emits a bare ellipsis — a truncated value always says how many
    characters were hidden, e.g. ``foo… [+57 chars]``.
    """
    if len(value) <= limit:
        return value
    kept = value[: limit - 1]
    hidden = len(value) - len(kept)
    return f"{kept}… [+{hidden} chars]"


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
