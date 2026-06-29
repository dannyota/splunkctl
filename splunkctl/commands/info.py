"""Info command — server info, license, version."""

from typing import Any

import click

from splunkctl import output
from splunkctl.client import get_client


@click.command()
@click.pass_context
def info(ctx: click.Context) -> None:
    """Show Splunk server info."""
    client = get_client(ctx)
    svc = client.service
    si: dict[str, Any] = dict(svc.info)

    row: dict[str, Any] = {
        "server_name": si.get("serverName", ""),
        "version": si.get("version", ""),
        "build": si.get("build", ""),
        "os": si.get("os_name", ""),
        "cpu_arch": si.get("cpu_arch", ""),
        "license_state": si.get("licenseState", ""),
        "mode": si.get("mode", ""),
        "guid": si.get("guid", ""),
    }
    output.render(ctx, row)
