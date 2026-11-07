"""Write SPL requires explicit confirmation before any dispatch."""

import json
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
    assert result.exit_code == (0 if yes else 1), result.output
    if yes:
        method = "create" if command == "run" else command
        getattr(client.return_value.service.jobs, method).assert_called_once()
    else:
        client.assert_not_called()
        assert json.loads(result.stderr)["error"] == {
            "kind": "confirmation_required",
            "http_status": None,
            "message": "[DRY RUN] SPL contains write command(s): outputlookup. "
            "Pass --yes to run it.",
        }
        assert result.stdout == ""


def test_ingest_refuses_before_siem_or_soar() -> None:
    with (
        patch("splunkctl.commands.soar._ingest_helpers.get_client") as siem,
        patch("splunkctl.commands.soar.ingest.get_soar_client") as soar,
    ):
        result = CliRunner().invoke(
            cli, ["soar", "ingest", "--spl", "index=main | collect index=x"]
        )
    assert result.exit_code == 1, result.output
    siem.assert_not_called()
    soar.assert_not_called()
    assert json.loads(result.stderr)["error"]["kind"] == "confirmation_required"


@pytest.mark.parametrize(
    "flags", [["--json"], ["--format", "json"], ["--format", "table"]]
)
def test_write_refusal_output_modes(flags: list[str]) -> None:
    with patch("splunkctl.commands.search.get_client") as client:
        result = CliRunner().invoke(
            cli, [*flags, "search", "oneshot", "| collect index=x"]
        )
    assert result.exit_code == 1
    assert result.stdout == ""
    client.assert_not_called()
    message = (
        "[DRY RUN] SPL contains write command(s): collect. Pass --yes to run it.\n"
    )
    if flags[-1] == "table":
        assert result.stderr == message
    else:
        assert json.loads(result.stderr)["error"]["kind"] == "confirmation_required"
