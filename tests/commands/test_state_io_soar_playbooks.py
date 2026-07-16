"""Tests for state-io SOAR playbook adapters (pull/diff/apply)."""

import base64
import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from splunkctl.commands import state_io
from splunkctl.commands.state_io_soar import (
    _name_from_filename,
    _safe_filename,
    apply_soar_playbooks,
    diff_soar_playbooks,
    pull_soar_playbooks,
)

# --------------------------------------------------------------------------
# filename helpers
# --------------------------------------------------------------------------


def test_safe_filename_replaces_slash() -> None:
    assert _safe_filename("local/my_playbook") == "local__my_playbook"


def test_safe_filename_no_slash() -> None:
    assert _safe_filename("simple") == "simple"


def test_name_from_filename_reverses_safe() -> None:
    assert _name_from_filename("local__my_playbook.tgz") == "local/my_playbook"


def test_name_from_filename_no_double_underscore() -> None:
    assert _name_from_filename("simple.tgz") == "simple"


# --------------------------------------------------------------------------
# mock helpers
# --------------------------------------------------------------------------


def _mock_soar_client(
    playbooks: list[dict[str, Any]] | None = None,
    exports: dict[int, bytes] | None = None,
) -> MagicMock:
    """Build a mock SOARClient for playbook operations."""
    client = MagicMock()
    pbs = playbooks or []
    exps = exports or {}

    def _iter_pages(path: str, **_kwargs: Any) -> list[dict[str, Any]]:
        if path == "playbook":
            return pbs
        return []

    client.iter_pages.side_effect = _iter_pages

    def _get_bytes(path: str, **_kwargs: Any) -> bytes:
        # path = "playbook/<id>/export"
        parts = path.split("/")
        pb_id = int(parts[1])
        return exps.get(pb_id, b"tgz-content")

    client.get_bytes.side_effect = _get_bytes
    return client


# --------------------------------------------------------------------------
# pull
# --------------------------------------------------------------------------


def test_pull_soar_playbooks_writes_tgz_and_index(tmp_path: Path) -> None:
    tgz_data = b"\x1f\x8b fake tgz"
    client = _mock_soar_client(
        playbooks=[{"id": 42, "name": "local/detect_malware"}],
        exports={42: tgz_data},
    )

    count = pull_soar_playbooks(client, tmp_path, None)

    assert count == 1
    out_dir = tmp_path / "soar-playbooks"
    assert (out_dir / "local__detect_malware.tgz").read_bytes() == tgz_data

    index = json.loads((out_dir / "index.json").read_text())
    assert len(index) == 1
    assert index[0]["id"] == 42
    assert index[0]["name"] == "local/detect_malware"
    assert index[0]["filename"] == "local__detect_malware.tgz"


def test_pull_soar_playbooks_multiple(tmp_path: Path) -> None:
    client = _mock_soar_client(
        playbooks=[
            {"id": 1, "name": "local/pb1"},
            {"id": 2, "name": "local/pb2"},
        ],
        exports={1: b"tgz1", 2: b"tgz2"},
    )

    count = pull_soar_playbooks(client, tmp_path, None)
    assert count == 2

    out_dir = tmp_path / "soar-playbooks"
    assert (out_dir / "local__pb1.tgz").read_bytes() == b"tgz1"
    assert (out_dir / "local__pb2.tgz").read_bytes() == b"tgz2"


def test_pull_soar_playbooks_empty(tmp_path: Path) -> None:
    client = _mock_soar_client(playbooks=[])
    count = pull_soar_playbooks(client, tmp_path, None)
    assert count == 0

    index = json.loads((tmp_path / "soar-playbooks" / "index.json").read_text())
    assert index == []


def test_pull_soar_playbooks_ignores_app_parameter(tmp_path: Path) -> None:
    """app parameter is accepted for signature compat but ignored."""
    client = _mock_soar_client(
        playbooks=[{"id": 1, "name": "local/pb1"}],
        exports={1: b"tgz"},
    )
    count = pull_soar_playbooks(client, tmp_path, "some_app")
    assert count == 1


