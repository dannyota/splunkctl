"""Tests for user and role management commands."""

from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from splunkctl.main import cli

_PATCH = "splunkctl.commands.users.get_client"


def _mock_user(
    name: str,
    *,
    realname: str = "",
    email: str = "",
    roles: list[str] | None = None,
    default_app: str = "",
    user_type: str = "",
) -> MagicMock:
    user = MagicMock()
    user.name = name
    user.content = {
        "realname": realname,
        "email": email,
        "roles": roles or ["user"],
        "defaultApp": default_app,
        "type": user_type,
        "tz": "",
        "lang": "en-US",
        "last_successful_login": "1719619200",
        "locked-out": "false",
        "capabilities": ["search", "list_inputs"],
    }
    return user


def _mock_role(
    name: str,
    *,
    imported_roles: list[str] | None = None,
    capabilities: list[str] | None = None,
    default_app: str = "",
) -> MagicMock:
    role = MagicMock()
    role.name = name
    role.content = {
        "imported_roles": imported_roles or [],
        "capabilities": capabilities or [],
        "defaultApp": default_app,
    }
    return role


@patch(_PATCH)
def test_list_users(mock_gc: MagicMock) -> None:
    mock_gc.return_value.service.users.list.return_value = [
        _mock_user("admin", realname="Admin", roles=["admin"], user_type="Splunk"),
        _mock_user("analyst", email="a@b.com", roles=["user", "power"]),
    ]
    runner = CliRunner()
    result = runner.invoke(cli, ["--json", "users", "list"])
    assert result.exit_code == 0
    assert "admin" in result.output
    assert "analyst" in result.output
    assert "a@b.com" in result.output


@patch(_PATCH)
def test_list_users_empty(mock_gc: MagicMock) -> None:
    mock_gc.return_value.service.users.list.return_value = []
    runner = CliRunner()
    result = runner.invoke(cli, ["--json", "users", "list"])
    assert result.exit_code == 0


@patch(_PATCH)
def test_get_user(mock_gc: MagicMock) -> None:
    mock_gc.return_value.service.users.__getitem__.return_value = _mock_user(
        "admin", realname="Admin User", roles=["admin", "power"]
    )
    runner = CliRunner()
    result = runner.invoke(cli, ["--json", "users", "get", "admin"])
    assert result.exit_code == 0
    assert "Admin User" in result.output
    assert "admin, power" in result.output
    assert "last_successful_login" in result.output
    assert "capabilities" in result.output


@patch(_PATCH)
def test_get_user_not_found(mock_gc: MagicMock) -> None:
    mock_gc.return_value.service.users.__getitem__.side_effect = KeyError("nope")
    runner = CliRunner()
    result = runner.invoke(cli, ["users", "get", "nope"])
    assert result.exit_code != 0


@patch(_PATCH)
def test_list_roles(mock_gc: MagicMock) -> None:
    mock_gc.return_value.service.roles.list.return_value = [
        _mock_role("admin", capabilities=["admin_all_objects", "edit_user"]),
        _mock_role("user", imported_roles=["power"], capabilities=["search"]),
    ]
    runner = CliRunner()
    result = runner.invoke(cli, ["--json", "users", "roles"])
    assert result.exit_code == 0
    assert "admin" in result.output
    assert "search" in result.output


@patch(_PATCH)
def test_roles_truncated_capabilities(mock_gc: MagicMock) -> None:
    caps = [f"cap_{i}" for i in range(10)]
    mock_gc.return_value.service.roles.list.return_value = [
        _mock_role("big_role", capabilities=caps),
    ]
    runner = CliRunner()
    # machine-readable output carries the full list
    result = runner.invoke(cli, ["--json", "users", "roles"])
    assert result.exit_code == 0
    assert "more)" not in result.output
    assert "cap_9" in result.output
    # table output truncates for readability
    result = runner.invoke(cli, ["--format", "table", "users", "roles"])
    assert result.exit_code == 0
    assert "+5 more" in result.output


@patch(_PATCH)
def test_create_user_dry_run(mock_gc: MagicMock) -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "users",
            "create",
            "--name",
            "newuser",
            "--password",
            "s3cret",
            "--roles",
            "user,power",
        ],
    )
    assert result.exit_code == 0
    assert "DRY RUN" in result.output
    mock_gc.return_value.service.users.create.assert_not_called()


