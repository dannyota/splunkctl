"""CLI integration tests for SOAR types in the state command group.

Covers `state pull/diff/push` with `--types soar-playbooks`,
`soar-lists`, and `soar-assets`, plus mixed SIEM+SOAR type requests.
Each test mocks the SOAR client so no live SOAR instance is needed.
"""

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from splunkctl.main import cli

_SIEM_PATCH = "splunkctl.commands.state.get_client"
_SOAR_PATCH = "splunkctl.commands.state.get_soar_client"
# soar-assets builds its own client internally -- mock that too.
_SOAR_ASSETS_PATCH = "splunkctl.commands.state_io_soar_assets._build_soar_client"


# --------------------------------------------------------------------------
# mock helpers
# --------------------------------------------------------------------------


def _mock_ss(
    name: str, spl: str = "search index=main", *, app: str = "search"
) -> MagicMock:
    ss = MagicMock()
    ss.name = name
    ss.content = {
        "search": spl,
        "description": "",
        "cron_schedule": "",
        "is_scheduled": "0",
        "disabled": "0",
        "actions": "",
        "alert_type": "",
        "alert.severity": "",
    }
    ss.access = {"app": app}
    return ss


def _base_svc() -> MagicMock:
    svc = MagicMock()
    svc.host = "localhost"
    svc.port = 8089
    svc.saved_searches.list.return_value = []
    return svc


