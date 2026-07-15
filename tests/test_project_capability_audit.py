# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json
from pathlib import Path

from draftpaper_cli.project_scaffold import create_project
from draftpaper_cli.passport import refresh_project_passport
from draftpaper_cli.project_versioning import create_project_version_from_plan, import_version_assets, plan_project_version


def test_cross_view_assignments_are_post_method_outputs_not_input_data() -> None:
    from draftpaper_cli.research_capabilities import DERIVED_METHOD_OUTPUT_ROLES

    expected = {
        "image_class_assignment",
        "physical_class_assignment",
        "assignment_stability",
        "concordance_metric",
        "bootstrap_interval",
        "observed_concordance",
        "permutation_null_distribution",
        "discordance_indicator",
    }

    assert expected.issubset(DERIVED_METHOD_OUTPUT_ROLES)


def test_supervised_predictions_and_physical_intervals_are_post_method_outputs() -> None:
    from draftpaper_cli.research_capabilities import DERIVED_METHOD_OUTPUT_ROLES

    assert {
        "predicted_image_class",
        "predicted_probability",
        "measured_class_interval",
        "measured_interval_uncertainty",
        "passband_mapping",
    }.issubset(DERIVED_METHOD_OUTPUT_ROLES)


def test_observed_colour_and_calibration_requirements_use_verified_canonical_roles() -> None:
    from draftpaper_cli.project_capability_audit import DATA_ROLE_COVERAGE_ALIASES

    assert DATA_ROLE_COVERAGE_ALIASES["observed_colours"] == {"photometric_colours"}
    assert DATA_ROLE_COVERAGE_ALIASES["calibration_bins"] == {"prediction_score"}


def test_audit_can_bind_hash_verified_lineage_method_code_without_activating_parent_state(tmp_path) -> None:
    from draftpaper_cli.project_capability_audit import audit_project_capabilities

    parent = create_project(
        root=tmp_path,
        idea="Scientific image group-aware validation",
        field="astronomy machine learning",
    ).path
    script = parent / "methods" / "scripts" / "run_group_validation.py"
    script.write_text(
        "# StratifiedGroupKFold group leakage fold audit\n"
        "def run_group_aware_validation():\n"
        "    return {'group': 'held-out', 'fold': 5}\n",
        encoding="utf-8",
    )
    refresh_project_passport(parent, event="lineage_method_fixture")
    plan_path = tmp_path / "lineage_method_plan.json"
    plan_project_version(parent, output=plan_path)
    child = create_project_version_from_plan(plan_path)["project_path"]
    import_version_assets(child, plan_path)
    project = Path(child)
    (project / "research_plan" / "plugin_sufficiency_report.json").write_text(
        json.dumps(
            {
                "requirement_assessments": [
                    {
                        "requirement_id": "method:fig:group_aware_validation",
                        "kind": "method",
                        "figure_id": "fig",
                        "method_family": "group_aware_validation",
                        "core": True,
                        "state": "project_method_implementation_required",
                    }
                ],
                "rescue_tasks": [],
            }
        ),
        encoding="utf-8",
    )
    (project / "research_plan" / "plugin_binding_plan.json").write_text(json.dumps({"bindings": []}), encoding="utf-8")

    result = audit_project_capabilities(project)
    binding = json.loads((project / "research_plan" / "plugin_binding_plan.json").read_text(encoding="utf-8"))["bindings"][0]

    assert result["decision"] == "pass"
    assert binding["coverage_basis"] == "verified_lineage_import"
    assert binding["validation_level"] == "lineage_hash_and_semantic_audited"
    assert binding["evidence"]["path"].startswith("lineage/imported_code/methods/")


def test_audit_converts_traceable_local_data_and_transformer_code_to_project_local_bindings(tmp_path) -> None:
    from draftpaper_cli.project_capability_audit import audit_project_capabilities

    project = create_project(root=tmp_path, idea="Astronomy transformer test", field="astronomy machine learning", target_journal="Test").path
    (project / "data" / "processed" / "events.csv").write_text(
        "label,spectral_hardness,multiwavelength_counterpart\n0,0.2,1\n", encoding="utf-8"
    )
    (project / "methods" / "scripts" / "fusion_transformer.py").write_text(
        "class TimeAwareFusionTransformer:\n    pass\n", encoding="utf-8"
    )
    report = {
        "decision": "blocked",
        "core_figure_decision": "blocked",
        "requirement_assessments": [
            {"requirement_id": "data:fig_main:label", "kind": "data", "figure_id": "fig_main", "role": "label", "core": True, "state": "missing"},
            {"requirement_id": "data:fig_main:spectral_features", "kind": "data", "figure_id": "fig_main", "role": "spectral_features", "core": True, "state": "missing"},
            {"requirement_id": "data:fig_main:multiwavelength_features", "kind": "data", "figure_id": "fig_main", "role": "multiwavelength_features", "core": True, "state": "missing"},
            {"requirement_id": "method:fig_main:multimodal_learning", "kind": "method", "figure_id": "fig_main", "method_family": "multimodal_learning", "core": True, "state": "missing"},
        ],
        "rescue_tasks": [],
    }
    (project / "research_plan" / "plugin_sufficiency_report.json").write_text(json.dumps(report), encoding="utf-8")
    (project / "research_plan" / "plugin_binding_plan.json").write_text(json.dumps({"bindings": []}), encoding="utf-8")

    result = audit_project_capabilities(project)
    updated = json.loads((project / "research_plan" / "plugin_sufficiency_report.json").read_text(encoding="utf-8"))
    bindings = json.loads((project / "research_plan" / "plugin_binding_plan.json").read_text(encoding="utf-8"))

    assert result["decision"] == "pass"
    assert updated["decision"] == "pass"
    assert {item["state"] for item in updated["requirement_assessments"]} == {"covered_project_local"}
    assert all(item["binding_scope"] == "project_local" for item in bindings["bindings"])
    project_state = json.loads((project / "project.json").read_text(encoding="utf-8"))
    assert project_state["stages"]["code"]["status"] == "draft"
    assert (project / "methods" / "project_local_code_acceptance.json").is_file()


