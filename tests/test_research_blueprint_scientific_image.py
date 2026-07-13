from __future__ import annotations

import json
from pathlib import Path

from draftpaper_cli.project_scaffold import create_project
from draftpaper_cli.research_capabilities import _extract_requirements
from draftpaper_cli.research_blueprint import build_research_blueprint


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
