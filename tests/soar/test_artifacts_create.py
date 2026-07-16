"""Tests for soar artifacts create — guard, CEF, SDI dedup, cef_types."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from splunkctl.main import cli
from splunkctl.soar.client import SOARError
from tests.soar.conftest import PATCH_CLIENT, PATCH_RESOLVE, soar_cfg

PATCH_SOAR_RESOLVE = "splunkctl.guard.cfg_mod.resolve_soar"


class TestArtifactsCreate:
    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_create_dry_run_default(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_soar_resolve: MagicMock,
    ) -> None:
        """Create without --yes prints dry-run and does not POST."""
        mock_resolve.return_value = soar_cfg()
        mock_soar_resolve.return_value = soar_cfg()
        client = MagicMock()
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            [
                "--json",
                "soar",
                "artifacts",
                "create",
                "--container",
                "1",
                "--name",
                "Test",
            ],
        )
        assert result.exit_code == 0
        assert "[DRY RUN]" in result.stderr
        client.post.assert_not_called()

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_create_with_yes(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_soar_resolve: MagicMock,
    ) -> None:
        """--yes actually creates the artifact."""
        mock_resolve.return_value = soar_cfg()
        mock_soar_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.post.return_value = {"success": True, "id": 77}
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            [
                "--json",
                "--yes",
                "soar",
                "artifacts",
                "create",
                "--container",
                "1",
                "--name",
                "Test",
            ],
        )
        assert result.exit_code == 0
        client.post.assert_called_once()
        body = client.post.call_args[1]["body"]
        assert body["container_id"] == 1
        assert body["name"] == "Test"

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_create_with_cef(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_soar_resolve: MagicMock,
    ) -> None:
        """--cef key=value pairs populate cef dict."""
        mock_resolve.return_value = soar_cfg()
        mock_soar_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.post.return_value = {"success": True, "id": 78}
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            [
                "--json",
                "--yes",
                "soar",
                "artifacts",
                "create",
                "--container",
                "1",
                "--name",
                "IP Hit",
                "--cef",
                "sourceAddress=1.2.3.4",
                "--cef",
                "destinationPort=443",
            ],
        )
        assert result.exit_code == 0
        body = client.post.call_args[1]["body"]
        assert body["cef"]["sourceAddress"] == "1.2.3.4"
        assert body["cef"]["destinationPort"] == "443"

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_create_with_cef_file(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_soar_resolve: MagicMock,
        tmp_path: Any,
    ) -> None:
        """--cef-file loads JSON into cef dict."""
        mock_resolve.return_value = soar_cfg()
        mock_soar_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.post.return_value = {"success": True, "id": 79}
        mock_cls.return_value = client

        cef_file = tmp_path / "cef.json"
        cef_file.write_text('{"sourceAddress": "10.0.0.1", "fileName": "mal.exe"}')

        result = CliRunner().invoke(
            cli,
            [
                "--json",
                "--yes",
                "soar",
                "artifacts",
                "create",
                "--container",
                "1",
                "--name",
                "File Hit",
                "--cef-file",
                str(cef_file),
            ],
        )
        assert result.exit_code == 0
        body = client.post.call_args[1]["body"]
        assert body["cef"]["sourceAddress"] == "10.0.0.1"
        assert body["cef"]["fileName"] == "mal.exe"

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_create_auto_contains_types(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_soar_resolve: MagicMock,
    ) -> None:
        """CEF keys in CEF_CONTAINS_MAP get auto-populated cef_types."""
        mock_resolve.return_value = soar_cfg()
        mock_soar_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.post.return_value = {"success": True, "id": 80}
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            [
                "--json",
                "--yes",
                "soar",
                "artifacts",
                "create",
                "--container",
                "1",
                "--name",
                "IP",
                "--cef",
                "sourceAddress=1.2.3.4",
            ],
        )
        assert result.exit_code == 0
        body = client.post.call_args[1]["body"]
        assert "sourceAddress" in body.get("cef_types", {})
        assert "ip" in body["cef_types"]["sourceAddress"]

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_create_explicit_cef_type(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_soar_resolve: MagicMock,
    ) -> None:
        """--cef-type field=type overrides built-in contains map."""
        mock_resolve.return_value = soar_cfg()
        mock_soar_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.post.return_value = {"success": True, "id": 81}
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            [
                "--json",
                "--yes",
                "soar",
                "artifacts",
                "create",
                "--container",
                "1",
                "--name",
                "Custom",
                "--cef",
                "myField=foo",
                "--cef-type",
                "myField=custom type",
            ],
        )
        assert result.exit_code == 0
        body = client.post.call_args[1]["body"]
        assert body["cef_types"]["myField"] == ["custom type"]

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_create_sdi_dedup_warns(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_soar_resolve: MagicMock,
    ) -> None:
        """--sdi with existing artifact warns with the duplicate id."""
        mock_resolve.return_value = soar_cfg()
        mock_soar_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.return_value = {
            "count": 1,
            "num_pages": 1,
            "data": [
                {"id": 55, "source_data_identifier": "abc123"},
            ],
        }
        client.post.return_value = {"success": True, "id": 82}
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            [
                "--json",
                "--yes",
                "soar",
                "artifacts",
                "create",
                "--container",
                "1",
                "--name",
                "Dup",
                "--sdi",
                "abc123",
            ],
        )
        assert result.exit_code == 0
        assert "55" in result.stderr
        assert "already exists" in result.stderr.lower()

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_create_no_automation(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_soar_resolve: MagicMock,
    ) -> None:
        """--no-automation sets run_automation false."""
        mock_resolve.return_value = soar_cfg()
        mock_soar_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.post.return_value = {"success": True, "id": 83}
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            [
                "--json",
                "--yes",
                "soar",
                "artifacts",
                "create",
                "--container",
                "1",
                "--name",
                "Quiet",
                "--no-automation",
            ],
        )
        assert result.exit_code == 0
        body = client.post.call_args[1]["body"]
        assert body.get("run_automation") is False

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_create_with_severity_and_type(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_soar_resolve: MagicMock,
    ) -> None:
        """--severity and --type populate the payload."""
        mock_resolve.return_value = soar_cfg()
        mock_soar_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.post.return_value = {"success": True, "id": 84}
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            [
                "--json",
                "--yes",
                "soar",
                "artifacts",
                "create",
                "--container",
                "1",
                "--name",
                "Alert",
                "--severity",
                "high",
                "--type",
                "network",
            ],
        )
        assert result.exit_code == 0
        body = client.post.call_args[1]["body"]
        assert body["severity"] == "high"
        assert body["type"] == "network"

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_create_sdi_precheck_failure_warns(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_soar_resolve: MagicMock,
    ) -> None:
        """Artifact create: SDI precheck SOARError emits warning, create proceeds."""
        mock_resolve.return_value = soar_cfg()
        mock_soar_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.side_effect = SOARError("server error", kind="http", http_status=500)
        client.post.return_value = {"success": True, "id": 88}
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            [
                "--yes",
                "--json",
                "soar",
                "artifacts",
                "create",
                "--container",
                "1",
                "--name",
                "Test",
                "--sdi",
                "SDI-fail",
            ],
        )
        assert result.exit_code == 0
        assert "could not verify SDI uniqueness" in result.stderr
        assert "server error" in result.stderr
        client.post.assert_called_once()

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_create_banner_shows_soar_host(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_soar_resolve: MagicMock,
    ) -> None:
        """Dry-run banner includes the SOAR host."""
        mock_resolve.return_value = soar_cfg()
        mock_soar_resolve.return_value = soar_cfg(host="soar.lab.local")
        client = MagicMock()
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            [
                "--json",
                "soar",
                "artifacts",
                "create",
                "--container",
                "1",
                "--name",
                "Test",
            ],
        )
        assert "soar.lab.local" in result.stderr


class TestValidateSeverity:
    def test_unknown_name_rejected(self) -> None:
        import pytest

        from splunkctl.commands.soar.artifacts import _validate_severity

        client = MagicMock()
        client.get.return_value = {"data": [{"name": "low"}, {"name": "high"}]}
        with pytest.raises(SOARError, match="not defined"):
            _validate_severity(client, "bogus")

    def test_known_name_passes(self) -> None:
        from splunkctl.commands.soar.artifacts import _validate_severity

        client = MagicMock()
        client.get.return_value = {"data": [{"name": "High"}]}
        _validate_severity(client, "high")  # no raise

    def test_full_page_falls_through_to_server(self) -> None:
        """>=50 severities means the page may be truncated — a name missing
        from a full page must not be rejected client-side."""
        from splunkctl.commands.soar.artifacts import _validate_severity

        client = MagicMock()
        client.get.return_value = {"data": [{"name": f"s{i}"} for i in range(50)]}
        _validate_severity(client, "not-on-first-page")  # no raise
