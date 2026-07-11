"""Tests for soar search command."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from splunkctl.main import cli
from splunkctl.soar.client import SOARError
from tests.soar.conftest import PATCH_CLIENT, PATCH_RESOLVE, soar_cfg

# Sample search results mimicking the normalized {count, num_pages, data}
# shape returned by SOARClient after envelope normalization.
_SEARCH_RESULTS: dict[str, Any] = {
    "count": 3,
    "num_pages": 1,
    "data": [
        {
            "id": 53,
            "name": "DNS",
            "category": "app",
            "verbose": "App",
            "model": "app",
            "url": "https://soar.test:8443/docs/app_reference/dns_abc",
        },
        {
            "id": 54,
            "name": "DNSDB",
            "category": "app",
            "verbose": "App",
            "model": "app",
            "url": "https://soar.test:8443/docs/app_reference/dnsdb_def",
        },
        {
            "id": 10,
            "name": "DNS Alert",
            "category": "container",
            "verbose": "Event",
            "model": "container",
            "url": "https://soar.test:8443/mission/10/summary/evidence",
        },
    ],
}


class TestSoarSearch:
    """Basic search invocation."""

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_basic_query(self, mock_resolve: MagicMock, mock_cls: MagicMock) -> None:
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.return_value = _SEARCH_RESULTS
        mock_cls.return_value = client

        result = CliRunner().invoke(cli, ["--json", "soar", "search", "dns"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 3
        assert data[0]["name"] == "DNS"
        assert data[0]["category"] == "app"

        # Verify the client was called with the right params.
        client.get.assert_called_once()
        call_args = client.get.call_args
        assert call_args[0][0] == "search"
        params = call_args[1]["params"]
        assert params["query"] == "dns"

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_query_with_categories(
        self, mock_resolve: MagicMock, mock_cls: MagicMock
    ) -> None:
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.return_value = {
            "count": 1,
            "num_pages": 1,
            "data": [_SEARCH_RESULTS["data"][0]],
        }
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli, ["--json", "soar", "search", "dns", "--categories", "app,container"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 1

        params = client.get.call_args[1]["params"]
        assert params["categories"] == "app,container"

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_empty_results(self, mock_resolve: MagicMock, mock_cls: MagicMock) -> None:
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.return_value = {"count": 0, "num_pages": 1, "data": []}
        mock_cls.return_value = client

        result = CliRunner().invoke(cli, ["--json", "soar", "search", "zzznomatch"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data == []

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_page_size_passed(
        self, mock_resolve: MagicMock, mock_cls: MagicMock
    ) -> None:
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.return_value = {"count": 0, "num_pages": 1, "data": []}
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli, ["--json", "soar", "search", "test", "--page-size", "5"]
        )
        assert result.exit_code == 0
        params = client.get.call_args[1]["params"]
        assert params["page_size"] == 5

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_page_passed(self, mock_resolve: MagicMock, mock_cls: MagicMock) -> None:
        """--page is forwarded as-is (1-based for /rest/search)."""
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.return_value = {"count": 0, "num_pages": 1, "data": []}
        mock_cls.return_value = client

        result = CliRunner().invoke(
            cli, ["--json", "soar", "search", "test", "--page", "2"]
        )
        assert result.exit_code == 0
        params = client.get.call_args[1]["params"]
        assert params["page"] == 2

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_missing_query_exits_nonzero(
        self, mock_resolve: MagicMock, mock_cls: MagicMock
    ) -> None:
        """query is a required argument."""
        mock_resolve.return_value = soar_cfg()
        mock_cls.return_value = MagicMock()

        result = CliRunner().invoke(cli, ["--json", "soar", "search"])
        assert result.exit_code != 0

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_page_0_rejected(
        self, mock_resolve: MagicMock, mock_cls: MagicMock
    ) -> None:
        """--page 0 exits with code 2 (Click validation)."""
        mock_resolve.return_value = soar_cfg()
        mock_cls.return_value = MagicMock()
        result = CliRunner().invoke(
            cli, ["--json", "soar", "search", "test", "--page", "0"]
        )
        assert result.exit_code == 2

    @patch(PATCH_CLIENT)
    @patch(PATCH_RESOLVE)
    def test_soar_error_exits_1(
        self, mock_resolve: MagicMock, mock_cls: MagicMock
    ) -> None:
        """SOARError (e.g. auth failure) exits 1 with typed envelope."""
        mock_resolve.return_value = soar_cfg()
        client = MagicMock()
        client.get.side_effect = SOARError(
            "Unauthorized", kind="auth", http_status=401
        )
        mock_cls.return_value = client

        result = CliRunner().invoke(cli, ["--json", "soar", "search", "dns"])
        assert result.exit_code == 1
        last = result.stderr.strip().splitlines()[-1]
        payload = json.loads(last)
        assert payload["error"]["kind"] == "auth"

    @patch(PATCH_RESOLVE)
    def test_no_host_exits_1(self, mock_resolve: MagicMock) -> None:
        mock_resolve.return_value = {"port": 8443, "verify": False}

        result = CliRunner().invoke(cli, ["--json", "soar", "search", "dns"])
        assert result.exit_code == 1
        last = result.stderr.strip().splitlines()[-1]
        payload = json.loads(last)
        assert payload["error"]["kind"] == "usage"


class TestSearchClientNormalization:
    """Verify SOARClient normalizes the /rest/search envelope correctly."""

    def test_search_envelope_preserves_num_pages(self) -> None:
        """The client must forward the server's real num_pages, not hardcode 1."""
        from splunkctl.soar.client import SOARClient

        client = SOARClient(host="fake", token="tok")  # noqa: S106
        body: dict[str, Any] = {
            "results": [{"id": 1, "name": "DNS"}],
            "count": 10,
            "num_pages": 5,
            "page": 1,
        }
        normalized = client._normalize_get_envelope(body, "search")
        assert normalized["num_pages"] == 5
        assert normalized["count"] == 10
        assert len(normalized["data"]) == 1

    def test_search_envelope_defaults_num_pages(self) -> None:
        """When server omits num_pages, default to 1."""
        from splunkctl.soar.client import SOARClient

        client = SOARClient(host="fake", token="tok")  # noqa: S106
        body: dict[str, Any] = {"results": [{"id": 1}], "count": 1}
        normalized = client._normalize_get_envelope(body, "search")
        assert normalized["num_pages"] == 1
