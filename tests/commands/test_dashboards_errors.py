"""Tests for dashboard error classification (C6).

Auth/network errors in dashboards commands must NOT be swallowed and
misreported as 'not found'.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from splunkctl.main import cli

_PATCH = "splunkctl.commands.dashboards.get_client"


def _http_401() -> Exception:
    """Create an SDK HTTPError(401) for testing."""
    from splunklib.binding import HTTPError

    resp = MagicMock(status=401, reason="Unauthorized")
    resp.body.read.return_value = (
        b"<response><messages><msg>Unauthorized</msg></messages></response>"
    )
    return HTTPError(resp)


@patch(_PATCH)
def test_get_auth_error_not_swallowed(mock_gc: MagicMock) -> None:
    """An auth/network error in _resolve must NOT report 'not found'."""
    mock_svc = MagicMock()
    mock_svc.dashboards.list.side_effect = _http_401()
    mock_gc.return_value.service = mock_svc

    result = CliRunner().invoke(cli, ["--json", "dashboards", "get", "test_dash"])
    assert "not_found" not in result.stderr


@patch(_PATCH)
def test_delete_auth_error_not_swallowed(mock_gc: MagicMock) -> None:
    """Auth errors in delete must not be misreported as not-found."""
    mock_svc = MagicMock()
    mock_svc.dashboards.list.side_effect = _http_401()
    mock_gc.return_value.service = mock_svc

    result = CliRunner().invoke(
        cli, ["--yes", "--json", "dashboards", "delete", "test_dash"]
    )
    assert "not_found" not in result.stderr


@patch(_PATCH)
def test_export_auth_error_not_swallowed(mock_gc: MagicMock) -> None:
    """Auth errors in export must not be misreported as not-found."""
    mock_svc = MagicMock()
    mock_svc.dashboards.list.side_effect = _http_401()
    mock_gc.return_value.service = mock_svc

    result = CliRunner().invoke(cli, ["--json", "dashboards", "export", "test_dash"])
    assert "not_found" not in result.stderr


@patch(_PATCH)
def test_share_auth_error_not_swallowed(mock_gc: MagicMock) -> None:
    """Auth errors in share must not be misreported as not-found."""
    mock_svc = MagicMock()
    mock_svc.dashboards.list.side_effect = _http_401()
    mock_gc.return_value.service = mock_svc

    result = CliRunner().invoke(
        cli,
        ["--yes", "--json", "dashboards", "share", "test_dash", "--sharing", "app"],
    )
    assert "not_found" not in result.stderr
