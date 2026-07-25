import json

from draftpaper_cli.executable_analysis import (
    compile_executable_analysis_specs,
    event_probability_ece_ast,
    render_formula_ast,
    validate_analysis_spec,
    validate_run_selection_policy,
)


def _spec() -> dict:
    return {
        "analysis_spec_id": "analysis:calibration",
        "estimand_id": "estimand:ece",
        "cohort_view_id": "view:test",
        "sample_unit": "event",
        "split_id": "test",
        "implementation_entry_point": "methods/src/calibration.py",
        "calibration": {"definition": "event_probability_ece", "implementation_definition": "event_probability_ece"},
        "resampling": {"uncertainty_semantics": "point_estimate_only"},
    }


def test_event_probability_ece_formula_is_derived_from_explicit_ast() -> None:
    formula = render_formula_ast(event_probability_ece_ast())
    assert "\\bar{p}_b" in formula
    assert "\\bar{y}_b" in formula
    assert "\\sum_{b=1}^{B}" in formula


def test_ece_definition_cannot_diverge_from_implementation() -> None:
    spec = _spec()
    spec["calibration"]["implementation_definition"] = "confidence_accuracy_ece"
    assert "calibration_definition_implementation_mismatch" in {item["code"] for item in validate_analysis_spec(spec)}


def test_nonpaired_interval_cannot_be_labelled_paired() -> None:
    spec = _spec()
    spec["resampling"] = {"uncertainty_semantics": "paired bootstrap interval", "paired": False, "resampling_unit": "event"}
    assert "paired_without_alignment" in {item["code"] for item in validate_analysis_spec(spec)}


def test_unlocked_best_seed_is_not_a_primary_policy() -> None:
    issues = validate_run_selection_policy({"selection_role": "primary", "aggregation_policy": "best_seed", "test_access_policy": "once", "locked_before_test_access": False})
    assert "post_hoc_best_seed_primary" in {item["code"] for item in issues}


def test_compiler_binds_method_task_to_figure_and_grouped_resampling(tmp_path) -> None:
    (tmp_path / "methods").mkdir()
    (tmp_path / "research_plan").mkdir()
    (tmp_path / "data").mkdir()
    (tmp_path / "methods" / "method_requirements.json").write_text(
        json.dumps({"primary_metric": "brier_score"}), encoding="utf-8"
    )
    (tmp_path / "research_plan" / "method_plan.json").write_text(
        json.dumps({
            "method_tasks": [{
                "task_id": "method_task_calibration",
                "figure_id": "fig_calibration",
                "method_family": "proper_scoring_rules",
                "method_components": ["proper_scoring_rules", "group_block_bootstrap"],
                "required_data": ["label", "probability", "group_id"],
                "validation_metric": "brier_score",
            }],
        }),
        encoding="utf-8",
    )
    (tmp_path / "research_plan" / "figure_storyboard.json").write_text(
        json.dumps({"figures": [{"figure_id": "fig_calibration"}]}), encoding="utf-8"
    )
    (tmp_path / "data" / "cohort_view_registry.json").write_text(
        json.dumps({
            "views": [{
                "cohort_view_id": "cohort_view:heldout",
                "sample_unit": "event",
                "split_id": "source_heldout",
            }],
        }),
        encoding="utf-8",
    )

    result = compile_executable_analysis_specs(tmp_path)
    payload = json.loads(
        (tmp_path / result["executable_analysis_spec"]).read_text(encoding="utf-8")
    )
    spec = payload["analysis_specs"][0]

    assert spec["figure_ids"] == ["fig_calibration"]
    assert spec["resampling"]["method"] == "group_block_bootstrap"
    assert spec["resampling"]["resampling_unit"] == "group_id"
    assert spec["resampling"]["group_id"] == "group_id"
