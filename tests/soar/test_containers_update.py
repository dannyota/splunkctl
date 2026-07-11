"""Tests for soar containers update — setters, bulk, tags, status by name."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from splunkctl.main import cli
from tests.soar.conftest import PATCH_CLIENT, PATCH_RESOLVE, soar_cfg

_WRITE_CFG = {**soar_cfg(), "username": "admin", "password": "changeme"}
PATCH_SOAR_RESOLVE = "splunkctl.guard.cfg_mod.resolve_soar"


def _soar_guard_cfg() -> dict[str, Any]:
    return {"host": "soar.test", "port": 8443}


class TestContainerUpdate:
    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_update_single(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard_resolve: MagicMock,
    ) -> None:
        """Update a single container."""
        mock_resolve.return_value = _WRITE_CFG
        mock_guard_resolve.return_value = _soar_guard_cfg()
        client = MagicMock()
        client.post.return_value = {"success": True}
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            [
                "--yes",
                "soar",
                "containers",
                "update",
                "42",
                "--severity",
                "critical",
            ],
        )
        assert result.exit_code == 0
        client.post.assert_called_once()
        (path,) = client.post.call_args[0]
        assert path == "container/42"
        body = client.post.call_args[1]["body"]
        assert body["severity"] == "critical"

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_update_status_numeric_rejected(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard_resolve: MagicMock,
    ) -> None:
        """Numeric status id is rejected with a usage error."""
        mock_resolve.return_value = _WRITE_CFG
        mock_guard_resolve.return_value = _soar_guard_cfg()
        client = MagicMock()
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            [
                "--yes",
                "--json",
                "soar",
                "containers",
                "update",
                "42",
                "--status",
                "2",
            ],
        )
        assert result.exit_code == 1
        last = result.stderr.strip().splitlines()[-1]
        payload = json.loads(last)
        assert payload["error"]["kind"] == "usage"
        assert "numeric id" in payload["error"]["message"]
        client.post.assert_not_called()

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_update_no_changes_errors(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard_resolve: MagicMock,
    ) -> None:
        """Update with no setters exits 1."""
        mock_resolve.return_value = _WRITE_CFG
        mock_guard_resolve.return_value = _soar_guard_cfg()
        client = MagicMock()
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            ["--yes", "--json", "soar", "containers", "update", "42"],
        )
        assert result.exit_code == 1

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_update_role(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard_resolve: MagicMock,
    ) -> None:
        """--role passes the role payload key (same as assign)."""
        mock_resolve.return_value = _WRITE_CFG
        mock_guard_resolve.return_value = _soar_guard_cfg()
        client = MagicMock()
        client.post.return_value = {"success": True}
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            [
                "--yes",
                "soar",
                "containers",
                "update",
                "42",
                "--role",
                "analyst",
            ],
        )
        assert result.exit_code == 0
        body = client.post.call_args[1]["body"]
        assert body["role"] == "analyst"

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_update_bulk(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard_resolve: MagicMock,
    ) -> None:
        """Bulk update posts array to /rest/container."""
        mock_resolve.return_value = _WRITE_CFG
        mock_guard_resolve.return_value = _soar_guard_cfg()
        client = MagicMock()
        client.post.return_value = {}
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            [
                "--yes",
                "soar",
                "containers",
                "update",
                "1",
                "2",
                "3",
                "--severity",
                "low",
            ],
        )
        assert result.exit_code == 0
        client.post.assert_called_once()
        (path,) = client.post.call_args[0]
        assert path == "container"
        body = client.post.call_args[1]["body"]
        assert isinstance(body, list)
        assert len(body) == 3
        assert body[0]["id"] == 1
        assert body[2]["id"] == 3
        assert all(item["severity"] == "low" for item in body)

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_update_with_tags_read_modify_write(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard_resolve: MagicMock,
    ) -> None:
        """Tags merge existing + new via read-modify-write."""
        mock_resolve.return_value = _WRITE_CFG
        mock_guard_resolve.return_value = _soar_guard_cfg()
        client = MagicMock()
        client.get.return_value = {"id": 42, "tags": ["existing"]}
        client.post.return_value = {"success": True}
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            [
                "--yes",
                "soar",
                "containers",
                "update",
                "42",
                "--tag",
                "new_tag",
            ],
        )
        assert result.exit_code == 0
        body = client.post.call_args[1]["body"]
        assert body["tags"] == ["existing", "new_tag"]

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_update_bulk_tags_per_container_merge(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard_resolve: MagicMock,
    ) -> None:
        """Bulk --tag merges each container's OWN existing tags."""
        mock_resolve.return_value = _WRITE_CFG
        mock_guard_resolve.return_value = _soar_guard_cfg()
        client = MagicMock()

        def get_side(path: str, **kw: Any) -> Any:
            if path == "container/1":
                return {"id": 1, "tags": ["alpha"]}
            if path == "container/2":
                return {"id": 2, "tags": ["beta"]}
            return {}

        client.get.side_effect = get_side
        client.post.return_value = {}
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            [
                "--yes",
                "soar",
                "containers",
                "update",
                "1",
                "2",
                "--tag",
                "shared",
            ],
        )
        assert result.exit_code == 0
        client.post.assert_called_once()
        (path,) = client.post.call_args[0]
        assert path == "container"
        body = client.post.call_args[1]["body"]
        assert isinstance(body, list)
        assert body[0]["id"] == 1
        assert body[0]["tags"] == ["alpha", "shared"]
        assert body[1]["id"] == 2
        assert body[1]["tags"] == ["beta", "shared"]

    @patch(PATCH_SOAR_RESOLVE)
    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_update_dry_run_tags_no_network(
        self,
        mock_resolve: MagicMock,
        mock_cls: MagicMock,
        mock_guard_resolve: MagicMock,
    ) -> None:
        """Dry-run update with --tag performs no API calls at all."""
        mock_resolve.return_value = _WRITE_CFG
        mock_guard_resolve.return_value = _soar_guard_cfg()
        client = MagicMock()
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli,
            ["soar", "containers", "update", "42", "--tag", "new_tag"],
        )
        assert result.exit_code == 0
        assert "[DRY RUN]" in result.stderr
        # Merge is deferred to apply time — preview says so, no I/O.
        assert "merged at apply time" in result.stderr
        client.get.assert_not_called()
        client.post.assert_not_called()
