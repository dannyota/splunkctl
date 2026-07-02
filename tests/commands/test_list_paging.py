"""Uniform --limit/--offset/--filter wiring on every list surface.

Server-capable surfaces pass count/offset through to the SDK call when
--filter is absent; with --filter everything is fetched and paging applies
client-side to the filtered set. Surfaces that already post-process rows
client-side (alerts, dashboards, inputs) filter and page client-side.

``SdkCollection`` mimics the forked SDK's paging contract (count omitted
means fetch everything) so these tests also guard the no-truncation
default against regressions.
"""

import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from splunkctl.main import cli


class SdkCollection:
    """Mimic the forked SDK Collection paging contract.

    ``count=None`` (the default) fetches everything — the SDK sends its
    null-count sentinel and the server returns the full collection. If a
    list command ever starts passing a default count or slicing the
    unfiltered set client-side, tests using this fake fail.
    """

    def __init__(self, entities: list[Any]) -> None:
        self._entities = entities
        self.calls: list[dict[str, Any]] = []

    def list(
        self, count: int | None = None, offset: int = 0, **kwargs: Any
    ) -> list[Any]:
        self.calls.append({"count": count, "offset": offset, **kwargs})
        items = self._entities[offset:]
        if count is not None:
            items = items[:count]
        return items


def _entity(name: str, **content: Any) -> MagicMock:
    e = MagicMock()
    e.name = name
    e.content = content
    e.access = {"app": "search", "owner": "admin"}
    return e


def _names(result_output: str, key: str = "name") -> list[str]:
    return [row[key] for row in json.loads(result_output)]


# --- no-truncation guard ---


@patch("splunkctl.commands.users.get_client")
def test_users_list_default_renders_all_beyond_page_size(mock_gc: MagicMock) -> None:
    """35 entries (> the server's 30-per-page default) all render by default.

    This is the no-truncation contract: bare list commands must keep
    fetching everything (SDK count sentinel), not a default page.
    """
    users = [_entity(f"user{i:02d}") for i in range(35)]
    fake = SdkCollection(users)
    mock_gc.return_value.service.users = fake
    result = CliRunner().invoke(cli, ["--json", "users", "list"])
    assert result.exit_code == 0
    assert len(_names(result.output)) == 35
    assert fake.calls == [{"count": None, "offset": 0}]


# --- validation ---


@patch("splunkctl.commands.users.get_client")
def test_limit_zero_is_usage_error(mock_gc: MagicMock) -> None:
    result = CliRunner().invoke(cli, ["users", "list", "--limit", "0"])
    assert result.exit_code == 2
    mock_gc.assert_not_called()


@patch("splunkctl.commands.users.get_client")
def test_negative_offset_is_usage_error(mock_gc: MagicMock) -> None:
    result = CliRunner().invoke(cli, ["users", "list", "--offset=-1"])
    assert result.exit_code == 2
    mock_gc.assert_not_called()


# --- server-paged surfaces ---


@patch("splunkctl.commands.users.get_client")
def test_users_list_limit_offset_server_side(mock_gc: MagicMock) -> None:
    users = [_entity(f"user{i}") for i in range(5)]
    fake = SdkCollection(users)
    mock_gc.return_value.service.users = fake
    result = CliRunner().invoke(
        cli, ["--json", "users", "list", "--limit", "2", "--offset", "1"]
    )
    assert result.exit_code == 0
    assert _names(result.output) == ["user1", "user2"]
    assert fake.calls == [{"count": 2, "offset": 1}]


@patch("splunkctl.commands.users.get_client")
def test_users_list_filter_pages_client_side(mock_gc: MagicMock) -> None:
    users = [_entity(n) for n in ["admin", "analyst-a", "analyst-b", "svc"]]
    fake = SdkCollection(users)
    mock_gc.return_value.service.users = fake
    result = CliRunner().invoke(
        cli, ["--json", "users", "list", "--filter", "ANALYST", "--limit", "1"]
    )
    assert result.exit_code == 0
    assert _names(result.output) == ["analyst-a"]
    # filter forces a full fetch; paging happened after filtering
    assert fake.calls == [{"count": None, "offset": 0}]


