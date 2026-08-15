"""Tests for SplunkClient browser-session integration."""

import time
from pathlib import Path
from unittest.mock import patch

import pytest

from splunkctl import config as cfg_mod
from splunkctl.auth import session as sess_mod
from splunkctl.client import SplunkClient
from splunkctl.errors import WebSessionError


def _write_browser_profile(tmp_path: Path) -> Path:
    path = tmp_path / "cfg.yaml"
    cfg_mod.save(
        {
            "host": "100.65.1.10",
            "port": 8089,
            "scheme": "https",
            "web_url": "http://100.65.1.10:8000",
            "auth_mode": "browser",
            "verify": True,
        },
        path,
    )
    return path


def _record() -> sess_mod.SessionRecord:
    return sess_mod.SessionRecord(
        target="siem",
        profile="default",
        origin="http://100.65.1.10:8000",
        values={"session_key": "K", "cookie": "splunkd_8000"},
        acquired_at=time.time(),
        last_validated_at=time.time(),
    )


@patch("splunkctl.client.splunk_client.connect")
@patch("splunkctl.auth.adapters.requests.get")
def test_browser_session_becomes_splunk_token(
    mock_get, mock_connect, tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(cfg_mod, "DEFAULT_DIR", tmp_path / ".splunkctl")
    path = _write_browser_profile(tmp_path)
    sess_mod.save("default", _record())
    mock_get.return_value.status_code = 200

    client = SplunkClient(config_path=path)
    _ = client.service

    _, kwargs = mock_connect.call_args
    assert kwargs["splunkToken"] == "K"


@patch("splunkctl.client.splunk_client.connect")
def test_expired_browser_session_is_deleted_and_raises(
    mock_connect, tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(cfg_mod, "DEFAULT_DIR", tmp_path / ".splunkctl")
    path = _write_browser_profile(tmp_path)
    sess_mod.save("default", _record())
    with patch("splunkctl.auth.adapters.requests.get") as mock_get:
        mock_get.return_value.status_code = 401
        with pytest.raises(WebSessionError):
            _ = SplunkClient(config_path=path).service
    assert not sess_mod.session_path("default", "siem").exists()


@patch("splunkctl.client.splunk_client.connect")
def test_unreachable_browser_session_is_not_deleted(
    mock_connect, tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(cfg_mod, "DEFAULT_DIR", tmp_path / ".splunkctl")
    path = _write_browser_profile(tmp_path)
    sess_mod.save("default", _record())
    with patch("splunkctl.auth.adapters.requests.get") as mock_get:
        mock_get.side_effect = ConnectionError("refused")
        with pytest.raises(WebSessionError):
            _ = SplunkClient(config_path=path).service
    assert sess_mod.session_path("default", "siem").exists()
