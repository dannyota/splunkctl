"""Tests for kvstore path escaping (CIDR keys, slashes in names)."""

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


# --- path escaping: CIDR keys, slashes in names ---


@patch(_PATCH)
def test_update_key_with_slash_escapes_path(mock_gc: MagicMock) -> None:
    """Ensure CIDR keys like '10.0.0.0/24' are escaped as path segments."""
    svc = mock_gc.return_value.service
    svc.post.return_value = _resp({"_key": "10.0.0.0/24"})

    result = CliRunner().invoke(
        cli,
        [
            "--yes",
            "kvstore",
            "update",
            "agenttest_g3",
            "10.0.0.0/24",
            "--data",
            '{"allowed": true}',
        ],
    )
    assert result.exit_code == 0
    svc.post.assert_called_once()
    call_path = svc.post.call_args[0][0]
    # path should contain escaped slash
    assert "10.0.0.0%2F24" in call_path
    assert "storage/collections/data/agenttest_g3/10.0.0.0%2F24" == call_path


@patch(_PATCH)
def test_query_collection_with_slash_escapes_path(mock_gc: MagicMock) -> None:
    """Ensure collection names with slashes are escaped in the path."""
    svc = mock_gc.return_value.service
    svc.get.return_value = _resp([])

    result = CliRunner().invoke(
        cli, ["--json", "kvstore", "query", "collection/with/slashes"]
    )
    assert result.exit_code == 0
    svc.get.assert_called_once()
    call_path = svc.get.call_args[0][0]
    # path should contain escaped slashes
    assert "collection%2Fwith%2Fslashes" in call_path
    assert "storage/collections/data/collection%2Fwith%2Fslashes" == call_path


@patch(_PATCH)
def test_remove_by_query_dry_run_no_call(mock_gc: MagicMock) -> None:
    """Ensure dry-run of remove --query does not call delete."""
    result = CliRunner().invoke(
        cli,
        [
            "kvstore",
            "remove",
            "agenttest_g3",
            "--query",
            '{"host": "evil.example"}',
        ],
    )
    assert result.exit_code == 0
    assert "[DRY RUN]" in result.stderr
    # ensure no actual delete happened
    mock_gc.return_value.service.delete.assert_not_called()