@patch("splunkctl.commands.users.get_client")
def test_roles_list_paging_and_filter(mock_gc: MagicMock) -> None:
    roles = [_entity(n) for n in ["admin", "power", "user", "sc_admin"]]
    fake = SdkCollection(roles)
    mock_gc.return_value.service.roles = fake
    result = CliRunner().invoke(
        cli, ["--json", "users", "roles", "list", "--limit", "2", "--offset", "1"]
    )
    assert result.exit_code == 0
    assert _names(result.output) == ["power", "user"]
    assert fake.calls == [{"count": 2, "offset": 1}]

    result = CliRunner().invoke(
        cli, ["--json", "users", "roles", "list", "--filter", "ADMIN"]
    )
    assert result.exit_code == 0
    assert _names(result.output) == ["admin", "sc_admin"]


@patch("splunkctl.commands.apps.get_client")
def test_apps_list_paging_and_filter(mock_gc: MagicMock) -> None:
    apps = [_entity(n) for n in ["search", "sse", "launcher"]]
    fake = SdkCollection(apps)
    mock_gc.return_value.service.apps = fake
    result = CliRunner().invoke(cli, ["--json", "apps", "list", "--limit", "1"])
    assert result.exit_code == 0
    assert _names(result.output) == ["search"]
    assert fake.calls == [{"count": 1, "offset": 0}]

    result = CliRunner().invoke(cli, ["--json", "apps", "list", "--filter", "SSE"])
    assert result.exit_code == 0
    assert _names(result.output) == ["sse"]


@patch("splunkctl.commands.indexes.get_client")
def test_indexes_list_paging_and_filter(mock_gc: MagicMock) -> None:
    idx = [_entity(n) for n in ["main", "_internal", "threat_intel"]]
    fake = SdkCollection(idx)
    mock_gc.return_value.service.indexes = fake
    result = CliRunner().invoke(
        cli, ["--json", "indexes", "list", "--limit", "1", "--offset", "2"]
    )
    assert result.exit_code == 0
    assert _names(result.output) == ["threat_intel"]
    assert fake.calls == [{"count": 1, "offset": 2}]

    result = CliRunner().invoke(cli, ["--json", "indexes", "list", "--filter", "int"])
    assert result.exit_code == 0
    assert _names(result.output) == ["_internal", "threat_intel"]


@patch("splunkctl.commands.hec.get_client")
def test_hec_list_paging_and_filter(mock_gc: MagicMock) -> None:
    toks = [_entity(f"http://{n}") for n in ["tok-a", "tok-b", "ingest"]]
    fake = SdkCollection(toks)
    mock_gc.return_value.service.hec_tokens = fake
    result = CliRunner().invoke(cli, ["--json", "hec", "list", "--limit", "2"])
    assert result.exit_code == 0
    assert _names(result.output) == ["http://tok-a", "http://tok-b"]
    assert fake.calls == [{"count": 2, "offset": 0}]

    result = CliRunner().invoke(cli, ["--json", "hec", "list", "--filter", "TOK"])
    assert result.exit_code == 0
    assert _names(result.output) == ["http://tok-a", "http://tok-b"]


@patch("splunkctl.commands.lookups.get_client")
def test_lookups_list_merges_app_kwargs_with_paging(mock_gc: MagicMock) -> None:
    lks = []
    for n in ["geo.csv", "mitre_map.csv", "users.csv"]:
        lk = MagicMock()
        lk.name = n
        lk.content = {}
        lk.access = SimpleNamespace(app="search", owner="nobody")
        lks.append(lk)
    fake = SdkCollection(lks)
    mock_gc.return_value.service.lookup_table_files = fake
    result = CliRunner().invoke(cli, ["--json", "lookups", "list", "--limit", "1"])
    assert result.exit_code == 0
    assert _names(result.output) == ["geo.csv"]
    assert fake.calls == [{"count": 1, "offset": 0, "app": "-", "owner": "-"}]

    result = CliRunner().invoke(cli, ["--json", "lookups", "list", "--filter", "MITRE"])
    assert result.exit_code == 0
    assert _names(result.output) == ["mitre_map.csv"]


