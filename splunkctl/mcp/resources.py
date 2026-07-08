"""MCP resources from docs/guides/ markdown files."""

from pathlib import Path
from typing import Any

_GUIDES_DIR = Path(__file__).resolve().parent.parent.parent / "docs" / "guides"


def _title_from_md(text: str) -> str:
    """Extract the first ``# Heading`` as the resource title."""
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
        if line.strip():
            break
    return ""


def load_guides() -> list[dict[str, Any]]:
    """Load all guide markdown files and return resource metadata."""
    guides: list[dict[str, Any]] = []
    if not _GUIDES_DIR.is_dir():
        return guides
    for path in sorted(_GUIDES_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        slug = path.stem
        title = _title_from_md(text)
        guides.append(
            {
                "slug": slug,
                "title": title or slug,
                "text": text,
            }
        )
    return guides
