"""Tests for apps commands."""

from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from splunkctl.main import cli


def _mock_app(
    name: str,
    *,
    label: str = "",
    version: str = "",
    visible: str = "true",
    disabled: str = "0",
    author: str = "",
    description: str = "",
) -> MagicMock:
    app = MagicMock()
    app.name = name
    app.content = {
        "label": label,
        "version": version,
        "visible": visible,
        "disabled": disabled,
        "author": author,
        "description": description,
    }
    return app


@patch("splunkctl.commands.apps.get_client")
def test_list_apps(mock_gc: MagicMock) -> None:
    mock_svc = MagicMock()
    mock_svc.apps.list.return_value = [
        _mock_app("search", label="Search", version="10.4.0", author="Splunk"),
        _mock_app("launcher", label="Launcher", version="1.0"),
    ]
    mock_gc.return_value.service = mock_svc
    runner = CliRunner()
    result = runner.invoke(cli, ["--json", "apps", "list"])
    assert result.exit_code == 0
    assert "search" in result.output
    assert "Search" in result.output
    assert "launcher" in result.output


@patch("splunkctl.commands.apps.get_client")
def test_list_apps_empty(mock_gc: MagicMock) -> None:
    mock_svc = MagicMock()
    mock_svc.apps.list.return_value = []
    mock_gc.return_value.service = mock_svc
    runner = CliRunner()
    result = runner.invoke(cli, ["--json", "apps", "list"])
    assert result.exit_code == 0
    assert "No apps found" in result.output or result.output.strip() == ""


@patch("splunkctl.commands.apps.get_client")
def test_get_app(mock_gc: MagicMock) -> None:
    mock_svc = MagicMock()
    app = _mock_app(
        "search",
        label="Search & Reporting",
        version="10.4.0",
        author="Splunk",
        description="Search app",
    )
    mock_svc.apps.__getitem__ = MagicMock(return_value=app)
    mock_gc.return_value.service = mock_svc
    runner = CliRunner()
    result = runner.invoke(cli, ["--json", "apps", "get", "search"])
    assert result.exit_code == 0
    assert "search" in result.output
    assert "10.4.0" in result.output


@patch("splunkctl.commands.apps.get_client")
def test_get_app_not_found(mock_gc: MagicMock) -> None:
    mock_svc = MagicMock()
    mock_svc.apps.__getitem__ = MagicMock(side_effect=KeyError("nope"))
    mock_gc.return_value.service = mock_svc
    runner = CliRunner()
    result = runner.invoke(cli, ["--json", "apps", "get", "nope"])
    assert result.exit_code != 0
    assert "not found" in result.output


@patch("splunkctl.commands.apps.get_client")
def test_install_dry_run(mock_gc: MagicMock, tmp_path: MagicMock) -> None:
    pkg = tmp_path / "app.spl"
    pkg.write_text("fake")
    runner = CliRunner()
    result = runner.invoke(
        cli, ["apps", "install", "--name", "myapp", "--path", str(pkg)]
    )
    assert result.exit_code == 0
    assert "[DRY RUN]" in result.output
    mock_gc.assert_not_called()


@patch("splunkctl.commands.apps.get_client")
def test_install_confirmed(mock_gc: MagicMock, tmp_path: MagicMock) -> None:
    pkg = tmp_path / "app.spl"
    pkg.write_text("fake")
    mock_svc = MagicMock()
    mock_gc.return_value.service = mock_svc
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["--yes", "apps", "install", "--name", "myapp", "--path", str(pkg)],
    )
    assert result.exit_code == 0
    assert "Installed" in result.output
    mock_svc.post.assert_called_once()


@patch("splunkctl.commands.apps.get_client")
def test_uninstall_dry_run(mock_gc: MagicMock) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["apps", "uninstall", "myapp"])
    assert result.exit_code == 0
    assert "[DRY RUN]" in result.output
    mock_gc.assert_not_called()


@patch("splunkctl.commands.apps.get_client")
def test_uninstall_confirmed(mock_gc: MagicMock) -> None:
    mock_svc = MagicMock()
    app = _mock_app("myapp")
    mock_svc.apps.__getitem__ = MagicMock(return_value=app)
    mock_gc.return_value.service = mock_svc
    runner = CliRunner()
    result = runner.invoke(cli, ["--yes", "apps", "uninstall", "myapp"])
    assert result.exit_code == 0
    assert "Uninstalled" in result.output
    app.delete.assert_called_once()


@patch("splunkctl.commands.apps.get_client")
def test_uninstall_not_found(mock_gc: MagicMock) -> None:
    mock_svc = MagicMock()
    mock_svc.apps.__getitem__ = MagicMock(side_effect=KeyError("nope"))
    mock_gc.return_value.service = mock_svc
    runner = CliRunner()
    result = runner.invoke(cli, ["--yes", "apps", "uninstall", "nope"])
    assert result.exit_code != 0
    assert "not found" in result.output


@patch("splunkctl.commands.apps.get_client")
def test_update_visible(mock_gc: MagicMock) -> None:
    mock_svc = MagicMock()
    app = _mock_app("myapp")
    mock_svc.apps.__getitem__ = MagicMock(return_value=app)
    mock_gc.return_value.service = mock_svc
    runner = CliRunner()
    result = runner.invoke(cli, ["--yes", "apps", "update", "myapp", "--visible"])
    assert result.exit_code == 0
    assert "Updated" in result.output
    app.update.assert_called_once_with(visible=True)


@patch("splunkctl.commands.apps.get_client")
def test_update_disabled(mock_gc: MagicMock) -> None:
    mock_svc = MagicMock()
    app = _mock_app("myapp")
    mock_svc.apps.__getitem__ = MagicMock(return_value=app)
    mock_gc.return_value.service = mock_svc
    runner = CliRunner()
    result = runner.invoke(cli, ["--yes", "apps", "update", "myapp", "--disabled"])
    assert result.exit_code == 0
    assert "Updated" in result.output
    app.update.assert_called_once_with(disabled=True)


@patch("splunkctl.commands.apps.get_client")
def test_update_no_options(mock_gc: MagicMock) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--yes", "apps", "update", "myapp"])
    assert result.exit_code != 0
    assert "No settings" in result.output


@patch("splunkctl.commands.apps.get_client")
def test_update_dry_run(mock_gc: MagicMock) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["apps", "update", "myapp", "--hidden"])
    assert result.exit_code == 0
    assert "[DRY RUN]" in result.output


@patch("splunkctl.commands.apps.get_client")
def test_update_not_found(mock_gc: MagicMock) -> None:
    mock_svc = MagicMock()
    mock_svc.apps.__getitem__ = MagicMock(side_effect=KeyError("nope"))
    mock_gc.return_value.service = mock_svc
    runner = CliRunner()
    result = runner.invoke(cli, ["--yes", "apps", "update", "nope", "--visible"])
    assert result.exit_code != 0
    assert "not found" in result.output


@patch("splunkctl.commands.apps.get_client")
def test_reload_dry_run(mock_gc: MagicMock) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["apps", "reload"])
    assert result.exit_code == 0
    assert "[DRY RUN]" in result.output
    mock_gc.assert_not_called()


@patch("splunkctl.commands.apps.get_client")
def test_reload_confirmed(mock_gc: MagicMock) -> None:
    mock_svc = MagicMock()
    mock_gc.return_value.service = mock_svc
    runner = CliRunner()
    result = runner.invoke(cli, ["--yes", "apps", "reload"])
    assert result.exit_code == 0
    assert "reloaded" in result.output
    mock_svc.get.assert_called_once_with("/services/apps/local/_reload")
