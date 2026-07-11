"""SOAR ingest — SIEM search results to SOAR containers + artifacts."""

from __future__ import annotations

from typing import Any

import click

from splunkctl import output
from splunkctl.commands.soar._client import get_soar_client
from splunkctl.commands.soar._ingest_helpers import (
    ContainerGroup,
    build_preview,
    dedup_check_artifact,
    dedup_check_container,
    fetch_sid_results,
    fetch_spl_results,
    load_map_file,
    validate_label,
)
from splunkctl.guard import soar_check
from splunkctl.soar.cimcef import (
    CEF_CONTAINS_MAP,
    CIM_CEF_MAP,
    artifact_name_for_row,
    auto_cef_types,
    container_name_for_row,
    map_severity,
    row_sdi,
    row_to_cef,
)
from splunkctl.soar.client import SOARError


@click.command("ingest")
@click.option(
    "--spl",
    default=None,
    help="SPL search to run on SIEM (mutually exclusive with --sid).",
)
@click.option(
    "--sid",
    default=None,
    help="Existing SIEM search job SID to fetch results from.",
)
@click.option(
    "--label",
    default="events",
    help="Container label (default: events).",
)
@click.option(
    "--severity",
    "severity_override",
    default=None,
    help="Override SOAR severity.",
)
@click.option(
    "--sensitivity",
    default="amber",
    help="Container sensitivity/TLP (default: amber).",
)
@click.option(
    "--sdi-field",
    default="event_id",
    help="Row field for SDI (default: event_id, else row hash).",
)
@click.option(
    "--container-name",
    "container_name_tmpl",
    default=None,
    help="Container name (literal or template).",
)
@click.option(
    "--container-name-field",
    default=None,
    help="Row field to use as container name.",
)
@click.option(
    "--grouping",
    is_flag=True,
    default=False,
    help="Group all rows into one container (default: one per row).",
)
@click.option(
    "--map",
    "map_overrides",
    multiple=True,
    help="CEF_KEY=SPLUNK_FIELD — map a result field onto a CEF key (repeatable).",
)
@click.option(
    "--map-file",
    default=None,
    type=click.Path(exists=True),
    help="YAML file with custom CIM->CEF mappings.",
)
@click.option(
    "--include-unmapped",
    is_flag=True,
    default=False,
    help="Pass unmapped fields through as custom CEF keys.",
)
@click.option(
    "--no-automation",
    is_flag=True,
    default=False,
    help="Suppress playbook automation on all artifacts.",
)
@click.option("--earliest", default=None, help="SIEM search earliest time.")
@click.option("--latest", default=None, help="SIEM search latest time.")
@click.option("--app", default=None, help="SIEM app context for the search.")
@click.pass_context
def ingest_cmd(
    ctx: click.Context,
    *,
    spl: str | None,
    sid: str | None,
    label: str,
    severity_override: str | None,
    sensitivity: str,
    sdi_field: str,
    container_name_tmpl: str | None,
    container_name_field: str | None,
    grouping: bool,
    map_overrides: tuple[str, ...],
    map_file: str | None,
    include_unmapped: bool,
    no_automation: bool,
    earliest: str | None,
    latest: str | None,
    app: str | None,
) -> None:
    """Ingest SIEM search results into SOAR as containers and artifacts."""
    if not spl and not sid:
        output.error("Provide --spl or --sid.", kind="usage")
        ctx.exit(1)
        return
    if spl and sid:
        output.error("--spl and --sid are mutually exclusive.", kind="usage")
        ctx.exit(1)
        return

    # ---- Build effective CIM map ----
    cim_map = dict(CIM_CEF_MAP)
    contains_map = dict(CEF_CONTAINS_MAP)
    if map_file:
        file_map, file_contains, include_unmapped_file = load_map_file(map_file)
        cim_map = file_map
        contains_map = {**CEF_CONTAINS_MAP, **file_contains}
        include_unmapped = include_unmapped or include_unmapped_file
    for override in map_overrides:
        cef_key, _, splunk_field = override.partition("=")
        if cef_key and splunk_field:
            cim_map[splunk_field] = cef_key

    # ---- Fetch results ----
    if spl:
        rows = fetch_spl_results(ctx, spl, earliest=earliest, latest=latest, app=app)
    elif sid:
        rows = fetch_sid_results(ctx, sid)
    else:
        rows = []

    if not rows:
        output.info("No results from SIEM search. Nothing to ingest.")
        return

    output.info(f"Fetched {len(rows)} result(s) from SIEM.")

    # ---- Group rows into containers ----
    groups = _group_rows(
        rows,
        grouping=grouping,
        severity_override=severity_override,
        sdi_field=sdi_field,
        container_name_tmpl=container_name_tmpl,
        container_name_field=container_name_field,
    )

    # ---- Dry-run preview ----
    preview = build_preview(groups, cim_map, include_unmapped=include_unmapped)
    action = f"Ingest {len(rows)} row(s) into SOAR"
    if not soar_check(ctx, action, details=preview):
        return

    # ---- Apply ----
    soar = get_soar_client(ctx)
    validate_label(soar, label)
    summary = _apply(
        ctx,
        soar,
        groups=groups,
        label=label,
        sensitivity=sensitivity,
        severity_override=severity_override,
        sdi_field=sdi_field,
        cim_map=cim_map,
        contains_map=contains_map,
        include_unmapped=include_unmapped,
        no_automation=no_automation,
    )
    output.render(ctx, summary)


