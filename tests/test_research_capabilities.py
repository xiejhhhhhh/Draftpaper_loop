# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from draftpaper_cli.project_scaffold import create_project


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _project_with_contract_inputs(tmp_path: Path, *, idea: str, field: str, figure: dict) -> Path:
    project = create_project(root=tmp_path, idea=idea, field=field, target_journal="Test Journal")
    project_path = project.path
    _write_json(project_path / "research_plan" / "claim_contract.json", {
        "claims": [{
            "claim_id": "claim_main",
            "claim": "The proposed analysis changes the target outcome in a reproducible cohort.",
            "claim_strength": "supported",
            "required_evidence": ["main_figure", "validated_method_output"],
        }],
    })
    _write_json(project_path / "results" / "figure_storyboard.json", {"figures": [figure]})
    _write_json(project_path / "methods" / "method_requirements.json", {
        "method_families": figure.get("method_families") or [],
        "required_data_features": figure.get("required_data_roles") or [],
        "primary_metric": figure.get("metric_family") or "f1_macro",
    })
    _write_json(project_path / "data" / "data_inventory.json", {"files": []})
    return project_path


def test_resolve_contract_builds_composite_interfaces_for_geography_ml(tmp_path: Path) -> None:
    from draftpaper_cli.research_capabilities import resolve_research_capabilities

    project = _project_with_contract_inputs(
        tmp_path,
        idea="Wheat NDVI remote sensing with random forest and spatial validation.",
        field="geography machine learning",
        figure={
            "figure_id": "fig_spatial_model",
            "research_question": "Does NDVI improve spatially blocked prediction?",
            "claim_ids": ["claim_main"],
            "required_data_roles": ["tabular_environment_dataset", "spatial_coordinates"],
            "method_families": ["random_forest", "spatial_validation"],
            "method_output_roles": ["prediction_metrics"],
            "manuscript_role": "main",
        },
    )

    result = resolve_research_capabilities(project)
    contract = json.loads((project / "research_plan" / "discipline_contract.json").read_text(encoding="utf-8"))
    capabilities = json.loads((project / "research_plan" / "research_capability_contract.json").read_text(encoding="utf-8"))

    assert result["status"] == "written"
    assert contract["primary_discipline"] == "geography"
    assert "machine_learning" in contract["secondary_disciplines"]
    assert contract["cross_discipline_interfaces"]
    assert {item["kind"] for item in capabilities["requirements"]} >= {"data", "method", "figure", "review"}
    assert any(item["figure_id"] == "fig_spatial_model" for item in capabilities["requirements"])


def test_resolve_contract_prefers_current_main_figure_contracts_over_stale_storyboard(tmp_path: Path) -> None:
    from draftpaper_cli.research_capabilities import resolve_research_capabilities

    project = _project_with_contract_inputs(
        tmp_path,
        idea="Astronomy classification with a transformer.",
        field="astronomy machine learning",
        figure={"figure_id": "figure_01", "claim_ids": ["claim_main"], "manuscript_role": "main"},
    )
    _write_json(project / "results" / "figure_contracts.json", {"main_contracts": [{
        "figure_id": "fig_actual", "storyboard_id": "figure_01", "required_data_roles": ["label"],
        "required_method_roles": ["baseline_model"], "manuscript_role": "main",
    }]})

    resolve_research_capabilities(project)
    capabilities = json.loads((project / "research_plan" / "research_capability_contract.json").read_text(encoding="utf-8"))

    assert {item.get("figure_id") for item in capabilities["requirements"]} == {"fig_actual"}


def test_sufficiency_requires_rescue_before_declaring_capability_unavailable(tmp_path: Path) -> None:
    from draftpaper_cli.research_capabilities import assess_plugin_sufficiency, resolve_research_capabilities

    project = _project_with_contract_inputs(
        tmp_path,
        idea="Astronomy catalog analysis using an unavailable bespoke quantum classifier.",
        field="astronomy machine learning",
        figure={
            "figure_id": "fig_unavailable",
            "research_question": "Can the bespoke classifier separate transient sources?",
            "claim_ids": ["claim_main"],
            "required_data_roles": ["unknown_proprietary_catalog"],
            "method_families": ["bespoke_quantum_classifier"],
            "method_output_roles": ["classification_metrics"],
            "manuscript_role": "main",
        },
    )
    resolve_research_capabilities(project)
    report = assess_plugin_sufficiency(project)

    saved = json.loads((project / "research_plan" / "plugin_sufficiency_report.json").read_text(encoding="utf-8"))
    assert report["decision"] == "rescue_required"
    assert saved["core_figure_decision"] == "rescue_required"
    assert (project / "research_plan" / "plugin_gap_plan.json").exists()
    assert any(item["state"] in {"missing", "blocked_external", "incompatible"} for item in saved["requirement_assessments"])


def test_sufficiency_accepts_first_party_local_templates_but_marks_project_verification_boundary(tmp_path: Path) -> None:
    from draftpaper_cli.research_capabilities import assess_plugin_sufficiency, resolve_research_capabilities

    project = _project_with_contract_inputs(
        tmp_path,
        idea="A tabular machine learning baseline model study.",
        field="machine learning",
        figure={
            "figure_id": "fig_baseline",
            "research_question": "Does the baseline model establish a reproducible reference?",
            "claim_ids": ["claim_main"],
            "required_data_roles": ["tabular_environment_dataset"],
            "method_families": ["baseline_model"],
            "method_output_roles": ["prediction_metrics"],
            "manuscript_role": "main",
        },
    )
    resolve_research_capabilities(project)
    result = assess_plugin_sufficiency(project)
    saved = json.loads((project / "research_plan" / "plugin_sufficiency_report.json").read_text(encoding="utf-8"))

    assert result["decision"] == "pass"
    covered = [item for item in saved["requirement_assessments"] if item["state"] == "covered"]
    assert any(item["coverage_basis"] == "local_template_requires_project_verification" for item in covered)


@pytest.mark.parametrize(
    ("idea", "field", "expected_primary", "expected_secondary"),
    [
        (
            "Time-aware transformer classification of X-ray transient light curves with spectral features.",
            "astronomy machine learning",
            "astronomy",
            "machine_learning",
        ),
        (
            "Bioinformatics RNA-seq transcriptomics and gene expression biomarkers predict clinical survival in a patient cohort.",
            "bioinformatics medicine",
            "bioinformatics",
            "medicine",
        ),
    ],
)
def test_resolve_contract_preserves_cross_discipline_roles(
    tmp_path: Path, idea: str, field: str, expected_primary: str, expected_secondary: str
) -> None:
    from draftpaper_cli.research_capabilities import resolve_research_capabilities

    project = _project_with_contract_inputs(
        tmp_path,
        idea=idea,
        field=field,
        figure={
            "figure_id": "fig_main",
            "research_question": "Does the model answer the target question?",
            "claim_ids": ["claim_main"],
            "required_data_roles": ["tabular_dataset"],
            "method_families": ["baseline_model"],
            "method_output_roles": ["prediction_metrics"],
            "manuscript_role": "main",
        },
    )
    resolve_research_capabilities(project)
    contract = json.loads((project / "research_plan" / "discipline_contract.json").read_text(encoding="utf-8"))

    assert contract["primary_discipline"] == expected_primary
    assert expected_secondary in contract["secondary_disciplines"]
    assert any(expected_secondary in item["disciplines"] for item in contract["cross_discipline_interfaces"])
