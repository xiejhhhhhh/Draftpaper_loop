# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json

from draftpaper_cli.orchestrator import run_pipeline
from draftpaper_cli.project_scaffold import create_project


def test_pipeline_stops_for_plugin_rescue_when_core_figure_is_insufficient(tmp_path) -> None:
    project = create_project(root=tmp_path, idea="Capability test", field="machine learning", target_journal="Test").path
    (project / "research_plan" / "research_plan.md").write_text("# Research plan\n", encoding="utf-8")
    (project / "research_plan" / "claim_contract.json").write_text("{}", encoding="utf-8")
    (project / "research_plan" / "discipline_contract.json").write_text(json.dumps({"primary_discipline": "machine_learning"}), encoding="utf-8")
    (project / "research_plan" / "plugin_sufficiency_report.json").write_text(json.dumps({"decision": "blocked"}), encoding="utf-8")

    result = run_pipeline(project)

    assert result["pipeline_state"] == "capability_audit_required"
    assert result["next_action"]["command"] == "audit-project-capabilities"
