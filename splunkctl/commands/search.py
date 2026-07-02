"""Search commands — run, export, oneshot, upload, jobs, job, cancel."""

import time
from pathlib import Path
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
@click.option("--detach", is_flag=True, help="Submit job and exit without waiting.")
@click.pass_context
def run_search(
    ctx: click.Context,
    spl: str,
    earliest: str | None,
    latest: str | None,
    limit: int,
    app: str | None,
    *,
    detach: bool,
) -> None:
    """Run a search synchronously and print results."""
    client = get_client(ctx)
    svc = client.service
    if app:
        svc.namespace["app"] = app
    query = _normalize_spl(spl)

    kwargs: dict[str, Any] = {
        "exec_mode": "normal",
        **_time_kwargs(earliest, latest),
    }

    output.info(f"Running: {query}")
    job: Any = svc.jobs.create(query, **kwargs)

    if detach:
        output.render(ctx, {"sid": job.sid, "status": "running"})
        return

    timeout: int = ctx.obj.get("timeout", 30)
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
    total = int(job.content.get("resultCount", len(rows)))
    output.render(ctx, rows)
    if total > len(rows):
        output.info(
            f"Showing {len(rows)} of {total} results"
            f" (sid={job.sid}; use: search job {job.sid} --offset {len(rows)})"
        )


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
        spl = str(content.get("search", ""))
        rows.append(
            {
                "sid": job.sid,
                "status": content.get("dispatchState", ""),
                "owner": content.get("author", ""),
                "spl": spl[:60] + ("…" if len(spl) > 60 else ""),
                "event_count": content.get("eventCount", 0),
                "run_duration": dur,
            }
        )
    output.render(ctx, rows)


@search_group.command("job")
@click.argument("sid")
@click.option("--offset", default=0, type=int, help="Result offset for paging.")
@click.option(
    "--count",
    "result_count",
    default=0,
    type=int,
    help="Max results (0=all).",
)
@click.option(
    "--events",
    "show_events",
    is_flag=True,
    help="Fetch raw events.",
)
@click.option(
    "--status-only",
    is_flag=True,
    help="Show status without results.",
)
@click.pass_context
def get_job(
    ctx: click.Context,
    sid: str,
    offset: int,
    result_count: int,
    *,
    show_events: bool,
    status_only: bool,
) -> None:
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

    if status_only or not done:
        output.render(ctx, status)
        return

    fetch_kw: dict[str, Any] = {"output_mode": "json"}
    if offset:
        fetch_kw["offset"] = offset
    if result_count:
        fetch_kw["count"] = result_count

    stream = job.events(**fetch_kw) if show_events else job.results(**fetch_kw)
    rows = _read_results(stream)
    total = int(content.get("resultCount", 0))
    output.info(f"Job {sid}: DONE -- {len(rows)} of {total}")
    output.render(ctx, rows)


@search_group.command("cancel")
@guard.guarded
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


_CHUNK_SIZE = 1024 * 1024  # 1 MB


def _human_size(nbytes: int) -> str:
    """Format a byte count with a sensible unit."""
    size = float(nbytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{nbytes} B"


@search_group.command("upload")
@guard.guarded
@click.option(
    "--path",
    "file_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False),
    help="Local file to upload (CSV, log, JSON, etc.).",
)
@click.option("--index", default="main", help="Target index.")
@click.option("--sourcetype", default=None, help="Source type (auto if omitted).")
@click.option("--source", default=None, help="Source label (defaults to filename).")
@click.option("--host", "src_host", default=None, help="Host metadata.")
@click.pass_context
def upload_data(
    ctx: click.Context,
    file_path: str,
    index: str,
    sourcetype: str | None,
    source: str | None,
    src_host: str | None,
) -> None:
    """Upload a local file into Splunk for indexing.

    Reads the file from your laptop and sends it to the remote Splunk
    instance via the receivers/simple REST endpoint.
    """
    p = Path(file_path)
    size = _human_size(p.stat().st_size)
    source = source or p.name

    parts = [f"file={p.name}", f"index={index}"]
    if sourcetype:
        parts.append(f"sourcetype={sourcetype}")
    parts.append(f"size={size}")
    details = f"Upload data: {', '.join(parts)}"
    if not guard.check(ctx, details):
        return

    client = get_client(ctx)
    svc = client.service

    kwargs: dict[str, str] = {"index": index, "source": source}
    if sourcetype:
        kwargs["sourcetype"] = sourcetype
    if src_host:
        kwargs["host"] = src_host

    data = p.read_bytes()
    try:
        svc.post("/services/receivers/simple", body=data, **kwargs)
    except Exception as exc:
        output.error(f"Upload failed: {exc}")
        ctx.exit(1)
        return
    output.info(f"Uploaded '{p.name}' ({size}) to index={index}.")
