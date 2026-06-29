"""Config commands — init, show, test."""

from pathlib import Path
from typing import Any

import click

from splunkctl import config as cfg_mod
from splunkctl import output
from splunkctl.client import SplunkClient


@click.group("config")
def config_group() -> None:
    """Manage splunkctl configuration."""


@config_group.command()
@click.option("--host", prompt=True, default="localhost", help="Splunk host.")
@click.option("--port", prompt=True, default=8089, type=int, help="Splunk port.")
@click.option("--username", prompt=True, default="admin", help="Splunk username.")
@click.option("--password", prompt=True, hide_input=True, help="Splunk password.")
@click.option(
    "--scheme",
    type=click.Choice(["https", "http"]),
    default="https",
    help="Connection scheme.",
)
@click.option("--verify/--no-verify", default=False, help="Verify SSL certificate.")
@click.option(
    "--path",
    type=click.Path(),
    default=None,
    help="Config file path (default: ~/.splunkctl/config.yaml).",
)
def init(
    host: str,
    port: int,
    username: str,
    password: str,
    scheme: str,
    verify: bool,
    path: str | None,
) -> None:
    """Interactive setup — create or overwrite config."""
    cfg: dict[str, Any] = {
        "host": host,
        "port": port,
        "username": username,
        "password": password,
        "scheme": scheme,
        "verify": verify,
    }
    dest = Path(path) if path else None
    saved = cfg_mod.save(cfg, dest)
    output.info(f"Config saved to {saved}")


@config_group.command()
@click.pass_context
def show(ctx: click.Context) -> None:
    """Display current config (secrets redacted)."""
    cfg_path = ctx.obj.get("config")
    cfg = cfg_mod.load(Path(cfg_path) if cfg_path else None)
    output.render(ctx, cfg_mod.redact(cfg))


@config_group.command()
@click.pass_context
def test(ctx: click.Context) -> None:
    """Verify connectivity and auth against the Splunk instance."""
    cfg_path = ctx.obj.get("config")
    config_path = Path(cfg_path) if cfg_path else None
    cfg = cfg_mod.load(config_path)

    output.info(
        f"Connecting to {cfg.get('scheme', 'https')}://"
        f"{cfg.get('host', 'localhost')}:{cfg.get('port', 8089)} ..."
    )

    try:
        client = SplunkClient(config_path=config_path)
        svc_info = client.service.info
        output.info(f"OK — {svc_info['serverName']} (Splunk {svc_info['version']})")
    except Exception as exc:
        output.error(str(exc))
        ctx.exit(1)
