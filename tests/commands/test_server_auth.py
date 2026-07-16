"""Tests for server auth commands."""

import json
from typing import Any
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from splunkctl.main import cli

_PATCH = "splunkctl.commands.server_auth.get_client"


def _resp(data: dict[str, Any]) -> MagicMock:
    resp = MagicMock()
    resp.body.read.return_value = json.dumps(data).encode()
    return resp


def _services_entry(
    *,
    name: str = "services",
    active_authmodule: str = "Splunk",
) -> dict[str, Any]:
    return {
        "name": name,
        "content": {"active_authmodule": active_authmodule},
    }


# --- auth show ---


@patch(_PATCH)
def test_auth_show_splunk(mock_gc: MagicMock) -> None:
    """Default Splunk native auth."""
    svc = mock_gc.return_value.service
    svc.get.return_value = _resp(
        {"entry": [_services_entry(active_authmodule="Splunk")]}
    )

    result = CliRunner().invoke(cli, ["--json", "server", "auth", "show"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data[0]["auth_type"] == "Splunk"


@patch(_PATCH)
def test_auth_show_ldap(mock_gc: MagicMock) -> None:
    svc = mock_gc.return_value.service
    svc.get.return_value = _resp({"entry": [_services_entry(active_authmodule="LDAP")]})

    result = CliRunner().invoke(cli, ["--json", "server", "auth", "show"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data[0]["auth_type"] == "LDAP"


@patch(_PATCH)
def test_auth_show_saml(mock_gc: MagicMock) -> None:
    svc = mock_gc.return_value.service
    svc.get.return_value = _resp({"entry": [_services_entry(active_authmodule="SAML")]})

    result = CliRunner().invoke(cli, ["--json", "server", "auth", "show"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data[0]["auth_type"] == "SAML"


@patch(_PATCH)
def test_auth_show_empty_entries(mock_gc: MagicMock) -> None:
    """No entries returns Splunk as default."""
    svc = mock_gc.return_value.service
    svc.get.return_value = _resp({"entry": []})

    result = CliRunner().invoke(cli, ["--json", "server", "auth", "show"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data[0]["auth_type"] == "Splunk"


# --- auth ldap ---


@patch(_PATCH)
def test_auth_ldap_not_configured(mock_gc: MagicMock) -> None:
    """LDAP command when auth is Splunk native."""
    svc = mock_gc.return_value.service
    svc.get.return_value = _resp(
        {"entry": [_services_entry(active_authmodule="Splunk")]}
    )

    result = CliRunner().invoke(cli, ["--json", "server", "auth", "ldap"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data[0]["status"] == "not_configured"


@patch(_PATCH)
def test_auth_ldap_configured(mock_gc: MagicMock) -> None:
    svc = mock_gc.return_value.service

    call_count = 0

    def fake_get(path: str, **kwargs: Any) -> MagicMock:
        nonlocal call_count
        call_count += 1
        if "providers/services" in path:
            return _resp({"entry": [_services_entry(active_authmodule="LDAP")]})
        return _resp(
            {
                "entry": [
                    {
                        "name": "corp-ldap",
                        "content": {
                            "host": "ldap.corp.example.com",
                            "port": 636,
                            "SSLEnabled": True,
                            "userBaseDN": "ou=users,dc=corp,dc=example,dc=com",
                            "groupBaseDN": "ou=groups,dc=corp,dc=example,dc=com",
                            "bindDN": "cn=splunk,ou=svc,dc=corp,dc=example,dc=com",
                            "userNameAttribute": "sAMAccountName",
                            "groupMemberAttribute": "member",
                        },
                    }
                ]
            }
        )

    svc.get.side_effect = fake_get

    result = CliRunner().invoke(cli, ["--json", "server", "auth", "ldap"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data[0]["name"] == "corp-ldap"
    assert data[0]["host"] == "ldap.corp.example.com"
    assert data[0]["userBaseDN"] == "ou=users,dc=corp,dc=example,dc=com"


@patch(_PATCH)
def test_auth_ldap_404_fallback(mock_gc: MagicMock) -> None:
    """LDAP endpoint 404 returns not_configured."""
    svc = mock_gc.return_value.service

    http_err = type("HTTPError", (Exception,), {"status": 404})()

    def fake_get(path: str, **kwargs: Any) -> MagicMock:
        if "providers/services" in path:
            return _resp({"entry": [_services_entry(active_authmodule="LDAP")]})
        raise http_err

    svc.get.side_effect = fake_get

    result = CliRunner().invoke(cli, ["--json", "server", "auth", "ldap"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data[0]["status"] == "not_configured"


# --- auth saml ---


@patch(_PATCH)
def test_auth_saml_not_configured(mock_gc: MagicMock) -> None:
    svc = mock_gc.return_value.service
    svc.get.return_value = _resp(
        {"entry": [_services_entry(active_authmodule="Splunk")]}
    )

    result = CliRunner().invoke(cli, ["--json", "server", "auth", "saml"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data[0]["status"] == "not_configured"


@patch(_PATCH)
def test_auth_saml_configured(mock_gc: MagicMock) -> None:
    svc = mock_gc.return_value.service

    def fake_get(path: str, **kwargs: Any) -> MagicMock:
        if "providers/services" in path:
            return _resp({"entry": [_services_entry(active_authmodule="SAML")]})
        return _resp(
            {
                "entry": [
                    {
                        "name": "okta-admins",
                        "content": {"roles": ["admin", "power"]},
                    },
                    {
                        "name": "okta-analysts",
                        "content": {"roles": "user"},
                    },
                ]
            }
        )

    svc.get.side_effect = fake_get

    result = CliRunner().invoke(cli, ["--json", "server", "auth", "saml"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert len(data) == 2
    assert data[0]["name"] == "okta-admins"
    assert data[0]["roles"] == "admin, power"
    # Single string role normalised to string display.
    assert data[1]["roles"] == "user"


@patch(_PATCH)
def test_auth_saml_404_fallback(mock_gc: MagicMock) -> None:
    svc = mock_gc.return_value.service

    http_err = type("HTTPError", (Exception,), {"status": 404})()

    def fake_get(path: str, **kwargs: Any) -> MagicMock:
        if "providers/services" in path:
            return _resp({"entry": [_services_entry(active_authmodule="SAML")]})
        raise http_err

    svc.get.side_effect = fake_get

    result = CliRunner().invoke(cli, ["--json", "server", "auth", "saml"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data[0]["status"] == "not_configured"


# --- auth role-mapping ---


@patch(_PATCH)
def test_auth_role_mapping(mock_gc: MagicMock) -> None:
    svc = mock_gc.return_value.service
    svc.get.return_value = _resp(
        {
            "entry": [
                {
                    "name": "admin",
                    "content": {
                        "imported_roles": ["power", "user"],
                        "srchFilter": "",
                        "srchIndexesAllowed": ["*"],
                        "defaultApp": "launcher",
                    },
                },
                {
                    "name": "user",
                    "content": {
                        "imported_roles": "can_delete",
                        "srchFilter": "index=main",
                        "srchIndexesAllowed": "main",
                        "defaultApp": "search",
                    },
                },
            ]
        }
    )

    result = CliRunner().invoke(cli, ["--json", "server", "auth", "role-mapping"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert len(data) == 2
    assert data[0]["name"] == "admin"
    assert data[0]["imported_roles"] == "power, user"
    assert data[0]["srchIndexesAllowed"] == "*"
    # Single string imported_roles normalised.
    assert data[1]["imported_roles"] == "can_delete"


@patch(_PATCH)
def test_auth_role_mapping_empty(mock_gc: MagicMock) -> None:
    svc = mock_gc.return_value.service
    svc.get.return_value = _resp({"entry": []})

    result = CliRunner().invoke(cli, ["--json", "server", "auth", "role-mapping"])
    assert result.exit_code == 0
    assert result.output.strip() == "[]"
