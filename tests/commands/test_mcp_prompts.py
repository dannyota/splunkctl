"""Tests for MCP prompt workflows."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from splunkctl.mcp.server import create_server


@pytest.fixture(scope="module")
def server() -> Any:
    return create_server()


def _run(coro: Any) -> Any:
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


def test_prompts_listed(server: Any) -> None:
    prompts = _run(server.list_prompts())
    names = {p.name for p in prompts}
    assert "investigate-ioc" in names
    assert "triage-notable" in names
    assert "audit-detection" in names
    assert "export-state" in names


def test_prompt_count_at_least_four(server: Any) -> None:
    prompts = _run(server.list_prompts())
    assert len(prompts) >= 4


def test_investigate_ioc_arguments(server: Any) -> None:
    prompts = _run(server.list_prompts())
    prompt = next(p for p in prompts if p.name == "investigate-ioc")
    arg_names = {a.name for a in (prompt.arguments or [])}
    assert "ioc_value" in arg_names
    assert "ioc_type" in arg_names
    required = {a.name for a in (prompt.arguments or []) if a.required}
    assert "ioc_value" in required


def test_investigate_ioc_returns_messages(server: Any) -> None:
    result = _run(server.get_prompt("investigate-ioc", {"ioc_value": "8.8.8.8"}))
    assert len(result.messages) == 2
    assert result.messages[0].role == "assistant"
    assert result.messages[1].role == "user"
    text = result.messages[1].content.text
    assert "8.8.8.8" in text


def test_investigate_ioc_respects_type(server: Any) -> None:
    result = _run(
        server.get_prompt(
            "investigate-ioc",
            {"ioc_value": "evil.com", "ioc_type": "domain"},
        )
    )
    text = result.messages[1].content.text
    assert "domain" in text.lower()
    assert "evil.com" in text


def test_triage_notable_with_id(server: Any) -> None:
    result = _run(server.get_prompt("triage-notable", {"notable_id": "ABC123"}))
    assert len(result.messages) == 2
    text = result.messages[1].content.text
    assert "ABC123" in text


def test_triage_notable_with_query(server: Any) -> None:
    result = _run(
        server.get_prompt(
            "triage-notable",
            {"search_query": "index=notable severity=critical"},
        )
    )
    text = result.messages[1].content.text
    assert "index=notable" in text


def test_triage_notable_no_params(server: Any) -> None:
    result = _run(server.get_prompt("triage-notable", {}))
    text = result.messages[1].content.text
    assert "recent notable" in text.lower()


def test_audit_detection_messages(server: Any) -> None:
    result = _run(
        server.get_prompt("audit-detection", {"rule_name": "My Detection Rule"})
    )
    assert len(result.messages) == 2
    assert result.messages[0].role == "assistant"
    text = result.messages[1].content.text
    assert "My Detection Rule" in text
    assert "rules get" in text


def test_export_state_default(server: Any) -> None:
    result = _run(server.get_prompt("export-state", {}))
    assert len(result.messages) == 2
    text = result.messages[1].content.text
    assert "savedsearches" in text
    assert "macros" in text
    assert "lookups" in text
    assert "state pull" in text


def test_export_state_custom_types(server: Any) -> None:
    result = _run(
        server.get_prompt(
            "export-state",
            {"types": "props,transforms", "app": "myapp"},
        )
    )
    text = result.messages[1].content.text
    assert "props" in text
    assert "transforms" in text
    assert "myapp" in text
    # Should not contain default types
    assert "savedsearches" not in text


def test_prompt_messages_have_text_content(server: Any) -> None:
    """All prompt messages use TextContent."""
    for name in ("investigate-ioc", "audit-detection", "export-state"):
        args: dict[str, str] = {}
        if name == "investigate-ioc":
            args = {"ioc_value": "test"}
        elif name == "audit-detection":
            args = {"rule_name": "test"}
        result = _run(server.get_prompt(name, args))
        for msg in result.messages:
            assert msg.content.type == "text"
            assert isinstance(msg.content.text, str)
            assert len(msg.content.text) > 0
