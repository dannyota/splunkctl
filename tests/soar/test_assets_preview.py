"""Dry-run previews must not print secret-looking asset configuration values."""

from splunkctl.commands.soar.assets import _redact_secrets


def test_redact_masks_secret_keys_only() -> None:
    body = {
        "name": "a",
        "configuration": {
            "password": "hunter2",
            "API_Key": "k",
            "auth_token": "t",
            "client_secret": "s",
            "dns_server": "8.8.8.8",
        },
    }
    out = _redact_secrets(body)
    assert out["configuration"] == {
        "password": "****",
        "API_Key": "****",
        "auth_token": "****",
        "client_secret": "****",
        "dns_server": "8.8.8.8",
    }
    assert body["configuration"]["password"] == "hunter2"


def test_redact_leaves_bodies_without_configuration() -> None:
    body = {"name": "a", "description": "d"}
    assert _redact_secrets(body) == body
