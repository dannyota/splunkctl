"""Tests for config init."""

import stat
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from click.testing import CliRunner

from splunkctl import config as cfg_mod
from splunkctl.main import cli
from tests.commands.test_config_cmd import _v2_config


def test_config_init(tmp_path: Path) -> None:
    runner = CliRunner()
    cfg = tmp_path / "config.yaml"
    result = runner.invoke(
        cli,
        ["config", "init", "--path", str(cfg)],
        input="myhost\n8089\nadmin\nsecret\ny\n",
    )
    assert result.exit_code == 0
    assert cfg.exists()
    assert "Config saved" in result.output


def test_config_init_profile_creates_v2(tmp_path: Path) -> None:
    cfg = tmp_path / "config.yaml"
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["config", "init", "--path", str(cfg), "--profile", "uat"],
        input="uathost\n9089\nuatuser\nuatpass\ny\n",
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
        input="uathost\n9089\nuatuser\nuatpass\ny\n",
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
        input="myhost\n8089\nadmin\nsecret\ny\n",
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
            "--verify",
        ],
    )
    assert result.exit_code == 0, result.output
    raw = yaml.safe_load(cfg.read_text())
    assert raw["profiles"]["uat"] == {"host": "uat-host", "port": 9089}
    assert raw["current"] == "uat"
    assert raw["profiles"]["default"]["host"] == "newhost"
    mode = cfg.stat().st_mode
    assert mode & 0o777 == 0o600


def test_config_init_soar_prompts_and_saves(tmp_path: Path) -> None:
    """config init --soar prompts for SOAR fields and saves them."""
    cfg = tmp_path / "config.yaml"
    # Pre-create a SIEM profile so --soar can add to it.
    _v2_config(cfg, {"default": {"host": "siem-host", "port": 8089}})
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["config", "init", "--soar", "--path", str(cfg)],
        input="soar-host\n8443\ntok123\nsoar-admin\nsoarpass\n\n\n",
    )
    assert result.exit_code == 0, result.output
    raw = yaml.safe_load(cfg.read_text())
    soar = raw["profiles"]["default"]["soar"]
    assert soar["host"] == "soar-host"
    assert soar["port"] == 8443
    assert soar["token"] == "tok123"
    assert soar["username"] == "soar-admin"
    assert soar["password"] == "soarpass"
    assert soar["verify"] is True


def test_config_init_soar_with_profile_flag(tmp_path: Path) -> None:
    """config init --soar --profile <name> saves to the right profile."""
    cfg = tmp_path / "config.yaml"
    _v2_config(
        cfg,
        {"lab": {"host": "siem-host"}, "prod": {"host": "prod-siem"}},
        current="lab",
    )
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["config", "init", "--soar", "--path", str(cfg), "--profile", "lab"],
        input="soar-lab\n8443\ntok-lab\n\n\n\n\n",
    )
    assert result.exit_code == 0, result.output
    raw = yaml.safe_load(cfg.read_text())
    assert raw["profiles"]["lab"]["soar"]["host"] == "soar-lab"
    # Verify sibling profile untouched.
    assert "soar" not in raw["profiles"]["prod"]


def test_config_init_soar_preserves_siem_fields(tmp_path: Path) -> None:
    """config init --soar must not clobber existing SIEM fields."""
    cfg = tmp_path / "config.yaml"
    _v2_config(
        cfg,
        {"lab": {"host": "siem-host", "port": 8089, "username": "admin"}},
        current="lab",
    )
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["config", "init", "--soar", "--path", str(cfg)],
        input="soar-host\n8443\ntok\n\n\n\n\n",
    )
    assert result.exit_code == 0, result.output
    raw = yaml.safe_load(cfg.read_text())
    # SIEM fields intact.
    assert raw["profiles"]["lab"]["host"] == "siem-host"
    assert raw["profiles"]["lab"]["port"] == 8089
    # SOAR added.
    assert raw["profiles"]["lab"]["soar"]["host"] == "soar-host"


