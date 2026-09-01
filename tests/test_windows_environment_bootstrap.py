from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[1] / "tools" / "bootstrap_windows_environment.ps1"
ENVIRONMENT_WORKFLOW = Path(__file__).parents[1] / ".github" / "workflows" / "environment-smoke.yml"


def test_windows_bootstrap_declares_only_core_system_packages() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert "-Mode Check" in source or 'ValidateSet("Check", "InstallCore")' in source
    assert "Git.Git" in source
    assert "MiKTeX.MiKTeX" in source
    assert "Microsoft.VCRedist.2015+.x64" in source
    assert "python install 3.11" in source
    assert "InstallerOverride" in source
    assert "MinerU" not in source
    assert "Node.js" not in source
    assert "CUDA" not in source


def test_windows_environment_smoke_prewarms_publication_probe_packages() -> None:
    source = ENVIRONMENT_WORKFLOW.read_text(encoding="utf-8")

    assert "miktex packages update-package-database" in source
    assert "miktex packages require $package" in source
    for package in ("natbib", "hyperref", "xurl", "booktabs", "amsmath", "fontspec", "graphics"):
        assert f'"{package}"' in source
    assert "kpsewhich plainnat.bst" in source
    assert "MiKTeX could not resolve plainnat.bst" in source


@pytest.mark.skipif(sys.platform != "win32", reason="The bootstrap executable contract is Windows-only.")
def test_windows_bootstrap_check_mode_is_read_only() -> None:
    completed = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SCRIPT),
            "-Mode",
            "Check",
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    payload = json.loads(completed.stdout)
    assert payload["schema_version"] == "dpl.windows_environment_bootstrap.v1"
    assert payload["mode"] == "Check"
    assert payload["mutated"] is False
