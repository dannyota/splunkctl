"""E5 integration tests for alert-action flags on rules create/update.

Verify that first-class action flags suppress warn_missing_action_fields when
the required companion field is provided.
"""

from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from splunkctl.main import cli

_PATCH = "splunkctl.commands.rules.get_client"


@patch(_PATCH)
def test_create_email_to_suppresses_e5_missing_field_warning(
    mock_gc: MagicMock,
) -> None:
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
            "--email-to",
            "soc@bank.example",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "requires action.email.to" not in result.output


@patch(_PATCH)
def test_create_webhook_url_suppresses_e5_missing_field_warning(
    mock_gc: MagicMock,
) -> None:
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
            "webhook",
            "--webhook-url",
            "https://hooks.example/x",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "requires action.webhook.param.url" not in result.output


@patch(_PATCH)
def test_create_email_action_without_email_to_still_warns_e5(
    mock_gc: MagicMock,
) -> None:
    """Sanity check: without the flag, E5's own warning is untouched."""
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
    assert "requires action.email.to" in result.output
    mock_gc.assert_not_called()


@patch(_PATCH)
def test_update_email_to_suppresses_e5_missing_field_warning(
    mock_gc: MagicMock,
) -> None:
    ss = MagicMock()
    ss.name = "r1"
    ss.content = {"actions": ""}
    mock_gc.return_value.service.saved_searches.__getitem__.return_value = ss

    result = CliRunner().invoke(
        cli,
        [
            "rules",
            "update",
            "r1",
            "--actions",
            "email",
            "--email-to",
            "soc@bank.example",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "requires action.email.to" not in result.output
