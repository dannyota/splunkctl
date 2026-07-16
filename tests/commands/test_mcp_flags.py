"""MCP flag-mapping tests — schema names vs real CLI flags, run guard.

Regression coverage for the live-found bugs: renamed Click options
(``--severity`` stored as ``severity_override``) broke typed-tool
invocation; ``--yes`` inside a raw ``run`` command string bypassed the
MCP guard; binary output (playbook export) crashed the result path.
"""

import asyncio
from unittest.mock import patch

from splunkctl.main import cli
from splunkctl.mcp.runner import _decode_stream, build_cli_args
from splunkctl.mcp.server import create_server
from splunkctl.mcp.tools import build_tool_index, leaf_count

IDX = build_tool_index(cli)


def test_renamed_option_maps_to_real_flag() -> None:
    """soar ingest's renamed options must invoke their real CLI flags."""
    entry = IDX["soar_ingest"]
    args = build_cli_args(
        entry,
        {
            "severity_override": "high",
            "map_overrides": ["a=b"],
            "container_name_tmpl": "t",
        },
    )
    assert "--severity" in args
    assert "--map" in args
    assert "--container-name" in args
    assert "--severity-override" not in args
    assert "--map-overrides" not in args
    assert "--container-name-tmpl" not in args


def test_trailing_underscore_param_normalized() -> None:
    """wait_ (keyword-avoidance) surfaces as wait, invokes --wait."""
    entry = IDX["soar_playbooks_run"]
    props = entry.schema["properties"]
    assert "wait" in props
    assert "wait_" not in props
    args = build_cli_args(entry, {"playbook": "p", "container_id": 1, "wait": True})
    assert "--wait" in args
    assert "--container" in args


def test_leaf_options_shadowing_global_names_survive() -> None:
    """--field (param name 'fields') and export --out stay in schemas.

    Globals live on the root group only — a leaf option that happens to
    share a global's name must not be stripped.
    """
    assert "fields" in IDX["soar_containers_create"].schema["properties"]
    assert "out" in IDX["soar_playbooks_export"].schema["properties"]
    args = build_cli_args(IDX["soar_containers_create"], {"fields": ["k=v"]})
    assert args[-2:] == ["--field", "k=v"]


def test_negatable_flag_false_emits_secondary_opt() -> None:
    """--force/--no-force: explicit false sends --no-force."""
    entry = IDX["soar_playbooks_import"]
    args = build_cli_args(entry, {"path": "./pb", "force": False})
    assert "--no-force" in args
    args_true = build_cli_args(entry, {"path": "./pb", "force": True})
    assert "--force" in args_true


def test_leaf_count_recurses_nested_groups() -> None:
    """Group counts match the number of typed tools a focus would load."""
    soar = cli.commands["soar"]
    cases = soar.commands["cases"]  # type: ignore[attr-defined]
    from splunkctl.mcp.tools import group_tools

    assert leaf_count(cases) == len(group_tools(IDX, "soar cases"))


def test_decode_stream_binary_safe() -> None:
    """Binary payloads (tgz export) yield a hint, not a decode crash."""
    assert _decode_stream(b"hello") == "hello"
    blob = b"\x1f\x8b\x08\x00" + bytes(range(256))
    result = _decode_stream(blob)
    assert "binary output" in result
    assert "--out" in result


def test_run_tool_rejects_yes_in_command_string() -> None:
    """--yes inside the raw command must not bypass the MCP guard.

    Rejected loudly (never executed, never silently stripped): after
    shlex a quoted option VALUE of '-y' is indistinguishable from the
    flag, so stripping would corrupt legitimate commands.
    """
    server = create_server()
    run_tool = server._tool_manager._tools["run"].fn

    for cmd in (
        "soar containers delete 1 --yes",
        "soar containers delete 1 -y",
        'soar containers delete 1 "--yes"',  # quoting must not sneak past
    ):
        with patch("splunkctl.mcp.server._exec_cli") as mock_exec:
            result = asyncio.run(run_tool(command=cmd, yes=False))
        mock_exec.assert_not_called()
        assert "yes=true" in result  # the error tells the agent how


def test_run_tool_yes_param_appends_flag() -> None:
    """yes=true is the one sanctioned way to apply through run."""
    server = create_server()
    run_tool = server._tool_manager._tools["run"].fn

    with patch("splunkctl.mcp.server._exec_cli") as mock_exec:
        mock_exec.return_value = "applied"
        asyncio.run(run_tool(command="soar containers delete 1", yes=True))
    tokens = mock_exec.call_args[0][0]
    assert tokens.count("--yes") == 1
    assert tokens[-1] == "--yes"


def test_run_tool_quoted_yes_value_never_eaten() -> None:
    """A quoted value that merely LOOKS like the yes flag is refused, not
    silently deleted — the old strip turned ``--content "-y"`` into a
    malformed command (argument shift / wrong write)."""
    server = create_server()
    run_tool = server._tool_manager._tools["run"].fn

    with patch("splunkctl.mcp.server._exec_cli") as mock_exec:
        result = asyncio.run(
            run_tool(command='soar containers add-note 5 --content "-y"', yes=True)
        )
    mock_exec.assert_not_called()
    assert "typed tool" in result  # points at the lossless alternative
