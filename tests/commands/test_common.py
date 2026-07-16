"""Tests for shared command helpers."""

from typing import Any
from unittest.mock import MagicMock, patch

import click
import pytest
from click.testing import CliRunner

from splunkctl.commands.common import (
    fetch_page,
    filter_by_name,
    page_slice,
    parse_set,
    resolve_leaf_command,
    warn_missing_action_fields,
    watch_loop,
)
from splunkctl.main import cli


def test_parse_set_happy_path() -> None:
    assert parse_set(("a=1", "b=two")) == {"a": "1", "b": "two"}


def test_parse_set_value_containing_equals() -> None:
    assert parse_set(("regex=user=(?<user>\\w+)",)) == {"regex": "user=(?<user>\\w+)"}


def test_parse_set_empty_value_allowed() -> None:
    assert parse_set(("cleared=",)) == {"cleared": ""}


def test_parse_set_missing_equals_rejected() -> None:
    with pytest.raises(click.BadParameter, match="KEY=VALUE"):
        parse_set(("nonsense",))


def test_parse_set_readonly_key_rejected() -> None:
    with pytest.raises(click.BadParameter, match="read-only"):
        parse_set(("eai:data=x",))


def test_warn_missing_action_fields_email_missing(
    capsys: pytest.CaptureFixture[str],
) -> None:
    warn_missing_action_fields("email", {})
    err = capsys.readouterr().err
    assert "action.email.to" in err
    assert "email" in err


def test_warn_missing_action_fields_satisfied_via_set(
    capsys: pytest.CaptureFixture[str],
) -> None:
    warn_missing_action_fields("email", {"action.email.to": "a@b"})
    assert capsys.readouterr().err == ""


def test_warn_missing_action_fields_webhook_missing(
    capsys: pytest.CaptureFixture[str],
) -> None:
    warn_missing_action_fields("webhook", {})
    err = capsys.readouterr().err
    assert "action.webhook.param.url" in err


def test_warn_missing_action_fields_unmapped_action_silent(
    capsys: pytest.CaptureFixture[str],
) -> None:
    warn_missing_action_fields("lookup", {})
    assert capsys.readouterr().err == ""


def test_warn_missing_action_fields_satisfied_by_existing(
    capsys: pytest.CaptureFixture[str],
) -> None:
    warn_missing_action_fields("email", {}, existing={"action.email.to": "a@b"})
    assert capsys.readouterr().err == ""


# --- list paging helpers ---


class _Named:
    def __init__(self, name: str) -> None:
        self.name = name


def test_filter_by_name_case_insensitive_substring() -> None:
    items = [_Named("Alpha"), _Named("beta"), _Named("ALPHABET")]
    out = filter_by_name(items, "alpha")
    assert [i.name for i in out] == ["Alpha", "ALPHABET"]


def test_filter_by_name_none_is_noop() -> None:
    items = [_Named("a"), _Named("b")]
    assert filter_by_name(items, None) == items


def test_filter_by_name_custom_key() -> None:
    rows = [{"rule": "Brute Force"}, {"rule": "Beaconing"}]
    out = filter_by_name(rows, "brute", name_of=lambda r: str(r["rule"]))
    assert out == [{"rule": "Brute Force"}]


def test_page_slice_offset_then_limit() -> None:
    items = list(range(10))
    assert page_slice(items, limit=3, offset=2) == [2, 3, 4]
    assert page_slice(items, limit=None, offset=8) == [8, 9]
    assert page_slice(items, limit=2, offset=0) == [0, 1]
    assert page_slice(items, limit=None, offset=0) == items


def test_fetch_page_no_flags_calls_bare() -> None:
    """No flags: the SDK fetch is called with no kwargs at all —

    the fetch-everything default must stay untouched.
    """
    calls: list[dict[str, Any]] = []

    def fetch(**kwargs: Any) -> list[_Named]:
        calls.append(kwargs)
        return [_Named("a"), _Named("b")]

    out = fetch_page(fetch, limit=None, offset=0, name_filter=None)
    assert calls == [{}]
    assert [i.name for i in out] == ["a", "b"]


