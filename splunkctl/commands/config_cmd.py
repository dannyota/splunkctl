"""Config commands — init, show, use, test."""

from pathlib import Path
from typing import Any

import click

from splunkctl import config as cfg_mod
from splunkctl import errors as err_mod
from splunkctl import output
from splunkctl.auth import detector
from splunkctl.client import SplunkClient


@click.group("config")
def config_group() -> None:
    """Manage splunkctl configuration."""


@config_group.command()
@click.option("--host", default=None, help="Splunk host.")
@click.option("--port", default=None, type=int, help="Splunk port.")
@click.option("--username", default=None, help="Splunk username.")
@click.option("--password", default=None, help="Splunk password.")
@click.option(
    "--scheme",
    type=click.Choice(["https", "http"]),
    default=None,
    help="Connection scheme.",
)
@click.option("--verify/--no-verify", default=None, help="Verify SSL certificate.")
@click.option(
    "--soar",
    "soar_mode",
    is_flag=True,
    default=False,
    help="Add SOAR connection settings to the profile.",
)
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
@click.option(
    "--web-url",
    default=None,
    help="Product web origin (Splunk Web, e.g. http://host:8000). Required "
    "for browser SAML login on SIEM.",
)
@click.option(
    "--auth-mode",
    "auth_mode",
    type=click.Choice(["auto", "token", "password", "browser"]),
    default="auto",
    help="Authentication mode. 'auto' probes the login route to detect SAML.",
)
@click.pass_context
def init(
    ctx: click.Context,
    host: str | None,
    port: int | None,
    username: str | None,
    password: str | None,
    scheme: str | None,
    verify: bool | None,
    soar_mode: bool,
    profile_name: str | None,
    path: str | None,
    web_url: str | None,
    auth_mode: str | None,
) -> None:
    """Interactive setup — create or overwrite config.

    Bare ``config init`` writes the flat (legacy-compatible) file — unless
    the destination already exists and uses the ``profiles:`` schema, in
    which case it folds the new values into ``profiles.default`` instead,
    leaving sibling profiles and the ``current`` pointer untouched. This
    never clobbers an existing multi-profile file.
    ``config init --profile <name>`` targets that named profile instead —
    use ``config use <name>`` afterwards to make it active.

    ``config init --soar`` prompts for SOAR connection settings and saves
    them as a nested ``soar:`` map within the profile, preserving existing
    SIEM fields.
    """
    dest = Path(path) if path else None
    if soar_mode:
        _init_soar(profile_name, dest, web_url, auth_mode)
        return

    # Prompt for SIEM fields not supplied via flags.
    host = host or click.prompt("Host", default="localhost")
    port = port or click.prompt("Port", default=8089, type=int)
    username = username or click.prompt("Username", default="admin")
    password = (
        password
        if password is not None
        else click.prompt("Password", default="", hide_input=True)
    )
    scheme = scheme or "https"
    if verify is None:
        verify = click.confirm("Verify TLS certificates", default=True)

    if auth_mode == "auto":
        auth_mode = (
            detector.probe(
                detector.siem_login_url(web_url), verify=bool(verify), timeout=30
            )
            if web_url
            else None
        )

    cfg: dict[str, Any] = {
        "host": host,
        "port": port,
        "username": username,
        "password": password,
        "scheme": scheme,
        "verify": verify,
    }
    if web_url:
        cfg["web_url"] = web_url
    if auth_mode in ("browser", "password", "token"):
        cfg["auth_mode"] = auth_mode
    if profile_name:
        saved = cfg_mod.save_profile(cfg, profile_name, dest)
    elif cfg_mod.is_v2_file(dest):
        saved = cfg_mod.save_profile(cfg, "default", dest)
    else:
        saved = cfg_mod.save(cfg, dest)
    output.info(f"Config saved to {saved}")


def _init_soar(
    profile_name: str | None,
    dest: Path | None,
    web_url: str | None,
    auth_mode: str | None,
) -> None:
    """Prompt for SOAR fields and merge into the target profile."""
    soar_host = click.prompt("SOAR host", type=str)
    soar_port = click.prompt("SOAR port", default=8443, type=int)
    soar_token = click.prompt("SOAR token", default="", type=str)
    soar_user = click.prompt("SOAR username", default="", type=str)
    soar_pass = click.prompt("SOAR password", default="", hide_input=True, type=str)
    soar_verify = click.confirm("Verify TLS certificates", default=True)

    soar_cfg: dict[str, Any] = {
        "host": soar_host,
        "port": soar_port,
        "verify": soar_verify,
    }
    if soar_token:
        soar_cfg["token"] = soar_token
    if soar_user:
        soar_cfg["username"] = soar_user
    if soar_pass:
        soar_cfg["password"] = soar_pass
    if web_url:
        soar_cfg["web_url"] = web_url
        if auth_mode == "auto":
            auth_mode = detector.probe(
                detector.soar_login_url(web_url), verify=soar_verify, timeout=30
            )
    elif auth_mode == "auto":
        auth_mode = None
    if auth_mode in ("browser", "password", "token"):
        soar_cfg["auth_mode"] = auth_mode

    # Resolve which profile to update (same precedence as resolve()).
    config_path = dest or cfg_mod.DEFAULT_PATH
    raw = cfg_mod._read_raw(config_path)  # noqa: SLF001
    name = cfg_mod._active_profile_name(raw, profile_name)  # noqa: SLF001

    # Load existing SIEM fields (if any) and attach the new soar: map.
    try:
        existing = dict(cfg_mod._profile_config(raw, name))  # noqa: SLF001
    except cfg_mod.ProfileNotFoundError:
        existing = {}
    existing["soar"] = soar_cfg
    saved = cfg_mod.save_profile(existing, name, dest)
    output.info(f"SOAR config saved to {saved}")


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
    payload: dict[str, Any] = {
        "profile": resolved["profile"],
        **cfg_mod.redact(resolved["cfg"]),
    }

    # Include redacted SOAR section if the profile has one.
    soar = cfg_mod.resolve_soar(config_path, profile=explicit_profile)
    # Only include soar: if the profile actually configured it (has a host).
    if "host" in soar:
        payload["soar"] = cfg_mod.redact_soar(soar)

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
        classified = err_mod.classify(exc)
        if classified is not None:
            output.error(
                classified.message,
                kind=classified.kind,
                http_status=classified.http_status,
            )
        else:
            output.error(str(exc))
        ctx.exit(1)
