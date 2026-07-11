"""Tests for SOAR infrastructure — client get_bytes and guard helpers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from splunkctl.soar.client import SOARClient, SOARError


# ---------------------------------------------------------------------------
# Client get_bytes
# ---------------------------------------------------------------------------
class TestClientGetBytes:
    def test_get_bytes_returns_raw_content(self) -> None:
        """get_bytes returns raw response content."""
        client = SOARClient(host="soar.test", token="tok")  # noqa: S106

        import requests

        mock_resp = MagicMock(spec=requests.Response)
        mock_resp.status_code = 200
        mock_resp.content = b"raw-bytes-here"
        mock_resp.headers = {"Content-Type": "application/octet-stream"}

        with patch.object(client._session, "request", return_value=mock_resp):
            result = client.get_bytes(
                "download_attachment", params={"vault_id": "abc123"}
            )
        assert result == b"raw-bytes-here"

    def test_get_bytes_raises_on_error(self) -> None:
        """get_bytes raises SOARError on non-2xx."""
        client = SOARClient(host="soar.test", token="tok")  # noqa: S106

        import requests

        mock_resp = MagicMock(spec=requests.Response)
        mock_resp.status_code = 404
        mock_resp.text = "Not Found"
        mock_resp.content = b"Not Found"
        mock_resp.headers = {"Content-Type": "text/html"}

        with patch.object(client._session, "request", return_value=mock_resp):
            with pytest.raises(SOARError):
                client.get_bytes("download_attachment", params={"vault_id": "missing"})


# ---------------------------------------------------------------------------
# SOAR guard banner + check
# ---------------------------------------------------------------------------
class TestSoarGuard:
    def test_soar_banner_format(self) -> None:
        """soar_banner produces (soar @ host:port) format."""
        from splunkctl.guard import soar_banner

        ctx = MagicMock()
        ctx.obj = {"config": None, "profile": None}

        with patch(
            "splunkctl.guard.cfg_mod.resolve_soar",
            return_value={"host": "soar.lab", "port": 8443},
        ):
            tag = soar_banner(ctx)
        assert "soar.lab" in tag
        assert "8443" in tag

    def test_soar_check_dry_run(self) -> None:
        """soar_check returns False in dry-run mode."""
        from splunkctl.guard import soar_check

        ctx = MagicMock()
        ctx.obj = {"dry_run": True, "config": None, "profile": None}

        with patch(
            "splunkctl.guard.cfg_mod.resolve_soar",
            return_value={"host": "soar.lab", "port": 8443},
        ):
            assert soar_check(ctx, "upload file") is False

    def test_soar_check_applies(self) -> None:
        """soar_check returns True with --yes."""
        from splunkctl.guard import soar_check

        ctx = MagicMock()
        ctx.obj = {"dry_run": False, "config": None, "profile": None}

        with patch(
            "splunkctl.guard.cfg_mod.resolve_soar",
            return_value={"host": "soar.lab", "port": 8443},
        ):
            assert soar_check(ctx, "upload file") is True
