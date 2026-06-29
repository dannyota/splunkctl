"""Tests for the skill command."""

from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from splunkctl.main import cli


def test_skill_prints_guide() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["skill"])
    assert result.exit_code == 0
    assert "splunkctl" in result.output
    assert "Agent Skill Guide" in result.output


def test_skill_print_subcommand() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["skill", "print"])
    assert result.exit_code == 0
    assert "## Auth" in result.output
    assert "## Commands" in result.output


def test_skill_bare_matches_print() -> None:
    runner = CliRunner()
    bare = runner.invoke(cli, ["skill"])
    explicit = runner.invoke(cli, ["skill", "print"])
    assert bare.output == explicit.output


def test_skill_install(tmp_path: Path) -> None:
    with patch(
        "splunkctl.commands.skill_cmd._INSTALL_DIR",
        tmp_path,
    ):
        runner = CliRunner()
        result = runner.invoke(cli, ["skill", "install"])
        assert result.exit_code == 0
        assert "Installed" in result.stderr

    written = (tmp_path / "SKILL.md").read_text()
    assert "splunkctl" in written
    assert "Agent Skill Guide" in written


def test_skill_install_idempotent(tmp_path: Path) -> None:
    with patch(
        "splunkctl.commands.skill_cmd._INSTALL_DIR",
        tmp_path,
    ):
        runner = CliRunner()
        runner.invoke(cli, ["skill", "install"])
        result = runner.invoke(cli, ["skill", "install"])
        assert result.exit_code == 0
        assert "Installed" in result.stderr


def test_skill_no_trailing_newline_duplication() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["skill"])
    assert not result.output.endswith("\n\n")
