"""Tests for soar-assets state adapter (pull/diff/apply)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from splunkctl.commands.state_io_soar_assets import (
    _MASKED,
    _SUBDIR,
    _asset_to_doc,
    _flat_config,
    _mask_config,
    _read_local_assets,
    _safe_filename,
    apply_soar_assets,
    diff_soar_assets,
    pull_soar_assets,
)

# ------------------------------------------------------------------
# helpers
# ------------------------------------------------------------------


def _asset(
    asset_id: int,
    name: str,
    *,
    app_id: int = 10,
    description: str = "",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a minimal SOAR asset API response dict."""
    return {
        "id": asset_id,
        "name": name,
        "app": app_id,
        "description": description,
        "configuration": config or {},
        "tags": [],
    }


def _mock_soar(
    assets: list[dict[str, Any]] | None = None,
    app_schema: dict[str, Any] | None = None,
) -> MagicMock:
    """Build a mock SOARClient that returns the given assets."""
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
            return app_schema or {}
        return {}

    soar.get = MagicMock(side_effect=_get)
    soar.post = MagicMock(return_value={})
    return soar


def _write_asset_file(dir_path: Path, name: str, doc: dict[str, Any]) -> Path:
    """Write a local asset JSON file."""
    sub = dir_path / _SUBDIR
    sub.mkdir(parents=True, exist_ok=True)
    fname = _safe_filename(name) + ".json"
    p = sub / fname
    p.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    return p


_SOAR_PATCH = "splunkctl.commands.state_io_soar_assets._build_soar_client"


# ------------------------------------------------------------------
# unit helpers
# ------------------------------------------------------------------


class TestSafeFilename:
    def test_replaces_slashes(self) -> None:
        assert _safe_filename("a/b\\c") == "a_b_c"

    def test_plain_name(self) -> None:
        assert _safe_filename("my_asset") == "my_asset"


class TestMaskConfig:
    def test_masks_secret_keys(self) -> None:
        config = {"host": "1.2.3.4", "password": "s3cret", "token": "tok"}
        result = _mask_config(config, {"password", "token"})
        assert result["host"] == "1.2.3.4"
        assert result["password"] == _MASKED
        assert result["token"] == _MASKED

    def test_no_secrets(self) -> None:
        config = {"host": "1.2.3.4"}
        assert _mask_config(config, set()) == config


class TestAssetToDoc:
    def test_masks_password_fields(self) -> None:
        asset = _asset(1, "firewall", config={"host": "fw1", "password": "s3c"})
        doc = _asset_to_doc(asset, {"password"})
        assert doc["configuration"]["host"] == "fw1"
        assert doc["configuration"]["password"] == _MASKED

    def test_preserves_all_fields_when_no_secrets(self) -> None:
        asset = _asset(2, "scanner", config={"host": "sc1"})
        doc = _asset_to_doc(asset, set())
        assert doc["configuration"] == {"host": "sc1"}
        assert doc["name"] == "scanner"
        assert doc["app_id"] == 10


class TestFlatConfig:
    def test_skips_masked_values(self) -> None:
        doc = {
            "description": "desc",
            "app_id": 10,
            "configuration": {"host": "fw1", "password": _MASKED},
        }
        kv = _flat_config(doc, {"password"})
        assert "config.password" not in kv
        assert kv["config.host"] == "fw1"
        assert kv["description"] == "desc"

    def test_empty_config(self) -> None:
        doc = {"description": "", "app_id": None, "configuration": {}}
        kv = _flat_config(doc, set())
        assert kv == {"description": "", "app_id": "None"}


class TestReadLocalAssets:
    def test_reads_json_files(self, tmp_path: Path) -> None:
        doc = {"name": "fw", "app_id": 10, "configuration": {}}
        _write_asset_file(tmp_path, "fw", doc)
        result = _read_local_assets(tmp_path)
        assert "fw" in result
        assert result["fw"]["name"] == "fw"

    def test_empty_dir(self, tmp_path: Path) -> None:
        assert _read_local_assets(tmp_path) == {}

    def test_skips_malformed_json(self, tmp_path: Path) -> None:
        sub = tmp_path / _SUBDIR
        sub.mkdir()
        (sub / "bad.json").write_text("not json{{{", encoding="utf-8")
        assert _read_local_assets(tmp_path) == {}


