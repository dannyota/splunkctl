"""Verify compatibility bounds for runtime dependencies."""

import tomllib
from pathlib import Path

from packaging.requirements import Requirement


def test_mcp_dependency_stays_on_supported_major() -> None:
    """Fresh installs must select MCP 2 without crossing into MCP 3."""
    pyproject = tomllib.loads(
        (Path(__file__).parent.parent / "pyproject.toml").read_text(encoding="utf-8")
    )
    dependencies = pyproject["project"]["dependencies"]
    mcp = Requirement(next(dep for dep in dependencies if dep.startswith("mcp")))

    assert not mcp.specifier.contains("1.29.0")
    assert mcp.specifier.contains("2.0.0")
    assert not mcp.specifier.contains("3.0.0")
