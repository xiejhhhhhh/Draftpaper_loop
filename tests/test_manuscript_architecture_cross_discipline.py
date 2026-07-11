# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json

import pytest

from draftpaper_cli.paper_narrative import build_paper_narrative
from draftpaper_cli.paper_quality_parity import assess_paper_quality_parity
from draftpaper_cli.project_scaffold import create_project
from draftpaper_cli.writing_architecture import (
    build_argument_matrices,
    build_panel_writing_contracts,
    build_section_lifecycles,
    resolve_venue_style_adapter,
)


def _json(path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


@pytest.mark.parametrize(
    ("idea", "field", "data_role", "method_output", "scientific_unit"),
    [
        ("Spatial vegetation response under held-out regional validation", "geography machine learning", "regional_measurements", "held_out_predictions", "region"),
        ("Transient classification from time-resolved observations", "astronomy machine learning", "time_resolved_observations", "validated_class_scores", "source"),
        ("Molecular signatures associated with clinical outcome", "bioinformatics medicine", "molecular_clinical_cohort", "survival_risk_estimates", "participant"),
    ],
)
def test_v022_manuscript_architecture_is_discipline_neutral(tmp_path, idea, field, data_role, method_output, scientific_unit) -> None:
    project = create_project(root=tmp_path, idea=idea, field=field, target_journal="Calibration").path
    (project / "results" / "result_manifest.yaml").parent.mkdir(parents=True, exist_ok=True)
    (project / "results" / "result_manifest.yaml").write_text(
        """main_figures:
  - id: main-comparison
    path: results/figures/main.png
    figure_group_id: main-story
    manuscript_role: main
    result_claim: The held-out comparison supports a bounded empirical difference.
    evidence_ids: [metric-main]
    run_id: run-main
appendix_figures:
  - id: robustness-check
    path: results/figures/robustness.png
    parent_figure_group: main-story
    manuscript_role: appendix
    result_claim: The diagnostic defines the stability boundary.
""",
        encoding="utf-8",
    )
    _json(project / "results" / "figure_plan.json", {"figure_groups": [{
        "id": "main-story", "scientific_question": "Does the validated analysis support the planned comparison?",
        "data_subset": "held_out", "scientific_unit": scientific_unit, "data_roles": [data_role],
        "method_outputs": [method_output], "comparison": "planned versus reference condition",
        "required_statistical_check": "uncertainty interval", "visual_grammar": "comparison plot",
        "expected_conclusion": "A bounded difference is supported.", "claim_boundary": "Interpret within the held-out cohort.",
    }]})
    _json(project / "results" / "figure_metadata.json", {"figures": [{"id": "main-story", "statistics": {"uncertainty": "reported"}}]})
    _json(project / "results" / "resolved_result_evidence.json", {"metrics": [{"evidence_id": "metric-main", "run_id": "run-main", "value": 0.8}]})
    _json(project / "writing" / "scientific_evidence_registry.json", {"records": [{
        "evidence_id": "metric-main", "entity_role": "result_metric", "value": 0.8,
        "run_id": "run-main", "target_sections": ["results", "discussion"],
    }], "blocking_conflicts": []})
    _json(project / "references" / "literature_summaries" / "prior.json", {"citation_key": "Prior2026", "title": "Prior evidence", "summary": "Prior work established a comparison under a related cohort."})

    build_paper_narrative(project)
    build_argument_matrices(project)
    build_section_lifecycles(project)
    build_panel_writing_contracts(project)
    resolve_venue_style_adapter(project)
    for section in ("introduction", "data", "methods", "results", "discussion"):
        _json(project / "writing" / "section_validation" / f"{section}.json", {
            "generated_at": "2026-07-12T10:00:00+00:00", "decision": "pass",
            "composition_mode": "codex_free_candidate", "quality_parity_eligible": True,
            "evidence_snapshot_id": "snapshot-1", "functional_job_coverage": {"decision": "pass", "score": 1.0},
        })
    _json(project / "review" / "results_manuscript_quality.json", {"decision": "pass", "score": 1.0})
    _json(project / "results" / "scientific_figure_quality_report.json", {"decision": "pass", "score": 1.0})
    _json(project / "citation_audit" / "final_citation_audit_report.json", {
        "generated_at": "2026-07-12T11:00:00+00:00", "decision": "pass", "blocking_issue_count": 0,
        "reference_coverage": {"coverage_ratio": 1.0},
    })

    report = assess_paper_quality_parity(project)

    assert report["decision"] == "pass"
    assert report["hard_correctness_score"] == 1.0
    assert report["functional_quality_score"] >= 0.95
