from __future__ import annotations

import json
from pathlib import Path

from draftpaper_cli.evidence_resolver import (
    SECTION_TOKEN_BUDGETS,
    resolve_figure_evidence,
    resolve_paragraph_evidence,
)
from draftpaper_cli.project_scaffold import create_project
from draftpaper_cli.result_evidence import resolve_result_evidence


def _json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _run_project(tmp_path: Path) -> Path:
    project = create_project(root=tmp_path, idea="Run-aware evidence", field="astronomy machine learning").path
    table = project / "results" / "tables" / "verified_model_metrics.csv"
    table.write_text(
        "run_id,cohort_id,sample_unit,split,model_id,metric,metric_dimension,value\n"
        "run-1,baseline,event,source_held_out,logistic_event_static,f1_macro,dimensionless_score,0.8667\n"
        "run-1,baseline,event,source_held_out,random_forest_event_static,f1_macro,dimensionless_score,0.8486\n"
        "run-1,token,event,source_held_out,token_transformer_time2vec_full,f1_macro,dimensionless_score,0.8053\n"
        "run-1,token,event,source_held_out,token_transformer_no_history,f1_macro,dimensionless_score,0.8205\n",
        encoding="utf-8",
    )
    (project / "methods" / "run_manifest.yaml").write_text(
        json.dumps({"status": "success", "run_id": "run-1", "output_files": ["results/tables/verified_model_metrics.csv"]}),
        encoding="utf-8",
    )
    resolve_result_evidence(project)
    return project


def test_figure_resolver_preserves_model_qualified_metrics_and_story_roles(tmp_path: Path) -> None:
    project = _run_project(tmp_path)
    _json(project / "results" / "figure_contracts.json", {"contracts": [
        {
            "figure_id": "fig_signal",
            "scientific_question": "What direct scientific signal distinguishes the classes?",
            "manuscript_role": "main",
        },
        {
            "figure_id": "fig_diagnostic",
            "scientific_question": "Is the result stable under a sensitivity diagnostic?",
            "manuscript_role": "appendix",
        },
    ]})
    _json(project / "results" / "figure_metadata.json", {"figures": [
        {"figure_id": "fig_signal", "x_role": "features", "y_role": "label_or_response", "variable_roles": ["features", "label_or_response"]},
        {"figure_id": "fig_diagnostic", "x_role": "model_variant", "y_role": "performance_metric", "variable_roles": ["model_variant", "performance_metric"]},
    ]})

    report = resolve_figure_evidence(project)

    assert report["status"] == "resolved"
    direct = next(item for item in report["panels"] if item["figure_id"] == "fig_signal")
    supporting = next(item for item in report["panels"] if item["figure_id"] == "fig_diagnostic")
    assert direct["story_role"] == "direct_scientific_signal"
    assert supporting["story_role"] == "supporting_diagnostic"
    assert direct["run_id"] == "run-1"
    assert set(direct["model_ids"]) == {
        "logistic_event_static",
        "random_forest_event_static",
        "token_transformer_time2vec_full",
        "token_transformer_no_history",
    }


def test_figure_resolver_rejects_identifier_only_scientific_panel(tmp_path: Path) -> None:
    project = _run_project(tmp_path)
    _json(project / "results" / "figure_contracts.json", {"contracts": [{"figure_id": "fig_bad", "manuscript_role": "main"}]})
    _json(project / "results" / "figure_metadata.json", {"figures": [{"figure_id": "fig_bad", "x_role": "source_id", "y_role": "obs_id"}]})

    report = resolve_figure_evidence(project)

    assert report["status"] == "blocked"
    issues = report["blocking"][0]["issues"]
    assert any(item["kind"] == "identifier_only_scientific_plot" for item in issues)


