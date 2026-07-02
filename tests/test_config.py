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


# --- Profiles (schema v2) ---


def _write_v2(path: Path, profiles: dict[str, Any], current: str | None = None) -> None:
    raw: dict[str, Any] = {"profiles": profiles}
    if current is not None:
        raw["current"] = current
    path.write_text(yaml.dump(raw, sort_keys=False))


def test_load_v2_uses_current_pointer(tmp_path: Path) -> None:
    p = tmp_path / "config.yaml"
    _write_v2(
        p,
        {"dev": {"host": "dev-host"}, "uat": {"host": "uat-host"}},
        current="uat",
    )
    cfg = config.load(p)
    assert cfg["host"] == "uat-host"


def test_load_v2_defaults_to_default_profile_when_no_current(tmp_path: Path) -> None:
    p = tmp_path / "config.yaml"
    _write_v2(p, {"default": {"host": "default-host"}, "uat": {"host": "uat-host"}})
    cfg = config.load(p)
    assert cfg["host"] == "default-host"


def test_load_v2_profile_flag_overrides_current(tmp_path: Path) -> None:
    p = tmp_path / "config.yaml"
    _write_v2(
        p,
        {"dev": {"host": "dev-host"}, "prod": {"host": "prod-host"}},
        current="dev",
    )
    cfg = config.load(p, profile="prod")
    assert cfg["host"] == "prod-host"


def test_load_v2_missing_profile_raises_not_found(tmp_path: Path) -> None:
    p = tmp_path / "config.yaml"
    _write_v2(p, {"dev": {"host": "dev-host"}})
    with pytest.raises(config.ProfileNotFoundError) as exc_info:
        config.load(p, profile="uat")
    assert exc_info.value.name == "uat"


def test_load_legacy_file_as_implicit_default(tmp_path: Path) -> None:
    p = tmp_path / "config.yaml"
    p.write_text(yaml.dump({"host": "legacy-host"}))
    cfg = config.load(p, profile="default")
    assert cfg["host"] == "legacy-host"


def test_load_legacy_file_requesting_other_profile_raises(tmp_path: Path) -> None:
    p = tmp_path / "config.yaml"
    p.write_text(yaml.dump({"host": "legacy-host"}))
    with pytest.raises(config.ProfileNotFoundError):
        config.load(p, profile="uat")


def test_load_no_file_requesting_named_profile_raises(tmp_path: Path) -> None:
    with pytest.raises(config.ProfileNotFoundError):
        config.load(tmp_path / "nonexistent.yaml", profile="uat")


def test_resolve_env_overrides_profile_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    p = tmp_path / "config.yaml"
    _write_v2(p, {"uat": {"host": "uat-host", "username": "uat-user"}}, current="uat")
    monkeypatch.setenv("SPLUNK_HOST", "env-host")
    resolved = config.resolve(p)
    assert resolved["cfg"]["host"] == "env-host"
    assert resolved["cfg"]["username"] == "uat-user"
    assert resolved["profile"] == "uat"
    assert resolved["source"] == "env"


def test_resolve_source_is_profile_when_no_overlay(tmp_path: Path) -> None:
    p = tmp_path / "config.yaml"
    _write_v2(p, {"uat": {"host": "uat-host"}}, current="uat")
    resolved = config.resolve(p)
    assert resolved["source"] == "profile"
    assert resolved["profile"] == "uat"


def test_resolve_source_is_flags_when_overrides_win(tmp_path: Path) -> None:
    p = tmp_path / "config.yaml"
    _write_v2(p, {"uat": {"host": "uat-host"}}, current="uat")
    resolved = config.resolve(p, overrides={"host": "flag-host"})
    assert resolved["cfg"]["host"] == "flag-host"
    assert resolved["source"] == "flags"


def test_resolve_flags_beat_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    p = tmp_path / "config.yaml"
    _write_v2(p, {"uat": {"host": "uat-host"}}, current="uat")
    monkeypatch.setenv("SPLUNK_HOST", "env-host")
    resolved = config.resolve(p, overrides={"host": "flag-host"})
    assert resolved["cfg"]["host"] == "flag-host"
    assert resolved["source"] == "flags"


