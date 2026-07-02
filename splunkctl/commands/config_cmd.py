"""Config commands — init, show, use, test."""

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
    "--profile",
    "profile_name",
    default=None,
    help=(
        "Create or update this named profile (schema v2), instead of the "
        "flat/default config file. A legacy file is upgraded, folding its "
        "existing values into 'profiles.default'."
    ),
)
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
    profile_name: str | None,
    path: str | None,
) -> None:
    """Interactive setup — create or overwrite config.

    Bare ``config init`` always writes the flat (legacy-compatible) file.
    ``config init --profile <name>`` targets that named profile instead —
    use ``config use <name>`` afterwards to make it active.
    """
    cfg: dict[str, Any] = {
        "host": host,
        "port": port,
        "username": username,
        "password": password,
        "scheme": scheme,
        "verify": verify,
    }
    dest = Path(path) if path else None
    if profile_name:
        saved = cfg_mod.save_profile(cfg, profile_name, dest)
    else:
        saved = cfg_mod.save(cfg, dest)
    output.info(f"Config saved to {saved}")


@config_group.command()
@click.pass_context
def show(ctx: click.Context) -> None:
    """Display config (secrets redacted).

    Shows the active profile (``--profile`` flag > ``current:`` pointer >
    ``default``) plus a one-line list of other known profiles. Pass the
    global ``--profile <name>`` to show a specific profile instead.
    """
    obj: dict[str, Any] = ctx.obj or {}
    cfg_path = obj.get("config")
    config_path = Path(cfg_path) if cfg_path else None
    explicit_profile = obj.get("profile")

    resolved = cfg_mod.resolve(config_path, profile=explicit_profile)
    payload = {"profile": resolved["profile"], **cfg_mod.redact(resolved["cfg"])}
    output.render(ctx, payload)

    if explicit_profile is None:
        others = [
            n for n in cfg_mod.profile_names(config_path) if n != resolved["profile"]
        ]
        if others:
            output.info(f"Other profiles: {', '.join(others)}")


@config_group.command("use")
@click.argument("name")
@click.pass_context
def use(ctx: click.Context, name: str) -> None:
    """Switch the active profile — sets 'current', no connectivity test."""
    obj: dict[str, Any] = ctx.obj or {}
    cfg_path = obj.get("config")
    config_path = Path(cfg_path) if cfg_path else None
    cfg_mod.use_profile(name, config_path)
    output.info(f"Active profile: {name}")


@config_group.command()
@click.pass_context
def test(ctx: click.Context) -> None:
    """Verify connectivity and auth against the Splunk instance."""
    obj: dict[str, Any] = ctx.obj or {}
    cfg_path = obj.get("config")
    profile = obj.get("profile")
    config_path = Path(cfg_path) if cfg_path else None
    cfg = cfg_mod.load(config_path, profile=profile)

    output.info(
        f"Connecting to {cfg.get('scheme', 'https')}://"
        f"{cfg.get('host', 'localhost')}:{cfg.get('port', 8089)} ..."
    )

    try:
        client = SplunkClient(config_path=config_path, profile=profile)
        svc_info = client.service.info
        output.info(f"OK — {svc_info['serverName']} (Splunk {svc_info['version']})")
    except Exception as exc:
        output.error(str(exc))
        ctx.exit(1)
