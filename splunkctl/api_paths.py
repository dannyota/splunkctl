"""Validate raw API paths before resolving credentials or opening a connection."""

import re
from urllib.parse import unquote

import click


def validate_path(path: str) -> str:
    """Return a service-absolute path; reject URL and decoding ambiguities."""
    if (
        not path
        or path.startswith("//")
        or re.match(r"[a-zA-Z][a-zA-Z0-9+.-]*:", path)
        or re.search(r"[\\\x00-\x20\x7f?#]", path)
    ):
        raise click.BadParameter("PATH must be a service-relative REST path")
    if re.search(r"%(?![0-9a-fA-F]{2})", path):
        raise click.BadParameter("PATH contains invalid percent encoding")
    decoded = path
    # Reject recursive escapes rather than trusting intermediary decode counts.
    while "%" in decoded:
        changed = unquote(decoded)
        if changed == decoded:
            break
        if "%" in changed or changed.count("/") != decoded.count("/"):
            raise click.BadParameter(
                "PATH contains encoded separators or recursive encoding"
            )
        decoded = changed
    if re.search(r"[\\\x00-\x1f\x7f?#]", decoded):
        raise click.BadParameter("PATH contains unsafe encoded characters")
    segments = decoded.split("/")
    if any(s in {".", ".."} for s in segments) or "//" in decoded:
        raise click.BadParameter("PATH contains dot or empty segments")
    if path.startswith("/"):
        if not (path.startswith("/services/") or path.startswith("/servicesNS/")):
            raise click.BadParameter(
                "absolute PATH must start with /services/ or /servicesNS/"
            )
        if path.startswith("/servicesNS/") and len(segments) < 5:
            raise click.BadParameter("servicesNS PATH requires owner, app and endpoint")
        return path
    return "/services/" + path