def test_paragraph_slices_preserve_bound_numbers_under_hard_budget(tmp_path: Path) -> None:
    project = _run_project(tmp_path)
    resolved = json.loads((project / "results" / "resolved_result_evidence.json").read_text(encoding="utf-8"))
    records = resolved["evidence_records"]
    _json(project / "writing" / "scientific_evidence_registry.json", {"records": records})
    evidence_ids = [item["evidence_id"] for item in records]
    outline = {
        "paragraphs": [
            {
                "paragraph_id": "results_comparison",
                "objective": "Compare all verified model variants without averaging model identities.",
                "required_evidence_ids": evidence_ids,
                "figure_or_table_links": ["fig_model_comparison"],
                "forbidden_content": ["generic unqualified metric"],
            }
        ]
    }

    report = resolve_paragraph_evidence(project, "results", outline=outline)
    slice_path = project / report["slices"][0]["path"]
    payload = json.loads(slice_path.read_text(encoding="utf-8"))

    assert report["within_budget"] is True
    assert report["estimated_tokens"] <= SECTION_TOKEN_BUDGETS["results"]
    assert {item["value"] for item in payload["bound_numbers"]} == {0.8667, 0.8486, 0.8053, 0.8205}
    assert set(report["slices"][0]["evidence_ids"]) == set(evidence_ids)


def test_paragraph_budget_rebalances_for_uneven_scientific_jobs(tmp_path: Path) -> None:
    project = _run_project(tmp_path)
    resolved = json.loads((project / "results" / "resolved_result_evidence.json").read_text(encoding="utf-8"))
    records = resolved["evidence_records"]
    _json(project / "writing" / "scientific_evidence_registry.json", {"records": records})
    evidence_ids = [item["evidence_id"] for item in records]
    outline = {"paragraphs": [
        {
            "paragraph_id": "results_rich_comparison",
            "objective": "Compare all model-qualified values.",
            "required_evidence_ids": evidence_ids,
        },
        {
            "paragraph_id": "results_boundary",
            "objective": "State the bounded interpretation.",
            "required_evidence_ids": [evidence_ids[0]],
        },
    ]}

    report = resolve_paragraph_evidence(project, "results", outline=outline)

    assert report["within_budget"] is True
    assert len(report["slices"]) == 2
    assert report["estimated_tokens"] <= SECTION_TOKEN_BUDGETS["results"]


def test_discussion_slices_keep_all_scoped_evidence_without_duplicate_binding_payloads(tmp_path: Path) -> None:
    project = _run_project(tmp_path)
    records = []
    for index in range(90):
        records.append({
            "evidence_id": f"evidence-{index:03d}",
            "entity_role": "result_metric_macro_f1",
            "value": 0.4 + index / 1000,
            "unit": "score",
            "metric_dimension": "dimensionless_score",
            "run_id": "run-1",
            "cohort_id": "main",
            "sample_unit": "source",
            "split": "group_held_out",
            "model_id": f"model-{index % 3}",
            "aggregation": ["mean_across_primary_folds", "pooled_out_of_fold", "mean_across_repeated_group_partitions"][index % 3],
            "analysis_variant": ["primary_fixed_partition", "primary_fixed_partition", "repeated_partition_sensitivity"][index % 3],
            "source_artifact": f"results/tables/metric_family_{index % 3}.csv",
            "source_hash": f"hash-{index % 3}",
            "target_sections": ["discussion"],
        })
    _json(project / "writing" / "scientific_evidence_registry.json", {"records": records})
    outline = {"paragraphs": [
        {
            "paragraph_id": f"discussion_{paragraph + 1}",
            "objective": "Interpret a distinct scientific claim.",
            "required_evidence_ids": [item["evidence_id"] for item in records[paragraph * 30:(paragraph + 1) * 30]],
        }
        for paragraph in range(3)
    ]}

    report = resolve_paragraph_evidence(project, "discussion", outline=outline)

    assert report["estimated_tokens"] <= SECTION_TOKEN_BUDGETS["discussion"]
    assert sum(len(item["evidence_ids"]) for item in report["slices"]) == 90
    first = json.loads((project / report["slices"][0]["path"]).read_text(encoding="utf-8"))
    assert set(first["bound_numbers"][0]) == {"evidence_id", "value", "unit"}
    assert {"aggregation", "analysis_variant"} <= set(first["selected_evidence"][0])
