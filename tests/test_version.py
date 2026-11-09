"""Verify package version is importable."""

from splunkctl import __version__


def test_version() -> None:
    assert __version__ == "0.17.2"


def test_alternate_script_declared() -> None:
    import tomllib
    from pathlib import Path

    project = tomllib.loads((Path(__file__).parents[1] / "pyproject.toml").read_text())
    assert project["project"]["scripts"]["splunkctl-py"] == "splunkctl.main:cli"
