"""Tests for splunkctl.config."""

from pathlib import Path

import pytest
import yaml

from splunkctl import config


def test_defaults_has_required_keys() -> None:
    d = config.defaults()
    assert "host" in d
    assert "port" in d
    assert "username" in d
    assert "scheme" in d
    assert d["port"] == 8089


def test_load_defaults_when_no_file(tmp_path: Path) -> None:
    cfg = config.load(tmp_path / "nonexistent.yaml")
    assert cfg == config.defaults()


def test_load_from_file(tmp_path: Path) -> None:
    p = tmp_path / "config.yaml"
    p.write_text(yaml.dump({"host": "splunk.example.com", "port": 9999}))
    cfg = config.load(p)
    assert cfg["host"] == "splunk.example.com"
    assert cfg["port"] == 9999
    assert cfg["username"] == "admin"


def test_load_env_overlay(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    p = tmp_path / "config.yaml"
    p.write_text(yaml.dump({"host": "file-host"}))
    monkeypatch.setenv("SPLUNK_HOST", "env-host")
    monkeypatch.setenv("SPLUNK_PORT", "1234")
    monkeypatch.setenv("SPLUNK_VERIFY", "true")
    cfg = config.load(p)
    assert cfg["host"] == "env-host"
    assert cfg["port"] == 1234
    assert cfg["verify"] is True


def test_load_empty_file(tmp_path: Path) -> None:
    p = tmp_path / "config.yaml"
    p.write_text("")
    cfg = config.load(p)
    assert cfg == config.defaults()


def test_save_creates_file(tmp_path: Path) -> None:
    p = tmp_path / "sub" / "config.yaml"
    config.save({"host": "saved-host", "port": 8089}, p)
    assert p.exists()
    loaded = yaml.safe_load(p.read_text())
    assert loaded["host"] == "saved-host"


def test_save_permissions(tmp_path: Path) -> None:
    p = tmp_path / "config.yaml"
    config.save(config.defaults(), p)
    mode = p.stat().st_mode
    assert mode & 0o777 == 0o600


def test_redact_masks_secrets() -> None:
    cfg = {"host": "localhost", "password": "s3cret", "token": "tok123"}
    r = config.redact(cfg)
    assert r["host"] == "localhost"
    assert r["password"] == "****"
    assert r["token"] == "****"


def test_redact_keeps_empty_secrets() -> None:
    cfg = {"password": "", "token": ""}
    r = config.redact(cfg)
    assert r["password"] == ""
    assert r["token"] == ""
