"""Verify package version is importable."""

from splunkctl import __version__


def test_version() -> None:
    assert __version__ == "0.10.1"
