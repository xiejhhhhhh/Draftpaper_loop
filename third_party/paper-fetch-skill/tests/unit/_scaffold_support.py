from __future__ import annotations

from pathlib import Path
import subprocess
import sys

from tests.paths import REPO_ROOT


SCAFFOLD_PROVIDER_SCRIPT = REPO_ROOT / "scripts" / "scaffold_provider.py"


def run_scaffold(tmp_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCAFFOLD_PROVIDER_SCRIPT),
            "--output-dir",
            str(tmp_path),
            *args,
        ],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