@patch("splunkctl.commands.rules.get_client")
def test_rules_list_merges_scope_kwargs_with_paging(mock_gc: MagicMock) -> None:
    rules = [_entity(n, is_scheduled="1") for n in ["r1", "r2", "r3"]]
    fake = SdkCollection(rules)
    mock_gc.return_value.service.saved_searches = fake
    result = CliRunner().invoke(
        cli, ["--json", "rules", "list", "--app", "sse", "--limit", "2"]
    )
    assert result.exit_code == 0
    assert _names(result.output) == ["r1", "r2"]
    assert fake.calls == [{"count": 2, "offset": 0, "app": "sse", "owner": "-"}]


@patch("splunkctl.commands.rules.get_client")
def test_rules_list_filter_keeps_existing_semantics(mock_gc: MagicMock) -> None:
    rules = [_entity(n) for n in ["Brute Force", "Beaconing", "Exfil"]]
    fake = SdkCollection(rules)
    mock_gc.return_value.service.saved_searches = fake
    result = CliRunner().invoke(cli, ["--json", "rules", "list", "--filter", "brute"])
    assert result.exit_code == 0
    assert _names(result.output) == ["Brute Force"]
    assert fake.calls == [{"count": None, "offset": 0}]


@patch("splunkctl.commands.parsers.get_client")
def test_sourcetypes_paging_and_filter(mock_gc: MagicMock) -> None:
    stanzas = [_entity(n) for n in ["syslog", "access_combined", "json_auto"]]
    fake = SdkCollection(stanzas)
    mock_gc.return_value.service.confs = {"props": fake}
    result = CliRunner().invoke(
        cli, ["--json", "parsers", "sourcetypes", "--limit", "1", "--offset", "1"]
    )
    assert result.exit_code == 0
    assert _names(result.output) == ["access_combined"]
    assert fake.calls == [{"count": 1, "offset": 1}]

    result = CliRunner().invoke(
        cli, ["--json", "parsers", "sourcetypes", "--filter", "SYS"]
    )
    assert result.exit_code == 0
    assert _names(result.output) == ["syslog"]


@patch("splunkctl.commands.parsers.get_client")
def test_extractions_paging_server_side_without_sourcetype(mock_gc: MagicMock) -> None:
    stanzas = [_entity(n) for n in ["t1", "t2", "t3"]]
    fake = SdkCollection(stanzas)
    mock_gc.return_value.service.confs = {"transforms": fake}
    result = CliRunner().invoke(
        cli, ["--json", "parsers", "extractions", "--limit", "2"]
    )
    assert result.exit_code == 0
    assert _names(result.output) == ["t1", "t2"]
    assert fake.calls == [{"count": 2, "offset": 0}]


@patch("splunkctl.commands.parsers.get_client")
def test_extractions_sourcetype_composes_with_paging(mock_gc: MagicMock) -> None:
    """--sourcetype keeps its existing client-side substring semantics;

    paging then applies to the filtered set.
    """
    names = ["syslog-extract", "syslog-hosts", "json-fields"]
    stanzas = [_entity(n) for n in names]
    fake = SdkCollection(stanzas)
    mock_gc.return_value.service.confs = {"transforms": fake}
    result = CliRunner().invoke(
        cli,
        [
            "--json",
            "parsers",
            "extractions",
            "--sourcetype",
            "syslog",
            "--limit",
            "1",
            "--offset",
            "1",
        ],
    )
    assert result.exit_code == 0
    assert _names(result.output) == ["syslog-hosts"]
    # client-side path: the fetch itself is unpaged
    assert fake.calls == [{"count": None, "offset": 0}]


