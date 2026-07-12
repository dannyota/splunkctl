"""Unit tests for SOARClient web-session auth and playbook deletion.

Playbook deletion has no REST route — the client logs into the Django
Web UI (CSRF cookie + AJAX login) and POSTs the same request the
browser does. These tests pin the handshake and the response-envelope
validation.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import requests

from splunkctl.soar.client import SOARClient, SOARError

_SESSION_PATCH = "splunkctl.soar.web.requests.Session"


def _resp(status: int = 200, json_data: Any = None) -> MagicMock:
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status
    if isinstance(json_data, Exception):
        resp.json.side_effect = json_data
    else:
        resp.json.return_value = json_data if json_data is not None else {}
    return resp


def _web_client(
    *,
    username: str | None = "admin",
    password: str | None = "pw",  # noqa: S107
    token: str | None = None,
) -> SOARClient:
    return SOARClient(
        host="soar.test",
        username=username,
        password=password,
        token=token,
        verify=False,
    )


def _session(csrf: str | None = "csrftok") -> MagicMock:
    # No spec: Session.cookies is an instance attribute, invisible to spec.
    sess = MagicMock()
    sess.cookies.get.return_value = csrf
    return sess


class TestWebLogin:
    def test_token_only_raises_auth(self) -> None:
        c = _web_client(username=None, password=None, token="tok")  # noqa: S106
        with pytest.raises(SOARError) as exc:
            c.web_delete_playbooks([1])
        assert exc.value.kind == "auth"
        assert "username/password" in exc.value.message

    def test_missing_csrf_cookie_raises(self) -> None:
        sess = _session(csrf=None)
        with patch(_SESSION_PATCH, return_value=sess), pytest.raises(SOARError) as exc:
            _web_client().web_delete_playbooks([1])
        assert "CSRF" in exc.value.message

    def test_invalid_credentials_raise_auth(self) -> None:
        sess = _session()
        sess.post.return_value = _resp(200, {"authenticated": False})
        with patch(_SESSION_PATCH, return_value=sess), pytest.raises(SOARError) as exc:
            _web_client().web_delete_playbooks([1])
        assert exc.value.kind == "auth"

    def test_non_json_login_response_raises(self) -> None:
        sess = _session()
        sess.post.return_value = _resp(302, ValueError("no json"))
        with patch(_SESSION_PATCH, return_value=sess), pytest.raises(SOARError) as exc:
            _web_client().web_delete_playbooks([1])
        assert exc.value.kind == "auth"
        assert exc.value.http_status == 302

    def test_session_reused_across_calls(self) -> None:
        sess = _session()
        sess.post.side_effect = [
            _resp(200, {"authenticated": True}),  # login
            _resp(200, {"done_count": 1, "fail_count": 0}),  # delete 1
            _resp(200, {"done_count": 1, "fail_count": 0}),  # delete 2
        ]
        with patch(_SESSION_PATCH, return_value=sess) as mock_session:
            c = _web_client()
            c.web_delete_playbooks([1])
            c.web_delete_playbooks([2])
        # Patching requests.Session catches the REST session (init) too:
        # exactly one MORE Session means one web login, reused after.
        assert mock_session.call_count == 2
        assert sess.post.call_count == 3  # login + two deletes


class TestWebDeletePlaybooks:
    def _delete(self, delete_resp: MagicMock, ids: list[int]) -> Any:
        sess = _session()
        sess.post.side_effect = [
            _resp(200, {"authenticated": True}),
            delete_resp,
        ]
        with patch(_SESSION_PATCH, return_value=sess):
            result = _web_client().web_delete_playbooks(ids)
        self.last_session = sess
        return result

    def test_posts_ids_with_csrf_header(self) -> None:
        self._delete(_resp(200, {"done_count": 2, "fail_count": 0}), [1, 2])
        call = self.last_session.post.call_args
        assert call[0][0].endswith("/playbooks")
        assert call[1]["json"] == {"ids": [1, 2], "delete": True}
        assert call[1]["headers"]["X-CSRFToken"] == "csrftok"

    def test_envelope_passthrough(self) -> None:
        body = {
            "done_count": 1,
            "fail_count": 0,
            "changes": ["Deleted playbook 'local/x' (id 1)"],
            "errors": [],
        }
        assert self._delete(_resp(200, body), [1]) == body

    def test_unexpected_envelope_raises(self) -> None:
        # A shape change must raise, not be misread as "nothing deleted".
        with pytest.raises(SOARError) as exc:
            self._delete(_resp(200, {"message": "ok"}), [1])
        assert "Unexpected response" in exc.value.message

    def test_failed_true_raises(self) -> None:
        with pytest.raises(SOARError) as exc:
            self._delete(_resp(200, {"failed": True, "message": "nope"}), [1])
        assert exc.value.message == "nope"

    def test_http_error_maps_kind(self) -> None:
        with pytest.raises(SOARError) as exc:
            self._delete(_resp(403, {"message": "forbidden"}), [1])
        assert exc.value.kind == "permission"
        assert exc.value.http_status == 403

    def test_non_json_delete_response_raises(self) -> None:
        with pytest.raises(SOARError) as exc:
            self._delete(_resp(500, ValueError("html error page")), [1])
        assert exc.value.http_status == 500
