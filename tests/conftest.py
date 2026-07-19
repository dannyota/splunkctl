"""Shared pytest fixtures for splunkctl tests."""

from pathlib import Path

import pytest

import splunkctl.config as cfg_mod


@pytest.fixture(autouse=True)
def _isolate_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep tests off the developer's real ~/.splunkctl and SPLUNK_*/SOAR_* env.

    Without this, a live config profile (e.g. the lab SOAR VM) leaks into
    commands that resolve credentials for real — doctor's SOAR section made
    actual network calls during the test run.
    """
    monkeypatch.setattr(cfg_mod, "DEFAULT_DIR", tmp_path / ".splunkctl")
    monkeypatch.setattr(
        cfg_mod, "DEFAULT_PATH", tmp_path / ".splunkctl" / "config.yaml"
    )
    for var in [*cfg_mod._ENV_MAP, *cfg_mod._SOAR_ENV_MAP]:
        monkeypatch.delenv(var, raising=False)
