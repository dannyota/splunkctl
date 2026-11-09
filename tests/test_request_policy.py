import pytest

from splunkctl.request_context import invocation
from splunkctl.request_policy import ReadOnlyError, check_request


@pytest.mark.parametrize(
    "method,path,kind",
    [
        ("POST", "/services/data/indexes", "siem"),
        ("GET", "/en-US/account/logout", "web"),
        ("HEAD", "/logout", "web"),
        ("GET", "/%6cogout", "web"),
        ("POST", "/rest/container", "soar"),
        ("HEAD", "/rest/container", "soar"),
        ("POST", "/services/search/jobs/foreign/control", "siem"),
        ("DELETE", "/services/search/jobs/foreign", "siem"),
    ],
)
def test_refused(method, path, kind):
    with invocation("test", True), pytest.raises(ReadOnlyError, match="read-only:"):
        check_request(
            method, "https://example.test" + path, "https://example.test", kind=kind
        )


def test_owned_job_control():
    with invocation("search run", True) as ctx:
        ctx.owned_sids.add("owned")
        check_request(
            "POST",
            "https://example.test/services/search/jobs/owned/control",
            "https://example.test",
            body="action=cancel",
        )
        with pytest.raises(ReadOnlyError):
            check_request(
                "POST",
                "https://example.test/services/search/jobs/owned/control",
                "https://example.test",
                body="action=enablepreview",
            )


def test_get_policy_and_origin():
    with invocation("test", True):
        check_request(
            "GET", "https://example.test/services/unknown", "https://example.test"
        )
        check_request(
            "POST", "https://example.test/services/auth/login", "https://example.test"
        )
        with pytest.raises(ReadOnlyError):
            check_request(
                "GET", "https://other.test/services/server/info", "https://example.test"
            )


@pytest.mark.parametrize(
    "query",
    [
        "",
        "?parse_only=false&reload_macros=false",
        "?parse_only=true&reload_macros=true",
        "?parse_only=true&parse_only=false&reload_macros=false",
    ],
)
def test_parser_cannot_execute_or_reload(query):
    with invocation("api get", True), pytest.raises(ReadOnlyError, match="parser"):
        check_request(
            "GET",
            "https://example.test/services/search/parser" + query,
            "https://example.test",
        )


def test_safe_parser_get():
    with invocation("api get", True):
        check_request(
            "GET",
            "https://example.test/services/search/parser?parse_only=true&reload_macros=false",
            "https://example.test",
        )


@pytest.mark.parametrize(
    "path",
    [
        "/services/apps/local/_reload",
        "/servicesNS/nobody/search/apps/local/_reload",
        "/services/apps/local/%5freload",
        "/debug/refresh",
    ],
)
def test_mutating_get_reload(path):
    with invocation("api get", True), pytest.raises(ReadOnlyError):
        check_request("GET", "https://example.test" + path, "https://example.test")


def test_owned_job_missing_action_fails_closed():
    with invocation("search run", True) as ctx:
        ctx.owned_sids.add("mine")
        with pytest.raises(ReadOnlyError):
            check_request(
                "POST",
                "https://example.test/services/search/jobs/mine/control",
                "https://example.test",
            )
