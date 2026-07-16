"""Tests for state-io soar-lists (decided_list) adapter."""

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from splunkctl.commands.state_io_soar import (
    _serialize_list_content,
    apply_soar_lists,
    diff_soar_lists,
    pull_soar_lists,
)

# --------------------------------------------------------------------------
# mock helpers
# --------------------------------------------------------------------------


def _mock_soar(
    lists: list[dict[str, Any]] | None = None,
) -> MagicMock:
    """Build a mock SOARClient with decided_list data."""
    client = MagicMock()
    items = lists or []

    def _iter_pages(endpoint: str, **_kw: Any) -> list[dict[str, Any]]:
        if endpoint == "decided_list":
            return items
        return []

    client.iter_pages.side_effect = _iter_pages

    def _get(path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        # decided_list/<id> -> find by id
        if path.startswith("decided_list/"):
            list_id = int(path.split("/")[1])
            for item in items:
                if item["id"] == list_id:
                    return item
        return {}

    client.get.side_effect = _get
    return client


# --------------------------------------------------------------------------
# pull
# --------------------------------------------------------------------------


def test_pull_soar_lists_writes_json_files(tmp_path: Path) -> None:
    soar = _mock_soar(
        [
            {"id": 1, "name": "blocklist", "content": [["ip"], ["10.0.0.1"]]},
            {"id": 2, "name": "allowlist", "content": [["domain"], ["example.com"]]},
        ]
    )

    count = pull_soar_lists(soar, tmp_path, None)
    assert count == 2

    bl = json.loads((tmp_path / "soar-lists" / "blocklist.json").read_text())
    assert bl == [["ip"], ["10.0.0.1"]]

    al = json.loads((tmp_path / "soar-lists" / "allowlist.json").read_text())
    assert al == [["domain"], ["example.com"]]


def test_pull_soar_lists_creates_subdir(tmp_path: Path) -> None:
    soar = _mock_soar([])
    count = pull_soar_lists(soar, tmp_path, None)
    assert count == 0
    assert (tmp_path / "soar-lists").is_dir()


def test_pull_soar_lists_ignores_app_param(tmp_path: Path) -> None:
    """The app parameter is accepted but ignored for SOAR types."""
    soar = _mock_soar([{"id": 1, "name": "test", "content": [["a"]]}])
    count = pull_soar_lists(soar, tmp_path, "some_app")
    assert count == 1


# --------------------------------------------------------------------------
# diff
# --------------------------------------------------------------------------


def test_diff_soar_lists_unchanged(tmp_path: Path) -> None:
    content = [["col1"], ["val1"]]
    soar = _mock_soar([{"id": 1, "name": "my_list", "content": content}])

    # Write the same content to disk.
    out_dir = tmp_path / "soar-lists"
    out_dir.mkdir()
    (out_dir / "my_list.json").write_bytes(_serialize_list_content(content))

    entries = diff_soar_lists(soar, tmp_path, None)
    assert len(entries) == 1
    assert entries[0]["name"] == "my_list"
    assert entries[0]["change"] == "unchanged"


def test_diff_soar_lists_modified(tmp_path: Path) -> None:
    soar = _mock_soar(
        [{"id": 1, "name": "my_list", "content": [["col1"], ["old_val"]]}]
    )

    out_dir = tmp_path / "soar-lists"
    out_dir.mkdir()
    (out_dir / "my_list.json").write_bytes(
        _serialize_list_content([["col1"], ["new_val"]])
    )

    entries = diff_soar_lists(soar, tmp_path, None)
    assert len(entries) == 1
    assert entries[0]["name"] == "my_list"
    assert entries[0]["change"] == "modified"


def test_diff_soar_lists_added(tmp_path: Path) -> None:
    """A local file with no live counterpart is classified as added."""
    soar = _mock_soar([])

    out_dir = tmp_path / "soar-lists"
    out_dir.mkdir()
    (out_dir / "new_list.json").write_bytes(
        _serialize_list_content([["col1"], ["val1"]])
    )

    entries = diff_soar_lists(soar, tmp_path, None)
    assert len(entries) == 1
    assert entries[0]["name"] == "new_list"
    assert entries[0]["change"] == "added"


def test_diff_soar_lists_removed(tmp_path: Path) -> None:
    """A live list with no local file is classified as removed."""
    soar = _mock_soar([{"id": 1, "name": "orphan_list", "content": [["x"]]}])

    # No soar-lists directory at all.
    entries = diff_soar_lists(soar, tmp_path, None)
    assert len(entries) == 1
    assert entries[0]["name"] == "orphan_list"
    assert entries[0]["change"] == "removed"


def test_diff_soar_lists_mixed(tmp_path: Path) -> None:
    """All four drift states in one pass."""
    unchanged_content = [["a"], ["1"]]
    soar = _mock_soar(
        [
            {"id": 1, "name": "unchanged", "content": unchanged_content},
            {"id": 2, "name": "modified", "content": [["b"], ["old"]]},
            {"id": 3, "name": "removed_only", "content": [["c"]]},
        ]
    )

    out_dir = tmp_path / "soar-lists"
    out_dir.mkdir()
    (out_dir / "unchanged.json").write_bytes(_serialize_list_content(unchanged_content))
    (out_dir / "modified.json").write_bytes(_serialize_list_content([["b"], ["new"]]))
    (out_dir / "added_only.json").write_bytes(_serialize_list_content([["d"], ["val"]]))

    entries = {e["name"]: e["change"] for e in diff_soar_lists(soar, tmp_path, None)}
    assert entries["unchanged"] == "unchanged"
    assert entries["modified"] == "modified"
    assert entries["removed_only"] == "removed"
    assert entries["added_only"] == "added"


# --------------------------------------------------------------------------
# apply (push)
# --------------------------------------------------------------------------


def test_apply_soar_lists_creates_new(tmp_path: Path) -> None:
    soar = _mock_soar([])

    out_dir = tmp_path / "soar-lists"
    out_dir.mkdir()
    content = [["header"], ["row1"]]
    (out_dir / "new_list.json").write_bytes(_serialize_list_content(content))

    records = apply_soar_lists(soar, tmp_path, None)
    assert len(records) == 1
    assert records[0]["name"] == "new_list"
    assert records[0]["change"] == "added"
    assert records[0]["type"] == "soar-lists"

    # Verify POST was called with create payload.
    soar.post.assert_called_once_with(
        "decided_list", body={"name": "new_list", "content": content}
    )


def test_apply_soar_lists_updates_modified(tmp_path: Path) -> None:
    old_content = [["col"], ["old"]]
    new_content = [["col"], ["new"]]
    soar = _mock_soar([{"id": 42, "name": "my_list", "content": old_content}])

    out_dir = tmp_path / "soar-lists"
    out_dir.mkdir()
    (out_dir / "my_list.json").write_bytes(_serialize_list_content(new_content))

    records = apply_soar_lists(soar, tmp_path, None)
    assert len(records) == 1
    assert records[0]["name"] == "my_list"
    assert records[0]["change"] == "modified"

    # Verify POST was called with update payload (content only, to the id).
    soar.post.assert_called_once_with("decided_list/42", body={"content": new_content})


def test_apply_soar_lists_skips_unchanged(tmp_path: Path) -> None:
    content = [["col"], ["val"]]
    soar = _mock_soar([{"id": 1, "name": "same", "content": content}])

    out_dir = tmp_path / "soar-lists"
    out_dir.mkdir()
    (out_dir / "same.json").write_bytes(_serialize_list_content(content))

    records = apply_soar_lists(soar, tmp_path, None)
    assert records == []
    soar.post.assert_not_called()


def test_apply_soar_lists_never_deletes(tmp_path: Path) -> None:
    """A live list absent from disk is never touched by apply."""
    soar = _mock_soar([{"id": 1, "name": "live_only", "content": [["x"]]}])

    out_dir = tmp_path / "soar-lists"
    out_dir.mkdir()
    # Empty directory — no local files.

    records = apply_soar_lists(soar, tmp_path, None)
    assert records == []
    soar.post.assert_not_called()
    soar.delete.assert_not_called()


def test_apply_soar_lists_no_dir(tmp_path: Path) -> None:
    """Missing soar-lists directory returns empty records."""
    soar = _mock_soar([])
    records = apply_soar_lists(soar, tmp_path, None)
    assert records == []


def test_round_trip_format(tmp_path: Path) -> None:
    """Content serialized by pull matches what soar lists export produces."""
    content = [["ip", "reason"], ["10.0.0.1", "bad actor"]]
    soar = _mock_soar([{"id": 1, "name": "blocklist", "content": content}])

    pull_soar_lists(soar, tmp_path, None)

    # The file format should be JSON with indent=2 + trailing newline.
    raw = (tmp_path / "soar-lists" / "blocklist.json").read_text()
    assert raw == json.dumps(content, indent=2) + "\n"
    assert json.loads(raw) == content
