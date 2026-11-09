"""Search prefix and Splunk error helpers."""

import json
import re
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from xml.etree import ElementTree

_macro_retry: ContextVar[bool] = ContextVar("splunkctl_macro_retry", default=False)


def effective_spl(spl: str) -> str:
    """Skip whitespace and complete leading SPL comments."""
    return re.sub(r"^(?:\s|```[\s\S]*?```)*", "", spl)


def macro_fallback(spl: str) -> str | None:
    """Return the unprefixed form only for a leading macro."""
    if _macro_retry.get() and spl.startswith("search "):
        raw = spl[len("search ") :]
        token = effective_spl(raw)
        if token.startswith("`") and not token.startswith("```"):
            return raw
    return None


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


@contextmanager
def macro_retry(spl: str) -> Iterator[None]:
    """Allow fallback only when the original query begins with a macro."""
    effective = effective_spl(spl)
    token = _macro_retry.set(
        effective.startswith("`") and not effective.startswith("```")
    )
    try:
        yield
    finally:
        _macro_retry.reset(token)