@patch("splunkctl.commands.search.get_client")
def test_search_jobs_paging_and_sid_filter(mock_gc: MagicMock) -> None:
    jobs = []
    for sid in ["100.1", "100.2", "200.1"]:
        j = MagicMock()
        j.sid = sid
        j.content = {"dispatchState": "DONE", "search": "search x", "eventCount": 1}
        j.access = {"owner": "splunk"}
        jobs.append(j)
    fake = SdkCollection(jobs)
    mock_gc.return_value.service.jobs = fake
    result = CliRunner().invoke(
        cli, ["--json", "search", "jobs", "--limit", "1", "--offset", "1"]
    )
    assert result.exit_code == 0
    assert _names(result.output, key="sid") == ["100.2"]
    assert fake.calls == [{"count": 1, "offset": 1}]

    result = CliRunner().invoke(cli, ["--json", "search", "jobs", "--filter", "100."])
    assert result.exit_code == 0
    assert _names(result.output, key="sid") == ["100.1", "100.2"]


# --- client-side surfaces ---


def _mock_alert_group(name: str, sids: list[str]) -> MagicMock:
    group = MagicMock()
    group.name = name
    firings = []
    for sid in sids:
        f = MagicMock()
        f.content = {"trigger_time": "t", "severity": "4", "sid": sid, "actions": ""}
        firings.append(f)
    group.alerts = firings
    return group


@patch("splunkctl.commands.alerts.get_client")
def test_alerts_list_filter_and_paging_over_rows(mock_gc: MagicMock) -> None:
    groups = [
        _mock_alert_group("Brute Force", ["s1", "s2"]),
        _mock_alert_group("Beaconing", ["s3"]),
    ]
    mock_gc.return_value.service.fired_alerts = groups
    result = CliRunner().invoke(cli, ["--json", "alerts", "list", "--filter", "brute"])
    assert result.exit_code == 0
    rows = json.loads(result.output)
    assert [r["sid"] for r in rows] == ["s1", "s2"]

    result = CliRunner().invoke(
        cli, ["--json", "alerts", "list", "--limit", "2", "--offset", "1"]
    )
    assert result.exit_code == 0
    rows = json.loads(result.output)
    assert [r["sid"] for r in rows] == ["s2", "s3"]


def _mock_dashboard(name: str, app: str = "search", is_dash: str = "1") -> MagicMock:
    d = MagicMock()
    d.name = name
    d.content = {"isDashboard": is_dash, "eai:data": "", "label": name}
    d.access = SimpleNamespace(app=app, owner="nobody", sharing="app")
    return d


@patch("splunkctl.commands.dashboards.get_client")
def test_dashboards_list_filter_and_paging_after_row_filters(
    mock_gc: MagicMock,
) -> None:
    items = [
        _mock_dashboard("ops_view", is_dash="0"),  # hidden by default
        _mock_dashboard("soc_overview"),
        _mock_dashboard("soc_detail"),
        _mock_dashboard("exec_summary"),
    ]
    mock_gc.return_value.service.dashboards.list.return_value = items
    result = CliRunner().invoke(
        cli, ["--json", "dashboards", "list", "--filter", "SOC", "--limit", "1"]
    )
    assert result.exit_code == 0
    assert _names(result.output) == ["soc_overview"]

    result = CliRunner().invoke(cli, ["--json", "dashboards", "list", "--offset", "2"])
    assert result.exit_code == 0
    assert _names(result.output) == ["exec_summary"]


def _mock_input(name: str, kind: str = "monitor") -> MagicMock:
    i = MagicMock()
    i.name = name
    i.kind = kind
    i.content = {"disabled": "0", "index": "main", "sourcetype": ""}
    return i


@patch("splunkctl.commands.inputs.get_client")
def test_inputs_list_kind_composes_with_filter_and_paging(mock_gc: MagicMock) -> None:
    items = [
        _mock_input("/var/log/syslog"),
        _mock_input("/var/log/auth.log"),
        _mock_input("9997", kind="tcp"),
    ]
    mock_gc.return_value.service.inputs.list.return_value = items
    result = CliRunner().invoke(
        cli,
        ["--json", "inputs", "list", "--kind", "monitor", "--filter", "LOG"],
    )
    assert result.exit_code == 0
    assert _names(result.output) == ["/var/log/syslog", "/var/log/auth.log"]

    result = CliRunner().invoke(
        cli, ["--json", "inputs", "list", "--limit", "1", "--offset", "1"]
    )
    assert result.exit_code == 0
    assert _names(result.output) == ["/var/log/auth.log"]
