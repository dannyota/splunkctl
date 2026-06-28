"""Click entry point and global flags."""

import click

from splunkctl import __version__


@click.group()
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
@click.option("--dry-run", is_flag=True, default=True, help="Preview mutations.")
@click.option("--yes", "-y", is_flag=True, help="Confirm mutation, skip dry-run.")
@click.option(
    "--config",
    "-c",
    type=click.Path(),
    default=None,
    help="Config file path.",
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
    dry_run: bool,
    yes: bool,
    config: str | None,
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
    ctx.obj["debug"] = debug
    ctx.obj["timeout"] = timeout
