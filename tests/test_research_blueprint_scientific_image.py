from __future__ import annotations

import json
from pathlib import Path

from draftpaper_cli.project_scaffold import create_project
from draftpaper_cli.research_capabilities import _extract_requirements
from draftpaper_cli.research_blueprint import build_research_blueprint
from draftpaper_cli.research_plan import _assert_cn_plan_quality, _render_research_plan_cn
from draftpaper_cli.statistical_validation import _task_families


def test_scientific_image_storyboard_is_not_time_series_or_xray_template() -> None:
    metadata = {
        "project_id": "image-representation",
        "idea": (
            "Test self-supervised vision representations of survey galaxy images with independent morphology, "
            "group-aware classification, redshift and luminosity confounder control, class imbalance, "
            "image missingness, and anomaly candidate discovery."
        ),
        "field": "astronomy machine learning scientific image representation",
        "target_journal": "ApJS",
    }
    literature = [{
        "bibtex_key": "Image2025",
        "title": "Self-supervised representation learning for astronomical images",
        "abstract": "Image embeddings support galaxy morphology analysis with held-out validation.",
        "citation_count": 10,
    }]
    blueprint = build_research_blueprint(
        project_meta=metadata,
        literature_items=literature,
        citation_rows=[{"citation_key": "Image2025", "claim": "current gap", "evidence_summary": "Image representations require confounder-aware validation."}],
        discipline_profile={"name": "composite:astronomy+machine_learning"},
        data_context={
            "status": "inventory_available",
            "file_count": 799,
            "external_file_count": 799,
            "tabular_file_count": 8,
            "cross_table_row_total": 31303,
            "table_summaries": [
                {"logical_name": "candidate_catalog.csv", "row_count": 5544, "column_count": 33, "missing_cell_ratio": 0.03},
                {"logical_name": "embedding_report.csv", "row_count": 4800, "column_count": 385, "missing_cell_ratio": 0.0},
            ],
            "feasibility": {"decision": "conditional_pass", "supported_claim_level": "exploratory or pilot claims only"},
            "role_coverage": {"required_roles": ["image_or_raster_data", "features"], "missing_roles": []},
        },
    )
    rendered = json.dumps(blueprint["figure_storyboard"], ensure_ascii=False).lower()
    assert "image coverage" in rendered
    assert "group-aware" in rendered
    assert "confounder" in rendered
    assert "anomaly candidates" in rendered
    assert "time-aware" not in rendered
    assert "flaring-source" not in rendered
    assert "light_curve" not in rendered
    assert "current_observation_tokens" not in rendered
    assert len(blueprint["research_claims"]) == 6
    figures = blueprint["figure_storyboard"]["figures"]
    assert figures[4]["claim_id"] == "claim_5_error_calibration"
    assert figures[5]["claim_id"] == "claim_6_anomaly_boundary"
    assert figures[4]["research_question"] != figures[5]["research_question"]
    assert all(
        "Show the evidence produced by" not in panel["expected_content"]
        for figure in figures
        for panel in figure["panels"]
    )

    plan_cn = _render_research_plan_cn(metadata, blueprint)
    _assert_cn_plan_quality(plan_cn)
    assert "5544 行" in plan_cn
    assert "4800 行" in plan_cn
    assert "31303" in plan_cn
    assert "跨表盘点总量" in plan_cn
    assert "探索性或先导性结论" in plan_cn
    assert "Which source" not in plan_cn
    families = _task_families(
        "euclid galaxy morphology classification representation group-aware validation anomaly candidates",
        {"primary_discipline": "astronomy", "secondary_disciplines": ["machine_learning"]},
    )
    assert "classification_validation" in families
    assert "representation_confounding" in families
    assert "anomaly_stability" in families
    assert "regression_fit_diagnostics" not in families
    assert "simulation_convergence" not in families


def test_explicit_scientific_objective_overrides_method_centred_image_template() -> None:
    metadata = {
        "project_id": "science-first-image",
        "title": "Galaxy physical states and visual structure",
        "idea": "Quantify the relation between galaxy visual structure and physical activity state.",
        "field": "astronomy machine learning",
        "target_journal": "ApJS",
        "research_objective": {
            "scientific_objective": "Quantify the relation between visual structure and physical state.",
            "primary_scientific_questions": [{
                "claim_id": "claim_physical_relation",
                "research_question": "How does visual structure vary across physical activity states?",
                "expected_finding": "Visual structure should show a bounded association with physical state.",
                "figure_contract": {
                    "proposed_title": "Galaxy structure across physical activity states",
                    "story_role": "direct_scientific_signal",
                    "required_data": ["image_embedding", "physical_state"],
                    "required_method": ["confounder_adjusted_association"],
                    "suggested_plot_type": "effect_summary",
                    "validation_metric": "adjusted_effect_with_uncertainty",
                    "panels": [{
                        "label": "a",
                        "scientific_role": "adjusted association",
                        "required_method": "confounder_adjusted_association",
                        "required_data_roles": ["image_embedding", "physical_state"],
                        "expected_content": "Estimate the adjusted morphology-state association.",
                    }],
                },
            }],
            "methodological_hypothesis": "DINOv2 can act as a visual measurement tool.",
            "data_scope": ["Euclid-DESI crossmatch"],
            "secondary_analyses": ["DINOv2 benchmark"],
            "claim_boundary": "Exploratory association only.",
        },
    }
    blueprint = build_research_blueprint(
        project_meta=metadata,
        literature_items=[{"bibtex_key": "Morph2026", "title": "Galaxy morphology", "citation_count": 1}],
        citation_rows=[{"citation_key": "Morph2026", "claim": "current gap", "evidence_summary": "Gap."}],
        discipline_profile={"primary_discipline": "astronomy"},
    )
    figure = blueprint["figure_storyboard"]["figures"][0]
    assert figure["proposed_title"] == "Galaxy structure across physical activity states"
    assert figure["required_method"] == ["confounder_adjusted_association"]
    assert "representation prediction" not in figure["proposed_title"].lower()


def test_storyboard_required_data_and_method_fields_enter_capability_contract(tmp_path: Path) -> None:
    project = create_project(root=tmp_path, idea="Scientific image representation", field="astronomy machine learning").path
    storyboard = {
        "figures": [{
            "figure_id": "fig_image",
            "research_question": "Does the representation generalize?",
            "required_data": ["image_embedding", "independent_target"],
            "required_method": ["group_aware_validation", "confounder_control"],
        }]
    }
    (project / "research_plan" / "figure_storyboard.json").write_text(json.dumps(storyboard), encoding="utf-8")
    profile = {"primary_discipline": "astronomy", "secondary_disciplines": ["machine_learning"]}
    requirements, _ = _extract_requirements(project, profile)
    kinds = {(item["kind"], item.get("role") or item.get("method_family")) for item in requirements}
    assert ("data", "image_embedding") in kinds
    assert ("data", "independent_target") in kinds
    assert ("method", "group_aware_validation") in kinds
    assert ("method", "confounder_control") in kinds
