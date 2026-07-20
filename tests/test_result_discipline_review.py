# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json

import pytest

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
    assert saved["recommended_next_action"]["command"] == "prepare-results-semantic-repair"
    assert not (project / "review" / "result_support_reopen_request.json").exists()


def test_result_review_reopens_result_support_for_evidence_failures(tmp_path, monkeypatch) -> None:
    import hashlib

    import draftpaper_cli.result_discipline_review as module

    project = create_project(root=tmp_path, idea="Evidence review", field="machine learning", target_journal="Test").path
    (project / "results" / "results.tex").write_text("Figure 1 summarizes the verified comparison.\n", encoding="utf-8")
    (project / "results" / "figure_plugin_trace_report.json").write_text(json.dumps({
        "decision": "pass",
        "figure_checks": [{
            "figure_id": "fig_1",
            "decision": "pass",
            "data_plugin_ids": ["table_loader"],
            "method_plugin_ids": ["baseline_model"],
            "run_output_event_id": "evt-current",
        }],
    }), encoding="utf-8")
    checkpoint = {
        "schema_version": "dpl.result_support_checkpoint.v3",
        "decision": "pass",
        "checkpoint_sha256": "a" * 64,
    }
    (project / "results" / "result_support_checkpoint.json").write_text(json.dumps(checkpoint), encoding="utf-8")
    monkeypatch.setattr(module, "assess_review_rules", lambda *args, **kwargs: {
        "decision": "revise_required",
        "selected_rule_count": 1,
        "rule_assessments": [],
        "rescue_tasks": [{"reason": "The selected evidence binding no longer satisfies the promoted rule."}],
        "recommended_next_commands": [],
    })

    result = module.review_results_with_discipline_rules(project)
    saved = json.loads((project / "review" / "result_discipline_review_report.json").read_text(encoding="utf-8"))
    reopen = json.loads((project / "review" / "result_support_reopen_request.json").read_text(encoding="utf-8"))

    assert result["decision"] == "repair_required"
    assert saved["recommended_next_action"]["command"] == "assess-result-support"
    assert reopen["status"] == "requested"
    assert reopen["result_support_checkpoint_sha256"] == "a" * 64
    assert reopen["result_discipline_review_sha256"] == hashlib.sha256(
        (project / "review" / "result_discipline_review_report.json").read_bytes()
    ).hexdigest()
    from draftpaper_cli.orchestrator import _gate_failure_action
    from draftpaper_cli.project_state import update_stage_status

    update_stage_status(project, "results", "draft")
    action = _gate_failure_action(project)
    assert action is not None
    assert action["command"] == "assess-result-support"


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


def test_result_review_reads_metrics_from_a_real_yaml_run_manifest(tmp_path) -> None:
    import draftpaper_cli.result_discipline_review as module

    project = create_project(root=tmp_path, idea="YAML review metrics", field="machine learning", target_journal="Test").path
    (project / "methods" / "run_manifest.yaml").write_text(
        "status: success\nrun_id: run-yaml\nmetrics:\n  f1_macro: 0.74\n",
        encoding="utf-8",
    )

    metrics = module._numeric_metrics(project)

    assert {item["metric_name"]: item["value"] for item in metrics}["f1"] == 0.74


@pytest.mark.parametrize(
    "manifest_payload",
    [
        {"status": "failed", "run_id": "run-current", "metrics": {"f1": 0.74}},
        {"status": "success", "metrics": {"f1": 0.74}},
    ],
)
def test_result_review_consumes_no_metrics_without_a_successful_selected_run(
    tmp_path, manifest_payload
) -> None:
    from draftpaper_cli import result_discipline_review as module

    project = create_project(root=tmp_path, idea="Selected review run", field="machine learning", target_journal="Test").path
    (project / "methods" / "run_manifest.yaml").write_text(
        json.dumps(manifest_payload), encoding="utf-8"
    )
    (project / "results" / "resolved_result_evidence.json").write_text(
        json.dumps({
            "status": "resolved",
            "run_id": "run-current",
            "metrics": [{"run_id": "run-current", "metric_name": "auc", "value": 0.91}],
        }),
        encoding="utf-8",
    )

    assert module._numeric_metrics(project) == []


def test_result_review_does_not_consume_resolved_metrics_outside_selected_run(tmp_path) -> None:
    from draftpaper_cli import result_discipline_review as module

    project = create_project(root=tmp_path, idea="Run-bound review metrics", field="machine learning", target_journal="Test").path
    (project / "methods" / "run_manifest.yaml").write_text(
        json.dumps({"status": "success", "run_id": "run-current", "metrics": {"f1": 0.55}}),
        encoding="utf-8",
    )
    (project / "results" / "resolved_result_evidence.json").write_text(
        json.dumps({
            "status": "resolved",
            "run_id": "run-old",
            "metrics": [
                {"run_id": "run-old", "metric_name": "f1", "value": 0.99},
                {"run_id": "run-current", "metric_name": "auc", "value": 0.98},
            ],
        }),
        encoding="utf-8",
    )

    metrics = module._numeric_metrics(project)

    assert metrics == [{"metric_name": "f1", "value": 0.55, "run_id": "run-current"}]


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


