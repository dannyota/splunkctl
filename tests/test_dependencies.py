"""Verify compatibility bounds for runtime dependencies."""

import tomllib
from pathlib import Path

from packaging.requirements import Requirement


def test_mcp_dependency_stays_on_supported_major() -> None:
    """Fresh installs must not select the incompatible MCP 2 SDK."""
    pyproject = tomllib.loads(
        (Path(__file__).parent.parent / "pyproject.toml").read_text(encoding="utf-8")
    )
    dependencies = pyproject["project"]["dependencies"]
    mcp = Requirement(next(dep for dep in dependencies if dep.startswith("mcp")))

    assert mcp.specifier.contains("1.28.1")
    assert not mcp.specifier.contains("2.0.0")
