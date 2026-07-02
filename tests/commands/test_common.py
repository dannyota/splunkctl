"""Tests for shared command helpers."""

import click
import pytest

from splunkctl.commands.common import parse_set, warn_missing_action_fields


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