def test_fetch_page_passes_count_and_offset_server_side() -> None:
    calls: list[dict[str, Any]] = []

    def fetch(**kwargs: Any) -> list[_Named]:
        calls.append(kwargs)
        return [_Named("b")]

    out = fetch_page(fetch, limit=1, offset=1, name_filter=None)
    assert calls == [{"count": 1, "offset": 1}]
    assert [i.name for i in out] == ["b"]


def test_fetch_page_filter_fetches_all_then_pages_client_side() -> None:
    """--filter: fetch everything (no kwargs), filter, then offset/limit

    apply to the filtered set.
    """
    calls: list[dict[str, Any]] = []
    names = ["alert-a", "rule-1", "alert-b", "alert-c"]

    def fetch(**kwargs: Any) -> list[_Named]:
        calls.append(kwargs)
        return [_Named(n) for n in names]

    out = fetch_page(fetch, limit=2, offset=1, name_filter="ALERT")
    assert calls == [{}]
    assert [i.name for i in out] == ["alert-b", "alert-c"]


# --- SPL quoting for injection prevention ---


def test_spl_quote_plain() -> None:
    """Plain string with no special characters."""
    from splunkctl.commands.common import spl_quote

    assert spl_quote("plain") == '"plain"'


def test_spl_quote_embedded_quote() -> None:
    """Double quote in the middle must be escaped."""
    from splunkctl.commands.common import spl_quote

    assert spl_quote('bob"smith') == '"bob\\"smith"'


def test_spl_quote_trailing_backslash() -> None:
    """Trailing backslash must be escaped to prevent SPL injection."""
    from splunkctl.commands.common import spl_quote

    assert spl_quote("x\\") == '"x\\\\"'


def test_spl_quote_backslash_then_quote() -> None:
    """Backslash before quote; backslash must be escaped first."""
    from splunkctl.commands.common import spl_quote

    assert spl_quote('x\\"') == '"x\\\\\\""'


# --- resolve_leaf_command ---


def test_resolve_leaf_command_finds_subcommand() -> None:
    leaf = resolve_leaf_command(cli, ["indexes", "list"])
    assert leaf is not None
    assert leaf.name == "list"


def test_resolve_leaf_command_returns_none_for_no_args() -> None:
    assert resolve_leaf_command(cli, []) is None


# --- watch_loop ---


def test_watch_loop_runs_twice_then_exits() -> None:
    """watch_loop re-invokes the command until KeyboardInterrupt."""
    calls: list[int] = []

    def fake_invoke(ctx: click.Context) -> None:
        calls.append(1)
        if len(calls) >= 2:
            raise KeyboardInterrupt

    ctx = click.Context(cli, obj={"watch": 2})
    with pytest.raises(KeyboardInterrupt):
        with patch("splunkctl.commands.common.time.sleep"):
            with patch("splunkctl.commands.common.subprocess.run"):
                # stdout is not a tty in tests, so clear is skipped
                watch_loop(ctx, 2, fake_invoke)
    assert len(calls) == 2


@patch("splunkctl.commands.common.time.sleep")
def test_watch_loop_survives_errors(mock_sleep: MagicMock) -> None:
    """Errors inside the loop are printed but don't stop the loop."""
    calls: list[int] = []

    def failing_invoke(ctx: click.Context) -> None:
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("transient failure")
        raise KeyboardInterrupt

    ctx = click.Context(cli, obj={"watch": 1})
    with pytest.raises(KeyboardInterrupt):
        watch_loop(ctx, 1, failing_invoke)
    assert len(calls) == 2


# --- --watch integration via CLI ---


def test_watch_rejected_for_mutation_command() -> None:
    """--watch must be rejected when used with a guarded mutation command."""
    runner = CliRunner()
    result = runner.invoke(cli, ["--watch", "5", "indexes", "create"])
    assert result.exit_code != 0
    assert "mutation" in result.output.lower()


def test_watch_rejected_without_tty() -> None:
    """--watch requires an interactive terminal."""
    runner = CliRunner()
    # CliRunner does not emulate a TTY, so this should be rejected.
    result = runner.invoke(cli, ["--watch", "5", "info"])
    assert result.exit_code != 0
    assert "tty" in result.output.lower()
