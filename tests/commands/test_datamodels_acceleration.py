"""Tests for datamodels acceleration status and rebuild.

Split out of test_datamodels.py (which covers list/get) purely for the
line-count budget — same domain, same REST layer (see kvstore.py's own
test_kvstore.py/test_kvstore_data.py split for the precedent).
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


def _summarization_entry(name: str, content: dict[str, object]) -> dict[str, object]:
    return {"name": name, "content": content}


# --- acceleration ---


@patch(_PATCH)
def test_acceleration_reports_none_accelerated_without_second_call(
    mock_gc: MagicMock,
) -> None:
    svc = mock_gc.return_value.service
    svc.get.return_value = _resp(
        {"entry": [_model_entry("internal_server", accelerated=False)]}
    )

    result = CliRunner().invoke(cli, ["--json", "datamodels", "acceleration"])
    assert result.exit_code == 0
    assert json.loads(result.output) == []
    # no accelerated models -> never bothers fetching admin/summarization
    svc.get.assert_called_once()


@patch(_PATCH)
def test_acceleration_status_for_accelerated_models(mock_gc: MagicMock) -> None:
    svc = mock_gc.return_value.service
    svc.get.side_effect = [
        _resp(
            {
                "entry": [
                    _model_entry(
                        "Authentication", app="Splunk_SA_CIM", accelerated=True
                    ),
                    _model_entry(
                        "Network_Traffic", app="Splunk_SA_CIM", accelerated=False
                    ),
                ]
            }
        ),
        _resp(
            {
                "entry": [
                    _summarization_entry(
                        "tstats:DM_Splunk_SA_CIM_Authentication",
                        {
                            "summary.complete": "0.5",
                            "summary.size": "1048576",
                            "summary.earliest_time": "1700000000",
                            "summary.latest_time": "1700086400",
                            "summary.last_error": [],
                        },
                    )
                ]
            }
        ),
    ]

    result = CliRunner().invoke(cli, ["--json", "datamodels", "acceleration"])
    assert result.exit_code == 0
    rows = json.loads(result.output)
    assert rows == [
        {
            "name": "Authentication",
            "app": "Splunk_SA_CIM",
            "enabled": True,
            "has_summary": True,
            "is_complete": False,
            "percent_complete": 50.0,
            "size": "1048576",
            "earliest_summarized": "1700000000",
            "latest_summarized": "1700086400",
            "last_error": "",
        }
    ]
    assert svc.get.call_args_list[1].kwargs == {
        "owner": "nobody",
        "app": "-",
        "output_mode": "json",
        "count": 0,
    }
    assert svc.get.call_args_list[1].args == ("admin/summarization",)


@patch(_PATCH)
def test_acceleration_no_summary_yet_has_no_exception(mock_gc: MagicMock) -> None:
    svc = mock_gc.return_value.service
    svc.get.side_effect = [
        _resp({"entry": [_model_entry("Authentication", accelerated=True)]}),
        _resp({"entry": []}),
    ]

    result = CliRunner().invoke(cli, ["--json", "datamodels", "acceleration"])
    assert result.exit_code == 0
    rows = json.loads(result.output)
    assert rows[0]["has_summary"] is False
    assert rows[0]["percent_complete"] is None
    assert rows[0]["is_complete"] is None


@patch(_PATCH)
def test_acceleration_complete_model(mock_gc: MagicMock) -> None:
    svc = mock_gc.return_value.service
    svc.get.side_effect = [
        _resp({"entry": [_model_entry("Authentication", accelerated=True)]}),
        _resp(
            {
                "entry": [
                    _summarization_entry(
                        "tstats:DM_search_Authentication",
                        {"summary.complete": "1.0", "summary.last_error": ["boom"]},
                    )
                ]
            }
        ),
    ]

    result = CliRunner().invoke(cli, ["--json", "datamodels", "acceleration"])
    assert result.exit_code == 0
    row = json.loads(result.output)[0]
    assert row["percent_complete"] == 100.0
    assert row["is_complete"] is True
    assert row["last_error"] == "boom"


@patch(_PATCH)
def test_acceleration_named_model_not_found(mock_gc: MagicMock) -> None:
    svc = mock_gc.return_value.service
    svc.get.return_value = _resp({"entry": []})

    result = CliRunner().invoke(cli, ["--json", "datamodels", "acceleration", "nope"])
    assert result.exit_code == 1
    err = json.loads(result.stderr)["error"]
    assert err["kind"] == "not_found"


@patch(_PATCH)
def test_acceleration_named_model_not_accelerated_shows_row(mock_gc: MagicMock) -> None:
    svc = mock_gc.return_value.service
    svc.get.side_effect = [
        _resp({"entry": [_model_entry("internal_server", accelerated=False)]}),
        _resp({"entry": []}),
    ]

    result = CliRunner().invoke(
        cli, ["--json", "datamodels", "acceleration", "internal_server"]
    )
    assert result.exit_code == 0
    row = json.loads(result.output)[0]
    assert row["enabled"] is False
    assert row["has_summary"] is False


# --- rebuild ---


@patch(_PATCH)
def test_rebuild_dry_run_no_post_calls(mock_gc: MagicMock) -> None:
    svc = mock_gc.return_value.service
    svc.get.return_value = _resp(
        {
            "entry": [
                _model_entry("Authentication", accelerated=True, earliest_time="-30d")
            ]
        }
    )

    result = CliRunner().invoke(cli, ["datamodels", "rebuild", "Authentication"])
    assert result.exit_code == 0
    assert "[DRY RUN]" in result.stderr
    assert "Authentication" in result.stderr
    svc.post.assert_not_called()


@patch(_PATCH)
def test_rebuild_not_accelerated_rejected_even_with_yes(mock_gc: MagicMock) -> None:
    svc = mock_gc.return_value.service
    svc.get.return_value = _resp(
        {"entry": [_model_entry("internal_server", accelerated=False)]}
    )

    result = CliRunner().invoke(
        cli, ["--yes", "--json", "datamodels", "rebuild", "internal_server"]
    )
    assert result.exit_code == 1
    err = json.loads(result.stderr)["error"]
    assert "not accelerated" in err["message"].lower()
    svc.post.assert_not_called()


@patch(_PATCH)
def test_rebuild_not_found(mock_gc: MagicMock) -> None:
    svc = mock_gc.return_value.service
    svc.get.return_value = _resp({"entry": []})

    result = CliRunner().invoke(
        cli, ["--yes", "--json", "datamodels", "rebuild", "nope"]
    )
    assert result.exit_code == 1
    err = json.loads(result.stderr)["error"]
    assert err["kind"] == "not_found"
    svc.post.assert_not_called()


@patch(_PATCH)
def test_rebuild_applies_with_yes_disables_then_reenables(mock_gc: MagicMock) -> None:
    svc = mock_gc.return_value.service
    svc.get.return_value = _resp(
        {
            "entry": [
                _model_entry(
                    "Authentication",
                    app="Splunk_SA_CIM",
                    accelerated=True,
                    earliest_time="-30d",
                )
            ]
        }
    )

    result = CliRunner().invoke(
        cli, ["--yes", "datamodels", "rebuild", "Authentication"]
    )
    assert result.exit_code == 0
    assert svc.post.call_count == 2
    first = svc.post.call_args_list[0]
    second = svc.post.call_args_list[1]
    assert first.args == ("datamodel/model/Authentication",)
    assert first.kwargs == {
        "owner": "nobody",
        "app": "Splunk_SA_CIM",
        "acceleration": "0",
    }
    assert second.args == ("datamodel/model/Authentication",)
    assert second.kwargs == {
        "owner": "nobody",
        "app": "Splunk_SA_CIM",
        "acceleration": "1",
        "acceleration.earliest_time": "-30d",
    }


@patch(_PATCH)
def test_rebuild_permission_denied_classified_envelope(mock_gc: MagicMock) -> None:
    svc = mock_gc.return_value.service
    svc.get.return_value = _resp(
        {"entry": [_model_entry("Authentication", accelerated=True)]}
    )
    svc.post.side_effect = _http_error(403, "Forbidden", "cannot modify acceleration")

    result = CliRunner().invoke(
        cli, ["--yes", "--json", "datamodels", "rebuild", "Authentication"]
    )
    assert result.exit_code == 1
    last_line = result.stderr.strip().splitlines()[-1]
    err = json.loads(last_line)["error"]
    assert err["kind"] == "permission"
    assert err["http_status"] == 403
