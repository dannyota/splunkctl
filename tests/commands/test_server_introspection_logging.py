"""Server telemetry and logging tests using live 10.6.1.1 response bodies."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from splunkctl.main import cli

_FIXTURES = Path(__file__).parents[1] / "fixtures/live/splunk-10.6.1.1"
_TELEMETRY = "splunkctl.commands.server_introspection.get_client"
_LOGGING = "splunkctl.commands.server_logging.get_client"


def _response(name: str) -> MagicMock:
    response = MagicMock()
    response.body.read.return_value = (_FIXTURES / f"{name}.json").read_bytes()
    return response


@pytest.mark.parametrize(
    ("command", "fixture", "endpoint"),
    [
        ("queues", "introspection-queues", "server/introspection/queues"),
        ("indexer", "introspection-indexer", "server/introspection/indexer"),
        ("disk", "status-partitions-space", "server/status/partitions-space"),
    ],
)
@pytest.mark.parametrize("fmt", ["json", "table", "csv"])
@patch(_TELEMETRY)
def test_introspection(mock_client, command, fixture, endpoint, fmt):
    service = mock_client.return_value.service
    service.get.return_value = _response(fixture)
    result = CliRunner().invoke(
        cli, ["--format", fmt, "server", "introspection", command]
    )
    assert result.exit_code == 0, result.output
    service.get.assert_called_once_with(
        f"/services/{endpoint}", output_mode="json", count=0
    )
    if fmt != "json":
        assert "fill_ratio" in result.stdout or "average_KBps" in result.stdout
        return
    rows = json.loads(result.stdout)
    if command == "queues":
        assert rows[0] == {
            "queue": "indexQueue",
            "current": 0,
            "maximum": 512000,
            "unit": "bytes",
            "fill_ratio": 0,
            "blocked": None,
        }
    elif command == "indexer":
        assert rows[0]["status"] == "normal"
        assert rows[0]["average_KBps"] == 76.0518753110841
    else:
        assert rows[0]["capacity"] == 301290.812
        assert rows[0]["available"] == 124392.344
        assert rows[0]["used"] == pytest.approx(161522.468)
        assert rows[0]["fill_ratio"] == pytest.approx(161522.468 / 301290.812)
        assert rows[0]["fs_type"] is None
        assert rows[1]["fs_type"] == "ext4"
        assert rows[0]["unit"] == "MB"


@pytest.mark.parametrize("component", [None, "TcpOutputProc"])
@patch(_LOGGING)
def test_logger_get(mock_client, component):
    service = mock_client.return_value.service
    fixture = "server-logger-TcpOutputProc" if component else "server-logger"
    service.get.return_value = _response(fixture)
    args = ["--json", "server", "log-level", "get"] + ([component] if component else [])
    result = CliRunner().invoke(cli, args)
    assert result.exit_code == 0, result.output
    rows = json.loads(result.stdout)
    assert rows[0]["level"] == ("INFO" if component else "WARN")
    if component:
        assert rows[0]["component"] == component
        service.get.assert_called_once_with(
            "/services/server/logger/TcpOutputProc", output_mode="json"
        )
    else:
        assert len(rows) == 3
        service.get.assert_called_once_with(
            "/services/server/logger", output_mode="json", count=0
        )


@pytest.mark.parametrize("level", ["debug", "warn", "error"])
@patch(_LOGGING)
def test_logger_preview(mock_client, level):
    service = mock_client.return_value.service
    service.get.return_value = _response("server-logger-TcpOutputProc")
    result = CliRunner().invoke(
        cli, ["--json", "server", "log-level", "set", "TcpOutputProc", level]
    )
    assert result.exit_code == 0, result.output
    assert result.stdout == ""
    assert f"INFO -> {level.upper()}" in result.stderr
    assert "Runtime only" in result.stderr
    service.post.assert_not_called()


@patch(_LOGGING)
def test_logger_apply_readback(mock_client):
    service = mock_client.return_value.service
    service.get.side_effect = [
        _response("server-logger-TcpOutputProc"),
        _response("logger-set-debug-response"),
    ]
    service.post.return_value = _response("logger-set-debug-response")
    result = CliRunner().invoke(
        cli, ["--json", "--yes", "server", "log-level", "set", "TcpOutputProc", "debug"]
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == [
        {"component": "TcpOutputProc", "level": "DEBUG"}
    ]
    service.post.assert_called_once_with(
        "/services/server/logger/TcpOutputProc", output_mode="json", level="DEBUG"
    )
    assert service.get.call_count == 2


@patch(_LOGGING)
def test_logger_unchanged(mock_client):
    service = mock_client.return_value.service
    service.get.return_value = _response("server-logger-TcpOutputProc")
    result = CliRunner().invoke(
        cli, ["--yes", "server", "log-level", "set", "TcpOutputProc", "info"]
    )
    assert result.exit_code == 0, result.output
    assert "unchanged" in result.stderr
    service.post.assert_not_called()


@pytest.mark.parametrize("level", ["FATAL", "BOGUS"])
@patch(_LOGGING)
def test_logger_invalid_level(mock_client, level):
    result = CliRunner().invoke(
        cli, ["server", "log-level", "set", "TcpOutputProc", level]
    )
    assert result.exit_code == 2
    mock_client.assert_not_called()


@patch(_LOGGING)
def test_logger_read_only(mock_client):
    service = mock_client.return_value.service
    service.get.return_value = _response("server-logger-TcpOutputProc")
    result = CliRunner().invoke(
        cli,
        [
            "--json",
            "--read-only",
            "--yes",
            "server",
            "log-level",
            "set",
            "TcpOutputProc",
            "DEBUG",
        ],
    )
    assert result.exit_code != 0
    assert json.loads(result.stderr)["error"]["kind"] == "permission"
    service.post.assert_not_called()


@patch(_LOGGING)
def test_logger_failed_confirmation(mock_client):
    service = mock_client.return_value.service
    service.get.return_value = _response("server-logger-TcpOutputProc")
    service.post.return_value = _response("logger-set-debug-response")
    result = CliRunner().invoke(
        cli, ["--json", "--yes", "server", "log-level", "set", "TcpOutputProc", "DEBUG"]
    )
    assert result.exit_code == 1
    assert result.stdout == ""
    assert "read-back" in result.stderr


@patch("splunkctl.commands.indexes.get_client")
def test_index_size_number(mock_client):
    entry = json.loads((_FIXTURES / "data-indexes.json").read_bytes())["entry"][0]
    index = MagicMock()
    index.name = entry["name"]
    index.content = entry["content"]
    mock_client.return_value.service.indexes.list.return_value = [index]
    result = CliRunner().invoke(cli, ["--json", "indexes", "list"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)[0]["currentDBSizeMB"] == 1


def test_logger_component_encoded_once_over_sdk():
    """The SDK receives one encoded path segment for all three calls."""
    import io
    from types import SimpleNamespace

    from splunklib.client import Service

    calls = []
    bodies = iter(
        [
            "server-logger-TcpOutputProc",
            "logger-set-debug-response",
            "logger-set-debug-response",
        ]
    )

    def network(url, message, **kwargs):
        calls.append((url, message["method"]))
        body = (_FIXTURES / f"{next(bodies)}.json").read_bytes()
        return {"status": 200, "reason": "OK", "headers": [], "body": io.BytesIO(body)}

    service = Service(host="example.test", token="test", handler=network)  # noqa: S106
    with patch(_LOGGING, return_value=SimpleNamespace(service=service)):
        result = CliRunner().invoke(
            cli, ["--json", "--yes", "server", "log-level", "set", "part /+%", "DEBUG"]
        )
    assert result.exit_code == 0, result.output
    expected = "https://example.test:8089/services/server/logger/part%20%2F%2B%25"
    assert [url.split("?")[0] for url, _ in calls] == [expected] * 3
    assert [method for _, method in calls] == ["GET", "POST", "GET"]
