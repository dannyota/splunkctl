"""Shared SOAR test helpers and fixtures."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

# Patch targets used by all SOAR command tests.
PATCH_RESOLVE = "splunkctl.commands.soar._client.cfg_mod.resolve_soar"
PATCH_CLIENT = "splunkctl.commands.soar._client.SOARClient"


def soar_cfg(
    *,
    host: str = "soar.test",
    port: int = 8443,
    token: str = "tok123",  # noqa: S107
    verify: bool = False,
) -> dict[str, Any]:
    """Default SOAR config dict for mocked tests."""
    return {"host": host, "port": port, "token": token, "verify": verify}


def mock_client(responses: dict[str, Any] | None = None) -> MagicMock:
    """Return a mock SOARClient whose ``.get()`` returns from *responses*."""
    client = MagicMock()
    if responses:
        client.get.side_effect = lambda path, **kw: responses.get(path, {})
    return client
