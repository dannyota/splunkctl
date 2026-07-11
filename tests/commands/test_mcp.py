"""Tests for the MCP server and tool generation."""

import json
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from splunkctl.main import cli
from splunkctl.mcp.tools import (
    build_tool_index,
    group_names,
    group_summary,
    group_tools,
)


def test_build_tool_index_populated() -> None:
    idx = build_tool_index(cli)
    assert len(idx) > 50
    assert "search_run" in idx
    assert "rules_list" in idx
    assert "alerts_list" in idx


def test_tool_names_use_underscores() -> None:
    idx = build_tool_index(cli)
    for name in idx:
        assert "-" not in name, f"Tool name has hyphen: {name}"


def test_skips_internal_groups() -> None:
    idx = build_tool_index(cli)
    for name in idx:
        assert not name.startswith("mcp_")
        assert not name.startswith("commands_")
        assert not name.startswith("skill_")
        assert not name.startswith("config_")


def test_search_run_schema() -> None:
    idx = build_tool_index(cli)
    entry = idx["search_run"]
    schema = entry.schema
    assert schema["type"] == "object"
    props = schema["properties"]
    assert "spl" in props
    assert props["spl"]["type"] == "string"
    assert "limit" in props
    assert props["limit"]["type"] == "integer"
    assert "spl" in schema.get("required", [])


def test_guarded_tools_marked() -> None:
    idx = build_tool_index(cli)
    guarded = [t for t in idx.values() if t.guarded]
    assert len(guarded) > 10
    assert any("dry-run" in t.description for t in guarded)


def test_global_flags_stripped() -> None:
    idx = build_tool_index(cli)
    for entry in idx.values():
        props = entry.schema.get("properties", {})
        assert "yes" not in props, f"{entry.name} exposes 'yes'"
        assert "json" not in props, f"{entry.name} exposes 'json'"
        assert "debug" not in props, f"{entry.name} exposes 'debug'"


def test_group_names_returns_groups() -> None:
    names = group_names(cli)
    assert "search" in names
    assert "rules" in names
    assert "mcp" not in names
    assert "commands" not in names


def test_group_tools_filters() -> None:
    idx = build_tool_index(cli)
    search_tools = group_tools(idx, "search")
    assert len(search_tools) > 0
    for t in search_tools:
        assert t.name.startswith("search_")


def test_group_summary_format() -> None:
    rows = group_summary(cli)
    assert len(rows) > 10
    for r in rows:
        assert "group" in r
        assert "description" in r
        assert "count" in r
        int(r["count"])


def test_choice_params_have_enum() -> None:
    idx = build_tool_index(cli)
    found_enum = False
    for entry in idx.values():
        for prop in entry.schema.get("properties", {}).values():
            if "enum" in prop:
                found_enum = True
                assert isinstance(prop["enum"], list)
                assert len(prop["enum"]) > 0
    assert found_enum, "Expected at least one tool with enum params"


def test_positional_args_tracked() -> None:
    idx = build_tool_index(cli)
    entry = idx["search_run"]
    assert "spl" in entry.positional
    assert "limit" not in entry.positional


def test_build_cli_args_positional() -> None:
    from splunkctl.mcp.server import _build_cli_args

    idx = build_tool_index(cli)
    entry = idx["search_run"]
    args = _build_cli_args(entry, {"spl": "index=main", "limit": 5})
    assert "--spl" not in args, "positional arg should not get a flag"
    assert "index=main" in args
    assert "--limit" in args


def test_build_cli_args_yes_passed() -> None:
    from splunkctl.mcp.server import _build_cli_args

    idx = build_tool_index(cli)
    guarded = [t for t in idx.values() if t.guarded]
    assert guarded
    entry = guarded[0]
    args = _build_cli_args(entry, {"yes": True})
    assert "--yes" in args

    args_no = _build_cli_args(entry, {"yes": False})
    assert "--yes" not in args_no


def test_variadic_argument_schema_is_array() -> None:
    idx = build_tool_index(cli)
    pairs = idx["conf_set"].schema["properties"]["pairs"]
    assert pairs["type"] == "array"
    assert pairs["items"]["type"] == "string"
    event_ids = idx["es_notables_update"].schema["properties"]["event_ids"]
    assert event_ids["type"] == "array"


def test_multiple_option_schema_is_array() -> None:
    idx = build_tool_index(cli)
    name = idx["rules_export"].schema["properties"]["name"]
    assert name["type"] == "array"
    assert name["items"]["type"] == "string"
    set_pairs = idx["hec_create"].schema["properties"]["set_pairs"]
    assert set_pairs["type"] == "array"


def test_build_cli_args_positional_array_in_order() -> None:
    from splunkctl.mcp.server import _build_cli_args

    idx = build_tool_index(cli)
    entry = idx["conf_set"]
    args = _build_cli_args(
        entry,
        {"pairs": ["a=1", "b=2"], "stanza": "mystanza", "file": "props"},
    )
    assert args[: len(entry.cmd_path)] == entry.cmd_path
    tail = args[len(entry.cmd_path) :]
    non_flags = [a for a in tail if not a.startswith("--")]
    assert non_flags == ["props", "mystanza", "a=1", "b=2"]


def test_build_cli_args_multiple_option_repeats_flag() -> None:
    from splunkctl.mcp.server import _build_cli_args

    idx = build_tool_index(cli)
    entry = idx["rules_export"]
    args = _build_cli_args(entry, {"name": ["r1", "r2"]})
    assert args.count("--name") == 2
    assert "r1" in args
    assert "r2" in args


def test_build_cli_args_json_string_array_coerced() -> None:
    from splunkctl.mcp.server import _build_cli_args

    idx = build_tool_index(cli)
    entry = idx["conf_set"]
    args = _build_cli_args(
        entry,
        {"file": "props", "stanza": "s", "pairs": '["a=1", "b=2"]'},
    )
    non_flags = [a for a in args[len(entry.cmd_path) :] if not a.startswith("--")]
    assert non_flags == ["props", "s", "a=1", "b=2"]


def test_mcp_serve_command_exists() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["mcp", "--help"])
    assert result.exit_code == 0
    assert "serve" in result.output
    assert "install" in result.output


def test_mcp_install_writes_config(tmp_path: Path) -> None:
    runner = CliRunner()
    with patch("splunkctl.commands.mcp_cmd.Path.cwd", return_value=tmp_path):
        result = runner.invoke(cli, ["mcp", "install"])
    assert result.exit_code == 0
    config = json.loads((tmp_path / ".mcp.json").read_text())
    assert "splunkctl" in config["mcpServers"]
    server = config["mcpServers"]["splunkctl"]
    assert "mcp" in server["args"]
    assert "serve" in server["args"]


def test_mcp_install_merges_existing(tmp_path: Path) -> None:
    existing = {"mcpServers": {"other": {"command": "other"}}}
    (tmp_path / ".mcp.json").write_text(json.dumps(existing))
    runner = CliRunner()
    with patch("splunkctl.commands.mcp_cmd.Path.cwd", return_value=tmp_path):
        result = runner.invoke(cli, ["mcp", "install"])
    assert result.exit_code == 0
    config = json.loads((tmp_path / ".mcp.json").read_text())
    assert "other" in config["mcpServers"]
    assert "splunkctl" in config["mcpServers"]