def test_resolve_non_identity_env_does_not_flip_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    p = tmp_path / "config.yaml"
    _write_v2(p, {"uat": {"host": "uat-host"}}, current="uat")
    monkeypatch.setenv("SPLUNK_APP", "search")
    resolved = config.resolve(p)
    assert resolved["source"] == "profile"


def test_profile_names_v2(tmp_path: Path) -> None:
    p = tmp_path / "config.yaml"
    _write_v2(p, {"dev": {}, "uat": {}, "prod": {}}, current="uat")
    assert config.profile_names(p) == ["dev", "prod", "uat"]


def test_profile_names_legacy(tmp_path: Path) -> None:
    p = tmp_path / "config.yaml"
    p.write_text(yaml.dump({"host": "h"}))
    assert config.profile_names(p) == ["default"]


def test_profile_names_no_file(tmp_path: Path) -> None:
    assert config.profile_names(tmp_path / "nonexistent.yaml") == ["default"]


def test_save_profile_creates_v2_from_scratch(tmp_path: Path) -> None:
    p = tmp_path / "config.yaml"
    config.save_profile({"host": "uat-host"}, "uat", p)
    raw = yaml.safe_load(p.read_text())
    assert raw["profiles"]["uat"]["host"] == "uat-host"
    assert "current" not in raw


def test_save_profile_upgrades_legacy_preserving_default(tmp_path: Path) -> None:
    p = tmp_path / "config.yaml"
    p.write_text(yaml.dump({"host": "legacy-host", "port": 8089}))
    config.save_profile({"host": "uat-host", "port": 8089}, "uat", p)
    raw = yaml.safe_load(p.read_text())
    assert raw["profiles"]["default"]["host"] == "legacy-host"
    assert raw["profiles"]["uat"]["host"] == "uat-host"


def test_save_profile_preserves_0600(tmp_path: Path) -> None:
    p = tmp_path / "config.yaml"
    p.write_text(yaml.dump({"host": "legacy-host"}))
    config.save_profile({"host": "uat-host"}, "uat", p)
    mode = p.stat().st_mode
    assert mode & 0o777 == 0o600


def test_save_profile_preserves_siblings_and_current(tmp_path: Path) -> None:
    p = tmp_path / "config.yaml"
    _write_v2(p, {"dev": {"host": "dev-host"}}, current="dev")
    config.save_profile({"host": "uat-host"}, "uat", p)
    raw = yaml.safe_load(p.read_text())
    assert raw["profiles"]["dev"]["host"] == "dev-host"
    assert raw["profiles"]["uat"]["host"] == "uat-host"
    assert raw["current"] == "dev"


def test_use_profile_sets_current(tmp_path: Path) -> None:
    p = tmp_path / "config.yaml"
    _write_v2(p, {"dev": {"host": "dev-host"}, "uat": {"host": "uat-host"}})
    config.use_profile("uat", p)
    raw = yaml.safe_load(p.read_text())
    assert raw["current"] == "uat"


def test_use_profile_not_found_raises(tmp_path: Path) -> None:
    p = tmp_path / "config.yaml"
    _write_v2(p, {"dev": {"host": "dev-host"}})
    with pytest.raises(config.ProfileNotFoundError) as exc_info:
        config.use_profile("uat", p)
    assert exc_info.value.name == "uat"
    raw = yaml.safe_load(p.read_text())
    assert "current" not in raw


def test_use_profile_does_not_test_connectivity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`config use` never opens a socket — it only rewrites the pointer."""
    import splunklib.client as splunk_client

    def _boom(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("config use must not connect to Splunk")

    monkeypatch.setattr(splunk_client, "connect", _boom)
    p = tmp_path / "config.yaml"
    _write_v2(p, {"dev": {"host": "dev-host"}, "uat": {"host": "uat-host"}})
    config.use_profile("uat", p)
    raw = yaml.safe_load(p.read_text())
    assert raw["current"] == "uat"
