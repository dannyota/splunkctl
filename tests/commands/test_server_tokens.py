"""Tests for server tokens commands."""

import json
from typing import Any
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from splunkctl.main import cli

_PATCH = "splunkctl.commands.server_tokens.get_client"


def _resp(data: dict[str, Any]) -> MagicMock:
    resp = MagicMock()
    resp.body.read.return_value = json.dumps(data).encode()
    return resp


def _token_entry(
    *,
    name: str = "token_abc",
    user: str = "admin",
    audience: str = "",
    exp: int | None = 1788934111,
    last_used: int = 1788000000,
    status: str = "enabled",
) -> dict[str, Any]:
    # Shape verified on Splunk 10.6.1.1: the entry name is the token id and
    # content has no id or userName.
    claims: dict[str, Any] = {"sub": user, "iss": f"{user} from splunk"}
    if audience:
        claims["aud"] = audience
    if exp is not None:
        claims["exp"] = exp
    return {
        "name": name,
        "content": {
            "claims": claims,
            "headers": {"alg": "HS512", "ttyp": "static", "ver": "v2"},
            "lastUsed": last_used,
            "lastUsedIp": "",
            "status": status,
        },
    }


# --- list ---


@patch(_PATCH)
def test_tokens_list(mock_gc: MagicMock) -> None:
    svc = mock_gc.return_value.service
    svc.get.return_value = _resp({"entry": [_token_entry()]})

    result = CliRunner().invoke(cli, ["--json", "server", "tokens", "list"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data[0]["id"] == "token_abc"
    assert data[0]["user"] == "admin"
    assert data[0]["expires"].startswith("2026-")
    assert data[0]["last_used"].startswith("2026-")
    assert svc.get.call_args[1].get("count") == 0


@patch(_PATCH)
def test_tokens_list_empty(mock_gc: MagicMock) -> None:
    svc = mock_gc.return_value.service
    svc.get.return_value = _resp({"entry": []})

    result = CliRunner().invoke(cli, ["--json", "server", "tokens", "list"])
    assert result.exit_code == 0
    assert result.output.strip() == "[]"


@patch(_PATCH)
def test_tokens_list_filter_user(mock_gc: MagicMock) -> None:
    svc = mock_gc.return_value.service
    svc.get.return_value = _resp({"entry": [_token_entry(user="analyst")]})

    result = CliRunner().invoke(
        cli, ["--json", "server", "tokens", "list", "--user", "analyst"]
    )
    assert result.exit_code == 0
    svc.get.assert_called_once()
    call_kwargs = svc.get.call_args
    assert call_kwargs[1].get("username") == "analyst"
    assert "userName" not in call_kwargs[1]


@patch(_PATCH)
def test_tokens_list_no_expiry(mock_gc: MagicMock) -> None:
    """Token without exp claim shows 'never'."""
    svc = mock_gc.return_value.service
    svc.get.return_value = _resp({"entry": [_token_entry(exp=None)]})

    result = CliRunner().invoke(cli, ["--json", "server", "tokens", "list"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data[0]["expires"] == "never"


@patch(_PATCH)
def test_tokens_list_last_used_zero(mock_gc: MagicMock) -> None:
    """lastUsedTime of 0 renders as 'never'."""
    svc = mock_gc.return_value.service
    svc.get.return_value = _resp({"entry": [_token_entry(last_used=0)]})

    result = CliRunner().invoke(cli, ["--json", "server", "tokens", "list"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data[0]["last_used"] == "never"


@patch(_PATCH)
def test_tokens_list_claims_as_string(mock_gc: MagicMock) -> None:
    """Claims may arrive as a JSON string rather than a dict."""
    entry = _token_entry()
    entry["content"]["claims"] = json.dumps(entry["content"]["claims"])
    svc = mock_gc.return_value.service
    svc.get.return_value = _resp({"entry": [entry]})

    result = CliRunner().invoke(cli, ["--json", "server", "tokens", "list"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data[0]["user"] == "admin"


# --- create ---


@patch(_PATCH)
def test_tokens_create_dry_run(mock_gc: MagicMock) -> None:
    """Without --yes, create shows dry-run and does not call the API."""
    result = CliRunner().invoke(
        cli, ["server", "tokens", "create", "--user", "admin", "--audience", "ci"]
    )
    assert result.exit_code == 0
    assert "[DRY RUN]" in result.stderr
    mock_gc.return_value.service.post.assert_not_called()


@patch(_PATCH)
def test_tokens_create_applies(mock_gc: MagicMock) -> None:
    svc = mock_gc.return_value.service
    svc.post.return_value = _resp(
        {
            "entry": [
                {
                    "content": {
                        "id": "new_token",
                        "token": "eyJra...secret",
                    }
                }
            ]
        }
    )

    result = CliRunner().invoke(
        cli,
        [
            "--yes",
            "--json",
            "server",
            "tokens",
            "create",
            "--user",
            "admin",
            "--audience",
            "ci",
        ],
    )
    assert result.exit_code == 0
    svc.post.assert_called_once()
    assert svc.post.call_args[1].get("audience") == "ci"
    assert "cannot be retrieved again" in result.stderr


@patch(_PATCH)
def test_tokens_create_requires_audience(mock_gc: MagicMock) -> None:
    """Splunk rejects a token without an audience, so the CLI requires one."""
    result = CliRunner().invoke(
        cli, ["--yes", "server", "tokens", "create", "--user", "admin"]
    )
    assert result.exit_code == 2
    assert "--audience" in result.output
    mock_gc.return_value.service.post.assert_not_called()


@patch(_PATCH)
def test_tokens_create_with_audience_and_expiry(mock_gc: MagicMock) -> None:
    svc = mock_gc.return_value.service
    svc.post.return_value = _resp(
        {"entry": [{"content": {"id": "t1", "token": "tok"}}]}
    )

    result = CliRunner().invoke(
        cli,
        [
            "--yes",
            "--json",
            "server",
            "tokens",
            "create",
            "--user",
            "admin",
            "--audience",
            "my-app",
            "--expires-in",
            "30",
        ],
    )
    assert result.exit_code == 0
    call_kwargs = svc.post.call_args
    assert call_kwargs[1].get("audience") == "my-app"
    assert call_kwargs[1].get("expires_on") == "+30d"


# --- revoke ---


@patch(_PATCH)
def test_tokens_revoke_dry_run(mock_gc: MagicMock) -> None:
    result = CliRunner().invoke(cli, ["server", "tokens", "revoke", "token_abc"])
    assert result.exit_code == 0
    assert "[DRY RUN]" in result.stderr
    mock_gc.return_value.service.delete.assert_not_called()


@patch(_PATCH)
def test_tokens_revoke_applies(mock_gc: MagicMock) -> None:
    """Revoke deletes through the owner's path with the id parameter."""
    svc = mock_gc.return_value.service
    svc.get.return_value = _resp(
        {"entry": [_token_entry(name="other"), _token_entry(user="analyst")]}
    )

    result = CliRunner().invoke(
        cli, ["--yes", "server", "tokens", "revoke", "token_abc"]
    )
    assert result.exit_code == 0
    svc.delete.assert_called_once_with(
        "/services/authorization/tokens/analyst", output_mode="json", id="token_abc"
    )
    assert "revoked" in result.stderr


@patch(_PATCH)
def test_tokens_revoke_unknown_id(mock_gc: MagicMock) -> None:
    """Splunk returns 200 for an unknown id, so revoke checks first."""
    svc = mock_gc.return_value.service
    svc.get.return_value = _resp({"entry": [_token_entry(name="other")]})

    result = CliRunner().invoke(
        cli, ["--yes", "--json", "server", "tokens", "revoke", "token_abc"]
    )
    assert result.exit_code == 1
    error = json.loads(result.stderr.strip().splitlines()[-1])
    assert error["error"]["kind"] == "not_found"
    svc.delete.assert_not_called()
