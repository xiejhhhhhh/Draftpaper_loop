from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from tools.audit_ruff_debt import build_report, write_baseline


def test_ruff_baseline_reports_no_new_debt(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    markdown = tmp_path / "baseline.md"
    finding = {"filename": "draftpaper_cli/example.py", "code": "F601", "message": "duplicate key", "location": {"row": 1, "column": 1}}
    with patch("tools.audit_ruff_debt.run_ruff", return_value={"status": "findings", "findings": [finding]}):
        created = write_baseline(tmp_path, baseline_path=baseline, markdown_path=markdown, historical_count=418, targets=("draftpaper_cli",))
    assert created["baseline_historical_count"] == 418
    with patch("tools.audit_ruff_debt.run_ruff", return_value={"status": "findings", "findings": [finding]}):
        report = build_report(tmp_path, baseline_path=baseline, targets=("draftpaper_cli",))
    assert report["status"] == "passed"
    assert report["no_new_debt"] is True


def test_ruff_baseline_detects_new_finding(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    markdown = tmp_path / "baseline.md"
    old = {"filename": "old.py", "code": "F401", "message": "unused", "location": {"row": 1, "column": 1}}
    new = {"filename": "new.py", "code": "F601", "message": "duplicate", "location": {"row": 2, "column": 1}}
    with patch("tools.audit_ruff_debt.run_ruff", return_value={"status": "findings", "findings": [old]}):
        write_baseline(tmp_path, baseline_path=baseline, markdown_path=markdown, targets=("draftpaper_cli",))
    with patch("tools.audit_ruff_debt.run_ruff", return_value={"status": "findings", "findings": [old, new]}):
        report = build_report(tmp_path, baseline_path=baseline, targets=("draftpaper_cli",))
    assert report["status"] == "failed"
    assert report["new_finding_keys"]
