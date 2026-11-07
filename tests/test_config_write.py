"""Config credentials are private throughout atomic writes."""

import os
import stat
from pathlib import Path
from unittest.mock import patch

import pytest

from splunkctl.config import load, save


@pytest.mark.parametrize("existing", [False, True])
def test_save_private_atomic_file(tmp_path: Path, existing: bool) -> None:
    parent = tmp_path / "settings"
    if existing:
        parent.mkdir(mode=0o755)
    path = parent / "config.yaml"
    old_umask = os.umask(0o022)
    try:
        save({"token": "secret"}, path)
    finally:
        os.umask(old_umask)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(parent.stat().st_mode) == (0o755 if existing else 0o700)
    assert list(parent.iterdir()) == [path]


def test_credentials_private_before_replace(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text("port: 8089\ntoken: old\n")
    replace = os.replace

    def checked_replace(src: str | Path, dst: str | Path) -> None:
        assert stat.S_IMODE(Path(src).stat().st_mode) == 0o600
        assert path.read_text() == "port: 8089\ntoken: old\n"
        replace(src, dst)

    with patch("splunkctl.config.os.replace", side_effect=checked_replace) as call:
        save({"token": "new"}, path)
    call.assert_called_once()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_failed_write_preserves_destination_and_removes_temp(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    original = "port: 8089\ntoken: old\n"
    path.write_text(original)
    with (
        patch("splunkctl.config.yaml.dump", side_effect=OSError("disk full")),
        pytest.raises(OSError, match="disk full"),
    ):
        save({"token": "new"}, path)
    assert path.read_text() == original
    assert list(tmp_path.iterdir()) == [path]


def test_token_only_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    save({"token": "t"}, path)
    assert load(path)["token"] == "t"


def test_save_through_symlink(tmp_path: Path) -> None:
    target = tmp_path / "target" / "config.yaml"
    target.parent.mkdir()
    target.write_text("port: 8089\ntoken: old\n")
    link = tmp_path / "config.yaml"
    link.symlink_to(target.relative_to(tmp_path))
    save({"token": "new"}, link)
    assert link.is_symlink()
    assert load(target)["token"] == "new"
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert list(target.parent.iterdir()) == [target]


def test_save_dangling_symlink(tmp_path: Path) -> None:
    target = tmp_path / "missing.yaml"
    link = tmp_path / "config.yaml"
    link.symlink_to(target)
    with pytest.raises(OSError, match="missing.yaml"):
        save({"token": "t"}, link)
    assert link.is_symlink()
    assert not target.exists()
