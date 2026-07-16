"""Output size cap with spill-to-file for MCP exec results."""

from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path

MAX_OUTPUT_BYTES: int = 4 << 20  # 4 MiB
SPILL_MAX_AGE_HOURS: int = 24
SUBPROCESS_TIMEOUT: int = 300

_SPILL_DIR_NAME = "splunkctl-mcp"


def _spill_dir() -> Path:
    """Return (and create) the spill directory for oversized MCP output."""
    base = Path(tempfile.gettempdir()) / _SPILL_DIR_NAME
    base.mkdir(parents=True, exist_ok=True)
    return base


def sweep_spill_dir() -> None:
    """Delete spill files older than SPILL_MAX_AGE_HOURS."""
    try:
        d = _spill_dir()
    except OSError:
        return
    cutoff = time.time() - SPILL_MAX_AGE_HOURS * 3600
    for f in d.iterdir():
        try:
            if f.stat().st_mtime < cutoff:
                f.unlink()
        except OSError:
            pass


def spill_output(text: str) -> str:
    """Write *text* to a temp file and return a JSON pointer message."""
    data = text.encode()
    fd = tempfile.NamedTemporaryFile(
        prefix="splunkctl-mcp-",
        suffix=".json",
        dir=str(_spill_dir()),
        delete=False,
        mode="wb",
    )
    try:
        fd.write(data)
    finally:
        fd.close()
    return json.dumps(
        {
            "file": fd.name,
            "bytes": len(data),
            "message": (
                "Output exceeded 4 MiB limit. Results saved to a temporary "
                "file (removed after 24h). Read the file to analyze, or use "
                "--limit or narrower filters to reduce output."
            ),
        }
    )


def truncate_utf8(text: str, limit: int) -> str:
    """Truncate *text* to at most *limit* bytes on a UTF-8 char boundary."""
    encoded = text.encode()
    total = len(encoded)
    if total <= limit:
        return text
    truncated = encoded[:limit].decode(errors="ignore")
    return (
        f"{truncated}\n[output truncated: {len(truncated.encode())} "
        f"of {total} bytes shown]"
    )


def timeout_message() -> str:
    """Return a clean timeout message for SUBPROCESS_TIMEOUT."""
    mins, secs = divmod(SUBPROCESS_TIMEOUT, 60)
    return (
        f"Command timed out after {mins}m{secs}s. Use --limit or narrower time range."
    )