# --------------------------------------------------------------------------
# diff
# --------------------------------------------------------------------------


def test_diff_soar_playbooks_unchanged(tmp_path: Path) -> None:
    """Playbook on disk matches live export exactly."""
    tgz = b"same-content"
    out_dir = tmp_path / "soar-playbooks"
    out_dir.mkdir()
    (out_dir / "local__pb1.tgz").write_bytes(tgz)
    (out_dir / "index.json").write_text(
        json.dumps([{"id": 1, "name": "local/pb1", "filename": "local__pb1.tgz"}])
    )

    client = _mock_soar_client(
        playbooks=[{"id": 1, "name": "local/pb1"}],
        exports={1: tgz},
    )

    entries = diff_soar_playbooks(client, tmp_path, None)
    assert len(entries) == 1
    assert entries[0]["name"] == "local/pb1"
    assert entries[0]["change"] == "unchanged"


def test_diff_soar_playbooks_modified(tmp_path: Path) -> None:
    """Playbook on disk differs from live export."""
    out_dir = tmp_path / "soar-playbooks"
    out_dir.mkdir()
    (out_dir / "local__pb1.tgz").write_bytes(b"local-version")
    (out_dir / "index.json").write_text(
        json.dumps([{"id": 1, "name": "local/pb1", "filename": "local__pb1.tgz"}])
    )

    client = _mock_soar_client(
        playbooks=[{"id": 1, "name": "local/pb1"}],
        exports={1: b"remote-version"},
    )

    entries = diff_soar_playbooks(client, tmp_path, None)
    assert len(entries) == 1
    assert entries[0]["name"] == "local/pb1"
    assert entries[0]["change"] == "modified"


def test_diff_soar_playbooks_added(tmp_path: Path) -> None:
    """Playbook on disk not present on the server."""
    out_dir = tmp_path / "soar-playbooks"
    out_dir.mkdir()
    (out_dir / "local__new_pb.tgz").write_bytes(b"new-playbook")
    (out_dir / "index.json").write_text(json.dumps([]))

    client = _mock_soar_client(playbooks=[])

    entries = diff_soar_playbooks(client, tmp_path, None)
    assert len(entries) == 1
    assert entries[0]["name"] == "local/new_pb"
    assert entries[0]["change"] == "added"


def test_diff_soar_playbooks_removed(tmp_path: Path) -> None:
    """Playbook on server not present on disk."""
    out_dir = tmp_path / "soar-playbooks"
    out_dir.mkdir()
    (out_dir / "index.json").write_text(json.dumps([]))

    client = _mock_soar_client(
        playbooks=[{"id": 5, "name": "local/orphan"}],
        exports={5: b"orphan-tgz"},
    )

    entries = diff_soar_playbooks(client, tmp_path, None)
    assert len(entries) == 1
    assert entries[0]["name"] == "local/orphan"
    assert entries[0]["change"] == "removed"


def test_diff_soar_playbooks_picks_up_manual_tgz(tmp_path: Path) -> None:
    """A .tgz not in index.json is still picked up for diff."""
    out_dir = tmp_path / "soar-playbooks"
    out_dir.mkdir()
    (out_dir / "local__manual.tgz").write_bytes(b"manual-pb")
    # No index.json at all

    client = _mock_soar_client(playbooks=[])

    entries = diff_soar_playbooks(client, tmp_path, None)
    assert len(entries) == 1
    assert entries[0]["name"] == "local/manual"
    assert entries[0]["change"] == "added"


# --------------------------------------------------------------------------
# apply
# --------------------------------------------------------------------------