def test_result_review_preserves_balanced_accuracy_as_its_own_metric(tmp_path) -> None:
    from draftpaper_cli.result_discipline_review import review_results_with_discipline_rules

    project = create_project(root=tmp_path, idea="Model result", field="machine learning", target_journal="Test").path
    (project / "results" / "results.tex").write_text(
        "The model reached balanced accuracy of 0.6030 in Figure 1.\n", encoding="utf-8"
    )
    (project / "results" / "figure_plugin_trace_report.json").write_text(
        json.dumps({"decision": "pass", "figure_checks": []}), encoding="utf-8"
    )
    (project / "methods" / "run_manifest.yaml").write_text(
        json.dumps({
            "status": "success",
            "run_id": "run-current",
            "metrics": {"balanced_accuracy": 0.603034814226722},
        }),
        encoding="utf-8",
    )

    result = review_results_with_discipline_rules(project)
    saved = json.loads((project / "review" / "result_discipline_review_report.json").read_text(encoding="utf-8"))

    assert result["decision"] == "pass"
    assert saved["results_semantic_audit"]["issues"] == []


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
    snapshot_path = project / "results" / "promoted_evidence_snapshot.json"
    snapshot_path.write_text(json.dumps({"snapshot_id": "snapshot-current"}), encoding="utf-8")
    run_manifest_path = project / "methods" / "run_manifest.yaml"
    run_manifest_path.write_text(
        json.dumps({"status": "success", "run_id": "run-current"}), encoding="utf-8"
    )
    resolved_evidence_path = project / "results" / "resolved_result_evidence.json"
    resolved_evidence_path.write_text(
        json.dumps({"status": "resolved", "run_id": "run-current", "metrics": []}), encoding="utf-8"
    )

    review_results_with_discipline_rules(project)
    saved = json.loads((project / "review" / "result_discipline_review_report.json").read_text(encoding="utf-8"))

    assert saved["evidence_snapshot_id"] == "snapshot-current"
    assert saved["results_sha256"] == hashlib.sha256((project / "results" / "results.tex").read_bytes()).hexdigest()
    assert saved["promoted_evidence_snapshot_sha256"] == hashlib.sha256(snapshot_path.read_bytes()).hexdigest()
    assert saved["result_manifest_sha256"] == hashlib.sha256((project / "results" / "result_manifest.yaml").read_bytes()).hexdigest()
    assert saved["figure_plugin_trace_sha256"] == hashlib.sha256((project / "results" / "figure_plugin_trace_report.json").read_bytes()).hexdigest()
    assert saved["evidence_bindings"] == {
        "results/results.tex": saved["results_sha256"],
        "results/promoted_evidence_snapshot.json": saved["promoted_evidence_snapshot_sha256"],
        "results/result_manifest.yaml": saved["result_manifest_sha256"],
        "results/figure_plugin_trace_report.json": saved["figure_plugin_trace_sha256"],
        "methods/run_manifest.yaml": hashlib.sha256(run_manifest_path.read_bytes()).hexdigest(),
        "results/resolved_result_evidence.json": hashlib.sha256(resolved_evidence_path.read_bytes()).hexdigest(),
    }


def test_orchestrator_ignores_results_review_from_previous_snapshot(tmp_path) -> None:
    import hashlib

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
    (project / "results" / "promoted_evidence_snapshot.json").write_text(
        json.dumps({"snapshot_id": "snapshot-new"}), encoding="utf-8"
    )
    candidate = project / "writing" / "candidates" / "results.tex"
    candidate.parent.mkdir(parents=True, exist_ok=True)
    candidate.write_text("Old Results.\n", encoding="utf-8")
    candidate_hash = hashlib.sha256(candidate.read_text(encoding="utf-8").encode("utf-8")).hexdigest()
    writing_artifacts = {
        "writing/section_packets/results.json": {"promoted_evidence_snapshot": {"snapshot_id": "snapshot-new"}},
        "writing/section_validation/results.json": {
            "composition_mode": "codex_free_candidate", "decision": "pass",
            "quality_parity_eligible": True, "candidate_hash": candidate_hash,
            "evidence_snapshot_id": "snapshot-new",
        },
        "writing/claim_bindings/results.json": {
            "status": "passed", "candidate_hash": candidate_hash, "evidence_snapshot_id": "snapshot-new",
        },
        "writing/scientific_editor/results.json": {"source_hash": candidate_hash, "decision": "pass"},
        "writing/section_acceptance/results.json": {
            "status": "accepted", "formal_release_eligible": True,
            "candidate_hash": candidate_hash, "evidence_snapshot_id": "snapshot-new",
        },
    }
    for relative, payload in writing_artifacts.items():
        path = project / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")
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
