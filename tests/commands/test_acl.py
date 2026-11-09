"""ACL contracts from captured Splunk 10.6.1.1 responses."""

import io
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from splunkctl import acl_ops
from splunkctl.main import cli

FIXTURES = Path(__file__).parents[1] / "fixtures/live/splunk-10.6.1.1"


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / (name + ".json")).read_text())


def response(name: str) -> SimpleNamespace:
    return SimpleNamespace(body=io.BytesIO(json.dumps(fixture(name)).encode()))


@pytest.fixture
def service():
    svc = MagicMock()
    svc.namespace = {"owner": None, "app": None}
    svc.get.side_effect = lambda *a, **k: response("acl-saved-searches")
    with patch(
        "splunkctl.commands.acl.get_client", return_value=SimpleNamespace(service=svc)
    ):
        yield svc


@pytest.mark.parametrize(
    "kind,file",
    [
        ("saved-search", "acl-saved-searches"),
        ("macro", "acl-conf-macros"),
        ("tag", "acl-tags-conf-tags"),
        ("lookup-definition", "acl-lookup-definition"),
        ("lookup-table", "acl-lookup-table-file"),
        ("data-model", "acl-datamodel"),
        ("field-extraction", "acl-props-extraction"),
        ("view", "acl-views"),
        ("dashboard", "acl-views"),
    ],
)
def test_get_live_acl(service, kind, file):
    body = fixture(file)
    service.get.side_effect = lambda *a, **k: response(file)
    result = CliRunner().invoke(
        cli,
        ["--json", "acl", "get", kind, body["entry"][0]["name"], "--owner", "admin"],
    )
    assert result.exit_code == 0, result.output
    row = json.loads(result.stdout)[0]
    assert row["owner"] == "admin"
    assert row["read"] is None and row["write"] is None
    assert row["modifiable"] is True


@pytest.mark.parametrize(
    "file,kind,encoded",
    [
        ("acl-tags-conf-tags", "tag", "sourcetype%3Dsc_live_acl_st"),
        (
            "acl-props-extraction",
            "field-extraction",
            "sc_live_acl_st%20%3A%20EXTRACT-sc_live_acl_ext",
        ),
    ],
)
def test_one_encoded_segment(service, file, kind, encoded):
    service.get.side_effect = lambda *a, **k: response(file)
    result = CliRunner().invoke(
        cli, ["acl", "get", kind, fixture(file)["entry"][0]["name"]]
    )
    assert result.exit_code == 0
    assert str(service.get.call_args.args[0]).endswith("/" + encoded)


def test_preview_and_apply_use_canonical_readback(service):
    args = [
        "--json",
        "acl",
        "set",
        "saved-search",
        "sc_live_acl_search",
        "--sharing",
        "app",
    ]
    result = CliRunner().invoke(cli, args)
    assert result.exit_code == 0
    assert "before:" in result.stderr and "after:" in result.stderr
    service.post.assert_not_called()
    service.get.side_effect = [
        response("acl-saved-searches"),
        response("acl-set-saved-search-getback"),
    ]
    service.post.return_value = response("acl-set-saved-search-response")
    result = CliRunner().invoke(cli, ["--yes", *args])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)[0]["sharing"] == "app"
    assert service.post.call_args.kwargs["body"] == {
        "owner": "admin",
        "sharing": "app",
        "app": "search",
    }
    assert (
        service.get.call_args.args[0]
        == "/servicesNS/nobody/search/saved/searches/sc_live_acl_search"
    )


def test_private_permissions_rejected(service):
    result = CliRunner().invoke(
        cli, ["--yes", "acl", "set", "saved-search", "x", "--read", "*"]
    )
    assert result.exit_code != 0
    assert "--read/--write require" in result.stderr
    service.post.assert_not_called()


def test_roles_validation_name_only_list(service):
    # No live roles fixture exists. EAI roles resolution only needs entry.name.
    role_body = {"entry": [{"name": "admin"}]}
    service.get.side_effect = [
        response("acl-saved-searches"),
        SimpleNamespace(body=io.BytesIO(json.dumps(role_body).encode())),
    ]
    result = CliRunner().invoke(
        cli,
        [
            "--yes",
            "acl",
            "set",
            "saved-search",
            "x",
            "--sharing",
            "app",
            "--read",
            "missing",
        ],
    )
    assert result.exit_code != 0
    assert "Unknown role: missing" in result.stderr
    service.post.assert_not_called()


def test_clear_and_normalize_roles():
    assert acl_ops.roles("") == []
    assert acl_ops.roles("admin,admin, user") == ["admin", "user"]
    assert acl_ops.roles(None) is None


def test_invalid_sharing_never_fetches(service):
    result = CliRunner().invoke(
        cli, ["acl", "set", "saved-search", "x", "--sharing", "invalid"]
    )
    assert result.exit_code != 0
    service.get.assert_not_called()


