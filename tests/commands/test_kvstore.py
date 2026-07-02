"""Tests for kvstore collection management (config API) + query."""

import json
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from splunkctl.main import cli

_PATCH = "splunkctl.commands.kvstore.get_client"


def _resp(body: object) -> MagicMock:
    r = MagicMock()
    if isinstance(body, (bytes, bytearray)):
        r.body.read.return_value = body
    else:
        r.body.read.return_value = json.dumps(body).encode()
    return r


# --- collections ---


@patch(_PATCH)
def test_collections_lists_names(mock_gc: MagicMock) -> None:
    svc = mock_gc.return_value.service
    svc.get.return_value = _resp(
        {
            "entry": [
                {
                    "name": "agenttest_g3",
                    "acl": {"app": "search", "owner": "nobody"},
                    "content": {"disabled": False},
                }
            ]
        }
    )

    result = CliRunner().invoke(cli, ["--json", "kvstore", "collections"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data == [
        {"name": "agenttest_g3", "app": "search", "owner": "nobody", "disabled": False}
    ]
    svc.get.assert_called_once_with(
        "storage/collections/config", owner="nobody", app="search", output_mode="json"
    )


@patch(_PATCH)
def test_collections_custom_app(mock_gc: MagicMock) -> None:
    svc = mock_gc.return_value.service
    svc.get.return_value = _resp({"entry": []})

    result = CliRunner().invoke(
        cli, ["--json", "kvstore", "collections", "--app", "Splunk_Security_Essentials"]
    )
    assert result.exit_code == 0
    svc.get.assert_called_once_with(
        "storage/collections/config",
        owner="nobody",
        app="Splunk_Security_Essentials",
        output_mode="json",
    )


@patch(_PATCH)
def test_collections_empty(mock_gc: MagicMock) -> None:
    svc = mock_gc.return_value.service
    svc.get.return_value = _resp({"entry": []})

    result = CliRunner().invoke(cli, ["--json", "kvstore", "collections"])
    assert result.exit_code == 0
    assert json.loads(result.output) == []


# --- create ---


def test_create_dry_run_no_call() -> None:
    result = CliRunner().invoke(cli, ["kvstore", "create", "agenttest_g3"])
    assert result.exit_code == 0
    assert "[DRY RUN]" in result.stderr
    assert "agenttest_g3" in result.stderr


@patch(_PATCH)
def test_create_applies_with_yes(mock_gc: MagicMock) -> None:
    svc = mock_gc.return_value.service

    result = CliRunner().invoke(cli, ["--yes", "kvstore", "create", "agenttest_g3"])
    assert result.exit_code == 0
    assert "created" in result.stderr
    svc.post.assert_called_once_with(
        "storage/collections/config", owner="nobody", app="search", name="agenttest_g3"
    )


@patch(_PATCH)
def test_create_custom_app(mock_gc: MagicMock) -> None:
    svc = mock_gc.return_value.service

    result = CliRunner().invoke(
        cli, ["--yes", "kvstore", "create", "agenttest_g3", "--app", "search_soc"]
    )
    assert result.exit_code == 0
    svc.post.assert_called_once_with(
        "storage/collections/config",
        owner="nobody",
        app="search_soc",
        name="agenttest_g3",
    )


# --- delete ---


def test_delete_dry_run_says_deletes_collection() -> None:
    result = CliRunner().invoke(cli, ["kvstore", "delete", "agenttest_g3"])
    assert result.exit_code == 0
    assert "[DRY RUN]" in result.stderr
    # unambiguous: this removes the whole collection, not a filtered subset
    assert "collection" in result.stderr.lower()
    assert "all" in result.stderr.lower()


@patch(_PATCH)
def test_delete_applies_with_yes(mock_gc: MagicMock) -> None:
    svc = mock_gc.return_value.service

    result = CliRunner().invoke(cli, ["--yes", "kvstore", "delete", "agenttest_g3"])
    assert result.exit_code == 0
    assert "deleted" in result.stderr
    svc.delete.assert_called_once_with(
        "storage/collections/config/agenttest_g3", owner="nobody", app="search"
    )


# --- query ---


@patch(_PATCH)
def test_query_basic(mock_gc: MagicMock) -> None:
    svc = mock_gc.return_value.service
    svc.get.return_value = _resp([{"_key": "k1", "host": "evil.example"}])

    result = CliRunner().invoke(cli, ["--json", "kvstore", "query", "agenttest_g3"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data == [{"_key": "k1", "host": "evil.example"}]
    svc.get.assert_called_once_with(
        "storage/collections/data/agenttest_g3",
        owner="nobody",
        app="search",
        output_mode="json",
    )


@patch(_PATCH)
def test_query_passes_query_limit_skip_sort_params(mock_gc: MagicMock) -> None:
    svc = mock_gc.return_value.service
    svc.get.return_value = _resp([])

    result = CliRunner().invoke(
        cli,
        [
            "--json",
            "kvstore",
            "query",
            "agenttest_g3",
            "--query",
            '{"host": "evil.example"}',
            "--limit",
            "10",
            "--skip",
            "5",
            "--sort",
            "-_key",
        ],
    )
    assert result.exit_code == 0
    svc.get.assert_called_once_with(
        "storage/collections/data/agenttest_g3",
        owner="nobody",
        app="search",
        output_mode="json",
        query='{"host": "evil.example"}',
        limit=10,
        skip=5,
        sort="-_key",
    )


@patch(_PATCH)
def test_query_invalid_json_is_usage_error(mock_gc: MagicMock) -> None:
    result = CliRunner().invoke(
        cli, ["kvstore", "query", "agenttest_g3", "--query", "{not json"]
    )
    assert result.exit_code == 2
    mock_gc.return_value.service.get.assert_not_called()
