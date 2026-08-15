import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[2]
VMLAB = ROOT / "installers" / "vmlab"


def run_bash(
    script: str, *, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    command_env = os.environ.copy()
    if env:
        command_env.update(env)
    return subprocess.run(  # noqa: S603
        ["/usr/bin/bash", "-c", script],
        cwd=ROOT,
        env=command_env,
        check=False,
        capture_output=True,
        text=True,
    )


def write_executable(path: Path, content: str) -> None:
    path.write_text(content)
    path.chmod(0o755)
