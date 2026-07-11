"""Ingest helpers — SIEM search, map-file loading, dedup checks, preview."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import click
import yaml
from splunklib.results import JSONResultsReader

from splunkctl import output
from splunkctl.client import get_client
from splunkctl.soar.cimcef import row_to_cef
from splunkctl.soar.client import SOARError

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


def normalize_spl(spl: str) -> str:
    """Auto-prepend ``search`` when the query needs it."""
    stripped = spl.strip()
    if stripped.startswith("|"):
        return stripped
    first_word = stripped.split()[0].lower() if stripped else ""
    if first_word == "search" or first_word in _GENERATING:
        return stripped
    return f"search {stripped}"


def read_results(stream: Any) -> list[dict[str, Any]]:
    """Parse a Splunk results stream into a list of dicts."""
    reader: Any = JSONResultsReader(stream)
    rows: list[dict[str, Any]] = []
    for item in reader:
        if isinstance(item, dict):
            rows.append(item)
    return rows


def fetch_spl_results(
    ctx: click.Context,
    spl: str,
    *,
    earliest: str | None,
    latest: str | None,
    app: str | None,
) -> list[dict[str, Any]]:
    """Run an SPL search on SIEM and return result rows."""
    client = get_client(ctx)
    svc = client.service
    if app:
        svc.namespace["app"] = app
    query = normalize_spl(spl)

    kwargs: dict[str, Any] = {"exec_mode": "normal"}
    if earliest:
        kwargs["earliest_time"] = earliest
    if latest:
        kwargs["latest_time"] = latest

    output.info(f"Running SIEM search: {query}")
    job: Any = svc.jobs.create(query, **kwargs)

    timeout: int = ctx.obj.get("timeout", 30)
    deadline = time.monotonic() + timeout
    while not job.is_done():
        if time.monotonic() > deadline:
            job.cancel()
            output.error(f"SIEM search timed out after {timeout}s.", kind="timeout")
            ctx.exit(1)
            raise SystemExit(1)
        time.sleep(0.5)
        job.refresh()

    return read_results(job.results(output_mode="json", count=0))


def fetch_sid_results(
    ctx: click.Context,
    sid: str,
) -> list[dict[str, Any]]:
    """Fetch results from an existing SIEM search job."""
    client = get_client(ctx)
    svc = client.service
    try:
        job: Any = svc.jobs[sid]
    except KeyError:
        output.error(f"Job '{sid}' not found on SIEM.", kind="not_found")
        ctx.exit(1)
        raise SystemExit(1) from None

    job.refresh()
    if not job.is_done():
        output.error(f"Job '{sid}' is still running.", kind="error")
        ctx.exit(1)
        raise SystemExit(1)

    return read_results(job.results(output_mode="json", count=0))


def load_map_file(
    path: str,
) -> tuple[dict[str, str], dict[str, list[str]], bool]:
    """Load a YAML map file and return (cim_map, contains_map, include_unmapped).

    Format::

        mappings:
          src: {cef: sourceAddress, contains: [ip]}
          custom_score: {cef: riskScore}
        unmapped: drop   # or "pass"
    """
    data = yaml.safe_load(Path(path).read_text())
    mappings: dict[str, Any] = data.get("mappings", {})
    cim_map: dict[str, str] = {}
    contains_map: dict[str, list[str]] = {}
    for cim_field, spec in mappings.items():
        if isinstance(spec, dict):
            cef_key = spec.get("cef", cim_field)
            cim_map[cim_field] = cef_key
            contains = spec.get("contains")
            if isinstance(contains, list) and contains:
                contains_map[cef_key] = [str(c) for c in contains]
        else:
            cim_map[cim_field] = str(spec)
    unmapped = data.get("unmapped", "drop")
    return cim_map, contains_map, unmapped == "pass"


def validate_label(soar: Any, label: str) -> bool:
    """Validate that a label exists on the SOAR instance."""
    try:
        result = soar.get("container_options", params={})
        labels: list[str] = []
        if isinstance(result, dict):
            for item in result.get("label", []):
                if isinstance(item, str):
                    labels.append(item)
                elif isinstance(item, dict):
                    labels.append(str(item.get("name", item.get("label", ""))))
        if labels and label not in labels:
            output.warning(
                f"Label '{label}' not found on SOAR "
                f"(available: {', '.join(labels)}). "
                f"Container creation may fail."
            )
            return False
    except SOARError:
        pass
    return True


def dedup_check_container(soar: Any, sdi: str) -> int | None:
    """Check if a container with this SDI already exists."""
    try:
        result = soar.get(
            "container",
            params={"_filter_source_data_identifier": f'"{sdi}"'},
        )
        data = result.get("data", []) if isinstance(result, dict) else []
        if data:
            return int(data[0].get("id", 0))
    except SOARError:
        pass
    return None


def dedup_check_artifact(soar: Any, sdi: str, container_id: int) -> int | None:
    """Check if an artifact with this SDI already exists."""
    try:
        result = soar.get(
            "artifact",
            params={
                "_filter_source_data_identifier": f'"{sdi}"',
                "_filter_container": container_id,
            },
        )
        data = result.get("data", []) if isinstance(result, dict) else []
        if data:
            return int(data[0].get("id", 0))
    except SOARError:
        pass
    return None


class ContainerGroup:
    """Accumulator for rows destined for one container."""

    __slots__ = ("name", "rows", "severity", "sdi")

    def __init__(self, name: str, severity: str, sdi: str) -> None:
        self.name = name
        self.rows: list[dict[str, Any]] = []
        self.severity = severity
        self.sdi = sdi


def build_preview(
    groups: dict[str, ContainerGroup],
    cim_map: dict[str, str],
    *,
    include_unmapped: bool = False,
) -> str:
    """Build the dry-run preview string."""
    lines: list[str] = []
    lines.append(f"Containers: {len(groups)}")
    for name, grp in groups.items():
        lines.append(f"  {name}: {len(grp.rows)} artifact(s)")

    lines.append("")
    lines.append("CIM -> CEF mapping (active):")
    shown = 0
    for cim, cef in sorted(cim_map.items()):
        lines.append(f"  {cim} -> {cef}")
        shown += 1
        if shown >= 10:
            remaining = len(cim_map) - shown
            if remaining > 0:
                lines.append(f"  ... and {remaining} more")
            break

    if groups:
        first_grp = next(iter(groups.values()))
        if first_grp.rows:
            sample_cef = row_to_cef(
                first_grp.rows[0],
                cim_map=cim_map,
                include_unmapped=include_unmapped,
            )
            if sample_cef:
                lines.append("")
                lines.append("Sample CEF payload:")
                lines.append(json.dumps(sample_cef, indent=2, default=str))

    return "\n".join(lines)
