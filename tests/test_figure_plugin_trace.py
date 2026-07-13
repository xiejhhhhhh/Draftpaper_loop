# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json

from draftpaper_cli.project_scaffold import create_project


def _json(path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_main_figure_trace_requires_data_and_method_plugins_before_codegen(tmp_path) -> None:
    from draftpaper_cli.figure_plugin_trace import validate_figure_plugin_trace

    project = create_project(root=tmp_path, idea="Test composite research.", field="geography machine learning", target_journal="Test").path
    _json(project / "research_plan" / "research_capability_contract.json", {"requirements": [{
        "requirement_id": "figure:fig_main", "kind": "figure", "figure_id": "fig_main", "claim_ids": ["claim_1"], "core": True,
    }]})
    _json(project / "research_plan" / "plugin_binding_plan.json", {"bindings": [
        {"requirement_id": "data:fig_main:table", "figure_id": "fig_main", "kind": "data", "plugin_id": "tabular_environment_dataset", "state": "covered"},
        {"requirement_id": "method:fig_main:baseline", "figure_id": "fig_main", "kind": "method", "plugin_id": "baseline_model", "state": "covered"},
        {"requirement_id": "review:fig_main", "figure_id": "fig_main", "kind": "review", "plugin_id": "model_statistical_validity_gate", "state": "covered"},
    ]})
    _json(project / "results" / "figure_contracts.json", {"main_contracts": [{"figure_id": "fig_main", "research_question": "Does the model improve prediction?"}]})

    prereq = validate_figure_plugin_trace(project)
    assert prereq["decision"] == "ready_for_codegen"

    (project / "results" / "tables" / "metrics.csv").write_text("metric,value\nf1,0.8\n", encoding="utf-8")
    _json(project / "methods" / "run_manifest.yaml", {"status": "success", "declared_outputs": ["results/tables/metrics.csv"]})
    (project / "methods" / "plugin_execution_ledger.jsonl").write_text(json.dumps({
        "figure_id": "fig_main", "plugin_id": "baseline_model", "stage": "methods", "status": "project_executed", "scientific_evidence_status": "project_result", "output_hashes": {"results/tables/metrics.csv": "hash"},
    }) + "\n", encoding="utf-8")

    completed = validate_figure_plugin_trace(project)
    assert completed["decision"] == "pass"
    check = completed["figure_checks"][0]
    assert check["claim_ids"] == ["claim_1"]
    assert check["method_plugin_ids"] == ["baseline_model"]


def test_main_figure_trace_does_not_require_review_rule_before_codegen(tmp_path) -> None:
    from draftpaper_cli.figure_plugin_trace import validate_figure_plugin_trace

    project = create_project(root=tmp_path, idea="Test research.", field="machine learning", target_journal="Test").path
    _json(project / "research_plan" / "research_capability_contract.json", {"requirements": [{
        "requirement_id": "figure:fig_main", "kind": "figure", "figure_id": "fig_main", "claim_ids": ["claim_1"], "core": True,
    }]})
    _json(project / "research_plan" / "plugin_binding_plan.json", {"bindings": [
        {"requirement_id": "data:fig_main:table", "figure_id": "fig_main", "kind": "data", "plugin_id": "table_loader", "state": "covered"},
        {"requirement_id": "method:fig_main:model", "figure_id": "fig_main", "kind": "method", "plugin_id": "baseline_model", "state": "covered"},
    ]})
    _json(project / "results" / "figure_contracts.json", {"main_contracts": [{"figure_id": "fig_main", "research_question": "Question"}]})

    report = validate_figure_plugin_trace(project)

    assert report["decision"] == "ready_for_codegen"
    assert "missing_review_rule_binding" not in {item["kind"] for item in report["figure_checks"][0]["issues"]}


def test_main_figure_trace_blocks_missing_method_binding(tmp_path) -> None:
    from draftpaper_cli.figure_plugin_trace import validate_figure_plugin_trace

    project = create_project(root=tmp_path, idea="Test research.", field="machine learning", target_journal="Test").path
    _json(project / "research_plan" / "research_capability_contract.json", {"requirements": [{
        "requirement_id": "figure:fig_main", "kind": "figure", "figure_id": "fig_main", "claim_ids": ["claim_1"], "core": True,
    }]})
    _json(project / "research_plan" / "plugin_binding_plan.json", {"bindings": []})
    _json(project / "results" / "figure_contracts.json", {"main_contracts": [{"figure_id": "fig_main", "research_question": "Question"}]})

    report = validate_figure_plugin_trace(project)
    assert report["decision"] == "capability_rescue_required"
    assert "missing_method_plugin_binding" in {item["kind"] for item in report["figure_checks"][0]["issues"]}


def test_main_figure_trace_requires_every_data_and_method_requirement(tmp_path) -> None:
    from draftpaper_cli.figure_plugin_trace import validate_figure_plugin_trace

    project = create_project(root=tmp_path, idea="Test research.", field="machine learning", target_journal="Test").path
    _json(project / "research_plan" / "research_capability_contract.json", {"requirements": [
        {"requirement_id": "figure:fig_main", "kind": "figure", "figure_id": "fig_main", "claim_ids": ["claim_1"], "core": True},
        {"requirement_id": "data:fig_main:features", "kind": "data", "figure_id": "fig_main", "core": True},
        {"requirement_id": "data:fig_main:hardness", "kind": "data", "figure_id": "fig_main", "core": True},
        {"requirement_id": "method:fig_main:model", "kind": "method", "figure_id": "fig_main", "core": True},
    ]})
    _json(project / "research_plan" / "plugin_binding_plan.json", {"bindings": [
        {"requirement_id": "data:fig_main:features", "figure_id": "fig_main", "kind": "data", "plugin_id": "feature_table", "state": "covered"},
        {"requirement_id": "method:fig_main:model", "figure_id": "fig_main", "kind": "method", "plugin_id": "baseline_model", "state": "covered"},
    ]})
    _json(project / "results" / "figure_contracts.json", {"main_contracts": [{"figure_id": "fig_main", "research_question": "Question"}]})

    report = validate_figure_plugin_trace(project)

    assert report["decision"] == "capability_rescue_required"
    issue = next(item for item in report["figure_checks"][0]["issues"] if item["kind"] == "missing_data_plugin_requirement")
    assert issue["requirement_id"] == "data:fig_main:hardness"


def test_main_figure_trace_does_not_require_pre_run_binding_for_derived_predictions(tmp_path) -> None:
    from draftpaper_cli.figure_plugin_trace import validate_figure_plugin_trace

    project = create_project(root=tmp_path, idea="Prediction uncertainty", field="machine learning", target_journal="Test").path
    _json(project / "research_plan" / "research_capability_contract.json", {"requirements": [
        {"requirement_id": "figure:fig_main", "kind": "figure", "figure_id": "fig_main", "claim_ids": ["claim_1"], "core": True},
        {"requirement_id": "data:fig_main:features", "kind": "data", "figure_id": "fig_main", "data_role_class": "input_data", "core": True},
        {"requirement_id": "data:fig_main:prediction_score", "kind": "data", "figure_id": "fig_main", "data_role_class": "derived_method_output", "core": True},
        {"requirement_id": "method:fig_main:model", "kind": "method", "figure_id": "fig_main", "core": True},
    ]})
    _json(project / "research_plan" / "plugin_binding_plan.json", {"bindings": [
        {"requirement_id": "data:fig_main:features", "figure_id": "fig_main", "kind": "data", "plugin_id": "feature_table", "state": "covered"},
        {"requirement_id": "method:fig_main:model", "figure_id": "fig_main", "kind": "method", "plugin_id": "baseline_model", "state": "covered"},
    ]})
    _json(project / "results" / "figure_contracts.json", {"main_contracts": [{"figure_id": "fig_main", "research_question": "Question"}]})

    report = validate_figure_plugin_trace(project)

    assert report["decision"] == "ready_for_codegen"
    assert "missing_data_plugin_requirement" not in {item["kind"] for item in report["figure_checks"][0]["issues"]}