@patch(_PATCH)
def test_create_user_confirmed(mock_gc: MagicMock) -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "--yes",
            "users",
            "create",
            "--name",
            "newuser",
            "--password",
            "s3cret",
            "--roles",
            "user",
            "--email",
            "new@test.com",
            "--realname",
            "New User",
        ],
    )
    assert result.exit_code == 0
    assert "Created user" in result.output
    mock_gc.return_value.service.users.create.assert_called_once_with(
        "newuser",
        password="s3cret",  # noqa: S106
        roles=["user"],
        email="new@test.com",
        realname="New User",
    )


@patch(_PATCH)
def test_create_user_failure(mock_gc: MagicMock) -> None:
    mock_gc.return_value.service.users.create.side_effect = Exception("conflict")
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "--yes",
            "users",
            "create",
            "--name",
            "dup",
            "--password",
            "x",
            "--roles",
            "user",
        ],
    )
    assert result.exit_code != 0


@patch(_PATCH)
def test_update_user_dry_run(mock_gc: MagicMock) -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["users", "update", "admin", "--roles", "admin,power"],
    )
    assert result.exit_code == 0
    assert "DRY RUN" in result.output


@patch(_PATCH)
def test_update_user_confirmed(mock_gc: MagicMock) -> None:
    mock_user = _mock_user("admin")
    mock_gc.return_value.service.users.__getitem__.return_value = mock_user
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "--yes",
            "users",
            "update",
            "admin",
            "--email",
            "new@test.com",
            "--default-app",
            "search",
        ],
    )
    assert result.exit_code == 0
    assert "Updated user" in result.output
    mock_user.update.assert_called_once_with(email="new@test.com", defaultApp="search")
    mock_user.refresh.assert_called_once()


@patch(_PATCH)
def test_update_user_no_fields(mock_gc: MagicMock) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--yes", "users", "update", "admin"])
    assert result.exit_code != 0


@patch(_PATCH)
def test_update_user_not_found(mock_gc: MagicMock) -> None:
    mock_gc.return_value.service.users.__getitem__.side_effect = KeyError("nope")
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["--yes", "users", "update", "nope", "--email", "x@y.com"],
    )
    assert result.exit_code != 0


@patch(_PATCH)
def test_delete_user_dry_run(mock_gc: MagicMock) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["users", "delete", "baduser"])
    assert result.exit_code == 0
    assert "DRY RUN" in result.output


@patch(_PATCH)
def test_delete_user_confirmed(mock_gc: MagicMock) -> None:
    mock_user = _mock_user("baduser")
    mock_gc.return_value.service.users.__getitem__.return_value = mock_user
    runner = CliRunner()
    result = runner.invoke(cli, ["--yes", "users", "delete", "baduser"])
    assert result.exit_code == 0
    assert "Deleted user" in result.output
    mock_user.delete.assert_called_once()


@patch(_PATCH)
def test_delete_user_not_found(mock_gc: MagicMock) -> None:
    mock_gc.return_value.service.users.__getitem__.side_effect = KeyError("nope")
    runner = CliRunner()
    result = runner.invoke(cli, ["--yes", "users", "delete", "nope"])
    assert result.exit_code != 0


@patch(_PATCH)
def test_get_user_json_full_capabilities(mock_gc: MagicMock) -> None:
    caps = [f"cap_{i}" for i in range(8)]
    user = MagicMock()
    user.name = "analyst"
    user.content = {"roles": ["user"], "capabilities": caps}
    mock_gc.return_value.service.users.__getitem__.return_value = user

    result = CliRunner().invoke(cli, ["--json", "users", "get", "analyst"])
    assert result.exit_code == 0
    for cap in caps:
        assert cap in result.output
    assert "more)" not in result.output


@patch(_PATCH)
def test_get_user_table_truncates(mock_gc: MagicMock) -> None:
    caps = [f"cap_{i}" for i in range(8)]
    user = MagicMock()
    user.name = "analyst"
    user.content = {"roles": ["user"], "capabilities": caps}
    mock_gc.return_value.service.users.__getitem__.return_value = user

    result = CliRunner().invoke(cli, ["--format", "table", "users", "get", "analyst"])
    assert result.exit_code == 0
    assert "(+3 more)" in result.output
    assert "cap_7" not in result.output