def test_no_change_skips_post(service):
    result = CliRunner().invoke(cli, ["--yes", "acl", "set", "saved-search", "x"])
    assert result.exit_code == 0
    service.post.assert_not_called()


@pytest.mark.parametrize("fmt", ["csv", "table"])
def test_null_permissions_blank(service, fmt):
    result = CliRunner().invoke(
        cli, ["--format", fmt, "acl", "get", "saved-search", "x"]
    )
    assert result.exit_code == 0
    assert "None" not in result.stdout


def test_adapter_acl_update_moves_delete_path():
    from splunkctl.rest_adapters import _Entity

    svc = MagicMock()
    original = fixture("acl-saved-searches")["entry"][0]
    entity = _Entity(svc, "saved/searches", original)
    svc.post.return_value = response("acl-set-saved-search-response")
    svc.get.return_value = response("acl-set-saved-search-getback")
    entity.acl_update(sharing="app")
    assert svc.post.call_args.kwargs["body"] == {"owner": "admin", "sharing": "app"}
    assert (
        str(svc.get.call_args.args[0])
        == "/servicesNS/nobody/search/saved/searches/sc_live_acl_search"
    )
    entity.delete()
    assert (
        str(svc.delete.call_args.args[0])
        == "/servicesNS/nobody/search/saved/searches/sc_live_acl_search"
    )


def test_client_shared_helper_preserves_owner_and_updates_sdk_path():
    from splunkctl.client import SplunkClient

    svc = MagicMock()
    svc.get.side_effect = [
        response("acl-saved-searches"),
        response("acl-set-saved-search-getback"),
    ]
    svc.post.return_value = response("acl-set-saved-search-response")
    entity = MagicMock()
    entry = fixture("acl-saved-searches")["entry"][0]
    entity.name, entity.access = entry["name"], entry["acl"]
    entity.path = "saved/searches/" + entry["name"]
    client = SplunkClient()
    client._service = svc
    client.set_acl(entity, sharing="app")
    assert svc.post.call_args.kwargs["body"]["owner"] == "admin"
    assert entity.path == "/servicesNS/nobody/search/saved/searches/sc_live_acl_search"
    entity.acl_update.assert_not_called()


@pytest.mark.parametrize(
    "namespace,selectors,expected",
    [
        (
            {"owner": "admin", "app": "search"},
            {"app": "search", "owner": None},
            "/servicesNS/admin/search/",
        ),
        (
            {"owner": "admin", "app": "search"},
            {"app": None, "owner": "admin"},
            "/servicesNS/admin/search/",
        ),
        (
            {"owner": None, "app": "search"},
            {"app": "search", "owner": None},
            "/servicesNS/-/search/",
        ),
        (
            {"owner": "user/name", "app": "my app"},
            {"app": None, "owner": None},
            "/servicesNS/user%2Fname/my%20app/",
        ),
    ],
)
def test_namespace_selectors_use_actual_sdk_wire(namespace, selectors, expected):
    from splunklib.client import Service

    svc = Service(token="test-token", **namespace)  # noqa: S106
    svc.http = MagicMock()
    svc.http.get.return_value = response("acl-saved-searches")
    entry = acl_ops.resolve(svc, "saved-search", "sc_live_acl_search", **selectors)
    assert entry["acl"]["owner"] == "admin"
    assert (
        str(svc.http.get.call_args.args[0])
        == str(svc.authority) + expected + "saved/searches/sc_live_acl_search"
    )


def wire(body):
    return SimpleNamespace(body=io.BytesIO(json.dumps(body).encode()))


@pytest.mark.parametrize(
    "read,write,expected",
    [
        ("power", None, {"perms.read": "power", "perms.write": "admin"}),
        (None, "power", {"perms.read": "*", "perms.write": "power"}),
        ("", None, {"perms.write": "admin"}),
        (None, "", {"perms.read": "*"}),
    ],
)
def test_merge_and_clear_permission_lists(service, read, write, expected):
    entry = fixture("acl-set-saved-search-getback")["entry"][0]
    service.get.side_effect = lambda *a, **k: wire({"entry": [{"name": "power"}]})
    fields = acl_ops.changes(
        service, entry, sharing=None, owner=None, read=read, write=write
    )
    assert {k: v for k, v in fields.items() if k.startswith("perms.")} == expected


@pytest.mark.parametrize("read,write", [("", ""), (" , ", "")])
def test_clear_both_before_requests(service, read, write):
    result = CliRunner().invoke(
        cli, ["acl", "set", "saved-search", "x", "--read", read, "--write", write]
    )
    assert result.exit_code == 2
    assert "cannot clear both" in result.stderr
    service.get.assert_not_called()
    service.post.assert_not_called()


