"""MCP positional values cannot enable global options."""

from unittest.mock import patch

import pytest
from click.testing import CliRunner

from splunkctl.main import cli
from splunkctl.mcp.runner import build_cli_args, exec_cli
from splunkctl.mcp.tools import build_tool_index


@pytest.mark.parametrize(
    ("tool", "params"),
    [
        ("rules_disable", {"name": "--yes"}),
        ("conf_set", {"file": "props", "stanza": "s", "pairs": ["a=1", "b=2"]}),
        ("es_notables_update", {"event_ids": ["--yes", "x"], "comment": "reviewed"}),
    ],
)
def test_positional_separator(tool: str, params: dict[str, object]) -> None:
    args = build_cli_args(build_tool_index(cli)[tool], params)
    assert "--" in args
    with patch("splunkctl.commands.conf.get_client"):
        result = CliRunner().invoke(cli, args)
    assert result.exit_code == 0, result.output
    assert "[DRY RUN]" in result.output


def test_force_json_precedes_separator() -> None:
    with patch("splunkctl.mcp.runner.subprocess.run") as run:
        run.return_value.stdout = b"[]"
        run.return_value.stderr = b""
        run.return_value.returncode = 0
        exec_cli(["search", "run", "--", "index=main"])
    argv = run.call_args.args[0]
    assert argv.index("--json") < argv.index("--")
