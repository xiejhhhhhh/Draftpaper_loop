# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json
import hashlib

from draftpaper_cli.orchestrator import run_pipeline
from draftpaper_cli.project_scaffold import create_project


def test_pipeline_stops_for_plugin_rescue_when_core_figure_is_insufficient(tmp_path) -> None:
    project = create_project(root=tmp_path, idea="Capability test", field="machine learning", target_journal="Test").path
    (project / "research_plan" / "research_plan.md").write_text("# Research plan\n", encoding="utf-8")
    (project / "research_plan" / "claim_contract.json").write_text("{}", encoding="utf-8")
    (project / "research_plan" / "discipline_contract.json").write_text(json.dumps({"primary_discipline": "machine_learning"}), encoding="utf-8")
    (project / "research_plan" / "plugin_sufficiency_report.json").write_text(json.dumps({"decision": "rescue_required"}), encoding="utf-8")

    result = run_pipeline(project)

    assert result["pipeline_state"] == "capability_audit_required"
    assert result["next_action"]["command"] == "audit-project-capabilities"


def test_legacy_blocked_sufficiency_is_not_treated_as_exhausted_search(tmp_path) -> None:
    project = create_project(root=tmp_path, idea="Capability test", field="machine learning", target_journal="Test").path
    (project / "research_plan" / "research_plan.md").write_text("# Research plan\n", encoding="utf-8")
    (project / "research_plan" / "claim_contract.json").write_text("{}", encoding="utf-8")
    (project / "research_plan" / "discipline_contract.json").write_text(json.dumps({"primary_discipline": "machine_learning"}), encoding="utf-8")
    (project / "research_plan" / "plugin_sufficiency_report.json").write_text(json.dumps({"decision": "blocked"}), encoding="utf-8")
    (project / "research_plan" / "project_capability_audit.json").write_text(json.dumps({"decision": "blocked"}), encoding="utf-8")

    result = run_pipeline(project)

    assert result["pipeline_state"] == "plugin_gap_detected"
    assert result["next_action"]["command"] == "prepare-plugin-rescue"


def test_changed_results_invalidates_old_discipline_review_report(tmp_path) -> None:
    project = create_project(root=tmp_path, idea="Result review", field="machine learning", target_journal="Test").path
    (project / "research_plan" / "research_capability_contract.json").write_text(json.dumps({"requirements": []}), encoding="utf-8")
    results = project / "results" / "results.tex"
    results.write_text("New repaired Results.\n", encoding="utf-8")
    review_dir = project / "review"
    review_dir.mkdir(exist_ok=True)
    review_dir.joinpath("result_discipline_review_report.json").write_text(json.dumps({
        "decision": "repair_required",
        "results_sha256": hashlib.sha256(b"Old Results.\n").hexdigest(),
        "recommended_next_action": {"command": "write-results", "reason": "Old issue"},
    }), encoding="utf-8")

    result = run_pipeline(project)

    assert result["next_action"]["command"] == "review-results-with-discipline-rules"
