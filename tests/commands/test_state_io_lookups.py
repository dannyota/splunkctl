"""Tests for state-io lookup, dashboard, manifest, and SPL-injection guards."""

import json
from pathlib import Path
from unittest.mock import MagicMock

from splunkctl.commands import state_io

# --------------------------------------------------------------------------
# mock helpers
# --------------------------------------------------------------------------


def _mock_lookup(name: str = "hosts.csv", app: str = "search") -> MagicMock:
    lk = MagicMock()
    lk.name = name
    lk.access = MagicMock()
    lk.access.app = app
    return lk


def _mock_dashboard(
    name: str = "my_dash", app: str = "search", xml: str = "<a/>"
) -> MagicMock:
    d = MagicMock()
    d.name = name
    d.access = MagicMock()
    d.access.app = app
    d.content = {"isDashboard": True}
    d.export.return_value = xml
    return d


def _client(svc: MagicMock) -> MagicMock:
    client = MagicMock()
    client.service = svc
    return client


# --------------------------------------------------------------------------
# lookups
# --------------------------------------------------------------------------


def test_pull_lookups_downloads_csv(tmp_path: Path) -> None:
    svc = MagicMock()
    svc.lookup_table_files.list.return_value = [_mock_lookup("hosts.csv")]
    svc.jobs.oneshot.return_value.read.return_value = b"host,ip\na,1\n"
    client = _client(svc)

    count = state_io.pull_lookups(client, tmp_path, None)
    assert count == 1
    content = (tmp_path / "lookups" / "hosts.csv").read_text()
    assert content == "host,ip\na,1\n"


def test_diff_lookups_hash_compare(tmp_path: Path) -> None:
    (tmp_path / "lookups").mkdir()
    (tmp_path / "lookups" / "hosts.csv").write_text("host,ip\na,1\n")
    svc = MagicMock()
    svc.lookup_table_files.list.return_value = [_mock_lookup("hosts.csv")]
    svc.jobs.oneshot.return_value.read.return_value = b"host,ip\na,2\n"
    client = _client(svc)

    entries = state_io.diff_lookups(client, tmp_path, None)
    assert len(entries) == 1
    assert entries[0]["change"] == "modified"


def test_apply_lookups_uploads_changed_file(tmp_path: Path) -> None:
    (tmp_path / "lookups").mkdir()
    (tmp_path / "lookups" / "hosts.csv").write_text("host,ip\na,2\n")
    svc = MagicMock()
    svc.lookup_table_files.list.return_value = [_mock_lookup("hosts.csv")]
    svc.jobs.oneshot.return_value.read.return_value = b"host,ip\na,1\n"
    client = _client(svc)

    records = state_io.apply_lookups(client, tmp_path, None)
    assert len(records) == 1
    assert records[0]["change"] == "modified"
    client.upload_lookup.assert_called_once()
    _, kwargs = client.upload_lookup.call_args
    assert kwargs["update"] is True


# --------------------------------------------------------------------------
# dashboards (pull + diff only)
# --------------------------------------------------------------------------


def test_pull_dashboards_writes_xml(tmp_path: Path) -> None:
    svc = MagicMock()
    svc.dashboards.list.return_value = [_mock_dashboard("my_dash", xml="<dashboard/>")]
    client = _client(svc)

    count = state_io.pull_dashboards(client, tmp_path, None)
    assert count == 1
    assert (tmp_path / "dashboards" / "my_dash.xml").read_text() == "<dashboard/>"


def test_diff_dashboards_removed(tmp_path: Path) -> None:
    (tmp_path / "dashboards").mkdir()
    svc = MagicMock()
    svc.dashboards.list.return_value = [_mock_dashboard("orphan_dash")]
    client = _client(svc)

    entries = state_io.diff_dashboards(client, tmp_path, None)
    assert entries == [{"name": "orphan_dash", "change": "removed"}]


def test_dashboards_has_no_apply_entrypoint() -> None:
    """Dashboards are pull+diff only -- no apply path exists (task brief)."""
    assert "dashboards" not in state_io.APPLY_FNS
    assert "dashboards" in state_io.PULL_FNS
    assert "dashboards" in state_io.DIFF_FNS


# --------------------------------------------------------------------------
# manifest / report / registry
# --------------------------------------------------------------------------


def test_types_registry_order() -> None:
    # Core SIEM types always come first in canonical order.
    siem_types = ("rules", "parsers", "macros", "lookups", "dashboards")
    assert state_io.TYPES[:5] == siem_types
    # soar-playbooks is registered and applicable.
    assert "soar-playbooks" in state_io.TYPES
    assert "soar-playbooks" in state_io.APPLICABLE_TYPES
    # dashboards remain pull+diff only.
    assert "dashboards" not in state_io.APPLICABLE_TYPES


def test_write_manifest_no_wall_clock(tmp_path: Path) -> None:
    state_io.write_manifest(tmp_path, host="localhost:8089", counts={"rules": 3})
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert manifest["host"] == "localhost:8089"
    assert manifest["types"] == {"rules": 3}
    assert "timestamp" not in manifest
    assert "version" in manifest


def test_write_report_shape(tmp_path: Path) -> None:
    report_path = tmp_path / "r.json"
    change: state_io.ChangeRecord = {
        "type": "rules",
        "name": "det1",
        "change": "modified",
        "before": {"search": "old"},
        "after": {"search": "new"},
    }
    state_io.write_report(
        report_path, host="h:8089", types=["rules"], changes=[change], applied=True
    )
    report = json.loads(report_path.read_text())
    assert report == {
        "host": "h:8089",
        "types": ["rules"],
        "changes": [change],
        "applied": True,
    }


def test_resolve_host() -> None:
    svc = MagicMock()
    svc.host = "splunk.example"
    svc.port = 8089
    client = _client(svc)
    assert state_io.resolve_host(client) == "splunk.example:8089"


# --------------------------------------------------------------------------
# SPL injection regression in state_io_blobs._download_csv
# --------------------------------------------------------------------------


def test_pull_lookups_quotes_name_in_spl(tmp_path: Path) -> None:
    """A hostile server-side lookup name must be quoted in the SPL query."""
    svc = MagicMock()
    name = "foo | delete index=main"
    svc.lookup_table_files.list.return_value = [_mock_lookup(name)]
    svc.jobs.oneshot.return_value.read.return_value = b"a,b\n1,2\n"
    client = _client(svc)

    state_io.pull_lookups(client, tmp_path, None)

    spl_arg = svc.jobs.oneshot.call_args.args[0]
    assert spl_arg == '| inputlookup "foo | delete index=main"'


def test_diff_lookups_quotes_name_in_spl(tmp_path: Path) -> None:
    """Diff path also quotes lookup names against SPL injection."""
    (tmp_path / "lookups").mkdir()
    name = 'tricky"name'
    (tmp_path / "lookups" / name).write_text("x\n")
    svc = MagicMock()
    svc.lookup_table_files.list.return_value = [_mock_lookup(name)]
    svc.jobs.oneshot.return_value.read.return_value = b"x\n"
    client = _client(svc)

    state_io.diff_lookups(client, tmp_path, None)

    spl_arg = svc.jobs.oneshot.call_args.args[0]
    assert spl_arg == '| inputlookup "tricky\\"name"'
