"""Tests for MCP output size cap, spill-to-file, and timeout handling."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from unittest.mock import patch

from splunkctl.mcp.output_cap import (
    MAX_OUTPUT_BYTES,
    SPILL_MAX_AGE_HOURS,
    SUBPROCESS_TIMEOUT,
    spill_output,
    sweep_spill_dir,
    timeout_message,
    truncate_utf8,
)

# --- truncate_utf8 ---


def test_truncate_utf8_under_limit() -> None:
    text = "hello world"
    assert truncate_utf8(text, 100) == text


def test_truncate_utf8_over_limit() -> None:
    text = "a" * 1000
    result = truncate_utf8(text, 100)
    assert "[output truncated:" in result
    assert "of 1000 bytes shown]" in result
    # The non-trailer portion should be <= 100 bytes
    body = result.split("\n[output truncated:")[0]
    assert len(body.encode()) <= 100


def test_truncate_utf8_multibyte_safe() -> None:
    """Truncation must not split a multi-byte UTF-8 character."""
    # Each char is 3 bytes in UTF-8
    text = "é" * 200  # 400 bytes (2 bytes each for e-acute)
    result = truncate_utf8(text, 101)
    body = result.split("\n[output truncated:")[0]
    # Must decode cleanly (no partial chars)
    body.encode()


# --- spill_output ---


def test_spill_output_creates_file(tmp_path: Path) -> None:
    big_text = "x" * 100
    with patch("splunkctl.mcp.output_cap._spill_dir", return_value=tmp_path):
        result = spill_output(big_text)
    payload = json.loads(result)
    assert "file" in payload
    assert payload["bytes"] == 100
    assert "exceeded 4 MiB" in payload["message"]
    assert Path(payload["file"]).read_text() == big_text


# --- sweep_spill_dir ---


def test_sweep_removes_old_files(tmp_path: Path) -> None:
    old_file = tmp_path / "splunkctl-mcp-old.json"
    new_file = tmp_path / "splunkctl-mcp-new.json"
    old_file.write_text("old")
    new_file.write_text("new")
    # Make old_file appear stale
    old_time = time.time() - (SPILL_MAX_AGE_HOURS + 1) * 3600
    os.utime(old_file, (old_time, old_time))

    with patch("splunkctl.mcp.output_cap._spill_dir", return_value=tmp_path):
        sweep_spill_dir()

    assert not old_file.exists()
    assert new_file.exists()


def test_sweep_handles_missing_dir() -> None:
    """sweep_spill_dir must not raise when the dir doesn't exist."""
    with patch("splunkctl.mcp.output_cap._spill_dir", side_effect=OSError("no dir")):
        sweep_spill_dir()  # no exception


# --- timeout_message ---


def test_timeout_message_content() -> None:
    msg = timeout_message()
    assert "5m0s" in msg
    assert "--limit" in msg


# --- Integration via _exec_cli ---


def test_exec_cli_spills_large_success_output(tmp_path: Path) -> None:
    """Success output > MAX_OUTPUT_BYTES is spilled to a temp file."""
    import subprocess as sp

    big = "R" * (MAX_OUTPUT_BYTES + 1024)
    fake_result = sp.CompletedProcess(
        args=[], returncode=0, stdout=big.encode(), stderr=b""
    )

    with (
        patch("splunkctl.mcp.server.subprocess.run", return_value=fake_result),
        patch("splunkctl.mcp.output_cap._spill_dir", return_value=tmp_path),
    ):
        from splunkctl.mcp.server import _exec_cli

        result = _exec_cli(["search", "run", "index=main"])

    payload = json.loads(result)
    assert "file" in payload
    assert payload["bytes"] > MAX_OUTPUT_BYTES
    spill_path = Path(payload["file"])
    assert spill_path.exists()
    assert len(spill_path.read_bytes()) > MAX_OUTPUT_BYTES


def test_exec_cli_truncates_large_error_output() -> None:
    """Error output > MAX_OUTPUT_BYTES is truncated with a notice."""
    import subprocess as sp

    big_err = "E" * (MAX_OUTPUT_BYTES + 2048)
    fake_result = sp.CompletedProcess(
        args=[], returncode=1, stdout=b"", stderr=big_err.encode()
    )

    with patch("splunkctl.mcp.server.subprocess.run", return_value=fake_result):
        from splunkctl.mcp.server import _exec_cli

        result = _exec_cli(["search", "run", "bad query"])

    assert "[output truncated:" in result
    assert len(result.encode()) <= MAX_OUTPUT_BYTES + 200  # trailer overhead


def test_exec_cli_timeout_returns_clean_message() -> None:
    """TimeoutExpired yields a user-friendly message, not a traceback."""
    import subprocess as sp

    with patch(
        "splunkctl.mcp.server.subprocess.run",
        side_effect=sp.TimeoutExpired(cmd=["splunkctl"], timeout=SUBPROCESS_TIMEOUT),
    ):
        from splunkctl.mcp.server import _exec_cli

        result = _exec_cli(["search", "run", "index=main | head 99999"])

    assert "timed out" in result
    assert "5m0s" in result
    assert "--limit" in result
    assert "Traceback" not in result


def test_exec_cli_normal_output_unchanged() -> None:
    """Output under the cap is returned as-is."""
    import subprocess as sp

    small = '{"results": []}'
    fake_result = sp.CompletedProcess(
        args=[], returncode=0, stdout=small.encode(), stderr=b""
    )

    with patch("splunkctl.mcp.server.subprocess.run", return_value=fake_result):
        from splunkctl.mcp.server import _exec_cli

        result = _exec_cli(["indexes", "list"])

    assert result == small


# --- Constants ---


def test_constants() -> None:
    assert MAX_OUTPUT_BYTES == 4 * 1024 * 1024
    assert SPILL_MAX_AGE_HOURS == 24
    assert SUBPROCESS_TIMEOUT == 300
