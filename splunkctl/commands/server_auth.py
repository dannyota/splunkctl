"""Authentication provider inspection — SAML, LDAP, role mapping."""

import json
from typing import Any

import click

from splunkctl import output
from splunkctl.client import get_client

_AUTH_SERVICES_PATH = "/services/authentication/providers/services"
_LDAP_CONFIG_PATH = "/services/admin/LDAP-config"
_SAML_GROUPS_PATH = "/services/admin/SAML-groups"
_ROLES_PATH = "/services/authorization/roles"


def _rest_json(svc: Any, path: str, **params: Any) -> dict[str, Any]:
    """GET a REST path and parse JSON."""
    resp = svc.get(path, output_mode="json", **params)
    body: dict[str, Any] = json.loads(resp.body.read())
    return body


def _detect_auth_type(entries: list[dict[str, Any]]) -> str:
    """Return the active authentication type from provider-services entries.

    Splunk may list multiple providers; the one whose ``active_authmodule``
    is set (or whose name is the active module) wins.  Falls back to
    ``Splunk`` when nothing matches.
    """
    for entry in entries:
        c: dict[str, Any] = entry.get("content", {})
        active = c.get("active_authmodule", "")
        if active:
            active_lower = str(active).lower()
            if "saml" in active_lower:
                return "SAML"
            if "ldap" in active_lower:
                return "LDAP"
            return str(active)
    return "Splunk"


@click.group("auth")
def auth_group() -> None:
    """Authentication provider inspection (read-only)."""


@auth_group.command("show")
@click.pass_context
def auth_show(ctx: click.Context) -> None:
    """Show the current authentication method and provider config."""
    client = get_client(ctx)
    svc = client.service

    body = _rest_json(svc, _AUTH_SERVICES_PATH, count=-1)
    entries: list[dict[str, Any]] = body.get("entry", [])

    auth_type = _detect_auth_type(entries)

    rows: list[dict[str, Any]] = []
    for entry in entries:
        c: dict[str, Any] = entry.get("content", {})
        rows.append(
            {
                "name": entry.get("name", ""),
                "auth_type": auth_type,
                "active_authmodule": c.get("active_authmodule", ""),
            }
        )

    if not rows:
        rows = [{"auth_type": "Splunk", "active_authmodule": "Splunk"}]

    output.render(ctx, rows)


@auth_group.command("ldap")
@click.pass_context
def auth_ldap(ctx: click.Context) -> None:
    """Show LDAP configuration (servers, base DNs).

    Feature-detects whether LDAP is configured before querying the
    LDAP-config endpoint.  Exits cleanly with a status message when
    LDAP is not the active provider.
    """
    client = get_client(ctx)
    svc = client.service

    # Detect active auth type first.
    services_body = _rest_json(svc, _AUTH_SERVICES_PATH, count=-1)
    auth_type = _detect_auth_type(services_body.get("entry", []))

    if auth_type != "LDAP":
        output.render(
            ctx,
            {"status": "not_configured", "active_auth": auth_type},
        )
        return

    try:
        body = _rest_json(svc, _LDAP_CONFIG_PATH, count=-1)
    except Exception as exc:
        if type(exc).__name__ == "HTTPError" and getattr(exc, "status", 0) == 404:
            output.render(
                ctx,
                {"status": "not_configured", "active_auth": auth_type},
            )
            return
        raise

    rows: list[dict[str, Any]] = []
    for entry in body.get("entry", []):
        c: dict[str, Any] = entry.get("content", {})
        rows.append(
            {
                "name": entry.get("name", ""),
                "host": c.get("host", ""),
                "port": c.get("port", ""),
                "SSLEnabled": c.get("SSLEnabled", ""),
                "userBaseDN": c.get("userBaseDN", ""),
                "groupBaseDN": c.get("groupBaseDN", ""),
                "bindDN": c.get("bindDN", ""),
                "userNameAttribute": c.get("userNameAttribute", ""),
                "groupMemberAttribute": c.get("groupMemberAttribute", ""),
            }
        )
    output.render(ctx, rows, empty="No LDAP strategies configured.")


@auth_group.command("saml")
@click.pass_context
def auth_saml(ctx: click.Context) -> None:
    """Show SAML IdP / group mappings.

    Feature-detects whether SAML is configured before querying the
    SAML-groups endpoint.  Exits cleanly with a status message when
    SAML is not the active provider.
    """
    client = get_client(ctx)
    svc = client.service

    # Detect active auth type first.
    services_body = _rest_json(svc, _AUTH_SERVICES_PATH, count=-1)
    auth_type = _detect_auth_type(services_body.get("entry", []))

    if auth_type != "SAML":
        output.render(
            ctx,
            {"status": "not_configured", "active_auth": auth_type},
        )
        return

    try:
        body = _rest_json(svc, _SAML_GROUPS_PATH, count=-1)
    except Exception as exc:
        if type(exc).__name__ == "HTTPError" and getattr(exc, "status", 0) == 404:
            output.render(
                ctx,
                {"status": "not_configured", "active_auth": auth_type},
            )
            return
        raise

    rows: list[dict[str, Any]] = []
    for entry in body.get("entry", []):
        c: dict[str, Any] = entry.get("content", {})
        roles = c.get("roles", [])
        if isinstance(roles, str):
            roles = [roles]
        rows.append(
            {
                "name": entry.get("name", ""),
                "roles": ", ".join(roles),
            }
        )
    output.render(ctx, rows, empty="No SAML group mappings found.")


def _format_list(value: Any) -> str:
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    return str(value) if value else ""


@auth_group.command("role-mapping")
@click.pass_context
def auth_role_mapping(ctx: click.Context) -> None:
    """Show roles with their authentication mapping info."""
    client = get_client(ctx)
    svc = client.service

    body = _rest_json(svc, _ROLES_PATH, count=-1)

    rows: list[dict[str, Any]] = []
    for entry in body.get("entry", []):
        c: dict[str, Any] = entry.get("content", {})
        imported = c.get("imported_roles", [])
        if isinstance(imported, str):
            imported = [imported]
        rows.append(
            {
                "name": entry.get("name", ""),
                "imported_roles": _format_list(imported),
                "srchFilter": c.get("srchFilter", ""),
                "srchIndexesAllowed": _format_list(c.get("srchIndexesAllowed", [])),
                "defaultApp": c.get("defaultApp", ""),
            }
        )
    output.render(ctx, rows, empty="No roles found.")
