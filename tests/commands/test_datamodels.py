"""Tests for datamodels list/get and self-discovery.

Covers the raw ``datamodel/model`` REST collection (no SDK entity, same
pattern as kvstore.py) plus the F1 classified-envelope path for a bare
REST failure. Acceleration status and rebuild live in
test_datamodels_acceleration.py — split out purely for the line-count
budget (see that file's docstring).
"""

import json
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from splunkctl.main import cli

_PATCH = "splunkctl.commands.datamodels.get_client"


def _resp(body: object) -> MagicMock:
    r = MagicMock()
    if isinstance(body, (bytes, bytearray)):
        r.body.read.return_value = body
    else:
        r.body.read.return_value = json.dumps(body).encode()
    return r


def _http_error(status: int, reason: str, msg: str) -> Exception:
    """Build a real splunklib HTTPError, matching what a live call actually
    raises (so errors.classify's name-based check applies)."""
    from splunklib.binding import HTTPError

    xml_body = (
        f'<response><messages><msg type="ERROR">{msg}</msg></messages></response>'
    ).encode()
    resp = MagicMock()
    resp.status = status
    resp.reason = reason
    resp.body.read.return_value = xml_body
    resp.headers = []
    return HTTPError(resp)


def _accel(
    *,
    enabled: bool = False,
    earliest_time: str = "",
    cron_schedule: str = "*/5 * * * *",
) -> str:
    """Build the JSON-encoded ``content.acceleration`` string Splunk emits."""
    return json.dumps(
        {
            "enabled": enabled,
            "earliest_time": earliest_time,
            "cron_schedule": cron_schedule,
            "max_time": 3600,
            "backfill_time": "",
            "source_guid": "",
            "manual_rebuilds": False,
        }
    )


def _model_entry(
    name: str,
    *,
    app: str = "search",
    accelerated: bool = False,
    earliest_time: str = "",
    disabled: bool = False,
    description: dict[str, object] | None = None,
) -> dict[str, object]:
    desc = description if description is not None else {"objects": []}
    return {
        "name": name,
        "acl": {"app": app, "owner": "nobody"},
        "content": {
            "acceleration": _accel(enabled=accelerated, earliest_time=earliest_time),
            "acceleration.allowed": True,
            "disabled": disabled,
            "displayName": name,
            "description": json.dumps(desc),
        },
    }


# --- list ---


