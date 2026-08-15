"""Tests for the SIEM and SOAR session adapters."""

from unittest.mock import MagicMock, patch

import pytest

from splunkctl.auth import adapters


def test_siem_extract_reads_splunkd_cookie() -> None:
    vals = adapters.SIEMAdapter().extract(
        {"splunkweb_csrf_token": "x", "splunkd_8000": "SESSIONKEY"}
    )
    assert vals == {"session_key": "SESSIONKEY", "cookie": "splunkd_8000"}


def test_siem_extract_missing_cookie_raises() -> None:
    with pytest.raises(adapters.ExtractError):
        adapters.SIEMAdapter().extract({"other": "x"})


@patch("splunkctl.auth.adapters.requests.get")
def test_siem_validate_uses_management_api(mock_get: MagicMock) -> None:
    mock_get.return_value.status_code = 200
    status = adapters.SIEMAdapter().validate(
        {"session_key": "k", "cookie": "splunkd_8000"},
        api_base="https://siem:8089",
        verify=True,
        timeout=30,
    )
    assert status == "valid"
    args, kwargs = mock_get.call_args
    assert args[0] == "https://siem:8089/services/server/info"
    assert kwargs["headers"] == {"Authorization": "Splunk k"}


@patch("splunkctl.auth.adapters.requests.get")
def test_siem_validate_returns_expired_on_401(mock_get: MagicMock) -> None:
    mock_get.return_value.status_code = 401
    status = adapters.SIEMAdapter().validate(
        {"session_key": "k", "cookie": "splunkd_8000"},
        api_base="https://siem:8089",
        verify=True,
        timeout=30,
    )
    assert status == "expired"


@patch("splunkctl.auth.adapters.requests.get")
def test_siem_validate_returns_unreachable_on_connection_error(
    mock_get: MagicMock,
) -> None:
    mock_get.side_effect = ConnectionError("refused")
    status = adapters.SIEMAdapter().validate(
        {"session_key": "k", "cookie": "splunkd_8000"},
        api_base="https://siem:8089",
        verify=True,
        timeout=30,
    )
    assert status == "unreachable"


def test_soar_extract_reads_sessionid_and_csrf() -> None:
    vals = adapters.SOARAdapter().extract(
        {"sessionid": "sid", "csrftoken": "csrf", "other": "x"}
    )
    assert vals == {"sessionid": "sid", "csrftoken": "csrf"}


def test_soar_extract_missing_cookies_raises() -> None:
    with pytest.raises(adapters.ExtractError):
        adapters.SOARAdapter().extract({"sessionid": "sid"})


@patch("splunkctl.auth.adapters.requests.get")
def test_soar_validate_hits_rest_version(mock_get: MagicMock) -> None:
    mock_get.return_value.status_code = 200
    vals = {"sessionid": "sid", "csrftoken": "csrf"}
    status = adapters.SOARAdapter().validate(
        vals, api_base="https://soar:8443", verify=True, timeout=30
    )
    assert status == "valid"
    args, kwargs = mock_get.call_args
    assert args[0] == "https://soar:8443/rest/version"
    assert kwargs["cookies"] == vals


def test_get_adapter_dispatch() -> None:
    assert isinstance(adapters.get_adapter("siem"), adapters.SIEMAdapter)
    assert isinstance(adapters.get_adapter("soar"), adapters.SOARAdapter)
