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
