"""Tests for splunkctl.guard."""

import click
from click.testing import CliRunner

from splunkctl import guard


def test_dry_run_blocks_and_previews() -> None:
    runner = CliRunner()

    @click.command()
    @click.pass_context
    def cmd(ctx: click.Context) -> None:
        ctx.ensure_object(dict)
        ctx.obj["dry_run"] = True
        ok = guard.check(ctx, "Delete index 'main'", details="3.2 GB will be freed")
        click.echo(f"proceed={ok}")

    result = runner.invoke(cmd)
    assert "proceed=False" in result.output
    assert "[DRY RUN]" in result.stderr
    assert "3.2 GB" in result.stderr
    assert "--yes" in result.stderr


def test_yes_flag_allows_mutation() -> None:
    runner = CliRunner()

    @click.command()
    @click.pass_context
    def cmd(ctx: click.Context) -> None:
        ctx.ensure_object(dict)
        ctx.obj["dry_run"] = False
        ok = guard.check(ctx, "Delete index 'main'")
        click.echo(f"proceed={ok}")

    result = runner.invoke(cmd)
    assert "proceed=True" in result.output
    assert "[DRY RUN]" not in result.stderr
