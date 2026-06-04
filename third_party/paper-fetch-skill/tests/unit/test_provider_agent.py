from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from tests.paths import REPO_ROOT
from tests.script_modules import load_script_module


SCRIPT_PATH = REPO_ROOT / "scripts" / "provider_agent.py"


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        check=False,
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
    )


def test_help_includes_agent_actions() -> None:
    result = run_cli("--help")

    assert result.returncode == 0
    assert "add" in result.stdout
    assert "continue" in result.stdout
    assert "status" in result.stdout
    assert "doctor" in result.stdout


def test_add_without_domain_or_manifest_stops_at_intake(tmp_path: Path) -> None:
    result = run_cli(
        "add",
        "--provider",
        "newpub",
        "--format",
        "json",
        "--state",
        str(tmp_path / "state.json"),
    )
    payload = json.loads(result.stdout)

    assert result.returncode == 2
    assert payload["target"] == "local-ready"
    assert payload["target_step"] == "provider-local-acceptance"
    assert payload["phase"] == "intake"
    assert "domain" in payload["why_stopped"]


def test_add_defaults_to_local_ready_runner_target(
    tmp_path: Path,
    capsys,
) -> None:
    module = load_script_module("provider_agent")
    captured: dict[str, str] = {}

    def fake_run_until(**kwargs):
        captured["target"] = kwargs["target"]
        captured["output_dir"] = kwargs["output_dir"]
        return None

    module._ensure_access_review_draft = lambda **_kwargs: None
    module._access_review_summary = lambda _provider: {
        "status": "approved",
        "approved": True,
        "path": "onboarding/access-reviews/mdpi.yml",
    }
    module._run_until = fake_run_until

    code = module.main(
        [
            "add",
            "--provider",
            "mdpi",
            "--domain",
            "mdpi.com",
            "--format",
            "json",
            "--state",
            str(tmp_path / "state.json"),
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert captured["target"] == "local-ready"
    assert captured["output_dir"] == ".paper-fetch-runs/mdpi-onboarding"
    assert payload["target_step"] == "provider-local-acceptance"


def test_add_explicit_merge_ready_runner_target(
    tmp_path: Path,
    capsys,
) -> None:
    module = load_script_module("provider_agent")
    captured: dict[str, str] = {}

    def fake_run_until(**kwargs):
        captured["target"] = kwargs["target"]
        return None

    module._ensure_access_review_draft = lambda **_kwargs: None
    module._access_review_summary = lambda _provider: {
        "status": "approved",
        "approved": True,
        "path": "onboarding/access-reviews/mdpi.yml",
    }
    module._run_until = fake_run_until

    code = module.main(
        [
            "add",
            "--provider",
            "mdpi",
            "--domain",
            "mdpi.com",
            "--target",
            "merge-ready",
            "--format",
            "json",
            "--state",
            str(tmp_path / "state.json"),
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert captured["target"] == "merge-ready"
    assert payload["target_step"] == "merge-ready"
