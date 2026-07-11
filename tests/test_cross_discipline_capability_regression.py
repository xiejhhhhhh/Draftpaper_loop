# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json

import pytest

from draftpaper_cli.project_scaffold import create_project


def _write(path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


@pytest.mark.parametrize(
    ("idea", "field", "data_plugin", "method_plugin", "review_plugin"),
    [
        ("Wheat NDVI spatial prediction using random forest.", "geography machine learning", "tabular_environment_dataset", "baseline_model", "model_statistical_validity_gate"),
        ("X-ray transient light curve classification with transformer baselines.", "astronomy machine learning", "remote_fits_zip_stream", "baseline_model", "model_statistical_validity_gate"),
        ("RNA-seq biomarkers for clinical survival prediction.", "bioinformatics medicine", "anndata_matrix_io", "baseline_model", "clinical_cohort_validity_gate"),
    ],
)
def test_cross_discipline_main_figure_has_complete_plugin_trace(tmp_path, idea, field, data_plugin, method_plugin, review_plugin) -> None:
    from draftpaper_cli.figure_plugin_trace import validate_figure_plugin_trace

    project = create_project(root=tmp_path, idea=idea, field=field, target_journal="Regression").path
    _write(project / "research_plan" / "research_capability_contract.json", {"requirements": [{
        "requirement_id": "figure:fig_main", "kind": "figure", "figure_id": "fig_main", "claim_ids": ["claim_main"], "core": True,
    }]})
    _write(project / "research_plan" / "plugin_binding_plan.json", {"bindings": [
        {"requirement_id": "data:fig_main", "figure_id": "fig_main", "kind": "data", "plugin_id": data_plugin, "state": "covered"},
        {"requirement_id": "method:fig_main", "figure_id": "fig_main", "kind": "method", "plugin_id": method_plugin, "state": "covered"},
        {"requirement_id": "review:fig_main", "figure_id": "fig_main", "kind": "review", "plugin_id": review_plugin, "state": "covered"},
    ]})
    _write(project / "results" / "figure_contracts.json", {"main_contracts": [{"figure_id": "fig_main", "research_question": "Primary scientific question"}]})
    (project / "results" / "tables" / "metrics.csv").write_text("metric,value\nf1,0.8\n", encoding="utf-8")
    _write(project / "methods" / "run_manifest.yaml", {"status": "success", "output_files": ["results/tables/metrics.csv"]})
    (project / "methods" / "plugin_execution_ledger.jsonl").write_text(json.dumps({
        "event_id": "project_run", "figure_id": "fig_main", "plugin_id": method_plugin,
        "status": "project_executed", "scientific_evidence_status": "project_result",
        "output_hashes": {"results/tables/metrics.csv": "hash"},
    }) + "\n", encoding="utf-8")

    report = validate_figure_plugin_trace(project)

    assert report["decision"] == "pass"
    assert report["figure_checks"][0]["data_plugin_ids"] == [data_plugin]
    assert report["figure_checks"][0]["method_plugin_ids"] == [method_plugin]
    assert report["figure_checks"][0]["review_rule_ids"] == [review_plugin]
