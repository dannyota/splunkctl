"""Active license group usage regression tests."""

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from splunkctl.main import cli


def _response(entries: list[dict[str, Any]]) -> MagicMock:
    response = MagicMock()
    response.body.read.return_value = json.dumps({"entry": entries}).encode()
    return response


@pytest.mark.parametrize("active_group", ["Trial", "Free", "Forwarder"])
def test_license_usage_scopes_to_active_group(active_group: str) -> None:
    fixtures = {
        "Trial": {
            "status": "EXPIRED",
            "quota": 524288000,
            "expiration_time": 1735689600,
        },
        "Free": {"status": "VALID", "quota": 524288000, "expiration_time": 2147483647},
        "Forwarder": {
            "status": "VALID",
            "quota": 1048576,
            "expiration_time": 2147483647,
        },
    }
    responses = {
        "/services/licenser/usage": _response(
            [{"content": {"slaves_usage_bytes": 262144, "quota": 0}}]
        ),
        "/services/licenser/groups": _response(
            [
                {"name": name, "content": {"is_active": int(name == active_group)}}
                for name in fixtures
            ]
        ),
        "/services/licenser/licenses": _response(
            [
                {"name": name, "content": {"group_id": name, **content}}
                for name, content in fixtures.items()
            ]
        ),
    }
    with patch("splunkctl.commands.server.get_client") as get_client:
        get_client.return_value.service.get.side_effect = lambda path, **kwargs: (
            responses[path]
        )
        result = CliRunner().invoke(cli, ["--json", "server", "license", "--usage"])

    assert result.exit_code == 0, result.output
    row = json.loads(result.output)[0]
    assert row["active_group"] == active_group
    assert row["active_group_status"] == fixtures[active_group]["status"]
    assert row["licenses_valid"] == (0 if active_group == "Trial" else 1)
    assert row["quota"] == ("1.0 MB" if active_group == "Forwarder" else "500.0 MB")
    assert row["pct_used"] == (25.0 if active_group == "Forwarder" else 0.1)
    assert row["soonest_expiry"] == (
        "2025-01-01" if active_group == "Trial" else "never"
    )


def test_license_usage_missing_active_group_does_not_use_other_licenses() -> None:
    with patch("splunkctl.commands.server.get_client") as get_client:
        get_client.return_value.service.get.return_value = _response(
            [
                {
                    "name": "Free",
                    "content": {
                        "is_active": "0",
                        "status": "VALID",
                        "group_id": "Free",
                        "quota": 100,
                    },
                }
            ]
        )
        result = CliRunner().invoke(cli, ["--json", "server", "license", "--usage"])

    assert result.exit_code == 0, result.output
    row = json.loads(result.output)[0]
    assert row["active_group"] == "unknown"
    assert row["active_group_status"] == "UNKNOWN"
    assert row["licenses_valid"] == 0
    assert row["quota"] == "0 B"