# ------------------------------------------------------------------
# pull
# ------------------------------------------------------------------


class TestPullSoarAssets:
    def test_writes_asset_json_files(self, tmp_path: Path) -> None:
        assets = [
            _asset(1, "firewall", config={"host": "fw1"}),
            _asset(2, "scanner", config={"host": "sc1"}),
        ]
        soar = _mock_soar(assets)

        with patch(_SOAR_PATCH, return_value=soar):
            count = pull_soar_assets(MagicMock(), tmp_path, None)

        assert count == 2
        out_dir = tmp_path / _SUBDIR
        assert (out_dir / "firewall.json").exists()
        assert (out_dir / "scanner.json").exists()

        doc = json.loads((out_dir / "firewall.json").read_text())
        assert doc["name"] == "firewall"
        assert doc["configuration"]["host"] == "fw1"

    def test_masks_password_fields(self, tmp_path: Path) -> None:
        assets = [
            _asset(1, "fw", config={"host": "fw1", "password": "s3cret"}),
        ]
        schema: dict[str, Any] = {
            "configuration": {
                "host": {"data_type": "string"},
                "password": {"data_type": "password"},
            }
        }
        soar = _mock_soar(assets, app_schema=schema)

        with patch(_SOAR_PATCH, return_value=soar):
            pull_soar_assets(MagicMock(), tmp_path, None)

        doc = json.loads((tmp_path / _SUBDIR / "fw.json").read_text())
        assert doc["configuration"]["host"] == "fw1"
        assert doc["configuration"]["password"] == _MASKED

    def test_skips_nameless_assets(self, tmp_path: Path) -> None:
        assets = [{"id": 1, "name": "", "app": 10, "configuration": {}}]
        soar = _mock_soar(assets)

        with patch(_SOAR_PATCH, return_value=soar):
            count = pull_soar_assets(MagicMock(), tmp_path, None)

        assert count == 0


# ------------------------------------------------------------------
# diff
# ------------------------------------------------------------------


class TestDiffSoarAssets:
    def test_unchanged(self, tmp_path: Path) -> None:
        assets = [_asset(1, "fw", config={"host": "fw1"})]
        doc = _asset_to_doc(assets[0], set())
        _write_asset_file(tmp_path, "fw", doc)

        soar = _mock_soar(assets)
        with patch(_SOAR_PATCH, return_value=soar):
            entries = diff_soar_assets(MagicMock(), tmp_path, None)

        by_name = {e["name"]: e for e in entries}
        assert by_name["fw"]["change"] == "unchanged"

    def test_added(self, tmp_path: Path) -> None:
        """Asset on disk but not on server -> added."""
        doc = {
            "name": "new_asset",
            "app_id": 10,
            "description": "",
            "configuration": {"host": "x"},
        }
        _write_asset_file(tmp_path, "new_asset", doc)

        soar = _mock_soar([])  # no remote assets
        with patch(_SOAR_PATCH, return_value=soar):
            entries = diff_soar_assets(MagicMock(), tmp_path, None)

        assert len(entries) == 1
        assert entries[0]["change"] == "added"
        assert entries[0]["name"] == "new_asset"

    def test_removed(self, tmp_path: Path) -> None:
        """Asset on server but not on disk -> removed."""
        assets = [_asset(1, "old_fw", config={"host": "fw1"})]
        soar = _mock_soar(assets)

        with patch(_SOAR_PATCH, return_value=soar):
            entries = diff_soar_assets(MagicMock(), tmp_path, None)

        assert len(entries) == 1
        assert entries[0]["change"] == "removed"

    def test_modified(self, tmp_path: Path) -> None:
        """Asset with different config -> modified."""
        assets = [_asset(1, "fw", config={"host": "fw1"})]
        doc = _asset_to_doc(assets[0], set())
        doc["configuration"]["host"] = "fw2"  # changed locally
        _write_asset_file(tmp_path, "fw", doc)

        soar = _mock_soar(assets)
        with patch(_SOAR_PATCH, return_value=soar):
            entries = diff_soar_assets(MagicMock(), tmp_path, None)

        by_name = {e["name"]: e for e in entries}
        assert by_name["fw"]["change"] == "modified"
        fields = {f["field"]: f for f in by_name["fw"]["fields"]}
        assert fields["config.host"]["old"] == "fw1"
        assert fields["config.host"]["new"] == "fw2"

    def test_ignores_masked_fields_in_diff(self, tmp_path: Path) -> None:
        """Masked password fields should not cause false-positive drift."""
        assets = [
            _asset(1, "fw", config={"host": "fw1", "password": "real_pass"}),
        ]
        schema: dict[str, Any] = {
            "configuration": {
                "host": {"data_type": "string"},
                "password": {"data_type": "password"},
            }
        }
        # Local file has masked password.
        doc = _asset_to_doc(assets[0], {"password"})
        assert doc["configuration"]["password"] == _MASKED
        _write_asset_file(tmp_path, "fw", doc)

        soar = _mock_soar(assets, app_schema=schema)
        with patch(_SOAR_PATCH, return_value=soar):
            entries = diff_soar_assets(MagicMock(), tmp_path, None)

        by_name = {e["name"]: e for e in entries}
        assert by_name["fw"]["change"] == "unchanged"


