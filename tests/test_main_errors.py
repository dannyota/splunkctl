"""JSON error envelope — kind/http_status classification in _CLI.invoke()."""

import json

import click
from click.testing import CliRunner

from splunkctl.main import _CLI


def _cli_raising(exc: Exception) -> click.Group:
    """Minimal group (same _CLI class as the real CLI) whose one command raises exc."""

    @click.group(cls=_CLI)
    @click.option("--json", "use_json", is_flag=True)
    @click.option("--format", "fmt", default=None)
    @click.pass_context
    def grp(ctx: click.Context, use_json: bool, fmt: str | None) -> None:
        ctx.ensure_object(dict)
        ctx.obj["json"] = use_json
        ctx.obj["format"] = fmt

    @grp.command()
    def boom() -> None:
        raise exc

    return grp


class HTTPError(Exception):
    """Stands in for splunklib.binding.HTTPError — classified by class name."""

    def __init__(self, status: int) -> None:
        self.status = status
        super().__init__(f"HTTP {status} error")


class AuthenticationError(Exception):
    """Stands in for splunklib.binding.AuthenticationError."""

    def __init__(self, status: int = 401) -> None:
        self.status = status
        super().__init__("Login failed.")


_FakeHTTPError = HTTPError
_FakeAuthenticationError = AuthenticationError


def _invoke_and_get_envelope(exc: Exception) -> tuple[int, dict[str, object]]:
    result = CliRunner().invoke(_cli_raising(exc), ["--json", "boom"])
    return result.exit_code, json.loads(result.stderr)["error"]


def test_http_401_maps_to_auth() -> None:
    exit_code, err = _invoke_and_get_envelope(_FakeHTTPError(401))
    assert exit_code == 1
    assert err["kind"] == "auth"
    assert err["http_status"] == 401


def test_http_403_maps_to_permission() -> None:
    exit_code, err = _invoke_and_get_envelope(_FakeHTTPError(403))
    assert exit_code == 1
    assert err["kind"] == "permission"
    assert err["http_status"] == 403


def test_http_404_maps_to_not_found() -> None:
    exit_code, err = _invoke_and_get_envelope(_FakeHTTPError(404))
    assert exit_code == 1
    assert err["kind"] == "not_found"
    assert err["http_status"] == 404


def test_http_409_maps_to_conflict() -> None:
    exit_code, err = _invoke_and_get_envelope(_FakeHTTPError(409))
    assert exit_code == 1
    assert err["kind"] == "conflict"
    assert err["http_status"] == 409


def test_http_other_status_maps_to_http() -> None:
    exit_code, err = _invoke_and_get_envelope(_FakeHTTPError(500))
    assert exit_code == 1
    assert err["kind"] == "http"
    assert err["http_status"] == 500


def test_authentication_error_maps_to_auth() -> None:
    exit_code, err = _invoke_and_get_envelope(_FakeAuthenticationError(401))
    assert exit_code == 1
    assert err["kind"] == "auth"
    assert err["http_status"] == 401


def test_timeout_error_maps_to_timeout() -> None:
    exit_code, err = _invoke_and_get_envelope(TimeoutError("timed out"))
    assert exit_code == 1
    assert err["kind"] == "timeout"
    assert err["http_status"] is None


def test_connection_refused_maps_to_connection() -> None:
    exit_code, err = _invoke_and_get_envelope(ConnectionRefusedError("refused"))
    assert exit_code == 1
    assert err["kind"] == "connection"
    assert err["http_status"] is None


def test_ssl_error_maps_to_connection() -> None:
    import ssl

    exit_code, err = _invoke_and_get_envelope(ssl.SSLError("bad handshake"))
    assert exit_code == 1
    assert err["kind"] == "connection"
    assert err["http_status"] is None


def test_unclassified_exception_still_propagates() -> None:
    """Guard against scope creep: unknown exceptions are not swallowed/reclassified."""
    result = CliRunner().invoke(_cli_raising(ValueError("weird")), ["--json", "boom"])
    assert result.exit_code != 0
    assert result.exception is not None
    assert "error" not in (result.stderr or "")
