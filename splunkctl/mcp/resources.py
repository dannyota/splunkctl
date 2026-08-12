"""MCP resources from docs/guides/ markdown files."""

from importlib.metadata import files
from pathlib import Path
from typing import Any

_SOURCE_GUIDES_DIR = Path(__file__).resolve().parent.parent.parent / "docs" / "guides"


def _installed_guides_dir() -> Path | None:
    """Locate guide data recorded by the installed distribution."""
    for item in files("splunkctl") or ():
        if item.parts[-4:-1] == ("share", "splunkctl", "guides"):
            return Path(item.locate()).parent
    return None


def _guides_dir() -> Path | None:
    """Locate guides in a source checkout or an installed distribution."""
    if _SOURCE_GUIDES_DIR.is_dir():
        return _SOURCE_GUIDES_DIR
    return _installed_guides_dir()


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
    guides_dir = _guides_dir()
    if guides_dir is None or not guides_dir.is_dir():
        return guides
    for path in sorted(guides_dir.glob("*.md")):
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
