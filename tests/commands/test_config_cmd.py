"""Tests for config commands."""

import json
import stat
from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml
from click.testing import CliRunner

from splunkctl.main import cli


def test_config_init(tmp_path: Path) -> None:
    runner = CliRunner()
    cfg = tmp_path / "config.yaml"
    result = runner.invoke(
        cli,
        ["config", "init", "--path", str(cfg)],
        input="myhost\n8089\nadmin\nsecret\n",
    )
    assert result.exit_code == 0
    assert cfg.exists()
    assert "Config saved" in result.output


def test_config_show() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--json", "config", "show"])
    assert result.exit_code == 0
    assert "host" in result.output


def test_config_show_redacts_password(tmp_path: Path) -> None:
    cfg = tmp_path / "config.yaml"
    cfg.write_text("host: h\npassword: secret123\n")
    runner = CliRunner()
    result = runner.invoke(cli, ["--json", "--config", str(cfg), "config", "show"])
    assert result.exit_code == 0
    assert "secret123" not in result.output


@patch("splunkctl.commands.config_cmd.SplunkClient")
def test_config_test_success(mock_cls: MagicMock) -> None:
    mock_svc = MagicMock()
    mock_svc.service.info = {"serverName": "test-srv", "version": "10.4.0"}
    mock_cls.return_value = mock_svc
    runner = CliRunner()
    result = runner.invoke(cli, ["config", "test"])
    assert result.exit_code == 0
    assert "OK" in result.output


@patch("splunkctl.commands.config_cmd.SplunkClient")
def test_config_test_failure(mock_cls: MagicMock) -> None:
    mock_cls.return_value.service = property(
        lambda self: (_ for _ in ()).throw(ConnectionError("refused"))
    )
    mock_cls.side_effect = None
    mock_instance = MagicMock()
    type(mock_instance).service = property(
        lambda self: (_ for _ in ()).throw(ConnectionError("refused"))
    )
    mock_cls.return_value = mock_instance
    runner = CliRunner()
    result = runner.invoke(cli, ["config", "test"])
    assert result.exit_code != 0


@patch("splunkctl.commands.config_cmd.SplunkClient")
def test_config_test_unreachable_host_maps_to_connection_envelope(
    mock_cls: MagicMock,
) -> None:
    """`config test --json` against an unreachable host classifies like any
    other command — same taxonomy as _CLI.invoke, not a bare fallback.

    stderr also carries the "Connecting to ..." advisory line printed
    before the connectivity check, so the envelope is parsed from the
    last line, same as the SKILL.md jq recipe does.
    """
    mock_cls.side_effect = ConnectionRefusedError("Connection refused")
    runner = CliRunner()
    result = runner.invoke(cli, ["--json", "config", "test"])
    assert result.exit_code == 1
    last_line = result.stderr.strip().splitlines()[-1]
    err = json.loads(last_line)["error"]
    assert err["kind"] == "connection"


# --- Profiles (schema v2) ---


def _v2_config(
    path: Path, profiles: dict[str, object], current: str | None = None
) -> None:
    raw: dict[str, object] = {"profiles": profiles}
    if current is not None:
        raw["current"] = current
    path.write_text(yaml.dump(raw, sort_keys=False))


def test_config_use_switches_current(tmp_path: Path) -> None:
    cfg = tmp_path / "config.yaml"
    _v2_config(cfg, {"dev": {"host": "dev-host"}, "uat": {"host": "uat-host"}})
    runner = CliRunner()
    result = runner.invoke(cli, ["--config", str(cfg), "config", "use", "uat"])
    assert result.exit_code == 0
    assert yaml.safe_load(cfg.read_text())["current"] == "uat"


def test_config_use_not_found_errors_with_envelope(tmp_path: Path) -> None:
    cfg = tmp_path / "config.yaml"
    _v2_config(cfg, {"dev": {"host": "dev-host"}})
    runner = CliRunner()
    result = runner.invoke(
        cli, ["--json", "--config", str(cfg), "config", "use", "uat"]
    )
    assert result.exit_code == 1
    err = json.loads(result.stderr)["error"]
    assert err["kind"] == "not_found"


def test_config_use_does_not_test_connectivity(tmp_path: Path) -> None:
    cfg = tmp_path / "config.yaml"
    _v2_config(cfg, {"dev": {"host": "dev-host"}, "uat": {"host": "uat-host"}})
    runner = CliRunner()
    with patch("splunklib.client.connect") as mock_connect:
        mock_connect.side_effect = AssertionError("must not connect")
        result = runner.invoke(cli, ["--config", str(cfg), "config", "use", "uat"])
    assert result.exit_code == 0, result.output
    mock_connect.assert_not_called()


