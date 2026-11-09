from uuid import UUID

from splunkctl.request_context import current, invocation, readonly, user_agent


def test_invocation_isolation_and_nested_watch():
    assert current() is None
    with invocation("search run", True) as first:
        UUID(first.request_id, version=4)
        assert readonly()
        assert f"cmd=search run; requestID={first.request_id}" in user_agent()
        with invocation("search run", False) as nested:
            assert nested is first
    with invocation("info", False) as second:
        assert second.request_id != first.request_id
    assert current() is None
