from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from draftpaper_cli.eval_runtime import baseline_eval, capture_eval, gate_eval, replay_eval
from draftpaper_cli.project_scaffold import create_project


def test_capture_baseline_replay_and_gate_are_content_free_and_deterministic(tmp_path: Path) -> None:
    project = create_project(root=tmp_path, idea="Private scientific idea", field="unseen_discipline").path
    secret = project / "data" / "raw" / "private.csv"
    secret.write_text("server,password,value\nprivate-host,secret,42\n", encoding="utf-8")

    captured = capture_eval(project, "unseen-case")
    capture_path = project / captured["capture"]
    capture_text = capture_path.read_text(encoding="utf-8")
    assert "private-host" not in capture_text
    assert "secret,42" not in capture_text
    assert captured["redaction_report"]["artifact_content_captured"] is False

    baseline_path = tmp_path / "public-baseline.json"
    baseline_eval(capture_path, baseline_path)
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    assert baseline["baseline_kind"] == "software_regression_invariants"
    assert baseline["manuscript_baseline_prohibited"] is True
    assert "local_project_locator" not in baseline

    replayed = replay_eval(project, baseline_path)
    assert replayed["status"] == "passed"
    gated = gate_eval(project / replayed["report"])
    assert gated["status"] == "passed"
    assert gated["manuscript_quality_comparison_performed"] is False

    secret.write_text("server,password,value\nprivate-host,changed,43\n", encoding="utf-8")
    changed = replay_eval(project, baseline_path)
    assert changed["status"] == "failed"
    assert "data/raw/private.csv" in changed["content_hash_changes"]


def test_nested_eval_cli_contract(tmp_path: Path) -> None:
    project = create_project(root=tmp_path, idea="CLI eval", field="engineering").path
    completed = subprocess.run(
        [sys.executable, "-m", "draftpaper_cli.cli", "eval", "capture", "--project", str(project), "--case", "cli-case"],
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["status"] == "captured"