def test_apply_soar_playbooks_imports_added(tmp_path: Path) -> None:
    """A local-only playbook is imported via import_playbook."""
    tgz = b"new-playbook-tgz"
    out_dir = tmp_path / "soar-playbooks"
    out_dir.mkdir()
    (out_dir / "local__new_pb.tgz").write_bytes(tgz)
    (out_dir / "index.json").write_text(json.dumps([]))

    client = _mock_soar_client(playbooks=[])
    client.post.return_value = {"id": 99}

    records = apply_soar_playbooks(client, tmp_path, None)

    assert len(records) == 1
    assert records[0]["type"] == "soar-playbooks"
    assert records[0]["name"] == "local/new_pb"
    assert records[0]["change"] == "added"

    # Verify the import_playbook POST
    client.post.assert_called_once()
    post_args = client.post.call_args
    assert post_args.args[0] == "import_playbook"
    body = post_args.kwargs["body"]
    assert body["scm"] == "local"
    assert body["force"] is True
    # Verify base64 encoding
    assert base64.b64decode(body["playbook"]) == tgz


def test_apply_soar_playbooks_imports_modified(tmp_path: Path) -> None:
    """A modified playbook is re-imported."""
    out_dir = tmp_path / "soar-playbooks"
    out_dir.mkdir()
    (out_dir / "local__pb1.tgz").write_bytes(b"new-version")
    (out_dir / "index.json").write_text(
        json.dumps([{"id": 1, "name": "local/pb1", "filename": "local__pb1.tgz"}])
    )

    client = _mock_soar_client(
        playbooks=[{"id": 1, "name": "local/pb1"}],
        exports={1: b"old-version"},
    )
    client.post.return_value = {"id": 1}

    records = apply_soar_playbooks(client, tmp_path, None)

    assert len(records) == 1
    assert records[0]["change"] == "modified"
    client.post.assert_called_once()


def test_apply_soar_playbooks_skips_unchanged(tmp_path: Path) -> None:
    """An unchanged playbook is not re-imported."""
    tgz = b"same-content"
    out_dir = tmp_path / "soar-playbooks"
    out_dir.mkdir()
    (out_dir / "local__pb1.tgz").write_bytes(tgz)
    (out_dir / "index.json").write_text(
        json.dumps([{"id": 1, "name": "local/pb1", "filename": "local__pb1.tgz"}])
    )

    client = _mock_soar_client(
        playbooks=[{"id": 1, "name": "local/pb1"}],
        exports={1: tgz},
    )

    records = apply_soar_playbooks(client, tmp_path, None)
    assert records == []
    client.post.assert_not_called()


def test_apply_soar_playbooks_never_deletes(tmp_path: Path) -> None:
    """A live playbook absent from disk is never deleted by apply."""
    out_dir = tmp_path / "soar-playbooks"
    out_dir.mkdir()
    (out_dir / "index.json").write_text(json.dumps([]))

    client = _mock_soar_client(
        playbooks=[{"id": 10, "name": "local/orphan"}],
        exports={10: b"orphan-tgz"},
    )

    records = apply_soar_playbooks(client, tmp_path, None)
    assert records == []
    client.post.assert_not_called()
    client.delete.assert_not_called()


def test_apply_soar_playbooks_no_dir(tmp_path: Path) -> None:
    """If soar-playbooks/ directory does not exist, apply returns empty."""
    client = MagicMock()
    records = apply_soar_playbooks(client, tmp_path, None)
    assert records == []


# --------------------------------------------------------------------------
# registry
# --------------------------------------------------------------------------


def test_soar_playbooks_registered_in_all_registries() -> None:
    """soar-playbooks is registered in TYPES, PULL/DIFF/APPLY_FNS, and
    APPLICABLE_TYPES."""
    assert "soar-playbooks" in state_io.TYPES
    assert "soar-playbooks" in state_io.APPLICABLE_TYPES
    assert "soar-playbooks" in state_io.PULL_FNS
    assert "soar-playbooks" in state_io.DIFF_FNS
    assert "soar-playbooks" in state_io.APPLY_FNS
    assert "soar-playbooks" in state_io.SOAR_TYPES
