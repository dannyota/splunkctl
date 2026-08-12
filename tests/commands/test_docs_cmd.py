"""Tests for the docs generate maintainer command."""

import json
import re
from pathlib import Path

from click.testing import CliRunner, Result

from splunkctl.main import cli
from splunkctl.mcp.tools import build_tool_index

REPO = Path(__file__).resolve().parent.parent.parent

# Every hand-written MCP tool count in the docs, with the regex that captures
# it. The generated reference keeps the command pages honest; this keeps the
# prose honest — these counts had drifted to 237 and 238 while the real
# number was 229.
TOOL_COUNT_CLAIMS = [
    ("docs/README.md", r"(\d+) tools with dynamic loading"),
    ("docs/guides/mcp.md", r"exposing all (\d+) tools"),
    ("docs/design/catalog.md", r"(\d+) auto-generated typed tools"),
    ("docs/index.html", r"access to (\d+) Splunk commands"),
    ("scripts/gen-seo.sh", r"access to (\d+) Splunk commands"),
]

SIDEBAR_SEED = """- [Home](/)

- **Commands**
  - [Search](guides/search.md)

- **Design**
  - [Architecture](design/architecture.md)
"""


def _generate(tmp_path: Path, *extra: str) -> tuple[Result, Path, Path]:
    sidebar = tmp_path / "_sidebar.md"
    if not sidebar.exists():
        sidebar.write_text(SIDEBAR_SEED, encoding="utf-8")
    out = tmp_path / "commands"
    result = CliRunner().invoke(
        cli,
        ["docs", "generate", "--out", str(out), "--sidebar", str(sidebar), *extra],
    )
    return result, out, sidebar


def test_generate_writes_index_and_pages(tmp_path: Path) -> None:
    result, out, _ = _generate(tmp_path)
    assert result.exit_code == 0, result.output
    index = (out / "README.md").read_text()
    assert "# Command reference" in index
    assert "[search](search.md)" in index
    search = (out / "search.md").read_text()
    assert "# splunkctl search" in search
    assert "## search run" in search
    assert "```text" in search


def test_generate_soar_page_covers_nested_subgroups(tmp_path: Path) -> None:
    result, out, _ = _generate(tmp_path)
    assert result.exit_code == 0, result.output
    soar = (out / "soar.md").read_text()
    assert "## soar playbooks list" in soar
    assert "## soar containers list" in soar


def test_generate_marks_guarded_mutations(tmp_path: Path) -> None:
    _, out, _ = _generate(tmp_path)
    indexes = (out / "indexes.md").read_text()
    create = indexes.split("## indexes create")[1].split("## ")[0]
    assert "Guarded mutation — dry-run by default" in create


def test_generate_renders_flags_table(tmp_path: Path) -> None:
    _, out, _ = _generate(tmp_path)
    search = (out / "search.md").read_text()
    assert "| Flag | Type | Default | Description |" in search
    assert "`--earliest`" in search


def test_generate_global_page_folds_leaf_commands(tmp_path: Path) -> None:
    _, out, _ = _generate(tmp_path)
    global_page = (out / "global.md").read_text()
    assert "# Global commands" in global_page
    assert "## doctor" in global_page
    assert "## info" in global_page
    assert "## commands" in global_page


def test_generate_inserts_sidebar_block_before_design(tmp_path: Path) -> None:
    _, _, sidebar = _generate(tmp_path)
    content = sidebar.read_text()
    assert "<!-- commands:start -->" in content
    assert "- **Command reference**" in content
    assert "[soar](commands/soar.md)" in content
    assert content.index("<!-- commands:end -->") < content.index("- **Design**")


def test_generate_sidebar_idempotent(tmp_path: Path) -> None:
    _, _, sidebar = _generate(tmp_path)
    first = sidebar.read_text()
    result, _, _ = _generate(tmp_path)
    assert result.exit_code == 0
    assert sidebar.read_text() == first
    assert first.count("<!-- commands:start -->") == 1


def test_generate_removes_stale_pages(tmp_path: Path) -> None:
    out = tmp_path / "commands"
    out.mkdir()
    (out / "bogus.md").write_text("# gone\n")
    result, out, _ = _generate(tmp_path)
    assert result.exit_code == 0
    assert "removed 1 stale" in result.output
    assert not (out / "bogus.md").exists()


def test_check_passes_when_fresh(tmp_path: Path) -> None:
    _generate(tmp_path)
    result, _, _ = _generate(tmp_path, "--check")
    assert result.exit_code == 0, result.output
    assert "ok: command reference is current" in result.output


def test_check_detects_stale_page(tmp_path: Path) -> None:
    _, out, _ = _generate(tmp_path)
    (out / "search.md").write_text("# edited by hand\n")
    result, _, _ = _generate(tmp_path, "--check")
    assert result.exit_code == 1
    assert "stale: search.md" in result.output


def test_check_detects_missing_and_orphaned(tmp_path: Path) -> None:
    _, out, _ = _generate(tmp_path)
    (out / "search.md").unlink()
    (out / "bogus.md").write_text("# orphan\n")
    result, _, _ = _generate(tmp_path, "--check")
    assert result.exit_code == 1
    assert "missing: search.md" in result.output
    assert "orphaned: bogus.md" in result.output


def test_check_detects_sidebar_drift(tmp_path: Path) -> None:
    _, _, sidebar = _generate(tmp_path)
    sidebar.write_text(SIDEBAR_SEED, encoding="utf-8")
    result, _, _ = _generate(tmp_path, "--check")
    assert result.exit_code == 1
    assert "command-reference block" in result.output


def test_docs_group_hidden_from_discovery() -> None:
    runner = CliRunner()
    help_result = runner.invoke(cli, ["--help"])
    assert not [
        ln for ln in help_result.output.splitlines() if ln.strip().startswith("docs")
    ]
    meta = runner.invoke(cli, ["commands"])
    names = [c["name"] for c in json.loads(meta.output)["commands"]]
    assert "docs" not in names


def test_docs_group_excluded_from_mcp_tools() -> None:
    index = build_tool_index(cli)
    assert not [n for n in index if n.startswith("docs_")]


def test_documented_tool_counts_match_the_mcp_index() -> None:
    """Every prose tool count must equal the real MCP tool count."""
    actual = str(len(build_tool_index(cli)))
    stale: list[str] = []
    for rel, pattern in TOOL_COUNT_CLAIMS:
        text = (REPO / rel).read_text(encoding="utf-8")
        found = re.findall(pattern, text)
        assert found, f"{rel}: nothing matched /{pattern}/ — did the wording change?"
        stale += [f"{rel}: claims {n}, actual {actual}" for n in found if n != actual]
    assert not stale, "stale MCP tool counts: " + "; ".join(stale)
