"""Tests for shared command helpers."""

import click
import pytest

from splunkctl.commands.common import parse_set


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