def test_audit_recognizes_common_project_local_analysis_roles(tmp_path) -> None:
    from draftpaper_cli.project_capability_audit import audit_project_capabilities

    project_path = create_project(
        root=tmp_path,
        idea="Astronomy baseline feature diagnostics",
        field="astronomy machine learning",
        target_journal="Test",
    ).path
    processed = project_path / "data" / "processed"
    scripts = project_path / "methods" / "scripts"
    processed.mkdir(parents=True, exist_ok=True)
    scripts.mkdir(parents=True, exist_ok=True)
    (processed / "history_lc_tokens.csv").write_text(
        "source_id,mjd,rate,class_label\n1,1.0,0.4,AGN\n",
        encoding="utf-8",
    )
    (scripts / "train_baselines.py").write_text(
        "# class_count and value_counts diagnostics\n"
        "# baseline random_forest feature importance and spectral feature_space\n",
        encoding="utf-8",
    )
    requirements = [
        ("data:fig_1:light_curve", "data", "light_curve"),
        ("method:fig_2:class_balance_check", "method", "class_balance_check"),
        ("method:fig_3:feature_space_diagnostic", "method", "feature_space_diagnostic"),
        ("method:fig_4:baseline_model", "method", "baseline_model"),
    ]
    report_path = project_path / "research_plan" / "plugin_sufficiency_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps({
            "requirement_assessments": [
                {
                    "requirement_id": requirement_id,
                    "figure_id": requirement_id.split(":")[1],
                    "kind": kind,
                    "role": role,
                    "state": "execution_required",
                    "core": True,
                }
                for requirement_id, kind, role in requirements
            ],
            "rescue_tasks": [],
        }),
        encoding="utf-8",
    )
    (project_path / "research_plan" / "plugin_binding_plan.json").write_text(
        json.dumps({"bindings": []}), encoding="utf-8"
    )

    result = audit_project_capabilities(project_path)

    assert result["decision"] == "pass"
    assert result["covered_project_local"] == 4


def test_audit_binds_verified_external_inventory_roles_without_copying_private_data(tmp_path) -> None:
    from draftpaper_cli.project_capability_audit import audit_project_capabilities

    project = create_project(
        root=tmp_path,
        idea="Scientific image representation analysis",
        field="astronomy machine learning",
        target_journal="Test",
    ).path
    inventory = project / "data" / "data_inventory.json"
    inventory.write_text(json.dumps({"files": [{"path": "external://source/embeddings.csv"}]}), encoding="utf-8")
    (project / "data" / "data_role_coverage_report.json").write_text(
        json.dumps(
            {
                "decision": "pass",
                "available_roles": [
                    "source_catalog",
                    "features",
                    "label_or_response",
                    "confounder_variables",
                    "sample_group",
                    "validation_design",
                ],
            }
        ),
        encoding="utf-8",
    )
    report = {
        "requirement_assessments": [
            {
                "requirement_id": "data:fig:image_embedding",
                "kind": "data",
                "figure_id": "fig",
                "role": "image_embedding",
                "data_role_class": "input_data",
                "core": True,
                "state": "project_data_implementation_required",
            },
            {
                "requirement_id": "data:fig:group_validation_split",
                "kind": "data",
                "figure_id": "fig",
                "role": "group_validation_split",
                "data_role_class": "input_data",
                "core": True,
                "state": "project_data_implementation_required",
            },
            {
                "requirement_id": "data:fig:prediction_score",
                "kind": "data",
                "figure_id": "fig",
                "role": "prediction_score",
                "data_role_class": "derived_method_output",
                "core": True,
                "state": "method_output_pending",
            },
        ],
        "rescue_tasks": [],
    }
    (project / "research_plan" / "plugin_sufficiency_report.json").write_text(
        json.dumps(report), encoding="utf-8"
    )
    (project / "research_plan" / "plugin_binding_plan.json").write_text(
        json.dumps({"bindings": []}), encoding="utf-8"
    )

    result = audit_project_capabilities(project)
    bindings = json.loads(
        (project / "research_plan" / "plugin_binding_plan.json").read_text(encoding="utf-8")
    )["bindings"]

    assert result["decision"] == "pass"
    assert result["covered_project_local"] == 2
    assert {item["coverage_basis"] for item in bindings} == {"verified_data_role_coverage"}
    assert all(item["evidence"]["path"] == "data/data_role_coverage_report.json" for item in bindings)


