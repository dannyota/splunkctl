"""Tests for doctor command."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from splunkctl import config as cfg_mod
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


@patch(_PATCH)
def test_doctor_config_pass(mock_gc: MagicMock) -> None:
    cfg_mod.DEFAULT_PATH.parent.mkdir(parents=True)
    cfg_mod.DEFAULT_PATH.write_text("profiles: {}\n")
    type(mock_gc.return_value).service = property(
        lambda self: (_ for _ in ()).throw(ConnectionError("offline"))
    )
    result = CliRunner().invoke(cli, ["--json", "doctor"])
    assert "PASS  Config" in result.stderr
    assert json.loads(result.stdout)[0] == {
        "check": "Config",
        "status": "OK",
        "detail": str(cfg_mod.DEFAULT_PATH),
    }


@patch(_PATCH)
def test_doctor_config_fallback(mock_gc: MagicMock) -> None:
    cfg_mod.DEFAULT_PATH.parent.mkdir(parents=True)
    cfg_mod.DEFAULT_PATH.write_text("host: bare\ntoken: foreign-secret\n")
    cfg_mod.FALLBACK_PATH.write_text("profiles: {}\n")
    type(mock_gc.return_value).service = property(
        lambda self: (_ for _ in ()).throw(ConnectionError("offline"))
    )
    result = CliRunner().invoke(cli, ["--json", "doctor"])
    assert "PASS  Config" in result.stderr
    assert (
        f"{cfg_mod.FALLBACK_PATH} "
        "(fallback: Splunk-format config at ~/.splunkctl/config.yaml)" in result.stderr
    )


@patch(_PATCH)
def test_doctor_foreign_strict_json_no_network(
    mock_gc: MagicMock, tmp_path: Path
) -> None:
    dest = tmp_path / "foreign.yaml"
    dest.write_text("host: bare\ntoken: foreign-secret\n")
    result = CliRunner().invoke(
        cli, ["--json", "--config", str(dest), "doctor", "--strict"]
    )
    assert result.exit_code == 1
    mock_gc.assert_not_called()
    rows = json.loads(result.stdout)
    assert rows == [
        {
            "check": "Config",
            "status": "FAIL",
            "detail": (
                f"Splunk-format config at {dest}: this is a flat host/token file "
                "written by Splunk's splunkctl. Pass a profiles file with --config, "
                "or create one with: splunkctl config init --path FILE"
            ),
            "hint": "Run splunkctl config init --path ~/.splunkctl/profiles.yaml",
        }
    ]


@pytest.mark.parametrize("strict", [False, True])
@pytest.mark.parametrize("mode", ["default", "explicit", "fallback"])
@patch("splunkctl.commands.doctor.urllib.request")
@patch(_PATCH)
def test_doctor_missing_config_warns_and_continues(
    mock_gc: MagicMock,
    mock_urllib: MagicMock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    strict: bool,
    mode: str,
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".mcp.json").write_text('{"mcpServers": {"splunkctl": {}}}')
    svc = _mock_service()
    svc.get.return_value.body.read.return_value = json.dumps(
        {"entry": [{"content": {"health": "green", "current": {"status": "ready"}}}]}
    ).encode()
    mock_gc.return_value.service = svc
    mock_urllib.build_opener.return_value.open.return_value.status = 200
    config_path = cfg_mod.DEFAULT_PATH
    args = ["--json"]
    if mode == "explicit":
        config_path = tmp_path / "missing.yaml"
        args += ["--config", str(config_path)]
    elif mode == "fallback":
        cfg_mod.DEFAULT_PATH.parent.mkdir(parents=True)
        cfg_mod.DEFAULT_PATH.write_text("host: bare\ntoken: foreign-secret\n")
        config_path = cfg_mod.FALLBACK_PATH
    args += ["doctor"]
    if strict:
        args += ["--strict"]

    result = CliRunner().invoke(cli, args)

    assert result.exit_code == (1 if strict else 0), result.output
    rows = json.loads(result.stdout)
    assert rows[0] == {
        "check": "Config",
        "status": "WARN",
        "detail": (
            f"{config_path} (not found; using defaults and environment variables)"
        ),
        "hint": "Run splunkctl config init",
    }
    assert "WARN  Config" in result.stderr
    assert "PASS  Config" not in result.stderr
    assert "hint: Run splunkctl config init" in result.stderr
    assert "PASS  REST API reachable" in result.stderr
    assert "1 warnings, 0 failures" in result.stderr
    assert rows[-1]["check"] == "MCP registered"
    assert not config_path.exists()
