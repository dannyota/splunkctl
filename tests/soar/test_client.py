"""Unit tests for splunkctl.soar.client — auth, errors, lazy init, TLS."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import requests

from splunkctl.soar.client import (
    SOARClient,
    SOARError,
)

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
# TLS warning
# -------------------------------------------------------------------


class TestTLSWarning:
    def test_emitted_once_and_not_when_verify_on(self) -> None:
        import splunkctl.soar.client as mod

        mod._tls_warned = False
        try:
            with patch("sys.stderr") as m:
                SOARClient(host="s", token="t", verify=False)  # noqa: S106
                SOARClient(host="s", token="t", verify=False)  # noqa: S106
            assert m.write.call_count == 1
            assert "TLS certificate verification is disabled" in m.write.call_args[0][0]
            mod._tls_warned = False
            with patch("sys.stderr") as m2:
                SOARClient(host="s", token="t", verify=True)  # noqa: S106
            m2.write.assert_not_called()
        finally:
            mod._tls_warned = False