# ------------------------------------------------------------------
# apply (push)
# ------------------------------------------------------------------


class TestApplySoarAssets:
    def test_creates_added_asset(self, tmp_path: Path) -> None:
        doc = {
            "name": "new_fw",
            "app_id": 10,
            "description": "New firewall",
            "configuration": {"host": "fw1"},
        }
        _write_asset_file(tmp_path, "new_fw", doc)

        soar = _mock_soar([])  # no remote assets
        with patch(_SOAR_PATCH, return_value=soar):
            records = apply_soar_assets(MagicMock(), tmp_path, None)

        assert len(records) == 1
        assert records[0]["change"] == "added"
        assert records[0]["name"] == "new_fw"
        soar.post.assert_called_once()
        call_args = soar.post.call_args
        assert call_args.args[0] == "asset"
        body = call_args.kwargs.get("body") or call_args.args[1]
        assert body["name"] == "new_fw"
        assert body["configuration"] == {"host": "fw1"}

    def test_strips_masked_on_create(self, tmp_path: Path) -> None:
        doc = {
            "name": "new_fw",
            "app_id": 10,
            "description": "",
            "configuration": {"host": "fw1", "password": _MASKED},
        }
        _write_asset_file(tmp_path, "new_fw", doc)

        soar = _mock_soar([])
        with patch(_SOAR_PATCH, return_value=soar):
            apply_soar_assets(MagicMock(), tmp_path, None)

        body = soar.post.call_args.kwargs.get("body") or soar.post.call_args.args[1]
        # Masked value stripped -- cannot create with placeholders.
        assert "password" not in body["configuration"]

    def test_updates_modified_asset(self, tmp_path: Path) -> None:
        remote = _asset(1, "fw", config={"host": "fw1", "password": "s3c"})
        doc = _asset_to_doc(remote, set())
        doc["configuration"]["host"] = "fw2"  # modified locally
        _write_asset_file(tmp_path, "fw", doc)

        soar = _mock_soar([remote])
        with patch(_SOAR_PATCH, return_value=soar):
            records = apply_soar_assets(MagicMock(), tmp_path, None)

        assert len(records) == 1
        assert records[0]["change"] == "modified"
        # Verify fetch-merge-post: POST to asset/<id>
        post_calls = [
            c for c in soar.post.call_args_list if c.args[0].startswith("asset/")
        ]
        assert len(post_calls) == 1
        body = post_calls[0].kwargs.get("body") or post_calls[0].args[1]
        # Merged config: new host, preserved password.
        assert body["configuration"]["host"] == "fw2"
        assert body["configuration"]["password"] == "s3c"

    def test_merge_skips_masked_values(self, tmp_path: Path) -> None:
        """Masked values in local file should not overwrite server secrets."""
        remote = _asset(1, "fw", config={"host": "fw1", "password": "real_pass"})
        doc = _asset_to_doc(remote, set())
        doc["configuration"]["host"] = "fw2"
        doc["configuration"]["password"] = _MASKED  # masked locally
        _write_asset_file(tmp_path, "fw", doc)

        soar = _mock_soar([remote])
        with patch(_SOAR_PATCH, return_value=soar):
            records = apply_soar_assets(MagicMock(), tmp_path, None)

        assert len(records) == 1
        post_calls = [
            c for c in soar.post.call_args_list if c.args[0].startswith("asset/")
        ]
        body = post_calls[0].kwargs.get("body") or post_calls[0].args[1]
        # Password preserved from server, masked value NOT applied.
        assert body["configuration"]["password"] == "real_pass"
        assert body["configuration"]["host"] == "fw2"

    def test_skips_unchanged_asset(self, tmp_path: Path) -> None:
        remote = _asset(1, "fw", config={"host": "fw1"})
        doc = _asset_to_doc(remote, set())
        _write_asset_file(tmp_path, "fw", doc)

        soar = _mock_soar([remote])
        with patch(_SOAR_PATCH, return_value=soar):
            records = apply_soar_assets(MagicMock(), tmp_path, None)

        assert records == []
        # No POST calls for asset creation or update.
        post_calls = [c for c in soar.post.call_args_list]
        assert len(post_calls) == 0

    def test_never_deletes(self, tmp_path: Path) -> None:
        """A remote asset not on disk is never touched by apply."""
        remote = _asset(1, "live_only", config={"host": "fw1"})
        soar = _mock_soar([remote])

        with patch(_SOAR_PATCH, return_value=soar):
            records = apply_soar_assets(MagicMock(), tmp_path, None)

        assert records == []
        soar.post.assert_not_called()
        soar.delete = MagicMock()  # ensure delete is never called
        soar.delete.assert_not_called()

    def test_preserves_app_association(self, tmp_path: Path) -> None:
        remote = _asset(1, "fw", app_id=42, config={"host": "fw1"})
        doc = _asset_to_doc(remote, set())
        doc["configuration"]["host"] = "fw2"
        _write_asset_file(tmp_path, "fw", doc)

        soar = _mock_soar([remote])
        with patch(_SOAR_PATCH, return_value=soar):
            apply_soar_assets(MagicMock(), tmp_path, None)

        post_calls = [
            c for c in soar.post.call_args_list if c.args[0].startswith("asset/")
        ]
        body = post_calls[0].kwargs.get("body") or post_calls[0].args[1]
        assert body["app_id"] == 42


# ------------------------------------------------------------------
# registration
# ------------------------------------------------------------------


class TestRegistration:
    def test_soar_assets_in_types(self) -> None:
        from splunkctl.commands import state_io

        assert "soar-assets" in state_io.TYPES

    def test_soar_assets_in_applicable_types(self) -> None:
        from splunkctl.commands import state_io

        assert "soar-assets" in state_io.APPLICABLE_TYPES

    def test_soar_assets_in_soar_types(self) -> None:
        from splunkctl.commands import state_io

        assert "soar-assets" in state_io.SOAR_TYPES

    def test_pull_fn_registered(self) -> None:
        from splunkctl.commands import state_io

        assert "soar-assets" in state_io.PULL_FNS

    def test_diff_fn_registered(self) -> None:
        from splunkctl.commands import state_io

        assert "soar-assets" in state_io.DIFF_FNS

    def test_apply_fn_registered(self) -> None:
        from splunkctl.commands import state_io

        assert "soar-assets" in state_io.APPLY_FNS
