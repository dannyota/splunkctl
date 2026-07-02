"""Click entry point and global flags."""

import sys
from typing import Any

import click

from splunkctl import __version__, output
from splunkctl import config as cfg_mod
from splunkctl import errors as err_mod
from splunkctl.commands.alerts import alerts_group
from splunkctl.commands.apps import apps_group
from splunkctl.commands.audit import audit_group
from splunkctl.commands.commands_meta import commands_meta
from splunkctl.commands.conf import conf_group
from splunkctl.commands.config_cmd import config_group
from splunkctl.commands.dashboards import dashboards_group
from splunkctl.commands.datamodels import datamodels_group
from splunkctl.commands.doctor import doctor_cmd
from splunkctl.commands.es import es_group
from splunkctl.commands.hec import hec_group
from splunkctl.commands.indexes import indexes_group
from splunkctl.commands.info import info
from splunkctl.commands.inputs import inputs_group
from splunkctl.commands.knowledge import eventtypes_group, macros_group, tags_group
from splunkctl.commands.kvstore import kvstore_group
from splunkctl.commands.lookups import lookups_group
from splunkctl.commands.parsers import parsers_group
from splunkctl.commands.rules import rules_group
from splunkctl.commands.search import search_group
from splunkctl.commands.server import server_group
from splunkctl.commands.skill_cmd import skill_group
from splunkctl.commands.users import users_group


class _CLI(click.Group):
    """Top-level group with flag hoisting and SDK error handling.

    Rewrites args so global flags (--yes, --json, --format, --fields)
    work in any position, not just before the subcommand.
    """

    _HOIST_FLAGS: frozenset[str] = frozenset(
        {
            "--yes",
            "-y",
            "--json",
            "--debug",
        }
    )
    _HOIST_VALUE: frozenset[str] = frozenset(
        {
            "--format",
            "--fields",
            "--timeout",
            "--out",
            "-o",
            "--config",
            "-c",
            "--profile",
        }
    )

    def _leaf_opts(self, args: list[str]) -> frozenset[str]:
        """Option names defined by the subcommand the args resolve to.

        A flag spelled the same as a global one stays with the leaf.
        """
        cmd: click.Command = self
        for tok in args:
            if tok.startswith("-"):
                continue
            if isinstance(cmd, click.Group) and tok in cmd.commands:
                cmd = cmd.commands[tok]
            else:
                break
        if cmd is self:
            return frozenset()
        opts: set[str] = set()
        for p in cmd.params:
            opts.update(p.opts)
            opts.update(p.secondary_opts)
        return frozenset(opts)

    def parse_args(self, ctx: click.Context, args: list[str]) -> list[str]:
        """Move known global flags to the front of the arg list."""
        leaf_opts = self._leaf_opts(args)
        prefix: list[str] = []
        rest: list[str] = []
        i = 0
        while i < len(args):
            if args[i] in self._HOIST_FLAGS and args[i] not in leaf_opts:
                prefix.append(args[i])
            elif (
                args[i] in self._HOIST_VALUE
                and args[i] not in leaf_opts
                and i + 1 < len(args)
            ):
                prefix.append(args[i])
                prefix.append(args[i + 1])
                i += 1
            else:
                rest.append(args[i])
            i += 1
        return super().parse_args(ctx, prefix + rest)

    def invoke(self, ctx: click.Context) -> Any:
        try:
            return super().invoke(ctx)
        except Exception as exc:
            if isinstance(exc, cfg_mod.ProfileNotFoundError):
                output.error(f"Profile not found: {exc.name}", kind="not_found")
                sys.exit(1)
            classified = err_mod.classify(exc)
            if classified is not None:
                output.error(
                    classified.message,
                    kind=classified.kind,
                    http_status=classified.http_status,
                )
                sys.exit(1)
            raise


@click.group(cls=_CLI)
@click.version_option(version=__version__, prog_name="splunkctl")
@click.option("--json", "use_json", is_flag=True, help="Force JSON output.")
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["table", "json", "csv", "jsonl"]),
    default=None,
    help="Output format.",
)
@click.option("--fields", default=None, help="Comma-separated fields to project.")
@click.option("--out", "-o", type=click.Path(), default=None, help="Write to file.")
@click.option("--yes", "-y", is_flag=True, help="Confirm mutation, skip dry-run.")
@click.option(
    "--config",
    "-c",
    type=click.Path(),
    default=None,
    help="Config file path.",
)
@click.option(
    "--profile",
    default=None,
    help="Named config profile to use (overrides the file's 'current' pointer).",
)
@click.option("--debug", is_flag=True, help="HTTP request/response logging.")
@click.option("--timeout", type=int, default=30, help="Request timeout in seconds.")
@click.pass_context
def cli(
    ctx: click.Context,
    *,
    use_json: bool,
    fmt: str | None,
    fields: str | None,
    out: str | None,
    yes: bool,
    config: str | None,
    profile: str | None,
    debug: bool,
    timeout: int,
) -> None:
    """CLI tool for Splunk Enterprise SIEM operations."""
    ctx.ensure_object(dict)
    ctx.obj["json"] = use_json
    ctx.obj["format"] = fmt
    ctx.obj["fields"] = fields
    ctx.obj["out"] = out
    ctx.obj["dry_run"] = not yes
    ctx.obj["config"] = config
    ctx.obj["profile"] = profile
    ctx.obj["debug"] = debug
    ctx.obj["timeout"] = timeout


cli.add_command(alerts_group)
cli.add_command(apps_group)
cli.add_command(audit_group)
cli.add_command(commands_meta)
cli.add_command(conf_group)
cli.add_command(config_group)
cli.add_command(dashboards_group)
cli.add_command(datamodels_group)
cli.add_command(doctor_cmd)
cli.add_command(es_group)
cli.add_command(eventtypes_group)
cli.add_command(hec_group)
cli.add_command(indexes_group)
cli.add_command(info)
cli.add_command(inputs_group)
cli.add_command(kvstore_group)
cli.add_command(lookups_group)
cli.add_command(macros_group)
cli.add_command(parsers_group)
cli.add_command(rules_group)
cli.add_command(search_group)
cli.add_command(server_group)
cli.add_command(skill_group)
cli.add_command(tags_group)
cli.add_command(users_group)
