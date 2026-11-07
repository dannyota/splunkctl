"""Global options must never consume leaf argument values."""

from unittest.mock import patch

import pytest
from click.testing import CliRunner

from splunkctl.main import cli


@pytest.mark.parametrize(
    "args",
    [
        ["rules", "disable", "--", "--yes"],
        ["rules", "update", "X", "--description", "--yes"],
        ["rules", "update", "X", "--description", "--json"],
        ["rules", "update", "X", "--description", "key=--yes"],
    ],
)
def test_leaf_values_remain_dry_run(args: list[str]) -> None:
    with patch("splunkctl.commands.rules.get_client") as client:
        result = CliRunner().invoke(cli, args)
    assert result.exit_code == 0, result.output
    assert "[DRY RUN]" in result.output
    client.assert_not_called()