def _mock_soar_client(
    playbooks: list[dict[str, Any]] | None = None,
    exports: dict[int, bytes] | None = None,
    lists: list[dict[str, Any]] | None = None,
) -> MagicMock:
    """Build a mock SOARClient covering playbooks and lists."""
    client = MagicMock()
    pbs = playbooks or []
    exps = exports or {}
    ls = lists or []

    def _iter_pages(endpoint: str, **_kw: Any) -> list[dict[str, Any]]:
        if endpoint == "playbook":
            return pbs
        if endpoint == "decided_list":
            return ls
        return []

    client.iter_pages.side_effect = _iter_pages

    def _get_bytes(path: str, **_kw: Any) -> bytes:
        parts = path.split("/")
        pb_id = int(parts[1])
        return exps.get(pb_id, b"tgz-content")

    client.get_bytes.side_effect = _get_bytes

    def _get(path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if path.startswith("decided_list/"):
            list_id = int(path.split("/")[1])
            for item in ls:
                if item["id"] == list_id:
                    return item
        return {}

    client.get.side_effect = _get
    return client


def _mock_soar_assets_client(
    assets: list[dict[str, Any]] | None = None,
) -> MagicMock:
    """Build a mock SOARClient for assets (separate module)."""
    soar = MagicMock()
    asset_list = assets or []

    def _get(endpoint: str, params: Any = None) -> dict[str, Any]:
        if endpoint == "asset":
            return {"data": asset_list}
        if endpoint.startswith("asset/"):
            aid = int(endpoint.split("/")[1])
            for a in asset_list:
                if a["id"] == aid:
                    return a
            return {}
        if endpoint.startswith("app/"):
            return {}
        return {}

    soar.get = MagicMock(side_effect=_get)
    soar.post = MagicMock(return_value={})
    return soar


# --------------------------------------------------------------------------
# pull
# --------------------------------------------------------------------------


@patch(_SOAR_PATCH)
def test_pull_soar_playbooks_via_cli(mock_gsc: MagicMock, tmp_path: Path) -> None:
    """state pull --types soar-playbooks writes tgz files and manifest."""
    tgz = b"\x1f\x8b fake"
    soar = _mock_soar_client(
        playbooks=[{"id": 1, "name": "local/detect"}],
        exports={1: tgz},
    )
    mock_gsc.return_value = soar

    target = tmp_path / "snap"
    result = CliRunner().invoke(
        cli, ["state", "pull", "--dir", str(target), "--types", "soar-playbooks"]
    )
    assert result.exit_code == 0, result.output
    assert (target / "soar-playbooks" / "local__detect.tgz").exists()
    manifest = json.loads((target / "manifest.json").read_text())
    assert manifest["types"] == {"soar-playbooks": 1}
    # No SIEM client needed -- host falls back to "soar".
    assert manifest["host"] == "soar"


@patch(_SOAR_ASSETS_PATCH)
def test_pull_soar_assets_via_cli(mock_build: MagicMock, tmp_path: Path) -> None:
    """state pull --types soar-assets writes asset JSON files."""
    soar = _mock_soar_assets_client(
        assets=[
            {
                "id": 1,
                "name": "fw",
                "app": 10,
                "configuration": {"host": "fw1"},
                "description": "",
                "tags": [],
            }
        ],
    )
    mock_build.return_value = soar

    target = tmp_path / "snap"
    with patch(_SOAR_PATCH, return_value=MagicMock()):
        result = CliRunner().invoke(
            cli, ["state", "pull", "--dir", str(target), "--types", "soar-assets"]
        )
    assert result.exit_code == 0, result.output
    assert (target / "soar-assets" / "fw.json").exists()
    manifest = json.loads((target / "manifest.json").read_text())
    assert manifest["types"] == {"soar-assets": 1}


# --------------------------------------------------------------------------
# diff
# --------------------------------------------------------------------------


@patch(_SOAR_PATCH)
def test_diff_soar_lists_via_cli(mock_gsc: MagicMock, tmp_path: Path) -> None:
    """state diff --types soar-lists returns structured drift."""
    content = [["col"], ["val"]]
    soar = _mock_soar_client(
        lists=[{"id": 1, "name": "blocklist", "content": content}],
    )
    mock_gsc.return_value = soar

    target = tmp_path / "snap"
    target.mkdir()
    out_dir = target / "soar-lists"
    out_dir.mkdir()
    (out_dir / "blocklist.json").write_text(
        json.dumps([["col"], ["new_val"]], indent=2) + "\n"
    )

    result = CliRunner().invoke(
        cli,
        ["--json", "state", "diff", "--dir", str(target), "--types", "soar-lists"],
    )
    assert result.exit_code == 0, result.output
    rows = json.loads(result.output)
    assert len(rows) == 1
    assert rows[0]["type"] == "soar-lists"
    assert rows[0]["name"] == "blocklist"
    assert rows[0]["change"] == "modified"


# --------------------------------------------------------------------------
# push
# --------------------------------------------------------------------------


@patch(_SOAR_PATCH)
def test_push_soar_playbooks_dry_run(mock_gsc: MagicMock, tmp_path: Path) -> None:
    """state push --types soar-playbooks without --yes is a dry run."""
    soar = _mock_soar_client(playbooks=[])
    mock_gsc.return_value = soar

    target = tmp_path / "snap"
    out_dir = target / "soar-playbooks"
    out_dir.mkdir(parents=True)
    (out_dir / "local__new_pb.tgz").write_bytes(b"new-tgz")
    (out_dir / "index.json").write_text(json.dumps([]))

    result = CliRunner().invoke(
        cli,
        ["state", "push", "--dir", str(target), "--types", "soar-playbooks"],
    )
    assert result.exit_code == 0, result.output
    assert "[DRY RUN]" in result.stderr
    soar.post.assert_not_called()


@patch(_SOAR_PATCH)
def test_push_soar_lists_yes_applies(mock_gsc: MagicMock, tmp_path: Path) -> None:
    """state push --types soar-lists --yes creates a new list."""
    soar = _mock_soar_client(lists=[])
    mock_gsc.return_value = soar

    target = tmp_path / "snap"
    out_dir = target / "soar-lists"
    out_dir.mkdir(parents=True)
    content = [["header"], ["row1"]]
    (out_dir / "new_list.json").write_text(json.dumps(content, indent=2) + "\n")

    report = tmp_path / "r.json"
    result = CliRunner().invoke(
        cli,
        [
            "--yes",
            "state",
            "push",
            "--dir",
            str(target),
            "--types",
            "soar-lists",
            "--report",
            str(report),
        ],
    )
    assert result.exit_code == 0, result.output
    soar.post.assert_called_once()

    payload = json.loads(report.read_text())
    assert payload["applied"] is True
    assert payload["types"] == ["soar-lists"]
    assert payload["changes"][0]["name"] == "new_list"
    assert payload["changes"][0]["change"] == "added"


# --------------------------------------------------------------------------
# mixed SIEM + SOAR
# --------------------------------------------------------------------------


@patch(_SIEM_PATCH)
@patch(_SOAR_PATCH)
def test_mixed_siem_soar_types(
    mock_gsc: MagicMock, mock_gc: MagicMock, tmp_path: Path
) -> None:
    """state pull --types rules,soar-playbooks uses both clients."""
    svc = _base_svc()
    svc.saved_searches.list.return_value = [_mock_ss("det1")]
    mock_gc.return_value.service = svc

    soar = _mock_soar_client(
        playbooks=[{"id": 1, "name": "local/pb1"}],
        exports={1: b"tgz1"},
    )
    mock_gsc.return_value = soar

    target = tmp_path / "snap"
    result = CliRunner().invoke(
        cli,
        ["state", "pull", "--dir", str(target), "--types", "rules,soar-playbooks"],
    )
    assert result.exit_code == 0, result.output
    assert (target / "rules.yml").exists()
    assert (target / "soar-playbooks" / "local__pb1.tgz").exists()

    manifest = json.loads((target / "manifest.json").read_text())
    assert manifest["types"] == {"rules": 1, "soar-playbooks": 1}
    # SIEM client is available, so host uses its address.
    assert manifest["host"] == "localhost:8089"

    # Both client factories called exactly once.
    mock_gc.assert_called_once()
    mock_gsc.assert_called_once()


# --------------------------------------------------------------------------
# validation
# --------------------------------------------------------------------------


def test_pull_rejects_unknown_soar_type(tmp_path: Path) -> None:
    """An invalid type name like 'soar-bogus' is rejected."""
    result = CliRunner().invoke(
        cli,
        ["state", "pull", "--dir", str(tmp_path / "snap"), "--types", "soar-bogus"],
    )
    assert result.exit_code != 0


def test_types_help_includes_soar() -> None:
    """The --types help text lists all SOAR types."""
    from splunkctl.commands import state_io

    for t in ("soar-playbooks", "soar-lists", "soar-assets"):
        assert t in state_io.TYPES
        assert t in state_io.SOAR_TYPES
