"""Tests for doctor command."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from splunkctl.main import cli

_PATCH = "splunkctl.commands.doctor.get_client"
_PATCH_SOAR_RESOLVE = "splunkctl.commands.doctor.cfg_mod.resolve_soar"
_PATCH_SOAR_CLIENT = "splunkctl.soar.client.SOARClient"


def _mock_service() -> MagicMock:
    svc = MagicMock()
    svc.username = "admin"
    svc.host = "splunk.example.com"
    svc.info = {
        "version": "10.4.0",
        "os_name": "Linux",
        "os_version": "5.15",
        "mode": "normal",
        "licenseState": "OK",
        "isTrial": "0",
    }

    health_resp = MagicMock()
    health_resp.body.read.return_value = json.dumps(
        {"entry": [{"content": {"health": "green"}}]}
    ).encode()
    svc.get.return_value = health_resp

    svc.messages.list.return_value = []

    user = MagicMock()
    user.content = {
        "roles": ["admin"],
        "capabilities": [
            "search",
            "admin_all_objects",
            "edit_user",
            "edit_roles",
            "edit_tcp",
            "edit_monitor",
            "list_inputs",
            "rest_apps_management",
            "change_own_password",
        ],
    }
    svc.users.__getitem__.return_value = user

    web_entity = MagicMock()
    web_entity.__getitem__ = MagicMock(
        side_effect=lambda k: "8000" if k == "httpport" else "",
    )
    web_entity.content = {"enableSplunkWebSSL": "0"}
    svc.confs.__getitem__.return_value.__getitem__.return_value = web_entity

    return svc


@patch("splunkctl.commands.doctor.urllib.request")
@patch(_PATCH)
def test_doctor_all_pass(mock_gc: MagicMock, mock_urllib: MagicMock) -> None:
    svc = _mock_service()
    mock_gc.return_value.service = svc

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_urllib.build_opener.return_value.open.return_value = mock_resp
    mock_urllib.HTTPSHandler = MagicMock()

    result = CliRunner().invoke(cli, ["doctor"])
    assert result.exit_code == 0
    assert "PASS  REST API reachable" in result.stderr
    assert "PASS  Authenticated" in result.stderr
    assert "PASS  cap:search" in result.stderr
    assert "0 failures" in result.stderr


@patch(_PATCH)
def test_doctor_connection_fail(mock_gc: MagicMock) -> None:
    mock_client = MagicMock()
    type(mock_client).service = property(
        lambda self: (_ for _ in ()).throw(
            ConnectionError("refused"),
        ),
    )
    mock_gc.return_value = mock_client

    result = CliRunner().invoke(cli, ["doctor"])
    assert result.exit_code != 0
    assert "FAIL" in result.stderr


@patch("splunkctl.commands.doctor.urllib.request")
@patch(_PATCH)
def test_doctor_json_output(mock_gc: MagicMock, mock_urllib: MagicMock) -> None:
    svc = _mock_service()
    mock_gc.return_value.service = svc

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_urllib.build_opener.return_value.open.return_value = mock_resp
    mock_urllib.HTTPSHandler = MagicMock()

    result = CliRunner().invoke(cli, ["--json", "doctor"])
    assert result.exit_code == 0
    assert '"check"' in result.output
    assert '"REST API reachable"' in result.output
    assert '"cap:search"' in result.output


@patch("splunkctl.commands.doctor.urllib.request")
@patch(_PATCH)
def test_doctor_hint_on_fail(mock_gc: MagicMock, mock_urllib: MagicMock) -> None:
    mock_client = MagicMock()
    type(mock_client).service = property(
        lambda self: (_ for _ in ()).throw(
            ConnectionError("refused"),
        ),
    )
    mock_gc.return_value = mock_client

    result = CliRunner().invoke(cli, ["doctor"])
    assert "hint:" in result.stderr
    assert "SPLUNK_HOST" in result.stderr


@patch("splunkctl.commands.doctor.urllib.request")
@patch(_PATCH)
def test_doctor_strict_warns_fail(mock_gc: MagicMock, mock_urllib: MagicMock) -> None:
    svc = _mock_service()
    svc.info["licenseState"] = "EXPIRED"
    mock_gc.return_value.service = svc

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_urllib.build_opener.return_value.open.return_value = mock_resp
    mock_urllib.HTTPSHandler = MagicMock()

    result_normal = CliRunner().invoke(cli, ["doctor"])
    assert result_normal.exit_code == 0

    result_strict = CliRunner().invoke(cli, ["doctor", "--strict"])
    assert result_strict.exit_code != 0


@patch("splunkctl.commands.doctor.urllib.request")
@patch(_PATCH)
def test_doctor_mcp_not_registered(
    mock_gc: MagicMock, mock_urllib: MagicMock, tmp_path: Path
) -> None:
    svc = _mock_service()
    mock_gc.return_value.service = svc

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_urllib.build_opener.return_value.open.return_value = mock_resp
    mock_urllib.HTTPSHandler = MagicMock()

    with patch("splunkctl.commands.doctor.Path.cwd", return_value=tmp_path):
        result = CliRunner().invoke(cli, ["doctor"])
    assert ".mcp.json not found" in result.stderr


@patch("splunkctl.commands.doctor.urllib.request")
@patch(_PATCH)
def test_doctor_json_includes_hints(mock_gc: MagicMock, mock_urllib: MagicMock) -> None:
    svc = _mock_service()
    svc.info["licenseState"] = "EXPIRED"
    mock_gc.return_value.service = svc

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_urllib.build_opener.return_value.open.return_value = mock_resp
    mock_urllib.HTTPSHandler = MagicMock()

    result = CliRunner().invoke(cli, ["--json", "doctor"])
    assert result.exit_code == 0
    assert '"hint"' in result.output
    assert '"WARN"' in result.output


# -------------------------------------------------------------------
# SOAR section tests
# -------------------------------------------------------------------


def _soar_cfg(
    *,
    host: str = "soar.test",
    port: int = 8443,
    token: str = "tok123",  # noqa: S107
    verify: bool = False,
) -> dict[str, object]:
    return {"host": host, "port": port, "token": token, "verify": verify}


def _soar_responses_all_pass() -> dict[str, object]:
    """Mock SOAR client.get responses for all-pass scenario."""
    return {
        "version": {"version": "8.5.0.248"},
        "health": {
            "status": {"nginx": "running", "splunkd": "running"},
        },
        "license": {
            "license_info": {"maximum_actions_per_day": 1000},
            "current_usage": {"recent_app_run_count": 42},
        },
    }


@patch(_PATCH_SOAR_RESOLVE)
@patch("splunkctl.commands.doctor.urllib.request")
@patch(_PATCH)
def test_doctor_soar_all_pass(
    mock_gc: MagicMock,
    mock_urllib: MagicMock,
    mock_soar_resolve: MagicMock,
) -> None:
    """SOAR section passes when version/health/license all return OK."""
    svc = _mock_service()
    mock_gc.return_value.service = svc

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_urllib.build_opener.return_value.open.return_value = mock_resp
    mock_urllib.HTTPSHandler = MagicMock()

    mock_soar_resolve.return_value = _soar_cfg()
    responses = _soar_responses_all_pass()

    with patch(_PATCH_SOAR_CLIENT) as mock_cls:
        soar = MagicMock()
        soar.get.side_effect = lambda path, **kw: responses.get(path, {})
        mock_cls.return_value = soar

        result = CliRunner().invoke(cli, ["doctor"])

    assert result.exit_code == 0
    assert "PASS  SOAR connection" in result.stderr
    assert "soar.test v8.5.0.248" in result.stderr
    assert "PASS  SOAR auth" in result.stderr
    assert "PASS  SOAR health" in result.stderr
    assert "all daemons running" in result.stderr
    assert "PASS  SOAR license" in result.stderr
    assert "quota 42/1000 actions/day" in result.stderr


@patch(_PATCH_SOAR_RESOLVE)
@patch("splunkctl.commands.doctor.urllib.request")
@patch(_PATCH)
def test_doctor_soar_skip_no_profile(
    mock_gc: MagicMock,
    mock_urllib: MagicMock,
    mock_soar_resolve: MagicMock,
) -> None:
    """SOAR section skipped when no soar: host in profile."""
    svc = _mock_service()
    mock_gc.return_value.service = svc

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_urllib.build_opener.return_value.open.return_value = mock_resp
    mock_urllib.HTTPSHandler = MagicMock()

    # No host → skip
    mock_soar_resolve.return_value = {"port": 8443, "verify": False}

    result = CliRunner().invoke(cli, ["doctor"])
    assert result.exit_code == 0
    assert "[SOAR] skipped" in result.stderr
    assert "no soar profile configured" in result.stderr


@patch(_PATCH_SOAR_RESOLVE)
@patch("splunkctl.commands.doctor.urllib.request")
@patch(_PATCH)
def test_doctor_soar_connection_fail(
    mock_gc: MagicMock,
    mock_urllib: MagicMock,
    mock_soar_resolve: MagicMock,
) -> None:
    """SOAR section fails gracefully on connection error; remaining checks skipped."""
    svc = _mock_service()
    mock_gc.return_value.service = svc

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_urllib.build_opener.return_value.open.return_value = mock_resp
    mock_urllib.HTTPSHandler = MagicMock()

    mock_soar_resolve.return_value = _soar_cfg()

    with patch(_PATCH_SOAR_CLIENT) as mock_cls:
        soar = MagicMock()
        soar.get.side_effect = ConnectionError("refused")
        mock_cls.return_value = soar

        result = CliRunner().invoke(cli, ["doctor"])

    assert result.exit_code != 0
    assert "FAIL  SOAR connection" in result.stderr
    # Auth/health/license should not appear (early return on connection fail)
    assert "SOAR auth" not in result.stderr
    assert "SOAR health" not in result.stderr


@patch(_PATCH_SOAR_RESOLVE)
@patch("splunkctl.commands.doctor.urllib.request")
@patch(_PATCH)
def test_doctor_soar_health_degraded(
    mock_gc: MagicMock,
    mock_urllib: MagicMock,
    mock_soar_resolve: MagicMock,
) -> None:
    """SOAR health warns when a daemon is not running."""
    svc = _mock_service()
    mock_gc.return_value.service = svc

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_urllib.build_opener.return_value.open.return_value = mock_resp
    mock_urllib.HTTPSHandler = MagicMock()

    mock_soar_resolve.return_value = _soar_cfg()
    responses: dict[str, object] = {
        "version": {"version": "8.5.0"},
        "health": {
            "status": {"nginx": "running", "crond": "stopped"},
        },
        "license": {"status": "valid"},
    }

    with patch(_PATCH_SOAR_CLIENT) as mock_cls:
        soar = MagicMock()
        soar.get.side_effect = lambda path, **kw: responses.get(path, {})
        mock_cls.return_value = soar

        result = CliRunner().invoke(cli, ["doctor"])

    assert "WARN  SOAR health" in result.stderr
    assert "degraded: crond" in result.stderr


@patch(_PATCH_SOAR_RESOLVE)
@patch("splunkctl.commands.doctor.urllib.request")
@patch(_PATCH)
def test_doctor_soar_license_quota_exceeded(
    mock_gc: MagicMock,
    mock_urllib: MagicMock,
    mock_soar_resolve: MagicMock,
) -> None:
    """SOAR license warns when actions used >= quota."""
    svc = _mock_service()
    mock_gc.return_value.service = svc

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_urllib.build_opener.return_value.open.return_value = mock_resp
    mock_urllib.HTTPSHandler = MagicMock()

    mock_soar_resolve.return_value = _soar_cfg()
    responses: dict[str, object] = {
        "version": {"version": "8.5.0"},
        "health": {"status": {"nginx": "running"}},
        "license": {
            "license_info": {"maximum_actions_per_day": 100},
            "current_usage": {"recent_app_run_count": 100},
        },
    }

    with patch(_PATCH_SOAR_CLIENT) as mock_cls:
        soar = MagicMock()
        soar.get.side_effect = lambda path, **kw: responses.get(path, {})
        mock_cls.return_value = soar

        result = CliRunner().invoke(cli, ["doctor"])

    assert "WARN  SOAR license" in result.stderr
    assert "quota 100/100" in result.stderr


@patch(_PATCH_SOAR_RESOLVE)
@patch("splunkctl.commands.doctor.urllib.request")
@patch(_PATCH)
def test_doctor_soar_json_output(
    mock_gc: MagicMock,
    mock_urllib: MagicMock,
    mock_soar_resolve: MagicMock,
) -> None:
    """SOAR checks appear in JSON output."""
    svc = _mock_service()
    mock_gc.return_value.service = svc

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_urllib.build_opener.return_value.open.return_value = mock_resp
    mock_urllib.HTTPSHandler = MagicMock()

    mock_soar_resolve.return_value = _soar_cfg()
    responses = _soar_responses_all_pass()

    with patch(_PATCH_SOAR_CLIENT) as mock_cls:
        soar = MagicMock()
        soar.get.side_effect = lambda path, **kw: responses.get(path, {})
        mock_cls.return_value = soar

        result = CliRunner().invoke(cli, ["--json", "doctor"])

    assert result.exit_code == 0
    assert '"SOAR connection"' in result.output
    assert '"SOAR auth"' in result.output
    assert '"SOAR health"' in result.output
    assert '"SOAR license"' in result.output


@patch(_PATCH_SOAR_RESOLVE)
@patch("splunkctl.commands.doctor.urllib.request")
@patch(_PATCH)
def test_doctor_soar_skip_json_output(
    mock_gc: MagicMock,
    mock_urllib: MagicMock,
    mock_soar_resolve: MagicMock,
) -> None:
    """SOAR skip result appears in JSON output with SKIP status."""
    svc = _mock_service()
    mock_gc.return_value.service = svc

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_urllib.build_opener.return_value.open.return_value = mock_resp
    mock_urllib.HTTPSHandler = MagicMock()

    mock_soar_resolve.return_value = {"port": 8443, "verify": False}

    result = CliRunner().invoke(cli, ["--json", "doctor"])
    assert result.exit_code == 0
    assert '"SOAR"' in result.output
    assert '"SKIP"' in result.output


@patch(_PATCH_SOAR_RESOLVE)
@patch("splunkctl.commands.doctor.urllib.request")
@patch(_PATCH)
def test_doctor_soar_basic_auth(
    mock_gc: MagicMock,
    mock_urllib: MagicMock,
    mock_soar_resolve: MagicMock,
) -> None:
    """SOAR auth detail shows 'basic' when no token is set."""
    svc = _mock_service()
    mock_gc.return_value.service = svc

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_urllib.build_opener.return_value.open.return_value = mock_resp
    mock_urllib.HTTPSHandler = MagicMock()

    cfg = _soar_cfg()
    cfg["token"] = None  # no token → basic auth
    mock_soar_resolve.return_value = cfg
    responses = _soar_responses_all_pass()

    with patch(_PATCH_SOAR_CLIENT) as mock_cls:
        soar = MagicMock()
        soar.get.side_effect = lambda path, **kw: responses.get(path, {})
        mock_cls.return_value = soar

        result = CliRunner().invoke(cli, ["doctor"])

    assert "token=basic" in result.stderr
