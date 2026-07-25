from draftpaper_cli.executable_analysis import (
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
