# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json
import hashlib

from draftpaper_cli.orchestrator import run_pipeline
from draftpaper_cli.project_scaffold import create_project


def test_plugin_sufficiency_waits_until_data_and_method_plan_are_available(tmp_path) -> None:
    from draftpaper_cli.passport import refresh_project_passport
    from draftpaper_cli.project_state import update_stage_status

    project = create_project(root=tmp_path, idea="New scientific image project", field="astronomy machine learning", target_journal="Test").path
    (project / "research_plan" / "research_plan.md").write_text("# Research plan\n", encoding="utf-8")
    (project / "research_plan" / "claim_contract.json").write_text("{}\n", encoding="utf-8")
    (project / "research_plan" / "discipline_contract.json").write_text(json.dumps({"primary_discipline": "astronomy"}), encoding="utf-8")
    update_stage_status(project, "references", "draft")
    update_stage_status(project, "journal_profile", "draft")
    update_stage_status(project, "research_feasibility", "draft")
    update_stage_status(project, "research_plan", "draft")
    update_stage_status(project, "research_plan_feasibility", "draft")
    refresh_project_passport(project, event="test_pre_sufficiency_data_route")

    result = run_pipeline(project)

    assert result["next_action"]["command"] == "assess-research-plan-feasibility"
    assert result["next_action"]["command"] != "assess-plugin-sufficiency"


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


def test_changed_results_without_current_lifecycle_rebuilds_before_discipline_review(tmp_path) -> None:
    from draftpaper_cli.passport import refresh_project_passport
    from draftpaper_cli.project_state import update_stage_status

    project = create_project(root=tmp_path, idea="Result review", field="machine learning", target_journal="Test").path
    capability_path = project / "research_plan" / "research_capability_contract.json"
    capability_path.write_text(json.dumps({"requirements": []}), encoding="utf-8")
    (project / "research_plan" / "plugin_sufficiency_report.json").write_text(json.dumps({
        "decision": "pass",
        "research_capability_contract_sha256": hashlib.sha256(capability_path.read_bytes()).hexdigest(),
    }), encoding="utf-8")
    results = project / "results" / "results.tex"
    results.write_text("New repaired Results.\n", encoding="utf-8")
    review_dir = project / "review"
    review_dir.mkdir(exist_ok=True)
    review_dir.joinpath("result_discipline_review_report.json").write_text(json.dumps({
        "decision": "repair_required",
        "results_sha256": hashlib.sha256(b"Old Results.\n").hexdigest(),
        "recommended_next_action": {"command": "write-results", "reason": "Old issue"},
    }), encoding="utf-8")
    update_stage_status(project, "results", "draft")
    refresh_project_passport(project, event="test_current_results")

    result = run_pipeline(project)

    assert result["next_action"]["command"] == "inventory-results"


def test_changed_capability_contract_invalidates_old_sufficiency_report(tmp_path) -> None:
    from draftpaper_cli.passport import refresh_project_passport
    from draftpaper_cli.project_state import update_stage_status

    project = create_project(root=tmp_path, idea="Capability version", field="machine learning", target_journal="Test").path
    (project / "research_plan" / "research_plan.md").write_text("# Research plan\n", encoding="utf-8")
    (project / "research_plan" / "claim_contract.json").write_text("{}\n", encoding="utf-8")
    (project / "research_plan" / "discipline_contract.json").write_text('{"primary_discipline":"machine_learning"}\n', encoding="utf-8")
    (project / "research_plan" / "research_capability_contract.json").write_text('{"requirements":[{"id":"new"}]}\n', encoding="utf-8")
    (project / "research_plan" / "plugin_sufficiency_report.json").write_text(
        json.dumps({"decision": "pass", "research_capability_contract_sha256": "old"}), encoding="utf-8"
    )
    update_stage_status(project, "data", "draft")
    update_stage_status(project, "method_plan", "draft")
    refresh_project_passport(project, event="test_changed_capability_contract")

    result = run_pipeline(project)

    assert result["next_action"]["command"] == "assess-plugin-sufficiency"


def test_new_sufficiency_report_invalidates_old_project_capability_audit(tmp_path) -> None:
    project = create_project(root=tmp_path, idea="Capability audit version", field="machine learning", target_journal="Test").path
    capability_path = project / "research_plan" / "research_capability_contract.json"
    capability_path.write_text('{"requirements":[{"id":"current"}]}\n', encoding="utf-8")
    capability_hash = hashlib.sha256(capability_path.read_bytes()).hexdigest()
    (project / "research_plan" / "plugin_sufficiency_report.json").write_text(json.dumps({
        "decision": "rescue_required",
        "generated_at": "current-sufficiency",
        "research_capability_contract_sha256": capability_hash,
    }), encoding="utf-8")
    (project / "research_plan" / "project_capability_audit.json").write_text(json.dumps({
        "decision": "rescue_required",
        "source_sufficiency_generated_at": "old-sufficiency",
        "research_capability_contract_sha256": capability_hash,
    }), encoding="utf-8")

    result = run_pipeline(project)

    assert result["next_action"]["command"] == "audit-project-capabilities"
