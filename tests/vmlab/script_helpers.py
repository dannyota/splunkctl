import os
import shutil
import subprocess
from pathlib import Path

import pytest

BASH = shutil.which("bash")
if BASH is None:
    pytest.skip("vmlab script tests require bash on PATH", allow_module_level=True)
_BASH_MAJOR = int(
    subprocess.run(  # noqa: S603
        [BASH, "-c", 'echo "${BASH_VERSINFO[0]}"'],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    or 0
)
if _BASH_MAJOR < 4:
    pytest.skip(
        "vmlab scripts target RHEL and need bash 4 or newer "
        f"(found major version {_BASH_MAJOR} at {BASH})",
        allow_module_level=True,
    )

ROOT = Path(__file__).parents[2]
VMLAB = ROOT / "installers" / "vmlab"


def run_bash(
    script: str, *, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    command_env = os.environ.copy()
    # Never load a developer's gitignored config.local.env during tests.
    command_env["VMLAB_LOCAL_ENV"] = "/dev/null"
    if env:
        command_env.update(env)
    return subprocess.run(  # noqa: S603
        [BASH, "-c", script],
        cwd=ROOT,
        env=command_env,
        check=False,
        capture_output=True,
        text=True,
    )


def write_executable(path: Path, content: str) -> None:
    path.write_text(content)
    path.chmod(0o755)
