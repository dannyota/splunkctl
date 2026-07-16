"""Tests for the MCP server and tool generation."""

import json
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from splunkctl.main import cli
from splunkctl.mcp.tools import (
    build_tool_index,
    direct_commands,
    group_names,
    group_summary,
    group_tools,
    has_subgroups,
    subgroup_names,
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
        if not entry.guarded:
            assert "yes" not in props, f"{entry.name} exposes 'yes'"
        assert "json" not in props, f"{entry.name} exposes 'json'"
        assert "debug" not in props, f"{entry.name} exposes 'debug'"


def test_guarded_schemas_expose_yes() -> None:
    idx = build_tool_index(cli)
    for entry in idx.values():
        props = entry.schema.get("properties", {})
        if entry.guarded:
            assert "yes" in props, f"{entry.name} missing 'yes'"
            assert props["yes"]["type"] == "boolean"
            assert props["yes"]["default"] is False
            assert "yes" not in entry.schema.get("required", [])


def test_schemas_reject_additional_properties() -> None:
    idx = build_tool_index(cli)
    for entry in idx.values():
        assert entry.schema.get("additionalProperties") is False, entry.name


def test_prompt_options_marked_required() -> None:
    import click

    from splunkctl.mcp.tools import _make_entry

    @click.command()
    @click.option("--secret", prompt=True, help="Prompted when absent.")
    def fake(secret: str) -> None:
        """Fake command."""

    entry = _make_entry(fake, ["fake"])
    assert "secret" in entry.schema.get("required", [])


def test_server_reports_splunkctl_version() -> None:
    from splunkctl import __version__
    from splunkctl.mcp.server import create_server

    server = create_server()
    opts = server._mcp_server.create_initialization_options()  # noqa: SLF001
    assert opts.server_version == __version__


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
    from splunkctl.mcp.runner import build_cli_args as _build_cli_args

    idx = build_tool_index(cli)
    entry = idx["search_run"]
    args = _build_cli_args(entry, {"spl": "index=main", "limit": 5})
    assert "--spl" not in args, "positional arg should not get a flag"
    assert "index=main" in args
    assert "--limit" in args


def test_build_cli_args_yes_passed() -> None:
    from splunkctl.mcp.runner import build_cli_args as _build_cli_args

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
    from splunkctl.mcp.runner import build_cli_args as _build_cli_args

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
    from splunkctl.mcp.runner import build_cli_args as _build_cli_args

    idx = build_tool_index(cli)
    entry = idx["rules_export"]
    args = _build_cli_args(entry, {"name": ["r1", "r2"]})
    assert args.count("--name") == 2
    assert "r1" in args
    assert "r2" in args


def test_build_cli_args_json_string_array_coerced() -> None:
    from splunkctl.mcp.runner import build_cli_args as _build_cli_args

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


# --- Soar MCP coverage tests ---


def test_soar_subgroup_names() -> None:
    sg = subgroup_names(cli, "soar")
    assert "containers" in sg
    assert "playbooks" in sg
    assert "actions" in sg
    assert "vault" in sg
    # Direct commands are NOT subgroups
    assert "test" not in sg
    assert "info" not in sg


def test_soar_has_subgroups() -> None:
    assert has_subgroups(cli, "soar")
    assert not has_subgroups(cli, "search")
    assert not has_subgroups(cli, "indexes")


def test_soar_direct_commands() -> None:
    dc = direct_commands(cli, "soar")
    assert "test" in dc
    assert "info" in dc
    assert "health" in dc
    # Subgroups should NOT appear
    assert "containers" not in dc
    assert "playbooks" not in dc


def test_group_tools_soar_subgroup() -> None:
    idx = build_tool_index(cli)
    containers = group_tools(idx, "soar containers")
    assert len(containers) >= 5
    for t in containers:
        assert t.name.startswith("soar_containers_")
    playbooks = group_tools(idx, "soar playbooks")
    assert len(playbooks) >= 5
    for t in playbooks:
        assert t.name.startswith("soar_playbooks_")


def test_group_tools_soar_all_is_large() -> None:
    idx = build_tool_index(cli)
    all_soar = group_tools(idx, "soar")
    assert len(all_soar) > 50, "soar tree should have many tools"


def test_soar_guarded_tools_have_yes() -> None:
    idx = build_tool_index(cli)
    soar_tools = [t for t in idx.values() if t.name.startswith("soar_")]
    guarded = [t for t in soar_tools if t.guarded]
    assert len(guarded) > 15
    for t in guarded:
        props = t.schema.get("properties", {})
        assert "yes" in props, f"{t.name} is guarded but missing 'yes'"
        assert props["yes"]["type"] == "boolean"


def test_soar_tool_index_nested_paths() -> None:
    idx = build_tool_index(cli)
    # Verify deeply nested tools resolve
    assert "soar_playbooks_run" in idx
    assert idx["soar_playbooks_run"].cmd_path == ["soar", "playbooks", "run"]
    assert "soar_containers_create" in idx
    assert "soar_actions_run" in idx


def test_group_summary_includes_soar_subgroups() -> None:
    rows = group_summary(cli)
    soar_row = next(r for r in rows if r["group"] == "soar")
    assert "subgroups" in soar_row
    assert "containers" in soar_row["subgroups"]
    assert "playbooks" in soar_row["subgroups"]
    # Non-nested groups should not have subgroups key
    search_row = next(r for r in rows if r["group"] == "search")
    assert "subgroups" not in search_row


def test_soar_guides_surface_as_resources() -> None:
    from splunkctl.mcp.resources import load_guides

    guides = load_guides()
    slugs = {g["slug"] for g in guides}
    assert "soar" in slugs
    assert "soar-playbooks" in slugs
    assert "soar-actions" in slugs


def test_usage_resolves_nested_soar_path() -> None:
    idx = build_tool_index(cli)
    # Simulate what usage_tool does
    command = "soar playbooks run"
    tool_name = command.strip().replace(" ", "_").replace("-", "_")
    entry = idx.get(tool_name)
    assert entry is not None, f"Failed to resolve: {command}"
    assert entry.name == "soar_playbooks_run"
    assert entry.guarded is True
