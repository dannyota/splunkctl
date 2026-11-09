"""Tests for the browser session store and target resolver."""

import json
import os
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from splunkctl import config as cfg_mod
from splunkctl.auth import session as sess
from splunkctl.main import cli


def _record(*, origin: str = "https://siem:8000") -> sess.SessionRecord:
    return sess.SessionRecord(
        target="siem",
        profile="default",
        origin=origin,
        values={"session_key": "abc", "cookie": "splunkd_8000"},
        acquired_at=time.time(),
        last_validated_at=time.time(),
    )


def test_save_writes_0600_file_and_0700_dir(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(cfg_mod, "DEFAULT_DIR", tmp_path / ".splunkctl")
    sess.save("default", _record())
    p = sess.session_path("default", "siem")
    assert p.exists()
    assert (p.stat().st_mode & 0o777) == 0o600
    assert (p.parent.stat().st_mode & 0o777) == 0o700


def test_load_returns_record_on_origin_match(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(cfg_mod, "DEFAULT_DIR", tmp_path / ".splunkctl")
    sess.save("default", _record())
    rec = sess.load("default", "siem", expected_origin="https://siem:8000")
    assert rec is not None
    assert rec.values["session_key"] == "abc"


def test_load_rejects_origin_mismatch(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(cfg_mod, "DEFAULT_DIR", tmp_path / ".splunkctl")
    sess.save("default", _record())
    assert sess.load("default", "siem", expected_origin="https://other:8000") is None


def test_load_returns_none_when_missing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(cfg_mod, "DEFAULT_DIR", tmp_path / ".splunkctl")
    assert sess.load("default", "siem", expected_origin="x") is None
    assert not cfg_mod.DEFAULT_DIR.exists()


def test_delete_removes_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(cfg_mod, "DEFAULT_DIR", tmp_path / ".splunkctl")
    sess.save("default", _record())
    sess.delete("default", "siem")
    assert not sess.session_path("default", "siem").exists()


def test_save_is_atomic_and_serializes(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(cfg_mod, "DEFAULT_DIR", tmp_path / ".splunkctl")
    sess.save("default", _record())
    raw = json.loads(sess.session_path("default", "siem").read_text())
    assert raw["target"] == "siem"
    assert "session_key" in raw["values"]


def test_resolve_target_siem_derives_management_api_base(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(cfg_mod, "DEFAULT_DIR", tmp_path / ".splunkctl")
    monkeypatch.setattr(cfg_mod, "DEFAULT_PATH", tmp_path / "cfg.yaml")
    cfg_mod.save(
        {
            "host": "100.65.1.10",
            "port": 8089,
            "scheme": "https",
            "web_url": "http://100.65.1.10:8000",
            "auth_mode": "browser",
            "verify": True,
        },
        tmp_path / "cfg.yaml",
    )
    ta = sess.resolve_target(tmp_path / "cfg.yaml", None, "siem")
    assert ta.web_url == "http://100.65.1.10:8000"
    assert ta.login_url == "http://100.65.1.10:8000/en-US/account/login"
    assert ta.api_base == "https://100.65.1.10:8089"
    assert ta.profile == "default"


def test_resolve_target_soar_defaults_web_url_to_origin(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(cfg_mod, "DEFAULT_DIR", tmp_path / ".splunkctl")
    monkeypatch.setattr(cfg_mod, "DEFAULT_PATH", tmp_path / "cfg.yaml")
    cfg_mod.save(
        {
            "host": "100.65.1.10",
            "soar": {"host": "100.65.1.11", "port": 8443, "auth_mode": "browser"},
        },
        tmp_path / "cfg.yaml",
    )
    ta = sess.resolve_target(tmp_path / "cfg.yaml", None, "soar")
    assert ta.web_url == "https://100.65.1.11:8443"
    assert ta.login_url == "https://100.65.1.11:8443/login"
    assert ta.api_base == ta.web_url


def test_resolve_target_soar_uses_sso_url_for_login(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(cfg_mod, "DEFAULT_DIR", tmp_path / ".splunkctl")
    monkeypatch.setattr(cfg_mod, "DEFAULT_PATH", tmp_path / "cfg.yaml")
    sso = (
        "https://100.65.1.11:8443/saml2/login"
        "?idp=http://100.65.1.1:8080/realms/splunklab&next=/"
    )
    cfg_mod.save(
        {
            "host": "100.65.1.10",
            "soar": {
                "host": "100.65.1.11",
                "port": 8443,
                "auth_mode": "browser",
                "web_url": "https://100.65.1.11:8443",
                "sso_url": sso,
            },
        },
        tmp_path / "cfg.yaml",
    )
    ta = sess.resolve_target(tmp_path / "cfg.yaml", None, "soar")
    assert ta.web_url == "https://100.65.1.11:8443"
    assert ta.login_url == sso


def test_resolve_target_siem_requires_web_url(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(cfg_mod, "DEFAULT_DIR", tmp_path / ".splunkctl")
    monkeypatch.setattr(cfg_mod, "DEFAULT_PATH", tmp_path / "cfg.yaml")
    cfg_mod.save({"host": "100.65.1.10", "auth_mode": "browser"}, tmp_path / "cfg.yaml")
    with pytest.raises(sess.SessionError):
        sess.resolve_target(tmp_path / "cfg.yaml", None, "siem")


@pytest.mark.parametrize("existing", [False, True])
def test_sessions_root_is_private_under_shared_umask(tmp_path, monkeypatch, existing):
    root = tmp_path / ".splunkctl"
    root.mkdir(mode=0o775)
    root.chmod(0o775)
    monkeypatch.setattr(cfg_mod, "DEFAULT_DIR", root)
    if existing:
        (root / "sessions" / "default").mkdir(parents=True)
        for directory in (root / "sessions", root / "sessions" / "default"):
            directory.chmod(0o775)
    previous = os.umask(0o002)
    try:
        sess.save("default", _record())
        assert (cfg_mod.DEFAULT_DIR / "sessions").stat().st_mode & 0o777 == 0o700
        assert (root / "sessions" / "default").stat().st_mode & 0o777 == 0o700
        assert root.stat().st_mode & 0o777 == 0o775
    finally:
        os.umask(previous)


@pytest.mark.parametrize("reader", ["load", "status"])
def test_reads_preserve_read_only_session_dirs(tmp_path, monkeypatch, reader):
    monkeypatch.setattr(cfg_mod, "DEFAULT_DIR", tmp_path / ".splunkctl")
    cfg_mod.save({"host": "siem", "web_url": "https://siem:8000"})
    record = _record()
    sess.save("default", record)
    directories = (
        cfg_mod.DEFAULT_DIR / "sessions",
        cfg_mod.DEFAULT_DIR / "sessions" / "default",
    )
    for directory in directories:
        directory.chmod(0o500)
    try:
        if reader == "load":
            assert sess.load("default", "siem", expected_origin=record.origin) == record
        else:
            with patch("splunkctl.commands.auth.get_adapter") as adapter:
                adapter.return_value.validate.return_value = "valid"
                result = CliRunner().invoke(
                    cli, ["--json", "auth", "status", "--target", "siem"]
                )
            assert result.exit_code == 0, result.output
            assert json.loads(result.output) == [{"target": "siem", "status": "valid"}]
        for directory in directories:
            assert directory.stat().st_mode & 0o777 == 0o500
    finally:
        for directory in directories:
            directory.chmod(0o700)