def _group_rows(
    rows: list[dict[str, Any]],
    *,
    grouping: bool,
    severity_override: str | None,
    sdi_field: str,
    container_name_tmpl: str | None,
    container_name_field: str | None,
) -> dict[str, ContainerGroup]:
    """Group result rows into container groups."""
    groups: dict[str, ContainerGroup] = {}
    if grouping:
        name = container_name_for_row(
            rows[0],
            template=container_name_tmpl,
            name_field=container_name_field,
        )
        sev = severity_override or map_severity(rows[0])
        grp = ContainerGroup(name, sev, row_sdi(rows[0], sdi_field))
        grp.rows = list(rows)
        groups[name] = grp
    else:
        for row in rows:
            name = container_name_for_row(
                row,
                template=container_name_tmpl,
                name_field=container_name_field,
            )
            sev = severity_override or map_severity(row)
            sdi = row_sdi(row, sdi_field)
            grp = ContainerGroup(name, sev, sdi)
            grp.rows = [row]
            groups[f"{name}::{sdi}"] = grp
    return groups


def _apply(
    ctx: click.Context,
    soar: Any,
    *,
    groups: dict[str, ContainerGroup],
    label: str,
    sensitivity: str,
    severity_override: str | None,
    sdi_field: str,
    cim_map: dict[str, str],
    contains_map: dict[str, list[str]],
    include_unmapped: bool,
    no_automation: bool,
) -> dict[str, Any]:
    """Create containers and artifacts on SOAR. Return summary dict."""
    created: list[dict[str, Any]] = []
    skipped_c = 0
    created_a = 0
    skipped_a = 0

    for grp in groups.values():
        existing_id = dedup_check_container(soar, grp.sdi)
        if existing_id is not None:
            output.warning(
                f"Container SDI '{grp.sdi}' already exists "
                f"(container {existing_id}). Skipping."
            )
            skipped_c += 1
            continue

        cid = _create_container(ctx, soar, grp, label=label, sensitivity=sensitivity)
        if cid is None:
            skipped_c += 1
            continue
        created.append({"id": cid, "name": grp.name})

        ca, sa = _create_artifacts(
            soar,
            grp.rows,
            container_id=cid,
            sdi_field=sdi_field,
            severity_override=severity_override,
            cim_map=cim_map,
            contains_map=contains_map,
            include_unmapped=include_unmapped,
            no_automation=no_automation,
        )
        created_a += ca
        skipped_a += sa

    summary: dict[str, Any] = {
        "containers_created": len(created),
        "containers_skipped": skipped_c,
        "artifacts_created": created_a,
        "artifacts_skipped": skipped_a,
    }
    if created:
        summary["container_ids"] = [c["id"] for c in created]
    return summary


def _create_container(
    ctx: click.Context,
    soar: Any,
    grp: ContainerGroup,
    *,
    label: str,
    sensitivity: str,
) -> int | None:
    """POST a container. Return id or None on dedup/error."""
    payload: dict[str, Any] = {
        "name": grp.name,
        "label": label,
        "severity": grp.severity,
        "sensitivity": sensitivity,
        "source_data_identifier": grp.sdi,
        "run_automation": False,
    }
    try:
        result = soar.post("container", body=payload)
    except SOARError as exc:
        if exc.data.get("existing_container_id"):
            eid = exc.data["existing_container_id"]
            output.warning(
                f"Container SDI '{grp.sdi}' already exists (container {eid}). Skipping."
            )
            return None
        output.error(exc.message, kind=exc.kind, http_status=exc.http_status)
        ctx.exit(1)
        return None
    cid = result.get("id")
    if not cid:
        output.error("Container created but no id returned.", kind="error")
        ctx.exit(1)
        return None
    return int(cid)


def _create_artifacts(
    soar: Any,
    rows: list[dict[str, Any]],
    *,
    container_id: int,
    sdi_field: str,
    severity_override: str | None,
    cim_map: dict[str, str],
    contains_map: dict[str, list[str]],
    include_unmapped: bool,
    no_automation: bool,
) -> tuple[int, int]:
    """Create artifacts for one container. Return (created, skipped)."""
    total = len(rows)
    created = 0
    skipped = 0
    for idx, row in enumerate(rows):
        art_sdi = row_sdi(row, sdi_field)
        existing = dedup_check_artifact(soar, art_sdi, container_id)
        if existing is not None:
            output.warning(
                f"Artifact SDI '{art_sdi}' already exists "
                f"(artifact {existing}). Skipping."
            )
            skipped += 1
            continue

        cef = row_to_cef(row, cim_map=cim_map, include_unmapped=include_unmapped)
        run_auto = not no_automation and idx == total - 1
        payload: dict[str, Any] = {
            "container_id": container_id,
            "name": artifact_name_for_row(row),
            "cef": cef,
            "cef_types": auto_cef_types(cef, contains_map=contains_map),
            "source_data_identifier": art_sdi,
            "severity": severity_override or map_severity(row),
            "run_automation": run_auto,
        }
        try:
            soar.post("artifact", body=payload)
            created += 1
        except SOARError as exc:
            output.error(
                f"Artifact creation failed: {exc.message}",
                kind=exc.kind,
                http_status=exc.http_status,
            )
    return created, skipped
