"""Search commands — run, export, oneshot, jobs, job, cancel."""

import time
from typing import Any

import click
from splunklib.results import JSONResultsReader

from splunkctl import guard, output
from splunkctl.client import get_client

_GENERATING = (
    "abstract",
    "bucket",
    "datamodel",
    "dbinspect",
    "eventcount",
    "inputcsv",
    "inputlookup",
    "loadjob",
    "makeresults",
    "mcollect",
    "metadata",
    "metasearch",
    "mstats",
    "pivot",
    "rest",
    "savedsearch",
    "tstats",
    "typeahead",
)


def _normalize_spl(spl: str) -> str:
    """Auto-prepend ``search`` when the query needs it."""
    stripped = spl.strip()
    if stripped.startswith("|"):
        return stripped
    first_word = stripped.split()[0].lower() if stripped else ""
    if first_word == "search" or first_word in _GENERATING:
        return stripped
    return f"search {stripped}"


def _time_kwargs(
    earliest: str | None,
    latest: str | None,
) -> dict[str, str]:
    """Build SDK time-range kwargs."""
    kw: dict[str, str] = {}
    if earliest:
        kw["earliest_time"] = earliest
    if latest:
        kw["latest_time"] = latest
    return kw


def _read_results(stream: Any) -> list[dict[str, Any]]:
    """Parse a Splunk results stream into a list of dicts."""
    reader: Any = JSONResultsReader(stream)
    rows: list[dict[str, Any]] = []
    for item in reader:
        if isinstance(item, dict):
            rows.append(item)
    return rows


@click.group("search")
def search_group() -> None:
    """Search and job management."""


@search_group.command("run")
@click.argument("spl")
@click.option("--earliest", default=None, help="Earliest time (e.g. -24h, -7d).")
@click.option("--latest", default=None, help="Latest time (e.g. now).")
@click.option("--limit", default=100, type=int, help="Max results (default 100).")
@click.option("--app", default=None, help="Splunk app context.")
@click.pass_context
def run_search(
    ctx: click.Context,
    spl: str,
    earliest: str | None,
    latest: str | None,
    limit: int,
    app: str | None,
) -> None:
    """Run a search synchronously and print results."""
    client = get_client(ctx)
    svc = client.service
    if app:
        svc.namespace["app"] = app
    query = _normalize_spl(spl)

    timeout: int = ctx.obj.get("timeout", 30)
    kwargs: dict[str, Any] = {
        "exec_mode": "normal",
        **_time_kwargs(earliest, latest),
    }

    output.info(f"Running: {query}")
    job: Any = svc.jobs.create(query, **kwargs)

    deadline = time.monotonic() + timeout
    while not job.is_done():
        if time.monotonic() > deadline:
            job.cancel()
            output.error(f"Search timed out after {timeout}s.")
            ctx.exit(1)
            return
        time.sleep(0.5)
        job.refresh()

    rows = _read_results(job.results(output_mode="json", count=limit))
    output.render(ctx, rows)


@search_group.command("export")
@click.argument("spl")
@click.option("--earliest", default=None, help="Earliest time.")
@click.option("--latest", default=None, help="Latest time.")
@click.option("--app", default=None, help="Splunk app context.")
@click.pass_context
def export_search(
    ctx: click.Context,
    spl: str,
    earliest: str | None,
    latest: str | None,
    app: str | None,
) -> None:
    """Streaming export for large result sets."""
    client = get_client(ctx)
    svc = client.service
    if app:
        svc.namespace["app"] = app
    query = _normalize_spl(spl)

    kwargs: dict[str, Any] = {
        "output_mode": "json",
        **_time_kwargs(earliest, latest),
    }

    output.info(f"Exporting: {query}")
    stream: Any = svc.jobs.export(query, **kwargs)
    rows = _read_results(stream)
    output.render(ctx, rows)


@search_group.command("oneshot")
@click.argument("spl")
@click.option("--earliest", default=None, help="Earliest time.")
@click.option("--latest", default=None, help="Latest time.")
@click.option("--limit", default=100, type=int, help="Max results (default 100).")
@click.option("--app", default=None, help="Splunk app context.")
@click.pass_context
def oneshot_search(
    ctx: click.Context,
    spl: str,
    earliest: str | None,
    latest: str | None,
    limit: int,
    app: str | None,
) -> None:
    """Quick one-off search."""
    client = get_client(ctx)
    svc = client.service
    if app:
        svc.namespace["app"] = app
    query = _normalize_spl(spl)

    kwargs: dict[str, Any] = {
        "output_mode": "json",
        "count": limit,
        **_time_kwargs(earliest, latest),
    }

    output.info(f"Oneshot: {query}")
    stream: Any = svc.jobs.oneshot(query, **kwargs)
    rows = _read_results(stream)
    output.render(ctx, rows)


@search_group.command("jobs")
@click.pass_context
def list_jobs(ctx: click.Context) -> None:
    """List running and recent search jobs."""
    client = get_client(ctx)
    svc = client.service

    rows: list[dict[str, Any]] = []
    for job in svc.jobs:
        content: dict[str, Any] = dict(job.content)
        dur = content.get("runDuration", "")
        if isinstance(dur, (float, str)):
            try:
                dur = f"{float(dur):.3f}"
            except (ValueError, TypeError):
                pass
        rows.append(
            {
                "sid": job.sid,
                "status": content.get("dispatchState", ""),
                "earliest": content.get("earliestTime", ""),
                "latest": content.get("latestTime", ""),
                "event_count": content.get("eventCount", 0),
                "run_duration": dur,
            }
        )
    output.render(ctx, rows)


@search_group.command("job")
@click.argument("sid")
@click.pass_context
def get_job(ctx: click.Context, sid: str) -> None:
    """Get status and results for a specific job."""
    client = get_client(ctx)
    svc = client.service

    try:
        job: Any = svc.jobs[sid]
    except KeyError:
        output.error(f"Job '{sid}' not found.")
        ctx.exit(1)
        return

    job.refresh()
    content: dict[str, Any] = dict(job.content)
    done: bool = job.is_done()

    status: dict[str, Any] = {
        "sid": job.sid,
        "status": content.get("dispatchState", ""),
        "earliest": content.get("earliestTime", ""),
        "latest": content.get("latestTime", ""),
        "event_count": content.get("eventCount", 0),
        "result_count": content.get("resultCount", 0),
        "run_duration": content.get("runDuration", ""),
        "is_done": done,
    }

    if done:
        rows = _read_results(job.results(output_mode="json"))
        if rows:
            output.info(f"Job {sid}: DONE - {len(rows)} result(s)")
            output.render(ctx, rows)
            return
    output.render(ctx, status)


@search_group.command("cancel")
@click.argument("sid")
@click.pass_context
def cancel_job(ctx: click.Context, sid: str) -> None:
    """Cancel a running search job."""
    if not guard.check(ctx, f"Cancel job '{sid}'"):
        return

    client = get_client(ctx)
    svc = client.service

    try:
        job: Any = svc.jobs[sid]
    except KeyError:
        output.error(f"Job '{sid}' not found.")
        ctx.exit(1)
        return

    job.cancel()
    output.info(f"Job '{sid}' cancelled.")
