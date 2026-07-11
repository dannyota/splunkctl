"""Unit tests for splunkctl.soar.client — SOARClient."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import requests

from splunkctl.soar.client import SOARClient, SOARError, build_filters

_EMPTY_PAGE: dict[str, Any] = {
    "count": 0,
    "num_pages": 0,
    "data": [],
}


def _mock_response(
    status_code: int = 200,
    json_data: Any = None,
    *,
    raise_for_status: bool = False,
) -> MagicMock:
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data if json_data is not None else {}
    resp.text = json.dumps(json_data) if json_data is not None else ""
    if raise_for_status:
        resp.raise_for_status.side_effect = requests.HTTPError(
            response=resp,
        )
    else:
        resp.raise_for_status = MagicMock()
    return resp


def _client(
    *,
    host: str = "soar.test",
    port: int = 8443,
    token: str | None = "tok123",  # noqa: S107
    username: str | None = None,
    password: str | None = None,
    verify: bool = False,
) -> SOARClient:
    return SOARClient(
        host=host,
        port=port,
        token=token,
        username=username,
        password=password,
        verify=verify,
    )


# -------------------------------------------------------------------
# Auth header selection
# -------------------------------------------------------------------


class TestAuthHeaders:
    def test_token_auth_on_get(self) -> None:
        c = _client(token="mytoken")  # noqa: S106
        with patch.object(c, "_session") as sess:
            sess.request.return_value = _mock_response(
                json_data=_EMPTY_PAGE,
            )
            c.get("container")
        kw = sess.request.call_args
        assert kw[1]["headers"]["ph-auth-token"] == "mytoken"

    def test_basic_auth_when_no_token(self) -> None:
        c = _client(
            token=None,
            username="admin",
            password="pass",  # noqa: S106
        )
        with patch.object(c, "_session") as sess:
            sess.request.return_value = _mock_response(
                json_data=_EMPTY_PAGE,
            )
            c.get("container")
        kw = sess.request.call_args
        assert kw[1]["auth"] == ("admin", "pass")
        assert "ph-auth-token" not in kw[1].get("headers", {})

    def test_delete_uses_basic_when_available(self) -> None:
        c = _client(
            token="tok",  # noqa: S106
            username="admin",
            password="pass",  # noqa: S106
        )
        with patch.object(c, "_session") as sess:
            sess.request.return_value = _mock_response(
                json_data={"success": True},
            )
            c.delete("container/1")
        kw = sess.request.call_args
        assert kw[1]["auth"] == ("admin", "pass")
        assert "ph-auth-token" not in kw[1].get("headers", {})

    def test_delete_token_only_raises(self) -> None:
        c = _client(
            token="tok",  # noqa: S106
            username=None,
            password=None,
        )
        with pytest.raises(SOARError, match="delete requires username/password"):
            c.delete("container/1")

    def test_delete_decided_list_allows_token(self) -> None:
        c = _client(
            token="tok",  # noqa: S106
            username=None,
            password=None,
        )
        with patch.object(c, "_session") as sess:
            sess.request.return_value = _mock_response(
                json_data={"success": True},
            )
            c.delete("decided_list/1")
        kw = sess.request.call_args
        assert kw[1]["headers"]["ph-auth-token"] == "tok"


# -------------------------------------------------------------------
# Lazy I/O
# -------------------------------------------------------------------


class TestLazy:
    def test_no_io_on_init(self) -> None:
        with patch("requests.Session") as mock_cls:
            _client()
            mock_cls.return_value.request.assert_not_called()


# -------------------------------------------------------------------
# Response envelope normalization
# -------------------------------------------------------------------


class TestEnvelopeNormalization:
    def test_standard_paginated(self) -> None:
        c = _client()
        data = [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}]
        resp = _mock_response(
            json_data={"count": 2, "num_pages": 1, "data": data},
        )
        with patch.object(c, "_session") as sess:
            sess.request.return_value = resp
            result = c.get("container")
        assert result == {"count": 2, "num_pages": 1, "data": data}

    def test_audit_bare_array(self) -> None:
        c = _client()
        rows = [{"action": "create", "time": "2026-01-01"}]
        resp = _mock_response(json_data=rows)
        with patch.object(c, "_session") as sess:
            sess.request.return_value = resp
            result = c.get("audit")
        assert result == {"count": 1, "num_pages": 1, "data": rows}

    def test_search_results_envelope(self) -> None:
        c = _client()
        items = [{"id": 1}]
        resp = _mock_response(
            json_data={"results": items, "count": 1},
        )
        with patch.object(c, "_session") as sess:
            sess.request.return_value = resp
            result = c.get("search", params={"query": "test"})
        assert result == {"count": 1, "num_pages": 1, "data": items}

    def test_succeeded_key_normalized(self) -> None:
        c = _client()
        body = {
            "succeeded": True,
            "vault_id": "abc",
            "hash": "sha1",
            "id": 5,
            "size": 100,
        }
        resp = _mock_response(json_data=body)
        with patch.object(c, "_session") as sess:
            sess.request.return_value = resp
            result = c.post("container_attachment", body={"file_name": "x"})
        assert result["success"] is True
        assert "succeeded" not in result

    def test_action_run_id_normalized(self) -> None:
        c = _client()
        body = {"success": True, "action_run_id": 42}
        resp = _mock_response(json_data=body)
        with patch.object(c, "_session") as sess:
            sess.request.return_value = resp
            result = c.post("action_run", body={"action": "test"})
        assert result["id"] == 42
        assert "action_run_id" not in result

    def test_playbook_run_id_normalized(self) -> None:
        c = _client()
        body = {"received": True, "playbook_run_id": "99"}
        resp = _mock_response(json_data=body)
        with patch.object(c, "_session") as sess:
            sess.request.return_value = resp
            result = c.post("playbook_run", body={"playbook_id": 1})
        assert result["id"] == "99"
        assert "playbook_run_id" not in result


# -------------------------------------------------------------------
# Error handling
# -------------------------------------------------------------------


class TestErrorHandling:
    def test_failed_true_on_200(self) -> None:
        c = _client()
        body = {"failed": True, "message": "Something went wrong"}
        resp = _mock_response(status_code=200, json_data=body)
        with patch.object(c, "_session") as sess:
            sess.request.return_value = resp
            with pytest.raises(SOARError) as exc_info:
                c.get("container")
        assert exc_info.value.kind == "error"
        assert "Something went wrong" in str(exc_info.value)

    def test_failed_true_on_400(self) -> None:
        c = _client()
        body = {"failed": True, "message": "Bad request data"}
        resp = _mock_response(status_code=400, json_data=body)
        with patch.object(c, "_session") as sess:
            sess.request.return_value = resp
            with pytest.raises(SOARError) as exc_info:
                c.post("container", body={})
        assert "Bad request data" in str(exc_info.value)

    def test_401_maps_to_auth_kind(self) -> None:
        c = _client()
        body = {"failed": True, "message": "Not authenticated"}
        resp = _mock_response(status_code=401, json_data=body)
        with patch.object(c, "_session") as sess:
            sess.request.return_value = resp
            with pytest.raises(SOARError) as exc_info:
                c.get("container")
        assert exc_info.value.kind == "auth"
        assert exc_info.value.http_status == 401

    def test_403_maps_to_permission_kind(self) -> None:
        c = _client()
        body = {"failed": True, "message": "Forbidden"}
        resp = _mock_response(status_code=403, json_data=body)
        with patch.object(c, "_session") as sess:
            sess.request.return_value = resp
            with pytest.raises(SOARError) as exc_info:
                c.get("container")
        assert exc_info.value.kind == "permission"
        assert exc_info.value.http_status == 403

    def test_404_maps_to_not_found_kind(self) -> None:
        c = _client()
        body = {"failed": True, "message": "Object not found"}
        resp = _mock_response(status_code=404, json_data=body)
        with patch.object(c, "_session") as sess:
            sess.request.return_value = resp
            with pytest.raises(SOARError) as exc_info:
                c.get("container/999")
        assert exc_info.value.kind == "not_found"
        assert exc_info.value.http_status == 404

    def test_message_from_response_body(self) -> None:
        c = _client()
        body = {"failed": True, "message": "Specific server message"}
        resp = _mock_response(status_code=500, json_data=body)
        with patch.object(c, "_session") as sess:
            sess.request.return_value = resp
            with pytest.raises(SOARError, match="Specific server message"):
                c.get("container")


# -------------------------------------------------------------------
# Filter builder
# -------------------------------------------------------------------


class TestFilterBuilder:
    def test_simple_string_quoted(self) -> None:
        result = build_filters(name="DNS")
        assert result["_filter_name"] == '"DNS"'

    def test_boolean_python_style(self) -> None:
        result = build_filters(active=True)
        assert result["_filter_active"] == "True"

    def test_boolean_false(self) -> None:
        result = build_filters(active=False)
        assert result["_filter_active"] == "False"

    def test_integer_unquoted(self) -> None:
        result = build_filters(container_id=5)
        assert result["_filter_container_id"] == "5"

    def test_operator_suffix(self) -> None:
        result = build_filters(name__icontains="test")
        assert result["_filter_name__icontains"] == '"test"'

    def test_in_list(self) -> None:
        result = build_filters(id__in=[1, 2, 3])
        assert result["_filter_id__in"] == "[1, 2, 3]"

    def test_exclude(self) -> None:
        result = build_filters(_exclude_status="closed")
        assert result["_exclude_status"] == '"closed"'

    def test_multiple_filters(self) -> None:
        result = build_filters(name="test", severity="high")
        assert "_filter_name" in result
        assert "_filter_severity" in result

    def test_none_value_skipped(self) -> None:
        result = build_filters(name="test", severity=None)
        assert "_filter_name" in result
        assert "_filter_severity" not in result
        assert "_exclude_severity" not in result


# -------------------------------------------------------------------
# Bulk update (array POST)
# -------------------------------------------------------------------


class TestBulkUpdate:
    def test_bulk_post_sends_array(self) -> None:
        c = _client()
        items = [
            {"id": 1, "status": "closed"},
            {"id": 2, "status": "closed"},
        ]
        resp = _mock_response(json_data={"success": True})
        with patch.object(c, "_session") as sess:
            sess.request.return_value = resp
            c.post("container", body=items)
        call_args = sess.request.call_args
        sent_body = json.loads(call_args[1]["data"])
        assert isinstance(sent_body, list)
        assert len(sent_body) == 2


# -------------------------------------------------------------------
# Pagination iterator
# -------------------------------------------------------------------


class TestPagination:
    def test_iterates_all_pages(self) -> None:
        c = _client()
        page0 = {
            "count": 3,
            "num_pages": 2,
            "data": [{"id": 1}, {"id": 2}],
        }
        page1 = {
            "count": 3,
            "num_pages": 2,
            "data": [{"id": 3}],
        }
        responses = [
            _mock_response(json_data=page0),
            _mock_response(json_data=page1),
        ]
        with patch.object(c, "_session") as sess:
            sess.request.side_effect = responses
            items = list(c.iter_pages("container", page_size=2))
        assert len(items) == 3
        assert [i["id"] for i in items] == [1, 2, 3]

    def test_single_page_no_extra_request(self) -> None:
        c = _client()
        page0 = {"count": 1, "num_pages": 1, "data": [{"id": 1}]}
        with patch.object(c, "_session") as sess:
            sess.request.return_value = _mock_response(
                json_data=page0,
            )
            items = list(c.iter_pages("container"))
        assert len(items) == 1
        assert sess.request.call_count == 1

    def test_empty_result(self) -> None:
        c = _client()
        page0 = {"count": 0, "num_pages": 0, "data": []}
        with patch.object(c, "_session") as sess:
            sess.request.return_value = _mock_response(
                json_data=page0,
            )
            items = list(c.iter_pages("container"))
        assert items == []


# -------------------------------------------------------------------
# URL construction
# -------------------------------------------------------------------


class TestURLConstruction:
    def test_base_url(self) -> None:
        c = _client(host="myhost", port=9443)
        assert c._base_url == "https://myhost:9443/rest"

    def test_path_normalization(self) -> None:
        c = _client()
        assert c._url("container") == "https://soar.test:8443/rest/container"
        assert c._url("/container") == "https://soar.test:8443/rest/container"
