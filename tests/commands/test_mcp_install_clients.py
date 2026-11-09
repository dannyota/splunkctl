"""Project MCP adapters preserve unrelated configuration."""

import json
import stat
from pathlib import Path
from unittest.mock import patch

import pytest
import tomlkit
from click.testing import CliRunner

from splunkctl.main import cli


@pytest.mark.parametrize(
    ("client", "filename", "key"),
    [
        ("claude", ".mcp.json", "url"),
        ("codex", ".codex/config.toml", "url"),
        ("cursor", ".cursor/mcp.json", "url"),
        ("gemini", ".gemini/settings.json", "httpUrl"),
    ],
)
def test_http_adapters(tmp_path: Path, client: str, filename: str, key: str) -> None:
    with patch("splunkctl.commands.mcp_cmd.Path.cwd", return_value=tmp_path):
        result = CliRunner().invoke(
            cli, ["mcp", "install", "--client", client, "--transport", "http"]
        )
    assert result.exit_code == 0, result.output
    raw = (tmp_path / filename).read_text()
    config = tomlkit.parse(raw) if client == "codex" else json.loads(raw)
    server = config["mcp_servers" if client == "codex" else "mcpServers"]["splunkctl"]
    assert server[key] == "http://127.0.0.1:8765/mcp"
    if client == "claude":
        assert server["type"] == "http"


def test_toml_comments_merge_and_idempotence(tmp_path: Path) -> None:
    dest = tmp_path / ".codex/config.toml"
    dest.parent.mkdir()
    dest.write_text(
        '# keep\nmodel = "test"\n[mcp_servers.other]\ncommand = "other"\n'
        '[mcp_servers.splunkctl]\nurl = "old"\nenabled = false # policy\n'
    )
    dest.chmod(0o640)
    with patch("splunkctl.commands.mcp_cmd.Path.cwd", return_value=tmp_path):
        runner = CliRunner()
        assert (
            runner.invoke(cli, ["mcp", "install", "--client", "codex"]).exit_code == 0
        )
        raw, mtime = dest.read_bytes(), dest.stat().st_mtime_ns
        assert (
            runner.invoke(cli, ["mcp", "install", "--client", "codex"]).exit_code == 0
        )
    assert dest.read_bytes() == raw
    assert dest.stat().st_mtime_ns == mtime
    assert stat.S_IMODE(dest.stat().st_mode) == 0o640
    assert b"# keep" in raw and b"# policy" in raw
    server = tomlkit.parse(raw.decode())["mcp_servers"]["splunkctl"]
    assert "url" not in server and server["enabled"] is False


@pytest.mark.parametrize(
    "raw", ["", "{// comment\n}", '{"mcpServers":[],"x":1}', "[]", '{"x": NaN}']
)
def test_invalid_json_refuses_with_entry(tmp_path: Path, raw: str) -> None:
    dest = tmp_path / ".mcp.json"
    dest.write_text(raw)
    with patch("splunkctl.commands.mcp_cmd.Path.cwd", return_value=tmp_path):
        result = CliRunner().invoke(cli, ["--json", "mcp", "install"])
    assert result.exit_code != 0
    assert "hand" in result.stderr
    assert "splunkctl" in result.stderr
    assert dest.read_text() == raw


def test_preview_readonly_and_transport_switch(tmp_path: Path) -> None:
    dest = tmp_path / ".mcp.json"
    dest.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "splunkctl": {"url": "old", "headers": {"x": "y"}, "custom": 1}
                }
            }
        )
    )
    original = dest.read_bytes()
    with patch("splunkctl.commands.mcp_cmd.Path.cwd", return_value=tmp_path):
        runner = CliRunner()
        result = runner.invoke(cli, ["mcp", "install", "--preview", "--read-only"])
        assert result.exit_code == 0
        assert dest.read_bytes() == original
        assert "--read-only" in result.output
        assert runner.invoke(cli, ["mcp", "install", "--read-only"]).exit_code == 0
        server = json.loads(dest.read_text())["mcpServers"]["splunkctl"]
        assert server["args"][-1] == "--read-only"
        assert "url" not in server and server["custom"] == 1
        result = runner.invoke(
            cli, ["mcp", "install", "--read-only", "--transport", "http"]
        )
        assert result.exit_code != 0


def test_json_merge_is_byte_idempotent(tmp_path: Path) -> None:
    dest = tmp_path / ".cursor/mcp.json"
    dest.parent.mkdir()
    dest.write_text(
        json.dumps(
            {
                "other": True,
                "mcpServers": {
                    "other": {"command": "other"},
                    "splunkctl": {"timeout": 5000},
                },
            }
        )
    )
    with patch("splunkctl.commands.mcp_cmd.Path.cwd", return_value=tmp_path):
        runner = CliRunner()
        args = ["mcp", "install", "--client", "cursor"]
        assert runner.invoke(cli, args).exit_code == 0
        raw, mtime = dest.read_bytes(), dest.stat().st_mtime_ns
        assert runner.invoke(cli, args).exit_code == 0
    config = json.loads(raw)
    assert config["other"] is True
    assert config["mcpServers"]["other"]["command"] == "other"
    assert config["mcpServers"]["splunkctl"]["timeout"] == 5000
    assert dest.read_bytes() == raw and dest.stat().st_mtime_ns == mtime


def test_new_preview_does_not_create_directories(tmp_path: Path) -> None:
    with patch("splunkctl.commands.mcp_cmd.Path.cwd", return_value=tmp_path):
        result = CliRunner().invoke(
            cli, ["mcp", "install", "--client", "codex", "--preview"]
        )
    assert result.exit_code == 0
    assert not (tmp_path / ".codex").exists()


def test_malformed_toml_refuses_with_toml_entry(tmp_path: Path) -> None:
    dest = tmp_path / ".codex/config.toml"
    dest.parent.mkdir()
    dest.write_text("[broken")
    with patch("splunkctl.commands.mcp_cmd.Path.cwd", return_value=tmp_path):
        result = CliRunner().invoke(cli, ["mcp", "install", "--client", "codex"])
    assert result.exit_code != 0
    assert "[mcp_servers.splunkctl]" in result.stderr
    assert dest.read_text() == "[broken"
