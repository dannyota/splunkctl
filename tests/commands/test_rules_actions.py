"""Tests for dry-run validation of required alert-action companion fields."""

from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from splunkctl.main import cli

_PATCH = "splunkctl.commands.rules.get_client"


@patch(_PATCH)
def test_create_email_missing_recipient_warns(mock_gc: MagicMock) -> None:
    result = CliRunner().invoke(
        cli,
        [
            "rules",
            "create",
            "--name",
            "r1",
            "--search",
            "index=main",
            "--actions",
            "email",
        ],
    )
    assert result.exit_code == 0
    assert "action.email.to" in result.output
    mock_gc.assert_not_called()


@patch(_PATCH)
def test_create_email_with_set_recipient_no_warning(mock_gc: MagicMock) -> None:
    result = CliRunner().invoke(
        cli,
        [
            "rules",
            "create",
            "--name",
            "r1",
            "--search",
            "index=main",
            "--actions",
            "email",
            "--set",
            "action.email.to=a@b",
        ],
    )
    assert result.exit_code == 0
    assert "Warning" not in result.output
    mock_gc.assert_not_called()


@patch(_PATCH)
def test_create_webhook_missing_url_warns(mock_gc: MagicMock) -> None:
    result = CliRunner().invoke(
        cli,
        [
            "rules",
            "create",
            "--name",
            "r1",
            "--search",
            "index=main",
            "--actions",
            "webhook",
        ],
    )
    assert result.exit_code == 0
    assert "action.webhook.param.url" in result.output
    mock_gc.assert_not_called()


@patch(_PATCH)
def test_create_unmapped_action_no_warning(mock_gc: MagicMock) -> None:
    result = CliRunner().invoke(
        cli,
        [
            "rules",
            "create",
            "--name",
            "r1",
            "--search",
            "index=main",
            "--actions",
            "lookup",
        ],
    )
    assert result.exit_code == 0
    assert "Warning" not in result.output
    mock_gc.assert_not_called()


@patch(_PATCH)
def test_create_yes_still_warns(mock_gc: MagicMock) -> None:
    """The warning is advisory only — --yes still applies the mutation."""
    svc = MagicMock()
    mock_gc.return_value.service = svc

    result = CliRunner().invoke(
        cli,
        [
            "--yes",
            "rules",
            "create",
            "--name",
            "r1",
            "--search",
            "index=main",
            "--actions",
            "email",
        ],
    )
    assert result.exit_code == 0
    assert "action.email.to" in result.output
    svc.saved_searches.create.assert_called_once()


@patch(_PATCH)
def test_update_email_missing_recipient_warns(mock_gc: MagicMock) -> None:
    ss = MagicMock()
    ss.name = "r1"
    ss.content = {"actions": ""}
    mock_gc.return_value.service.saved_searches.__getitem__.return_value = ss

    result = CliRunner().invoke(cli, ["rules", "update", "r1", "--actions", "email"])
    assert result.exit_code == 0
    assert "action.email.to" in result.output


@patch(_PATCH)
def test_update_email_already_set_server_side_no_warning(mock_gc: MagicMock) -> None:
    ss = MagicMock()
    ss.name = "r1"
    ss.content = {"actions": "email", "action.email.to": "soc@example.com"}
    mock_gc.return_value.service.saved_searches.__getitem__.return_value = ss

    result = CliRunner().invoke(cli, ["rules", "update", "r1", "--actions", "email"])
    assert result.exit_code == 0
    assert "Warning" not in result.output


@patch(_PATCH)
def test_update_no_actions_flag_skips_lookup(mock_gc: MagicMock) -> None:
    """No --actions means nothing to validate — no extra round-trip."""
    result = CliRunner().invoke(cli, ["rules", "update", "r1", "--search", "index=web"])
    assert result.exit_code == 0
    assert "Warning" not in result.output
    mock_gc.assert_not_called()
