import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[1]
CHECK_LENGTHS = ROOT / "scripts" / "check-lengths.sh"


def test_length_check_ignores_internal_plans(tmp_path: Path) -> None:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    shutil.copy2(CHECK_LENGTHS, scripts / CHECK_LENGTHS.name)
    plans = tmp_path / "docs" / "plans"
    plans.mkdir(parents=True)
    (plans / "internal.md").write_text("plan\n" * 451)

    result = subprocess.run(  # noqa: S603
        ["/usr/bin/bash", str(scripts / CHECK_LENGTHS.name)],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "docs/plans/internal.md" not in result.stdout


def test_length_check_still_rejects_oversized_user_docs(tmp_path: Path) -> None:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    shutil.copy2(CHECK_LENGTHS, scripts / CHECK_LENGTHS.name)
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "user-guide.md").write_text("guide\n" * 451)

    result = subprocess.run(  # noqa: S603
        ["/usr/bin/bash", str(scripts / CHECK_LENGTHS.name)],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "DOC TOO LONG  docs/user-guide.md: 451 lines" in result.stdout