@pytest.mark.parametrize("corrupt", ["read", "write"])
def test_readback_checks_both_lists(service, corrupt):
    entry = fixture("acl-set-saved-search-getback")["entry"][0]
    fields = {
        "owner": "admin",
        "sharing": "app",
        "perms.read": "power",
        "perms.write": "admin",
    }
    entry["acl"]["perms"] = {"read": ["power"], "write": ["admin"]}
    entry["acl"]["perms"][corrupt] = ["wrong"]
    service.post.return_value = wire({"entry": [entry]})
    service.get.side_effect = lambda *a, **k: wire({"entry": [entry]})
    with pytest.raises(Exception, match="read-back"):
        acl_ops.update(service, entry, fields)


def test_clear_readback_rejects_retained_list(service):
    entry = fixture("acl-set-saved-search-getback")["entry"][0]
    service.post.return_value = wire({"entry": [entry]})
    service.get.side_effect = lambda *a, **k: wire({"entry": [entry]})
    with pytest.raises(Exception, match="read-back"):
        acl_ops.update(
            service, entry, {"owner": "admin", "sharing": "app", "perms.write": "admin"}
        )


@pytest.mark.parametrize("name", ["sc_live_acl_search", "folder/search"])
def test_applied_owner_change_and_slash_wire(name):
    from urllib.parse import quote

    from splunklib.client import Service

    calls = []
    entry = fixture("acl-saved-searches")["entry"][0]
    entry["name"] = name
    path = "/servicesNS/admin/search/saved/searches/" + quote(name, safe="")
    entry["links"]["alternate"] = path

    def network(url, message, **kwargs):
        calls.append((url.split("?")[0], message["method"]))
        if message["method"] == "POST":
            entry["acl"]["owner"] = "power"
            entry["links"]["alternate"] = path.replace("/admin/", "/power/")
        return {
            "status": 200,
            "reason": "OK",
            "headers": [],
            "body": io.BytesIO(json.dumps({"entry": [entry]}).encode()),
        }

    svc = Service(host="example.test", token="test", handler=network)  # noqa: S106
    with patch(
        "splunkctl.commands.acl.get_client", return_value=SimpleNamespace(service=svc)
    ):
        result = CliRunner().invoke(
            cli,
            [
                "--json",
                "--yes",
                "acl",
                "set",
                "saved-search",
                name,
                "--current-owner",
                "admin",
                "--owner",
                "power",
            ],
        )
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)[0]["owner"] == "power"
    assert calls == [
        ("https://example.test:8089" + path, "GET"),
        ("https://example.test:8089" + path + "/acl", "POST"),
        ("https://example.test:8089" + path.replace("/admin/", "/power/"), "GET"),
    ]


@pytest.mark.parametrize("found", ["admin", "nobody", None])
def test_datamodel_owner_fallback_500_body(found):
    from splunklib.client import Service

    calls = []

    def network(url, message, **kwargs):
        path = url.split("?")[0]
        calls.append(path)
        status = 200
        if path.endswith("/authentication/current-context"):
            body = {"entry": [{"content": {"username": "admin"}}]}
        elif found and f"/servicesNS/{found}/search/" in path:
            body = fixture("acl-datamodel")
        else:
            status = 500
            body = {
                "messages": [
                    {
                        "type": "ERROR",
                        "text": "Cannot get username when all users are selected",
                    }
                ]
            }
        return {
            "status": status,
            "reason": "OK" if status == 200 else "Internal Server Error",
            "headers": [],
            "body": io.BytesIO(json.dumps(body).encode()),
        }

    svc = Service(host="example.test", token="test", handler=network)  # noqa: S106
    with patch(
        "splunkctl.commands.acl.get_client", return_value=SimpleNamespace(service=svc)
    ):
        result = CliRunner().invoke(cli, ["--json", "acl", "set", "data-model", "x"])
    if found:
        assert result.exit_code == 0, result.output
    else:
        assert result.exit_code == 1
        assert '"kind": "not_found"' in result.stderr
        assert "pass --current-owner" in result.stderr
    assert not any("/servicesNS/-/" in p for p in calls)
    assert any("/servicesNS/admin/search/" in p for p in calls)
    assert any("/servicesNS/nobody/search/" in p for p in calls) == (found != "admin")


def test_private_restore_keeps_permissions(service):
    entry = fixture("acl-set-saved-search-getback")["entry"][0]
    restored = json.loads(json.dumps(entry))
    restored["acl"]["sharing"] = "user"
    service.get.side_effect = [wire({"entry": [entry]}), wire({"entry": [restored]})]
    service.post.return_value = wire({"entry": [restored]})
    result = CliRunner().invoke(
        cli, ["--json", "--yes", "acl", "set", "saved-search", "x", "--sharing", "user"]
    )
    assert result.exit_code == 0, result.output
    row = json.loads(result.stdout)[0]
    assert row["sharing"] == "user"
    assert row["read"] == ["*"] and row["write"] == ["admin"]
