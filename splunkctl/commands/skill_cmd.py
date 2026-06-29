"""Skill commands — print or install the embedded SKILL.md."""

import importlib.resources
from pathlib import Path

import click

from splunkctl import output

_INSTALL_DIR = Path.home() / ".claude" / "skills" / "splunkctl"


def _load_skill() -> str:
    """Read SKILL.md from the installed package."""
    try:
        ref = importlib.resources.files("splunkctl.skill").joinpath("SKILL.md")
        return ref.read_text(encoding="utf-8")
    except FileNotFoundError:
        output.error("SKILL.md not found in package. Reinstall splunkctl.")
        raise SystemExit(1) from None


@click.group("skill", invoke_without_command=True)
@click.pass_context
def skill_group(ctx: click.Context) -> None:
    """Print or install the embedded agent skill guide."""
    if ctx.invoked_subcommand is None:
        click.echo(_load_skill(), nl=False)


@skill_group.command("print")
def skill_print() -> None:
    """Print SKILL.md to stdout."""
    click.echo(_load_skill(), nl=False)


@skill_group.command("install")
def skill_install() -> None:
    """Install SKILL.md to ~/.claude/skills/splunkctl/."""
    _INSTALL_DIR.mkdir(parents=True, exist_ok=True)
    dest = _INSTALL_DIR / "SKILL.md"
    dest.write_text(_load_skill(), encoding="utf-8")
    output.info(f"Installed to {dest}")
