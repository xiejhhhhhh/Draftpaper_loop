# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json

from draftpaper_cli.project_scaffold import create_project


def test_result_review_repairs_incomplete_trace_without_routing_to_plugin_rescue(tmp_path) -> None:
    from draftpaper_cli.result_discipline_review import review_results_with_discipline_rules

    project = create_project(root=tmp_path, idea="Remote sensing prediction with random forest.", field="geography machine learning", target_journal="Test").path
    (project / "results" / "results.tex").write_text("\\section{Results}\n", encoding="utf-8")
    (project / "results" / "figure_plugin_trace_report.json").write_text(json.dumps({"decision": "blocked", "figure_checks": []}), encoding="utf-8")

    result = review_results_with_discipline_rules(project)
    saved = json.loads((project / "review" / "result_discipline_review_report.json").read_text(encoding="utf-8"))

    assert result["decision"] == "pass"
    assert saved["trace_decision"] == "blocked"
    assert saved["recommended_next_action"]["command"] == "write-introduction"


def test_result_review_flags_untraceable_metric_and_internal_artifact_language(tmp_path) -> None:
    from draftpaper_cli.result_discipline_review import review_results_with_discipline_rules

    project = create_project(root=tmp_path, idea="Model result", field="machine learning", target_journal="Test").path
    (project / "results" / "results.tex").write_text(
        "The model reached F1=0.1234 from results/tables/metrics.csv.\\n", encoding="utf-8"
    )
    (project / "results" / "figure_plugin_trace_report.json").write_text(json.dumps({"decision": "pass", "figure_checks": []}), encoding="utf-8")
    (project / "methods" / "run_manifest.yaml").write_text(json.dumps({"status": "success", "metrics": {"f1": "0.8667"}}), encoding="utf-8")

    result = review_results_with_discipline_rules(project)
    saved = json.loads((project / "review" / "result_discipline_review_report.json").read_text(encoding="utf-8"))

    assert result["decision"] == "repair_required"
    kinds = {item["kind"] for item in saved["results_semantic_audit"]["issues"]}
    assert {"untraceable_metric_claim", "internal_artifact_language"} <= kinds
    assert all(item["severity"] == "repair_required" for item in saved["results_semantic_audit"]["issues"] if item["kind"] != "missing_figure_interpretation")


def test_result_review_selects_rules_only_for_plugin_generated_figures(tmp_path) -> None:
    from draftpaper_cli.result_discipline_review import review_results_with_discipline_rules

    project = create_project(root=tmp_path, idea="Model result", field="machine learning", target_journal="Test").path
    (project / "results" / "results.tex").write_text("Figure 1 shows the verified model comparison.\n", encoding="utf-8")
    (project / "results" / "figure_plugin_trace_report.json").write_text(json.dumps({
        "decision": "pass",
        "figure_checks": [
            {"figure_id": "fig_plugin", "decision": "pass", "data_plugin_ids": ["table_loader"], "method_plugin_ids": ["baseline_model"], "run_output_event_id": "evt_1"},
            {"figure_id": "fig_supplied", "decision": "pass", "data_plugin_ids": [], "method_plugin_ids": [], "run_output_event_id": None},
        ],
    }), encoding="utf-8")

    result = review_results_with_discipline_rules(project)
    saved = json.loads((project / "review" / "result_discipline_review_report.json").read_text(encoding="utf-8"))

    assert result["decision"] in {"pass", "repair_required"}
    assert saved["reviewed_figure_ids"] == ["fig_plugin"]
    assert saved["skipped_figure_ids"] == ["fig_supplied"]


def test_result_review_requires_complete_executed_plugin_trace_to_activate_rules(tmp_path) -> None:
    from draftpaper_cli.result_discipline_review import review_results_with_discipline_rules

    project = create_project(root=tmp_path, idea="Model result", field="machine learning", target_journal="Test").path
    (project / "results" / "results.tex").write_text("Figure 1 summarizes the result.\n", encoding="utf-8")
    (project / "results" / "figure_plugin_trace_report.json").write_text(json.dumps({
        "decision": "ready_for_codegen",
        "figure_checks": [
            {"figure_id": "data_only", "data_plugin_ids": ["table_loader"], "method_plugin_ids": [], "run_output_event_id": None},
            {"figure_id": "planned_only", "data_plugin_ids": ["table_loader"], "method_plugin_ids": ["baseline_model"], "run_output_event_id": None},
        ],
    }), encoding="utf-8")

    review_results_with_discipline_rules(project)
    saved = json.loads((project / "review" / "result_discipline_review_report.json").read_text(encoding="utf-8"))

    assert saved["reviewed_figure_ids"] == []
    assert saved["skipped_figure_ids"] == ["data_only", "planned_only"]
    assert saved["review_rule_gate"]["selected_rule_count"] == 0


