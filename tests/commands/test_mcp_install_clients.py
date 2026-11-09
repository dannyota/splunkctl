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


@pytest.mark.parametrize(
    "client,filename",
    [
        ("codex", ".codex/config.toml"),
        ("cursor", ".cursor/mcp.json"),
        ("gemini", ".gemini/settings.json"),
        ("claude", ".mcp.json"),
    ],
)
@pytest.mark.parametrize(
    "link", ["parent", "parent_dangling", "destination", "dangling"]
)
def test_refuse_symlinks_before_read(tmp_path, client, filename, link):
    if client == "claude" and link.startswith("parent"):
        pytest.skip("Claude has no config subdirectory")
    project = tmp_path / "project"
    project.mkdir()
    target = tmp_path / "outside"
    target.mkdir()
    sentinel = target / "config"
    sentinel.write_text("private settings")
    before = sentinel.stat().st_mtime_ns
    dest = project / filename
    if link.startswith("parent"):
        dest.parent.symlink_to(
            target if link == "parent" else tmp_path / "missing",
            target_is_directory=True,
        )
    else:
        dest.parent.mkdir(exist_ok=True)
        dest.symlink_to(sentinel if link == "destination" else target / "missing")
    with (
        patch("splunkctl.commands.mcp_cmd.Path.cwd", return_value=project),
        patch.object(
            Path, "read_text", side_effect=AssertionError("read before refusal")
        ),
        patch(
            "splunkctl.mcp.install.os.fdopen",
            side_effect=AssertionError("read before refusal"),
        ),
    ):
        result = CliRunner().invoke(cli, ["mcp", "install", "--client", client])
    assert result.exit_code == 2, result.output
    assert "symlink" in result.stderr.lower()
    assert sentinel.read_text() == "private settings"
    assert sentinel.stat().st_mtime_ns == before


@pytest.mark.parametrize(
    "raw", ['{"mcpServers": {}, "mcpServers": {}}', '{"x": {"a":1,"a":2}}']
)
def test_duplicate_json_keys_preserve_bytes_and_mtime(tmp_path, raw):
    dest = tmp_path / ".mcp.json"
    dest.write_text(raw)
    before = dest.stat().st_mtime_ns
    with patch("splunkctl.commands.mcp_cmd.Path.cwd", return_value=tmp_path):
        result = CliRunner().invoke(cli, ["mcp", "install"])
    assert result.exit_code == 2
    assert "Duplicate" in result.stderr
    assert dest.read_text() == raw
    assert dest.stat().st_mtime_ns == before


@pytest.mark.parametrize("global_flag", [True, False])
@pytest.mark.parametrize("transport", ["stdio", "http"])
def test_global_and_local_read_only(tmp_path, global_flag, transport):
    args = (
        (["--read-only"] if global_flag else [])
        + ["mcp", "install"]
        + ([] if global_flag else ["--read-only"])
        + ["--transport", transport]
    )
    with patch("splunkctl.commands.mcp_cmd.Path.cwd", return_value=tmp_path):
        result = CliRunner().invoke(cli, args)
    if transport == "http":
        assert result.exit_code == 2
        assert (
            "--read-only requires stdio; URL registration cannot enforce server policy."
            in result.stderr
        )
        assert not (tmp_path / ".mcp.json").exists()
    else:
        assert result.exit_code == 0
        assert (
            json.loads((tmp_path / ".mcp.json").read_text())["mcpServers"]["splunkctl"][
                "args"
            ][-1]
            == "--read-only"
        )


def test_atomic_replace_stays_in_verified_directory(tmp_path):
    import os

    project = tmp_path / "project"
    config_dir = project / ".cursor"
    config_dir.mkdir(parents=True)
    dest = config_dir / "mcp.json"
    dest.write_text('{"keep": true}')
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "mcp.json"
    sentinel.write_text('{"private": true}')
    original = sentinel.read_bytes(), sentinel.stat().st_mtime_ns
    moved = project / "verified"
    replace = os.replace

    def swap_then_replace(*args, **kwargs):
        config_dir.rename(moved)
        config_dir.symlink_to(outside, target_is_directory=True)
        return replace(*args, **kwargs)

    with (
        patch("splunkctl.commands.mcp_cmd.Path.cwd", return_value=project),
        patch("splunkctl.mcp.install.os.replace", side_effect=swap_then_replace),
    ):
        result = CliRunner().invoke(cli, ["mcp", "install", "--client", "cursor"])
    assert result.exit_code == 0, result.output
    assert (sentinel.read_bytes(), sentinel.stat().st_mtime_ns) == original
    config = json.loads((moved / "mcp.json").read_text())
    assert config["keep"] is True
    assert config["mcpServers"]["splunkctl"]["args"][-1] == "serve"
