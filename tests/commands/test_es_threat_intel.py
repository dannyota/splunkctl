"""Tests for the es threat-intel commands."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from splunkctl.main import cli

_PATCH = "splunkctl.commands.es.get_client"


def _mock_svc_with_es() -> MagicMock:
    """A service mock where the ES app entity fetch succeeds."""
    svc = MagicMock()
    svc.apps.__getitem__.return_value = MagicMock()
    return svc


def _mock_svc_without_es() -> MagicMock:
    """A service mock where the ES app entity fetch raises KeyError."""
    svc = MagicMock()
    svc.apps.__getitem__.side_effect = KeyError("no such app")
    return svc


def _rest_response(body: dict[str, object]) -> MagicMock:
    """Build a mock SDK response whose ``.body.read()`` returns JSON."""
    resp = MagicMock()
    resp.body.read.return_value = json.dumps(body).encode()
    return resp


_SAMPLE_ENTRIES: dict[str, object] = {
    "entry": [
        {
            "name": "key-001",
            "content": {
                "threat_collection": "ip_intel",
                "ip": "10.0.0.1",
                "domain": "",
                "description": "test indicator",
                "weight": "1",
                "threat_key": "abc",
            },
        },
        {
            "name": "key-002",
            "content": {
                "threat_collection": "domain_intel",
                "ip": "",
                "domain": "evil.example.com",
                "description": "malicious domain",
                "weight": "3",
                "threat_key": "def",
            },
        },
    ]
}


# --- feature detection ---


@patch(_PATCH)
def test_threat_intel_list_es_not_installed(mock_gc: MagicMock) -> None:
    mock_gc.return_value.service = _mock_svc_without_es()

    result = CliRunner().invoke(cli, ["--json", "es", "threat-intel", "list"])
    assert result.exit_code == 1
    payload = json.loads(result.stderr)
    assert payload["error"]["kind"] == "not_found"
    assert "SplunkEnterpriseSecuritySuite" in payload["error"]["message"]


@patch(_PATCH)
def test_threat_intel_upload_es_not_installed(mock_gc: MagicMock) -> None:
    mock_gc.return_value.service = _mock_svc_without_es()

    result = CliRunner().invoke(
        cli,
        [
            "--yes",
            "--json",
            "es",
            "threat-intel",
            "upload",
            "--type",
            "ip_intel",
            "--file",
            __file__,  # any existing file
        ],
    )
    assert result.exit_code == 1
    last = result.stderr.strip().splitlines()[-1]
    payload = json.loads(last)
    assert payload["error"]["kind"] == "not_found"


@patch(_PATCH)
def test_threat_intel_delete_es_not_installed(mock_gc: MagicMock) -> None:
    mock_gc.return_value.service = _mock_svc_without_es()

    result = CliRunner().invoke(
        cli, ["--yes", "--json", "es", "threat-intel", "delete", "key-001"]
    )
    assert result.exit_code == 1
    last = result.stderr.strip().splitlines()[-1]
    payload = json.loads(last)
    assert payload["error"]["kind"] == "not_found"


# --- list ---


@patch(_PATCH)
def test_list_returns_rows(mock_gc: MagicMock) -> None:
    svc = _mock_svc_with_es()
    svc.get.return_value = _rest_response(_SAMPLE_ENTRIES)
    mock_gc.return_value.service = svc

    result = CliRunner().invoke(cli, ["--json", "es", "threat-intel", "list"])
    assert result.exit_code == 0
    rows = json.loads(result.stdout)
    assert len(rows) == 2
    assert rows[0]["key"] == "key-001"
    assert rows[0]["ip"] == "10.0.0.1"
    assert rows[1]["domain"] == "evil.example.com"

    svc.get.assert_called_once()
    call_args = svc.get.call_args
    assert call_args.args[0] == "/services/data/threat_intel/item"
    assert call_args.kwargs["output_mode"] == "json"
    assert call_args.kwargs["count"] == 100


@patch(_PATCH)
def test_list_with_type_filter(mock_gc: MagicMock) -> None:
    svc = _mock_svc_with_es()
    svc.get.return_value = _rest_response({"entry": []})
    mock_gc.return_value.service = svc

    result = CliRunner().invoke(
        cli, ["--json", "es", "threat-intel", "list", "--type", "ip_intel"]
    )
    assert result.exit_code == 0
    call_kwargs = svc.get.call_args.kwargs
    assert call_kwargs["threat_collection"] == "ip_intel"


@patch(_PATCH)
def test_list_with_limit(mock_gc: MagicMock) -> None:
    svc = _mock_svc_with_es()
    svc.get.return_value = _rest_response({"entry": []})
    mock_gc.return_value.service = svc

    result = CliRunner().invoke(
        cli, ["--json", "es", "threat-intel", "list", "--limit", "25"]
    )
    assert result.exit_code == 0
    assert svc.get.call_args.kwargs["count"] == 25


@patch(_PATCH)
def test_list_empty(mock_gc: MagicMock) -> None:
    svc = _mock_svc_with_es()
    svc.get.return_value = _rest_response({"entry": []})
    mock_gc.return_value.service = svc

    result = CliRunner().invoke(cli, ["es", "threat-intel", "list"])
    assert result.exit_code == 0
    assert result.stdout.strip() == "[]"

    result = CliRunner().invoke(
        cli, ["--format", "table", "es", "threat-intel", "list"]
    )
    assert result.exit_code == 0
    assert "No threat-intelligence items found" in result.stderr


# --- upload ---


@patch(_PATCH)
def test_upload_dry_run(mock_gc: MagicMock, tmp_path: Path) -> None:
    csv_file = tmp_path / "iocs.csv"
    csv_file.write_text("ip,description\n10.0.0.1,test\n")

    result = CliRunner().invoke(
        cli,
        [
            "es",
            "threat-intel",
            "upload",
            "--type",
            "ip_intel",
            "--file",
            str(csv_file),
        ],
    )
    assert result.exit_code == 0
    assert "[DRY RUN]" in result.stderr
    assert "ip_intel" in result.stderr
    assert "iocs.csv" in result.stderr
    mock_gc.assert_not_called()


@patch(_PATCH)
def test_upload_applies(mock_gc: MagicMock, tmp_path: Path) -> None:
    svc = _mock_svc_with_es()
    svc.post.return_value = _rest_response({"entry": [{"name": "ok"}]})
    mock_gc.return_value.service = svc

    csv_file = tmp_path / "iocs.csv"
    csv_file.write_text("ip,description\n10.0.0.1,test\n")

    result = CliRunner().invoke(
        cli,
        [
            "--yes",
            "es",
            "threat-intel",
            "upload",
            "--type",
            "ip_intel",
            "--file",
            str(csv_file),
        ],
    )
    assert result.exit_code == 0
    svc.post.assert_called_once()
    call_args = svc.post.call_args
    assert call_args.args[0] == "/services/data/threat_intel/upload"
    assert call_args.kwargs["threat_collection"] == "ip_intel"
    assert call_args.kwargs["filename"] == "iocs.csv"
    assert "Uploaded" in result.stderr


@patch(_PATCH)
def test_upload_empty_response_body(mock_gc: MagicMock, tmp_path: Path) -> None:
    svc = _mock_svc_with_es()
    resp = MagicMock()
    resp.body.read.return_value = b""
    svc.post.return_value = resp
    mock_gc.return_value.service = svc

    csv_file = tmp_path / "iocs.csv"
    csv_file.write_text("ip\n10.0.0.1\n")

    result = CliRunner().invoke(
        cli,
        [
            "--yes",
            "es",
            "threat-intel",
            "upload",
            "--type",
            "ip_intel",
            "--file",
            str(csv_file),
        ],
    )
    assert result.exit_code == 0
    assert "Uploaded" in result.stderr


@patch(_PATCH)
def test_upload_requires_type(mock_gc: MagicMock) -> None:
    result = CliRunner().invoke(
        cli, ["--yes", "es", "threat-intel", "upload", "--file", __file__]
    )
    assert result.exit_code == 2


@patch(_PATCH)
def test_upload_requires_file(mock_gc: MagicMock) -> None:
    result = CliRunner().invoke(
        cli, ["--yes", "es", "threat-intel", "upload", "--type", "ip_intel"]
    )
    assert result.exit_code == 2


# --- delete ---


@patch(_PATCH)
def test_delete_dry_run(mock_gc: MagicMock) -> None:
    result = CliRunner().invoke(cli, ["es", "threat-intel", "delete", "key-001"])
    assert result.exit_code == 0
    assert "[DRY RUN]" in result.stderr
    assert "key-001" in result.stderr
    mock_gc.assert_not_called()


@patch(_PATCH)
def test_delete_applies(mock_gc: MagicMock) -> None:
    svc = _mock_svc_with_es()
    mock_gc.return_value.service = svc

    result = CliRunner().invoke(
        cli, ["--yes", "es", "threat-intel", "delete", "key-001"]
    )
    assert result.exit_code == 0
    svc.delete.assert_called_once()
    call_args = svc.delete.call_args
    assert call_args.args[0] == "/services/data/threat_intel/item/key-001"
    assert "Deleted" in result.stderr


@patch(_PATCH)
def test_delete_missing_key_is_usage_error(mock_gc: MagicMock) -> None:
    result = CliRunner().invoke(cli, ["--yes", "es", "threat-intel", "delete"])
    assert result.exit_code == 2


# --- commands --json includes threat-intel ---


def test_commands_json_includes_threat_intel_group() -> None:
    result = CliRunner().invoke(cli, ["commands"])
    assert result.exit_code == 0
    tree = json.loads(result.output)
    es_node = next(c for c in tree["commands"] if c["name"] == "es")
    ti_node = next(c for c in es_node["subcommands"] if c["name"] == "threat-intel")
    sub_names = [c["name"] for c in ti_node["subcommands"]]
    assert set(sub_names) == {"list", "upload", "delete"}
    upload_node = next(c for c in ti_node["subcommands"] if c["name"] == "upload")
    assert upload_node.get("guarded") is True
    delete_node = next(c for c in ti_node["subcommands"] if c["name"] == "delete")
    assert delete_node.get("guarded") is True
