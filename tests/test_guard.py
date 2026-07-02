"""Tests for splunkctl.guard."""

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import click
import pytest
import yaml
from click.testing import CliRunner

from splunkctl import config as cfg_mod
from splunkctl import guard


def _cmd_ctx(ctx: click.Context, *, dry_run: bool, config_path: Path) -> None:
    ctx.ensure_object(dict)
    ctx.obj["dry_run"] = dry_run
    ctx.obj["config"] = str(config_path)


def test_dry_run_blocks_and_previews(tmp_path: Path) -> None:
    runner = CliRunner()

    @click.command()
    @click.pass_context
    def cmd(ctx: click.Context) -> None:
        _cmd_ctx(ctx, dry_run=True, config_path=tmp_path / "config.yaml")
        ok = guard.check(ctx, "Delete index 'main'", details="3.2 GB will be freed")
        click.echo(f"proceed={ok}")

    result = runner.invoke(cmd)
    assert "proceed=False" in result.output
    assert "[DRY RUN]" in result.stderr
    assert "3.2 GB" in result.stderr
    assert "--yes" in result.stderr


def test_yes_flag_allows_mutation(tmp_path: Path) -> None:
    runner = CliRunner()

    @click.command()
    @click.pass_context
    def cmd(ctx: click.Context) -> None:
        _cmd_ctx(ctx, dry_run=False, config_path=tmp_path / "config.yaml")
        ok = guard.check(ctx, "Delete index 'main'")
        click.echo(f"proceed={ok}")

    result = runner.invoke(cmd)
    assert "proceed=True" in result.output
    assert "[DRY RUN]" not in result.stderr


# --- Guard banner: profile/host provenance (bank-safety contract) ---


def _write_v2(path: Path, profiles: dict[str, Any], current: str | None = None) -> None:
    raw: dict[str, Any] = {"profiles": profiles}
    if current is not None:
        raw["current"] = current
    path.write_text(yaml.dump(raw, sort_keys=False))


def test_dry_run_banner_shows_profile_and_host(tmp_path: Path) -> None:
    cfg_path = tmp_path / "config.yaml"
    _write_v2(cfg_path, {"uat": {"host": "localhost", "port": 8089}}, current="uat")
    runner = CliRunner()

    @click.command()
    @click.pass_context
    def cmd(ctx: click.Context) -> None:
        _cmd_ctx(ctx, dry_run=True, config_path=cfg_path)
        guard.check(ctx, "Disable saved search 'X'")

    result = runner.invoke(cmd)
    assert "[DRY RUN]" in result.stderr
    assert "(profile: uat @ localhost:8089)" in result.stderr


def test_yes_confirmation_shows_profile_and_host(tmp_path: Path) -> None:
    cfg_path = tmp_path / "config.yaml"
    _write_v2(cfg_path, {"uat": {"host": "localhost", "port": 8089}}, current="uat")
    runner = CliRunner()

    @click.command()
    @click.pass_context
    def cmd(ctx: click.Context) -> None:
        _cmd_ctx(ctx, dry_run=False, config_path=cfg_path)
        guard.check(ctx, "Disable saved search 'X'")

    result = runner.invoke(cmd)
    assert "(profile: uat @ localhost:8089)" in result.stderr


def test_banner_shows_explicit_profile_flag_over_current(tmp_path: Path) -> None:
    cfg_path = tmp_path / "config.yaml"
    _write_v2(
        cfg_path,
        {"uat": {"host": "uat-host"}, "prod": {"host": "prod-host"}},
        current="uat",
    )
    runner = CliRunner()

    @click.command()
    @click.pass_context
    def cmd(ctx: click.Context) -> None:
        _cmd_ctx(ctx, dry_run=True, config_path=cfg_path)
        ctx.obj["profile"] = "prod"
        guard.check(ctx, "Delete index 'main'")

    result = runner.invoke(cmd)
    assert "(profile: prod @ prod-host:8089)" in result.stderr


def test_banner_shows_env_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg_path = tmp_path / "config.yaml"
    _write_v2(cfg_path, {"uat": {"host": "uat-host"}}, current="uat")
    monkeypatch.setenv("SPLUNK_HOST", "env-host")
    runner = CliRunner()

    @click.command()
    @click.pass_context
    def cmd(ctx: click.Context) -> None:
        _cmd_ctx(ctx, dry_run=True, config_path=cfg_path)
        guard.check(ctx, "Delete index 'main'")

    result = runner.invoke(cmd)
    assert "(env @ env-host:8089)" in result.stderr


def test_banner_shows_flags_source(tmp_path: Path) -> None:
    cfg_path = tmp_path / "config.yaml"
    _write_v2(cfg_path, {"uat": {"host": "uat-host"}}, current="uat")

    ctx = click.Context(click.Command("x"))
    ctx.ensure_object(dict)
    ctx.obj["config"] = str(cfg_path)

    tag = guard.banner(ctx, overrides={"host": "flag-host"})
    assert tag == "(flags @ flag-host:8089)"


def test_banner_no_config_file_uses_builtin_defaults(tmp_path: Path) -> None:
    runner = CliRunner()

    @click.command()
    @click.pass_context
    def cmd(ctx: click.Context) -> None:
        _cmd_ctx(ctx, dry_run=True, config_path=tmp_path / "nonexistent.yaml")
        guard.check(ctx, "Delete index 'main'")

    result = runner.invoke(cmd)
    assert "(profile: default @ localhost:8089)" in result.stderr


# --- No-network guarantee ---


@patch("splunklib.client.connect")
def test_banner_never_triggers_network(mock_connect: MagicMock, tmp_path: Path) -> None:
    """Building the banner must never dial out — lazy auth is non-negotiable."""
    mock_connect.side_effect = AssertionError("banner must not connect")
    cfg_path = tmp_path / "config.yaml"
    _write_v2(cfg_path, {"uat": {"host": "uat-host"}}, current="uat")
    runner = CliRunner()

    @click.command()
    @click.pass_context
    def cmd(ctx: click.Context) -> None:
        _cmd_ctx(ctx, dry_run=True, config_path=cfg_path)
        ok = guard.check(ctx, "Delete index 'main'")
        click.echo(f"proceed={ok}")

    result = runner.invoke(cmd)
    assert result.exit_code == 0, result.output
    mock_connect.assert_not_called()


def test_check_missing_profile_propagates(tmp_path: Path) -> None:
    """A --profile that doesn't exist surfaces, rather than silently defaulting."""
    cfg_path = tmp_path / "config.yaml"
    _write_v2(cfg_path, {"dev": {"host": "dev-host"}})

    ctx = click.Context(click.Command("x"))
    ctx.ensure_object(dict)
    ctx.obj["config"] = str(cfg_path)
    ctx.obj["profile"] = "missing"
    ctx.obj["dry_run"] = True

    with pytest.raises(cfg_mod.ProfileNotFoundError):
        guard.check(ctx, "Delete index 'main'")
