# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json
from pathlib import Path

from draftpaper_cli.project_state import update_stage_status


def write_core_evidence_pass(project_path: Path, *, figure_count: int) -> None:
    (project_path / "core_evidence").mkdir(parents=True, exist_ok=True)
    payload = {
        "decision": "pass",
        "requires_user_confirmation": True,
        "figure_count": figure_count,
        "workflow_coverage": {
            "data_supplementation": True,
            "data_integration": True,
            "method_analysis": True,
            "figure_production": True,
            "result_validity": True,
        },
    }
    (project_path / "core_evidence" / "core_evidence_report.json").write_text(json.dumps(payload), encoding="utf-8")
    (project_path / "core_evidence" / "core_evidence_report.html").write_text("<html><body>pass</body></html>", encoding="utf-8")
    update_stage_status(project_path, "core_evidence", "draft")
