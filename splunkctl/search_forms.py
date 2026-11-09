"""Search prefix and Splunk error helpers."""

import json
import re
from typing import Any
from xml.etree import ElementTree

from splunklib.binding import HTTPError

from splunkctl.request_context import readonly
from splunkctl.request_policy import ReadOnlyError


def effective_spl(spl: str) -> str:
    """Skip whitespace and complete leading SPL comments."""
    return re.sub(r"^(?:\s|```[\s\S]*?```)*", "", spl)


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
    effective = effective_spl(stripped)
    if effective.startswith("|"):
        return stripped
    first_word = effective.split()[0].lower() if effective else ""
    if first_word == "search" or first_word in _GENERATING:
        return stripped
    return f"search {stripped}"


def splunk_message(body: bytes) -> str:
    """Extract a Splunk JSON or XML error message."""
    try:
        data = json.loads(body)
        return str(data["messages"][0]["text"])
    except (ValueError, KeyError, IndexError, TypeError):
        try:
            return ElementTree.fromstring(body).findtext(".//msg") or ""  # noqa: S314
        except ElementTree.ParseError:
            return ""


def choose_search_form(service: Any, spl: str, **namespace: Any) -> str:
    """Select a leading macro's form before creating any search job."""
    prefixed = normalize_spl(spl)
    token = effective_spl(spl.strip())
    if not token.startswith("`") or token.startswith("```"):
        return prefixed

    def parse(query: str) -> None:
        response = service.post(
            "search/parser",
            q=query,
            output_mode="json",
            parse_only="true",
            reload_macros="false",
            **namespace,
        )
        response.body.read()
        if response.status != 200:
            raise ValueError(f"search/parser returned HTTP {response.status}")

    try:
        try:
            parse(prefixed)
            return prefixed
        except HTTPError as exc:
            if not (
                400 <= exc.status < 500
                and "must be the first command" in splunk_message(exc.body)
            ):
                raise
        bare = spl.strip()
        parse(bare)
        return bare
    except Exception as exc:
        if readonly():
            if isinstance(exc, HTTPError):
                detail = splunk_message(exc.body) or str(exc)
                raise ReadOnlyError(
                    "search/parser rejected the search: " + detail[:200]
                ) from exc
            raise ReadOnlyError(
                "search/parser request failed: " + str(exc)[:200]
            ) from exc
        return prefixed