def test_config_show_active_profile_and_other_profiles(tmp_path: Path) -> None:
    cfg = tmp_path / "config.yaml"
    _v2_config(
        cfg,
        {"dev": {"host": "dev-host"}, "uat": {"host": "uat-host"}},
        current="uat",
    )
    runner = CliRunner()
    result = runner.invoke(cli, ["--json", "--config", str(cfg), "config", "show"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)[0]
    assert data["profile"] == "uat"
    assert data["host"] == "uat-host"
    assert "Other profiles: dev" in result.stderr


def test_config_show_explicit_profile_flag(tmp_path: Path) -> None:
    cfg = tmp_path / "config.yaml"
    _v2_config(
        cfg,
        {"dev": {"host": "dev-host"}, "uat": {"host": "uat-host"}},
        current="uat",
    )
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["--json", "--config", str(cfg), "--profile", "dev", "config", "show"],
    )
    assert result.exit_code == 0
    data = json.loads(result.stdout)[0]
    assert data["profile"] == "dev"
    assert data["host"] == "dev-host"
    assert "Other profiles" not in result.stderr


def test_config_show_legacy_file_presents_as_default(tmp_path: Path) -> None:
    cfg = tmp_path / "config.yaml"
    cfg.write_text("host: legacy-host\n")
    runner = CliRunner()
    result = runner.invoke(cli, ["--json", "--config", str(cfg), "config", "show"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)[0]
    assert data["profile"] == "default"
    assert data["host"] == "legacy-host"


def test_config_init_profile_creates_v2(tmp_path: Path) -> None:
    cfg = tmp_path / "config.yaml"
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["config", "init", "--path", str(cfg), "--profile", "uat"],
        input="uathost\n9089\nuatuser\nuatpass\n",
    )
    assert result.exit_code == 0
    raw = yaml.safe_load(cfg.read_text())
    assert raw["profiles"]["uat"]["host"] == "uathost"
    assert "default" not in raw["profiles"]


def test_config_init_profile_upgrades_legacy_preserving_default_and_perms(
    tmp_path: Path,
) -> None:
    cfg = tmp_path / "config.yaml"
    cfg.write_text(yaml.dump({"host": "legacy-host", "port": 8089}))
    cfg.chmod(stat.S_IRUSR | stat.S_IWUSR)
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["config", "init", "--path", str(cfg), "--profile", "uat"],
        input="uathost\n9089\nuatuser\nuatpass\n",
    )
    assert result.exit_code == 0
    raw = yaml.safe_load(cfg.read_text())
    assert raw["profiles"]["default"]["host"] == "legacy-host"
    assert raw["profiles"]["uat"]["host"] == "uathost"
    mode = cfg.stat().st_mode
    assert mode & 0o777 == 0o600


def test_config_init_bare_still_writes_flat_file(tmp_path: Path) -> None:
    """Bare `config init` keeps writing the unchanged legacy shape."""
    cfg = tmp_path / "config.yaml"
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["config", "init", "--path", str(cfg)],
        input="myhost\n8089\nadmin\nsecret\n",
    )
    assert result.exit_code == 0
    raw = yaml.safe_load(cfg.read_text())
    assert "profiles" not in raw
    assert raw["host"] == "myhost"


def test_config_init_bare_never_clobbers_existing_profiles(tmp_path: Path) -> None:
    """Bare `config init` against a v2 file must fold into 'default', not
    overwrite the whole file and destroy sibling profiles."""
    cfg = tmp_path / "config.yaml"
    _v2_config(
        cfg,
        {
            "default": {"host": "old-default-host"},
            "uat": {"host": "uat-host", "port": 9089},
        },
        current="uat",
    )
    cfg.chmod(stat.S_IRUSR | stat.S_IWUSR)
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "config",
            "init",
            "--path",
            str(cfg),
            "--host",
            "newhost",
            "--port",
            "8089",
            "--username",
            "admin",
            "--password",
            "secret",
        ],
    )
    assert result.exit_code == 0, result.output
    raw = yaml.safe_load(cfg.read_text())
    assert raw["profiles"]["uat"] == {"host": "uat-host", "port": 9089}
    assert raw["current"] == "uat"
    assert raw["profiles"]["default"]["host"] == "newhost"
    mode = cfg.stat().st_mode
    assert mode & 0o777 == 0o600


def test_global_profile_flag_selects_profile_for_read_commands(
    tmp_path: Path,
) -> None:
    """--profile changes which profile's config get_client resolves."""
    cfg = tmp_path / "config.yaml"
    _v2_config(
        cfg,
        {"dev": {"host": "dev-host"}, "prod": {"host": "prod-host"}},
        current="dev",
    )
    runner = CliRunner()
    with patch("splunklib.client.connect") as mock_connect:
        mock_connect.return_value = MagicMock()
        runner.invoke(
            cli,
            ["--config", str(cfg), "--profile", "prod", "config", "test"],
        )
    call_kwargs = mock_connect.call_args.kwargs
    assert call_kwargs["host"] == "prod-host"
