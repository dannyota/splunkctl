"""REST adapter contracts against the upstream SDK request boundary."""

import io
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from splunklib.binding import HTTPError, UrlEncoded

from splunkctl.client import SplunkClient


def entry(name: str = "a/b %2F", **content: object) -> dict:
    return {
        "name": name,
        "content": {"eai:data": "<dashboard/>", **content},
        "acl": {"owner": "alice", "app": "my app", "sharing": "app"},
    }


def response(entries: list[dict]) -> MagicMock:
    resp = MagicMock()
    resp.body.read.return_value = json.dumps({"entry": entries}).encode()
    return resp


def client() -> SplunkClient:
    result = SplunkClient()
    result._service = MagicMock()
    result._service.namespace = {"owner": None, "app": None}
    return result


def test_lazy_adapters_always_override_service_properties() -> None:
    c = client()
    for name in ("dashboards", "lookup_table_files", "hec_tokens"):
        assert getattr(c, name) is getattr(c, name)
        assert getattr(c, name) is not getattr(c.service, name)


@pytest.mark.parametrize(
    "kind,path",
    [
        ("dashboards", "data/ui/views"),
        ("lookup_table_files", "data/lookup-table-files"),
        ("hec_tokens", "data/inputs/http"),
    ],
)
def test_list_defaults_all_and_preserves_paging(kind: str, path: str) -> None:
    c = client()
    c.service.get.return_value = response([entry(str(i)) for i in range(65)])
    items = getattr(c, kind).list(owner="-", app="-")
    assert [x.name for x in items] == [str(i) for i in range(65)]
    c.service.get.assert_called_once_with(
        path, owner="-", app="-", output_mode="json", count=0
    )
    c.service.get.reset_mock()
    getattr(c, kind).list(count=7, offset=31, search="name=*abc*", app="search")
    c.service.get.assert_called_once_with(
        path,
        owner=None,
        app="search",
        output_mode="json",
        count=7,
        offset=31,
        search="name=*abc*",
    )


def test_dashboard_entity_mutations_use_resolved_namespace_and_encoded_path() -> None:
    c = client()
    c.service.get.return_value = response([entry()])
    d = c.dashboards["a/b %2F"]
    assert d.export() == "<dashboard/>"
    assert d.content["eai:data"] == d.content.__getattr__("eai:data")
    assert d.access.app == d.access["app"] == "my app"
    d.update(**{"eai:data": "<form/>"})
    d.acl_update(owner="bob", sharing="global")
    d.delete()
    path = c.service.get.call_args.args[0]
    assert path == "data/ui/views/a%2Fb%20%252F"
    assert isinstance(path, UrlEncoded)
    assert UrlEncoded(path) == path
    c.service.post.assert_any_call(
        path, owner="alice", app="my%20app", **{"eai:data": "<form/>"}
    )
    c.service.post.assert_any_call(
        "/servicesNS/alice/my%20app/" + str(path) + "/acl",
        body={"owner": "bob", "sharing": "global"},
    )
    c.service.delete.assert_called_once_with(path, owner="alice", app="my%20app")


def test_create_dashboard_posts_form_and_resolves_entity() -> None:
    c = client()
    c.service.get.return_value = response([entry("new")])
    d = c.dashboards.create("new", "<dashboard/>", app="search")
    assert d.name == "new"
    c.service.post.assert_called_once_with(
        "data/ui/views",
        owner=None,
        app="search",
        name="new",
        **{"eai:data": "<dashboard/>"},
    )


@pytest.mark.parametrize(
    "requested,returned", [("token", "http://token"), ("http://token", "token")]
)
def test_hec_aliases_and_enable_disable(requested: str, returned: str) -> None:
    c = client()
    c.service.get.return_value = response(
        [
            entry(
                returned,
                token="secret",  # noqa: S106
            )
        ]
    )
    t = c.hec_tokens[requested]
    assert t.name == returned
    t.enable()
    t.disable()
    path = "data/inputs/http/" + UrlEncoded(returned, encode_slash=True)
    c.service.post.assert_any_call(path, owner="alice", app="my%20app", disabled="0")
    c.service.post.assert_any_call(path, owner="alice", app="my%20app", disabled="1")


def test_hec_create_and_lookup_delete() -> None:
    c = client()
    c.service.get.return_value = response([entry("token")])
    assert c.hec_tokens.create("token", index="main").name == "token"
    c.service.post.assert_called_once_with(
        "data/inputs/http", owner=None, app=None, name="token", index="main"
    )
    c.service.get.return_value = response([entry("hosts.csv")])
    c.lookup_table_files["hosts.csv"].delete()
    c.service.delete.assert_called_once_with(
        "data/lookup-table-files/hosts.csv", owner="alice", app="my%20app"
    )


@pytest.mark.parametrize("status", [401, 403, 404, 500])
def test_only_entity_404_becomes_key_error(status: int) -> None:
    c = client()
    error = HTTPError(
        SimpleNamespace(
            status=status,
            reason="failure",
            headers=[],
            body=io.BytesIO(b""),
        )
    )
    c.service.get.side_effect = error
    with pytest.raises(KeyError if status == 404 else HTTPError) as caught:
        c.dashboards["absent"]
    if status != 404:
        assert caught.value is error
    with pytest.raises(HTTPError) as caught:
        c.dashboards.list()
    assert caught.value is error


