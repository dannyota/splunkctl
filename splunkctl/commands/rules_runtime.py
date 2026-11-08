"""Scheduling and test execution helpers for saved searches."""

from typing import Any

from splunkctl import output
from splunkctl.commands.search import _normalize_spl


def schedule_flag(cron: Any) -> str:
    """Schedule only when a nonempty cron expression exists."""
    return "1" if str(cron or "").strip() else "0"


def warn_unscheduled(name: str, kwargs: dict[str, Any]) -> None:
    """Explain why an enabled saved search will not run on a schedule."""
    if kwargs.get("disabled") == "0" and kwargs.get("is_scheduled") == "0":
        output.info(
            f"Saved search '{name}' is enabled but not scheduled: no cron configured."
        )


def start_test(client: Any, ss: Any, earliest: str | None, latest: str | None) -> Any:
    """Run disabled rules as ad hoc SPL, otherwise dispatch without actions."""
    if str(ss.content.get("disabled", "0")).lower() in {"1", "true"}:
        kwargs: dict[str, Any] = {"exec_mode": "normal"}
        if app := ss.access.get("app"):
            kwargs["app"] = app
        for key, override in (("earliest_time", earliest), ("latest_time", latest)):
            value = (
                override if override is not None else ss.content.get(f"dispatch.{key}")
            )
            if value:
                kwargs[key] = value
        output.info(f"'{ss.name}' is disabled; running its SPL as an ad hoc search.")
        return client.service.jobs.create(
            _normalize_spl(ss.content["search"]), **kwargs
        )

    dispatch_kwargs = {"trigger_actions": "0"}
    if earliest:
        dispatch_kwargs["dispatch.earliest_time"] = earliest
    if latest:
        dispatch_kwargs["dispatch.latest_time"] = latest
    output.info(f"Dispatching '{ss.name}' over {earliest or '(rule window)'}")
    return ss.dispatch(**dispatch_kwargs)