def test_audit_binds_available_role_even_when_another_role_blocks_global_coverage(tmp_path) -> None:
    from draftpaper_cli.project_capability_audit import audit_project_capabilities

    project = create_project(root=tmp_path, idea="Image classification with literature validation", field="astronomy").path
    (project / "data" / "data_inventory.json").write_text(
        json.dumps({"files": [{"path": "external://catalog.csv"}]}), encoding="utf-8"
    )
    (project / "data" / "data_role_coverage_report.json").write_text(
        json.dumps({"decision": "blocked", "available_roles": ["label_or_response"]}),
        encoding="utf-8",
    )
    (project / "research_plan" / "plugin_sufficiency_report.json").write_text(
        json.dumps({
            "requirement_assessments": [{
                "requirement_id": "data:fig:morphology_label",
                "kind": "data",
                "figure_id": "fig",
                "role": "morphology_label",
                "data_role_class": "input_data",
                "core": True,
                "state": "project_data_implementation_required",
            }],
            "rescue_tasks": [],
        }),
        encoding="utf-8",
    )
    (project / "research_plan" / "plugin_binding_plan.json").write_text(
        json.dumps({"bindings": []}), encoding="utf-8"
    )

    result = audit_project_capabilities(project)

    assert result["decision"] == "pass"
    assert result["covered_project_local"] == 1


def test_audit_maps_science_first_galaxy_roles_to_verified_inventory(tmp_path) -> None:
    from draftpaper_cli.project_capability_audit import audit_project_capabilities

    project = create_project(root=tmp_path, idea="Galaxy morphology physics", field="astronomy").path
    (project / "data" / "data_inventory.json").write_text(json.dumps({"files": []}), encoding="utf-8")
    (project / "data" / "data_role_coverage_report.json").write_text(
        json.dumps({
            "decision": "pass",
            "available_roles": [
                "image_or_raster_data", "quality_flags", "features", "confounder_variables",
                "mag_g", "mag_r", "mag_z", "color_gr", "color_rz", "abs_mag_r", "color_w1w2",
                "label_or_response", "z", "sample_group",
            ],
        }),
        encoding="utf-8",
    )
    roles = [
        "image_validity", "embedding_membership", "selection_covariates",
        "continuous_colour_magnitude_observables", "catalog_profile_morphology",
        "physical_state_proxy", "redshift", "absolute_magnitude", "apparent_magnitude",
        "image_quality_flags", "group_id", "proxy_label_definition",
    ]
    (project / "research_plan" / "plugin_sufficiency_report.json").write_text(
        json.dumps({
            "requirement_assessments": [
                {
                    "requirement_id": f"data:fig:{role}", "kind": "data", "figure_id": "fig",
                    "role": role, "data_role_class": "input_data", "core": True,
                    "state": "project_data_implementation_required",
                }
                for role in roles
            ],
            "rescue_tasks": [],
        }),
        encoding="utf-8",
    )
    (project / "research_plan" / "plugin_binding_plan.json").write_text(json.dumps({"bindings": []}), encoding="utf-8")

    result = audit_project_capabilities(project)
    report = json.loads((project / "research_plan" / "project_capability_audit.json").read_text(encoding="utf-8"))

    assert result["decision"] == "pass"
    assert report["project_data_implementation_required"] == []


def test_new_method_family_needs_semantic_signature_not_one_generic_word(tmp_path) -> None:
    from draftpaper_cli.project_capability_audit import audit_project_capabilities

    project = create_project(root=tmp_path, idea="Galaxy transition populations", field="astronomy").path
    (project / "methods" / "scripts" / "run_analysis.py").write_text(
        "# generic population analysis with redshift\n",
        encoding="utf-8",
    )
    (project / "research_plan" / "plugin_sufficiency_report.json").write_text(
        json.dumps({
            "requirement_assessments": [{
                "requirement_id": "method:fig:transition_population_analysis",
                "kind": "method", "figure_id": "fig", "method_family": "transition_population_analysis",
                "core": True, "state": "project_method_implementation_required",
            }],
            "rescue_tasks": [],
        }),
        encoding="utf-8",
    )
    (project / "research_plan" / "plugin_binding_plan.json").write_text(json.dumps({"bindings": []}), encoding="utf-8")

    result = audit_project_capabilities(project)
    report = json.loads((project / "research_plan" / "project_capability_audit.json").read_text(encoding="utf-8"))

    assert result["decision"] == "project_implementation_required"
    assert report["project_method_implementation_required"] == ["method:fig:transition_population_analysis"]