@patch(_PATCH)
def test_list_basic_columns(mock_gc: MagicMock) -> None:
    svc = mock_gc.return_value.service
    svc.get.return_value = _resp(
        {
            "entry": [
                _model_entry("cim_auth", app="Splunk_SA_CIM", accelerated=True),
                _model_entry("internal_server", app="search", accelerated=False),
            ]
        }
    )

    result = CliRunner().invoke(cli, ["--json", "datamodels", "list"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data == [
        {
            "name": "cim_auth",
            "app": "Splunk_SA_CIM",
            "accelerated": True,
            "disabled": False,
        },
        {
            "name": "internal_server",
            "app": "search",
            "accelerated": False,
            "disabled": False,
        },
    ]
    svc.get.assert_called_once_with(
        "datamodel/model", owner="nobody", app="-", output_mode="json"
    )


@patch(_PATCH)
def test_list_app_option_scopes_request(mock_gc: MagicMock) -> None:
    svc = mock_gc.return_value.service
    svc.get.return_value = _resp({"entry": []})

    result = CliRunner().invoke(
        cli, ["--json", "datamodels", "list", "--app", "Splunk_SA_CIM"]
    )
    assert result.exit_code == 0
    svc.get.assert_called_once_with(
        "datamodel/model", owner="nobody", app="Splunk_SA_CIM", output_mode="json"
    )


@patch(_PATCH)
def test_list_limit_offset_passed_server_side(mock_gc: MagicMock) -> None:
    svc = mock_gc.return_value.service
    svc.get.return_value = _resp({"entry": []})

    result = CliRunner().invoke(
        cli, ["--json", "datamodels", "list", "--limit", "2", "--offset", "1"]
    )
    assert result.exit_code == 0
    svc.get.assert_called_once_with(
        "datamodel/model",
        owner="nobody",
        app="-",
        output_mode="json",
        count=2,
        offset=1,
    )


@patch(_PATCH)
def test_list_filter_is_client_side_case_insensitive(mock_gc: MagicMock) -> None:
    svc = mock_gc.return_value.service
    svc.get.return_value = _resp(
        {
            "entry": [
                _model_entry("Authentication"),
                _model_entry("Network_Traffic"),
                _model_entry("Web"),
            ]
        }
    )

    result = CliRunner().invoke(
        cli, ["--json", "datamodels", "list", "--filter", "auth"]
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert [row["name"] for row in data] == ["Authentication"]
    # filter forces a full (unpaged) fetch — no count/offset sent
    svc.get.assert_called_once_with(
        "datamodel/model", owner="nobody", app="-", output_mode="json"
    )


@patch(_PATCH)
def test_list_empty(mock_gc: MagicMock) -> None:
    svc = mock_gc.return_value.service
    svc.get.return_value = _resp({"entry": []})

    result = CliRunner().invoke(cli, ["--json", "datamodels", "list"])
    assert result.exit_code == 0
    assert json.loads(result.output) == []


@patch(_PATCH)
def test_list_kv_store_independent_failure_classified(mock_gc: MagicMock) -> None:
    """A REST failure is never swallowed locally — it reaches the central
    F1 classifier as a clean envelope, same as kvstore/es."""
    svc = mock_gc.return_value.service
    svc.get.side_effect = _http_error(503, "Service Unavailable", "datamodel down")

    result = CliRunner().invoke(cli, ["--json", "datamodels", "list"])
    assert result.exit_code == 1
    err = json.loads(result.stderr)["error"]
    assert err["kind"] == "http"
    assert err["http_status"] == 503


# --- get ---


@patch(_PATCH)
def test_get_not_found(mock_gc: MagicMock) -> None:
    svc = mock_gc.return_value.service
    svc.get.return_value = _resp({"entry": []})

    result = CliRunner().invoke(cli, ["--json", "datamodels", "get", "nope"])
    assert result.exit_code == 1
    err = json.loads(result.stderr)["error"]
    assert err["kind"] == "not_found"
    svc.get.assert_called_once_with(
        "datamodel/model",
        owner="nobody",
        app="-",
        output_mode="json",
        search="name=nope",
        count=1,
    )


@patch(_PATCH)
def test_get_surfaces_detection_engineering_fields(mock_gc: MagicMock) -> None:
    svc = mock_gc.return_value.service
    description = {
        "objects": [
            {
                "objectName": "authentication",
                "constraints": [{"search": "tag=authentication tag=network"}],
            },
            {"objectName": "Failed_Authentication", "constraints": []},
        ]
    }
    svc.get.return_value = _resp(
        {
            "entry": [
                _model_entry(
                    "Authentication",
                    app="Splunk_SA_CIM",
                    accelerated=True,
                    earliest_time="-30d",
                    description=description,
                )
            ]
        }
    )

    result = CliRunner().invoke(cli, ["--json", "datamodels", "get", "Authentication"])
    assert result.exit_code == 0
    row = json.loads(result.output)[0]
    assert row == {
        "name": "Authentication",
        "app": "Splunk_SA_CIM",
        "displayName": "Authentication",
        "disabled": False,
        "acceleration_enabled": True,
        "acceleration_earliest_time": "-30d",
        "acceleration_cron_schedule": "*/5 * * * *",
        "object_count": 2,
        "objects": "authentication, Failed_Authentication",
        "root_search": "tag=authentication tag=network",
    }


@patch(_PATCH)
def test_get_definition_flag_prints_raw_model(mock_gc: MagicMock) -> None:
    svc = mock_gc.return_value.service
    description = {"objects": [{"objectName": "authentication", "fields": []}]}
    svc.get.return_value = _resp(
        {"entry": [_model_entry("Authentication", description=description)]}
    )

    result = CliRunner().invoke(
        cli, ["datamodels", "get", "Authentication", "--definition"]
    )
    assert result.exit_code == 0
    assert json.loads(result.output) == description


@patch(_PATCH)
def test_get_app_option_scopes_search(mock_gc: MagicMock) -> None:
    svc = mock_gc.return_value.service
    svc.get.return_value = _resp({"entry": [_model_entry("Authentication")]})

    result = CliRunner().invoke(
        cli, ["--json", "datamodels", "get", "Authentication", "--app", "Splunk_SA_CIM"]
    )
    assert result.exit_code == 0
    svc.get.assert_called_once_with(
        "datamodel/model",
        owner="nobody",
        app="Splunk_SA_CIM",
        output_mode="json",
        search="name=Authentication",
        count=1,
    )


# --- self-discovery ---


def test_commands_json_includes_datamodels_with_rebuild_guarded() -> None:
    result = CliRunner().invoke(cli, ["commands"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    group = next(c for c in data["commands"] if c["name"] == "datamodels")
    sub_names = [s["name"] for s in group["subcommands"]]
    assert sub_names == ["acceleration", "get", "list", "rebuild"]
    rebuild = next(s for s in group["subcommands"] if s["name"] == "rebuild")
    assert rebuild.get("guarded") is True
    for verb in ("list", "get", "acceleration"):
        cmd = next(s for s in group["subcommands"] if s["name"] == verb)
        assert not cmd.get("guarded")
