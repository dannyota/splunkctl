"""Tests for the first-class alert-action flags on rules create/update.

--email-to/--email-subject/--webhook-url are sugar over --set action.*;
they must integrate with E5's warn_missing_action_fields (satisfy it once
supplied) and add their own advisory when the companion action isn't
enabled via --actions.
"""

from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from splunkctl.main import cli

_PATCH = "splunkctl.commands.rules.get_client"


# --- create: flag -> field mapping ---


@patch(_PATCH)
def test_create_email_to_maps_to_field(mock_gc: MagicMock) -> None:
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
    _, kwargs = svc.saved_searches.create.call_args
    assert kwargs["action.email.to"] == "soc@bank.example"
    assert "Warning" not in result.output


@patch(_PATCH)
def test_create_email_subject_maps_to_field(mock_gc: MagicMock) -> None:
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
            "--email-subject",
            "Suspicious login",
        ],
    )
    assert result.exit_code == 0, result.output
    _, kwargs = svc.saved_searches.create.call_args
    assert kwargs["action.email.subject"] == "Suspicious login"


@patch(_PATCH)
def test_create_webhook_url_maps_to_field(mock_gc: MagicMock) -> None:
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
    _, kwargs = svc.saved_searches.create.call_args
    assert kwargs["action.webhook.param.url"] == "https://hooks.example/x"
    assert "Warning" not in result.output


# --- conflict with --set: usage error, exit 2 ---


def test_create_email_to_conflicts_with_set() -> None:
    result = CliRunner().invoke(
        cli,
        [
            "rules",
            "create",
            "--name",
            "r1",
            "--search",
            "x",
            "--email-to",
            "a@b",
            "--set",
            "action.email.to=c@d",
        ],
    )
    assert result.exit_code == 2
    assert "--email-to conflicts with --set action.email.to" in result.output


def test_create_email_subject_conflicts_with_set() -> None:
    result = CliRunner().invoke(
        cli,
        [
            "rules",
            "create",
            "--name",
            "r1",
            "--search",
            "x",
            "--email-subject",
            "a",
            "--set",
            "action.email.subject=b",
        ],
    )
    assert result.exit_code == 2
    assert "--email-subject conflicts with --set action.email.subject" in result.output


def test_create_webhook_url_conflicts_with_set() -> None:
    result = CliRunner().invoke(
        cli,
        [
            "rules",
            "create",
            "--name",
            "r1",
            "--search",
            "x",
            "--webhook-url",
            "https://a",
            "--set",
            "action.webhook.param.url=https://b",
        ],
    )
    assert result.exit_code == 2
    assert (
        "--webhook-url conflicts with --set action.webhook.param.url" in result.output
    )


def test_update_email_to_conflicts_with_set() -> None:
    result = CliRunner().invoke(
        cli,
        [
            "rules",
            "update",
            "r1",
            "--email-to",
            "a@b",
            "--set",
            "action.email.to=c@d",
        ],
    )
    assert result.exit_code == 2
    assert "--email-to conflicts with --set action.email.to" in result.output


# --- empty-value validation (requirement 5: non-empty only) ---


def test_create_email_to_empty_rejected() -> None:
    result = CliRunner().invoke(
        cli,
        ["rules", "create", "--name", "r1", "--search", "x", "--email-to", ""],
    )
    assert result.exit_code == 2
    assert "--email-to" in result.output
    assert "empty" in result.output


# --- advisory: flag set but the companion action isn't enabled ---


@patch(_PATCH)
def test_create_email_to_without_email_action_warns(mock_gc: MagicMock) -> None:
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
            "--email-to",
            "soc@bank.example",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "not in --actions" in result.output
    assert "email" in result.output
    svc.saved_searches.create.assert_called_once()  # advisory does not block


@patch(_PATCH)
def test_create_webhook_url_without_webhook_action_warns(mock_gc: MagicMock) -> None:
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
            "--webhook-url",
            "https://hooks.example/x",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "not in --actions" in result.output
    assert "webhook" in result.output


@patch(_PATCH)
def test_create_email_to_and_subject_warn_once_per_action(mock_gc: MagicMock) -> None:
    """Both email flags map to the same action — dedup to one warning."""
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
            "--email-to",
            "soc@bank.example",
            "--email-subject",
            "hi",
        ],
    )
    assert result.exit_code == 0, result.output
    assert result.output.count("Warning") == 1


@patch(_PATCH)
def test_create_email_to_with_email_action_no_advisory(mock_gc: MagicMock) -> None:
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
    assert "Warning" not in result.output


# --- E5 integration: missing-field warning suppressed once flag given ---


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


# --- update path ---


def _mock_update_ss(actions: str = "") -> MagicMock:
    ss = MagicMock()
    ss.name = "r1"
    ss.content = {"actions": actions}
    return ss


@patch(_PATCH)
def test_update_email_to_maps_to_field(mock_gc: MagicMock) -> None:
    ss = _mock_update_ss()
    mock_gc.return_value.service.saved_searches.__getitem__.return_value = ss

    result = CliRunner().invoke(
        cli,
        [
            "--yes",
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
    _, kwargs = ss.update.call_args
    assert kwargs["action.email.to"] == "soc@bank.example"
    assert "Warning" not in result.output


@patch(_PATCH)
def test_update_webhook_url_maps_to_field(mock_gc: MagicMock) -> None:
    ss = _mock_update_ss()
    mock_gc.return_value.service.saved_searches.__getitem__.return_value = ss

    result = CliRunner().invoke(
        cli,
        [
            "--yes",
            "rules",
            "update",
            "r1",
            "--actions",
            "webhook",
            "--webhook-url",
            "https://hooks.example/x",
        ],
    )
    assert result.exit_code == 0, result.output
    _, kwargs = ss.update.call_args
    assert kwargs["action.webhook.param.url"] == "https://hooks.example/x"


@patch(_PATCH)
def test_update_email_to_without_email_action_warns(mock_gc: MagicMock) -> None:
    result = CliRunner().invoke(
        cli,
        ["rules", "update", "r1", "--email-to", "soc@bank.example"],
    )
    assert result.exit_code == 0, result.output
    assert "not in --actions" in result.output
    mock_gc.assert_not_called()  # advisory alone stays offline, like other dry runs


@patch(_PATCH)
def test_update_email_to_suppresses_e5_missing_field_warning(
    mock_gc: MagicMock,
) -> None:
    ss = _mock_update_ss()
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
