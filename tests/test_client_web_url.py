"""The Web UI session must honor a configured web_url over the server's port."""

from typing import Any

from splunkctl.client import _WebSession


class _Settings:
    content = {"enableSplunkWebSSL": "0"}

    def __getitem__(self, key: str) -> str:
        assert key == "httpport"
        return "8000"


class _Service:
    host = "splunk.internal"
    username = "admin"
    password = "pw"  # noqa: S105
    confs: dict[str, Any] = {"web": {"settings": _Settings()}}


def test_base_url_prefers_configured_web_url() -> None:
    session = _WebSession(_Service(), web_url="http://127.0.0.1:18000/")
    assert session._base_url == "http://127.0.0.1:18000"


def test_base_url_falls_back_to_server_httpport() -> None:
    session = _WebSession(_Service())
    assert session._base_url == "http://splunk.internal:8000"
