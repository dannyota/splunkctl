"""Invocation metadata shared by every HTTP transport."""

import os
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field, replace
from uuid import uuid4

from splunkctl import __version__


@dataclass(frozen=True)
class Invocation:
    """Immutable request identity with invocation-owned search jobs."""

    command: str
    read_only: bool
    request_id: str = field(default_factory=lambda: str(uuid4()))
    owned_sids: set[str] = field(default_factory=set, compare=False)


_context: ContextVar[Invocation | None] = ContextVar(
    "splunkctl_invocation", default=None
)


def current() -> Invocation | None:
    """Return active invocation metadata, if any."""
    return _context.get()


def env_readonly() -> bool:
    """Read the non-disabling environment switch."""
    return os.environ.get("SPLUNKCTL_READ_ONLY", "").lower() in {"1", "true", "yes"}


def readonly() -> bool:
    """Return whether the active invocation protects server state."""
    ctx = current()
    return bool(ctx and ctx.read_only) or env_readonly()


@contextmanager
def invocation(command: str, read_only: bool = False) -> Iterator[Invocation]:
    """Scope one identity, preserving it across nested watch iterations."""
    existing = current()
    if existing is not None:
        if read_only and not existing.read_only:
            strengthened = replace(existing, read_only=True)
            token = _context.set(strengthened)
            try:
                yield strengthened
            finally:
                _context.reset(token)
        else:
            yield existing
        return
    ctx = Invocation(command, read_only or env_readonly())
    token = _context.set(ctx)
    try:
        yield ctx
    finally:
        _context.reset(token)


def user_agent() -> str:
    """Build the exact final-dispatch User-Agent."""
    ctx = current() or Invocation("library", env_readonly())
    return f"splunkctl/{__version__} (cmd={ctx.command}; requestID={ctx.request_id})"