def test_result_review_matches_metric_name_and_value_not_value_only(tmp_path) -> None:
    from draftpaper_cli.result_discipline_review import review_results_with_discipline_rules

    project = create_project(root=tmp_path, idea="Model result", field="machine learning", target_journal="Test").path
    (project / "results" / "results.tex").write_text("The model reached AUC=0.82 in Figure 1.\n", encoding="utf-8")
    (project / "results" / "figure_plugin_trace_report.json").write_text(json.dumps({"decision": "pass", "figure_checks": []}), encoding="utf-8")
    (project / "methods" / "run_manifest.yaml").write_text(json.dumps({"status": "success", "metrics": {"f1": 0.82}}), encoding="utf-8")

    result = review_results_with_discipline_rules(project)
    saved = json.loads((project / "review" / "result_discipline_review_report.json").read_text(encoding="utf-8"))

    assert result["decision"] == "repair_required"
    assert any(item["kind"] == "untraceable_metric_claim" for item in saved["results_semantic_audit"]["issues"])


def test_result_review_binds_current_evidence_snapshot_and_manifests(tmp_path) -> None:
    import hashlib

    from draftpaper_cli.result_discipline_review import review_results_with_discipline_rules

    project = create_project(root=tmp_path, idea="Model result", field="machine learning", target_journal="Test").path
    (project / "results" / "results.tex").write_text("Figure 1 summarizes the result.\n", encoding="utf-8")
    (project / "results" / "result_manifest.yaml").write_text('{"figures": []}\n', encoding="utf-8")
    (project / "results" / "figure_plugin_trace_report.json").write_text(
        json.dumps({"decision": "pass", "figure_checks": []}), encoding="utf-8"
    )
    (project / "core_evidence").mkdir(parents=True, exist_ok=True)
    (project / "core_evidence" / "core_evidence_report.json").write_text(
        json.dumps({"decision": "pass", "promoted_evidence_snapshot_id": "snapshot-current"}), encoding="utf-8"
    )

    review_results_with_discipline_rules(project)
    saved = json.loads((project / "review" / "result_discipline_review_report.json").read_text(encoding="utf-8"))

    assert saved["evidence_snapshot_id"] == "snapshot-current"
    assert saved["result_manifest_sha256"] == hashlib.sha256((project / "results" / "result_manifest.yaml").read_bytes()).hexdigest()
    assert saved["figure_plugin_trace_sha256"] == hashlib.sha256((project / "results" / "figure_plugin_trace_report.json").read_bytes()).hexdigest()


def test_orchestrator_ignores_results_review_from_previous_snapshot(tmp_path) -> None:
    from draftpaper_cli.orchestrator import _gate_failure_action
    from draftpaper_cli.project_state import update_stage_status

    project = create_project(root=tmp_path, idea="Model result", field="machine learning", target_journal="Test").path
    (project / "research_plan" / "research_capability_contract.json").write_text("{}\n", encoding="utf-8")
    (project / "results" / "results.tex").write_text("Old Results.\n", encoding="utf-8")
    (project / "results" / "result_manifest.yaml").write_text('{"figures": []}\n', encoding="utf-8")
    (project / "results" / "figure_plugin_trace_report.json").write_text('{"decision": "pass"}\n', encoding="utf-8")
    (project / "core_evidence").mkdir(parents=True, exist_ok=True)
    (project / "core_evidence" / "core_evidence_report.json").write_text(
        json.dumps({"decision": "pass", "promoted_evidence_snapshot_id": "snapshot-new"}), encoding="utf-8"
    )
    (project / "review").mkdir(parents=True, exist_ok=True)
    (project / "review" / "result_discipline_review_report.json").write_text(
        json.dumps({
            "decision": "repair_required",
            "results_sha256": __import__("hashlib").sha256((project / "results" / "results.tex").read_bytes()).hexdigest(),
            "evidence_snapshot_id": "snapshot-old",
            "recommended_next_action": {"command": "verify-methods"},
        }),
        encoding="utf-8",
    )
    update_stage_status(project, "results", "draft")

    action = _gate_failure_action(project)

    assert action is not None
    assert action["command"] == "review-results-with-discipline-rules"


def test_orchestrator_does_not_review_stale_results_file(tmp_path) -> None:
    from draftpaper_cli.orchestrator import _gate_failure_action

    project = create_project(root=tmp_path, idea="Model result", field="machine learning", target_journal="Test").path
    (project / "research_plan" / "research_capability_contract.json").write_text("{}\n", encoding="utf-8")
    (project / "results" / "results.tex").write_text("Historical Results.\n", encoding="utf-8")

    assert _gate_failure_action(project) is None


def test_orchestrator_ignores_historical_quality_failure_when_latex_is_stale(tmp_path) -> None:
    from draftpaper_cli.orchestrator import _gate_failure_action

    project = create_project(root=tmp_path, idea="Model result", field="machine learning", target_journal="Test").path
    (project / "quality_checks" / "quality_report.json").write_text(
        json.dumps({"status": "failed"}), encoding="utf-8"
    )

    assert _gate_failure_action(project) is None