def test_empty_and_malformed_responses_and_network_errors() -> None:
    c = client()
    c.service.get.return_value = response([])
    with pytest.raises(KeyError):
        c.dashboards["absent"]
    c.service.get.return_value.body.read.return_value = b"not json"
    with pytest.raises(json.JSONDecodeError):
        c.dashboards.list()
    c.service.get.return_value.body.read.return_value = b"{}"
    with pytest.raises(ValueError):
        c.dashboards.list()
    error = ConnectionError("offline")
    c.service.get.side_effect = error
    with pytest.raises(ConnectionError) as caught:
        c.hec_tokens["token"]
    assert caught.value is error


@pytest.mark.parametrize(
    "requested,alias", [("token", "http://token"), ("http://token", "token")]
)
def test_hec_retries_only_missing_alias(requested: str, alias: str) -> None:
    c = client()
    c.service.get.side_effect = [response([]), response([entry(alias)])]
    assert c.hec_tokens[requested].name == alias
    assert len(c.service.get.call_args_list) == 2
    assert c.service.get.call_args.args[0] == "data/inputs/http/" + UrlEncoded(
        alias, encode_slash=True
    )


def test_malformed_hec_entry_does_not_retry_alias() -> None:
    c = client()
    c.service.get.return_value.body.read.return_value = b"{}"
    with pytest.raises(ValueError, match="entry"):
        c.hec_tokens["token"]
    c.service.get.assert_called_once()


def test_upstream_wire_encodes_namespaces_and_acl_form() -> None:
    from urllib.parse import parse_qs

    from splunklib.client import Service

    c = client()
    service = Service(token="test-token")  # noqa: S106
    service.http = MagicMock()
    service.http.get.return_value = response([entry()])
    c._service = service
    d = c.dashboards["a/b %2F"]
    d.update(**{"eai:data": "<form/>"})
    d.acl_update(owner="bob", sharing="global")
    d.delete()
    update = service.http.post.call_args_list[0]
    assert str(update.args[0]).endswith(
        "/servicesNS/alice/my%20app/data/ui/views/a%2Fb%20%252F"
    )
    acl = service.http.post.call_args_list[1]
    assert str(acl.args[0]).endswith(
        "/servicesNS/alice/my%20app/data/ui/views/a%2Fb%20%252F/acl"
    )
    assert acl.kwargs["body"] == {"owner": "bob", "sharing": "global"}
    # Exercise the SDK's actual form encoder too, without a network connection.
    from splunklib.binding import HttpLib

    transport = HttpLib(
        MagicMock(
            return_value={"status": 200, "reason": "OK", "headers": [], "body": b""}
        )
    )
    transport.post(acl.args[0], body=acl.kwargs["body"])
    message = transport.handler.call_args.args[1]
    assert parse_qs(message["body"].decode()) == {
        "owner": ["bob"],
        "sharing": ["global"],
    }


@pytest.mark.parametrize(
    "raw",
    [
        b"null",
        b'{"entry":null}',
        b'{"entry":[{}]}',
        b'{"entry":[{"name":"x","content":{},"acl":null}]}',
    ],
)
def test_malformed_metadata_is_not_missing(raw: bytes) -> None:
    c = client()
    c.service.get.return_value.body.read.return_value = raw
    with pytest.raises(ValueError):
        c.hec_tokens["x"]
    c.service.get.assert_called_once()


def test_content_acl_fallback_and_mutation_errors_propagate() -> None:
    c = client()
    item = entry("x")
    item["content"]["eai:acl"] = item.pop("acl")
    c.service.get.return_value = response([item])
    d = c.dashboards.list()[0]
    assert dict(d.access) == {"owner": "alice", "app": "my app", "sharing": "app"}
    error = ConnectionError("offline")
    c.service.post.side_effect = error
    c.service.delete.side_effect = error
    for operation in (d.update, d.acl_update, d.delete):
        with pytest.raises(ConnectionError) as caught:
            operation()
        assert caught.value is error


def test_list_namespace_retained_without_acl() -> None:
    c = client()
    c.service.get.return_value = response([{"name": "x", "content": {}}])
    c.lookup_table_files.list(owner="bob", app="search")[0].delete()
    c.service.delete.assert_called_once_with(
        "data/lookup-table-files/x", owner="bob", app="search"
    )


def test_default_service_namespace_is_encoded_for_entity_requests() -> None:
    from splunklib.client import Service

    c = client()
    service = Service(token="test-token", owner="alice/name", app="my app")  # noqa: S106
    service.http = MagicMock()
    service.http.get.return_value = response([{"name": "http://x", "content": {}}])
    c._service = service
    t = c.hec_tokens["x"]
    t.disable()
    t.delete()
    for request in (service.http.get, service.http.post, service.http.delete):
        assert "/servicesNS/alice%2Fname/my%20app/" in str(request.call_args.args[0])
