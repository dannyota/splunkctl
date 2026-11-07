"""Write SPL requires explicit confirmation before any dispatch."""

from unittest.mock import patch

import pytest
from click.testing import CliRunner

from splunkctl.main import cli


@pytest.mark.parametrize("command", ["run", "export", "oneshot"])
@pytest.mark.parametrize("yes", [False, True])
def test_write_search_guard(command: str, yes: bool) -> None:
    args = ["search", command, "index=main | outputlookup x"]
    if yes:
        args.insert(0, "--yes")
    if command == "run":
        args.append("--detach")
    with (
        patch("splunkctl.commands.search.get_client") as client,
        patch("splunkctl.commands.search.read_results", return_value=[]),
    ):
        client.return_value.service.jobs.create.return_value.sid = "123"
        result = CliRunner().invoke(cli, args)
    assert result.exit_code == 0, result.output
    if yes:
        method = "create" if command == "run" else command
        getattr(client.return_value.service.jobs, method).assert_called_once()
    else:
        client.assert_not_called()
        assert (
            "[DRY RUN] SPL contains write command(s): outputlookup. "
            "Pass --yes to run it."
        ) in result.stderr


def test_ingest_refuses_before_siem_or_soar() -> None:
    with (
        patch("splunkctl.commands.soar._ingest_helpers.get_client") as siem,
        patch("splunkctl.commands.soar.ingest.get_soar_client") as soar,
    ):
        result = CliRunner().invoke(
            cli, ["soar", "ingest", "--spl", "index=main | collect index=x"]
        )
    assert result.exit_code == 0, result.output
    siem.assert_not_called()
    soar.assert_not_called()
    assert "SPL contains write command(s): collect" in result.stderr
