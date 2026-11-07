"""Tests for splunkctl.config."""

from pathlib import Path
from typing import Any

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
    assert d["verify"] is True


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
    p.write_text(yaml.dump({"host": "file-host", "port": 8089}))
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


# --- Profiles (schema v2) ---


# --- SOAR profile section (L1) ---


def test_soar_defaults() -> None:
    """soar_defaults returns correct default port and verify."""
    d = config.soar_defaults()
    assert d["port"] == 8443
    assert d["verify"] is True
    # No host/token/username/password defaults — those must be explicit.
    assert "host" not in d
    assert "token" not in d
    assert "username" not in d
    assert "password" not in d


def test_redact_soar_masks_secrets() -> None:
    """redact_soar masks token and password, keeps others."""
    soar_cfg: dict[str, Any] = {
        "host": "soar-host",
        "port": 8443,
        "token": "tok123",
        "username": "admin",
        "password": "s3cret",
        "verify": False,
    }
    r = config.redact_soar(soar_cfg)
    assert r["host"] == "soar-host"
    assert r["token"] == "****"
    assert r["password"] == "****"
    assert r["username"] == "admin"
    assert r["port"] == 8443


def test_redact_soar_keeps_empty_secrets() -> None:
    """Empty token/password stays empty, not redacted."""
    soar_cfg: dict[str, Any] = {"token": "", "password": ""}
    r = config.redact_soar(soar_cfg)
    assert r["token"] == ""
    assert r["password"] == ""


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ({"host": "https://splunk.example:8089", "extra": 1}, True),
        ({"host": "bare", "token": "secret"}, True),
        ({"token": "secret"}, True),
        ({"host": "bare"}, True),
        ({"host": "", "token": ""}, True),
        ({"profiles": {}, "host": "https://example"}, False),
        ({"host": "bare", "port": 8089}, False),
        ({"host": "bare", "scheme": "https"}, False),
        ({"username": "admin"}, False),
        ({"password": "secret"}, False),
        ({"token": 123}, False),
        ({}, False),
    ],
)
def test_foreign_detection(raw: dict[str, Any], expected: bool) -> None:
    assert config.is_foreign(raw) is expected


def _foreign_default() -> None:
    config.DEFAULT_PATH.parent.mkdir(parents=True, exist_ok=True)
    config.DEFAULT_PATH.write_text(
        "host: https://foreign.example:8089\ntoken: secret-value\n"
    )


def test_effective_path_explicit_never_redirects() -> None:
    _foreign_default()
    assert config.effective_path(config.DEFAULT_PATH) == (config.DEFAULT_PATH, False)


def test_effective_path_implicit_fallback() -> None:
    _foreign_default()
    assert config.effective_path(None) == (config.FALLBACK_PATH, True)


def test_effective_path_missing_default() -> None:
    assert config.effective_path(None) == (config.DEFAULT_PATH, False)


def test_effective_path_invalid_yaml_never_raises() -> None:
    config.DEFAULT_PATH.parent.mkdir(parents=True)
    config.DEFAULT_PATH.write_text("[invalid")
    assert config.effective_path(None) == (config.DEFAULT_PATH, False)


@pytest.mark.parametrize(
    "reader", ["resolve", "resolve_soar", "load", "profile_names", "is_v2_file"]
)
def test_explicit_foreign_read_refused(reader: str) -> None:
    _foreign_default()
    with pytest.raises(config.ForeignConfigError) as caught:
        getattr(config, reader)(config.DEFAULT_PATH)
    assert caught.value.path == config.DEFAULT_PATH
    assert (
        str(caught.value) == f"Splunk-format config at {config.DEFAULT_PATH}. "
        "Use --config to select another file."
    )


def test_implicit_missing_fallback_defaults() -> None:
    _foreign_default()
    assert config.load() == config.defaults()
    assert config.resolve_soar() == config.soar_defaults()
    assert config.profile_names() == ["default"]
    assert not config.is_v2_file()


def test_implicit_fallback_overlay(monkeypatch: pytest.MonkeyPatch) -> None:
    _foreign_default()
    config.FALLBACK_PATH.write_text(
        "host: fallback\nport: 9000\nsoar:\n  host: soar-fallback\n"
    )
    monkeypatch.setenv("SPLUNK_HOST", "env-host")
    monkeypatch.setenv("SOAR_TOKEN", "env-token")
    assert config.resolve()["cfg"]["host"] == "env-host"
    assert config.load()["port"] == 9000
    assert config.resolve_soar()["host"] == "soar-fallback"
    assert config.resolve_soar()["token"] == "env-token"


@pytest.mark.parametrize("writer", ["save", "save_profile", "use_profile"])
def test_foreign_write_preserves_bytes_and_mode(writer: str) -> None:
    _foreign_default()
    config.DEFAULT_PATH.chmod(0o640)
    before = config.DEFAULT_PATH.read_bytes()
    with pytest.raises(config.ForeignConfigError):
        _write_config(writer, config.DEFAULT_PATH)
    assert config.DEFAULT_PATH.read_bytes() == before
    assert config.DEFAULT_PATH.stat().st_mode & 0o777 == 0o640


def _write_config(writer: str, path: Path | None) -> None:
    if writer == "save":
        config.save({"host": "ours", "port": 8089}, path)
    elif writer == "save_profile":
        config.save_profile({"host": "ours"}, "new", path)
    else:
        config.use_profile("default", path)


@pytest.mark.parametrize("writer", ["save", "save_profile", "use_profile"])
def test_fallback_write_permissions(writer: str) -> None:
    _foreign_default()
    if writer == "use_profile":
        config.save_profile({"port": 8089}, "other")
        config.save_profile({"port": 9090}, "default")
        config.use_profile("other")
    _write_config(writer, None)
    assert config.FALLBACK_PATH.stat().st_mode & 0o777 == 0o600
    assert "secret-value" in config.DEFAULT_PATH.read_text()


@pytest.mark.parametrize("operation", ["load", "save", "save_profile", "use_profile"])
def test_foreign_fallback_refused(operation: str) -> None:
    _foreign_default()
    config.FALLBACK_PATH.write_text("token: foreign-fallback\n")
    with pytest.raises(config.ForeignConfigError):
        if operation == "load":
            config.load()
        else:
            _write_config(operation, None)
