"""Knowledge object ACL commands."""

import json

import click

from splunkctl import acl_ops, guard, output
from splunkctl.client import get_client


@click.group("acl")
def acl_group() -> None:
    """Inspect and change knowledge object permissions.

    TYPE tag uses NAME field=value (the tags.conf stanza). Macro names must
    include their exact stanza suffix, including (n). Field-extraction names
    are '<stanza> : EXTRACT-<name>'.
    """


@acl_group.command("get")
@click.argument("type", type=click.Choice(list(acl_ops.RESOURCES)))
@click.argument("name")
@click.option("--app", default=None, help="App namespace (default: current).")
@click.option("--owner", default=None, help="Owner namespace (default: current).")
@click.pass_context
def get_acl(
    ctx: click.Context, type: str, name: str, app: str | None, owner: str | None
) -> None:
    """Show object permissions and modification capabilities."""
    entry = acl_ops.resolve(get_client(ctx).service, type, name, app=app, owner=owner)
    output.render(ctx, acl_ops.row(entry))


@acl_group.command("set")
@guard.guarded
@click.argument("type", type=click.Choice(list(acl_ops.RESOURCES)))
@click.argument("name")
@click.option("--app", default=None, help="App namespace (default: current).")
@click.option("--current-owner", default=None, help="Current owner namespace.")
@click.option("--sharing", type=click.Choice(["user", "app", "global"]))
@click.option("--owner", default=None, help="New object owner.")
@click.option(
    "--read", default=None, help="Read roles, comma-separated; '*' everyone, '' clears."
)
@click.option(
    "--write",
    default=None,
    help="Write roles, comma-separated; '*' everyone, '' clears.",
)
@click.pass_context
def set_acl(
    ctx: click.Context,
    type: str,
    name: str,
    app: str | None,
    current_owner: str | None,
    sharing: str | None,
    owner: str | None,
    read: str | None,
    write: str | None,
) -> None:
    """Preview or apply object permission changes."""
    svc = get_client(ctx).service
    entry = acl_ops.resolve(svc, type, name, app=app, owner=current_owner)
    fields = acl_ops.changes(
        svc, entry, sharing=sharing, owner=owner, read=read, write=write
    )
    if acl_ops.unchanged(entry, fields):
        output.render(ctx, acl_ops.row(entry))
        output.info("Permissions unchanged.")
        return
    details = (
        "  before: "
        + json.dumps(acl_ops.row(entry))
        + "\n  after: "
        + json.dumps(fields)
    )
    if not guard.check(ctx, f"Set {type} '{name}' permissions", details=details):
        return
    output.render(ctx, acl_ops.row(acl_ops.update(svc, entry, fields)))