def test_config_init_verify_defaults_true(tmp_path: Path) -> None:
    """config init with default TLS prompt (Enter=yes) writes verify: true."""
    cfg = tmp_path / "config.yaml"
    runner = CliRunner()
    # Accept all defaults including TLS verification (Enter = yes)
    result = runner.invoke(
        cli,
        ["config", "init", "--path", str(cfg)],
        input="myhost\n8089\nadmin\nsecret\n\n",
    )
    assert result.exit_code == 0, result.output
    raw = yaml.safe_load(cfg.read_text())
    assert raw["verify"] is True


def test_config_init_verify_no_writes_false(tmp_path: Path) -> None:
    """config init answering 'n' to TLS prompt writes verify: false."""
    cfg = tmp_path / "config.yaml"
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["config", "init", "--path", str(cfg)],
        input="myhost\n8089\nadmin\nsecret\nn\n",
    )
    assert result.exit_code == 0, result.output
    raw = yaml.safe_load(cfg.read_text())
    assert raw["verify"] is False


def test_config_init_verify_flag_skips_prompt(tmp_path: Path) -> None:
    """--verify / --no-verify flags skip the interactive TLS prompt."""
    cfg = tmp_path / "config.yaml"
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["config", "init", "--path", str(cfg), "--no-verify"],
        input="myhost\n8089\nadmin\nsecret\n",
    )
    assert result.exit_code == 0, result.output
    raw = yaml.safe_load(cfg.read_text())
    assert raw["verify"] is False


def test_config_init_always_writes_explicit_verify(tmp_path: Path) -> None:
    """Every config init run writes an explicit verify key."""
    cfg = tmp_path / "config.yaml"
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["config", "init", "--path", str(cfg)],
        input="myhost\n8089\nadmin\nsecret\ny\n",
    )
    assert result.exit_code == 0, result.output
    raw = yaml.safe_load(cfg.read_text())
    assert "verify" in raw


@pytest.mark.parametrize("soar", [False, True])
def test_init_honors_global_config(tmp_path: Path, soar: bool) -> None:
    dest = tmp_path / "chosen.yaml"
    args = ["--config", str(dest), "config", "init"]
    if soar:
        args += ["--soar"]
    result = CliRunner().invoke(
        cli,
        args,
        input=(
            "soar\n8443\ntoken\n\n\n\n\n" if soar else "ours\n8089\nadmin\nsecret\ny\n"
        ),
    )
    assert result.exit_code == 0, result.output
    assert dest.exists()
    assert not cfg_mod.DEFAULT_PATH.exists()


def test_init_foreign_default_uses_fallback() -> None:
    cfg_mod.DEFAULT_PATH.parent.mkdir(parents=True)
    cfg_mod.DEFAULT_PATH.write_text("host: bare\ntoken: foreign-secret\n")
    result = CliRunner().invoke(
        cli, ["config", "init"], input="ours\n8089\nadmin\nsecret\ny\n"
    )
    assert result.exit_code == 0, result.output
    assert cfg_mod.FALLBACK_PATH.exists()
    notice = (
        f"Splunk-format config at {cfg_mod.DEFAULT_PATH}; using {cfg_mod.FALLBACK_PATH}"
    )
    assert result.stderr.count(notice) == 1
    assert f"Config saved to {cfg_mod.FALLBACK_PATH}" in result.output
    assert cfg_mod.DEFAULT_PATH.read_text() == "host: bare\ntoken: foreign-secret\n"


@pytest.mark.parametrize("soar", [False, True])
def test_init_foreign_path_refuses_before_prompt(tmp_path: Path, soar: bool) -> None:
    dest = tmp_path / "foreign.yaml"
    dest.write_text("host: bare\ntoken: foreign-secret\n")
    args = ["config", "init", "--path", str(dest), "--web-url", "https://example"]
    if soar:
        args += ["--soar"]
    with patch("splunkctl.auth.detector.probe") as probe:
        result = CliRunner().invoke(cli, args)
    assert result.exit_code == 1
    assert (
        f"Refusing to write Splunk-format config at {dest}. "
        "Choose another file with --path or --config." in result.output
    )
    assert "Host:" not in result.output
    assert "SOAR host:" not in result.output
    probe.assert_not_called()
