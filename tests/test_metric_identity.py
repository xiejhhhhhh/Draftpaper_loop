from __future__ import annotations

from draftpaper_cli.evidence_identity import (
    build_metric_identity_report,
    compare_evidence,
    normalize_metric_evidence,
    select_primary_metric,
)


def _metric(**overrides):
    payload = {
        "metric_name": "macro_f1",
        "task_id": "task-a",
        "cohort_id": "cohort-a",
        "sample_unit": "entity",
        "model_id": "model-a",
        "validation_design_id": "group-held-out",
        "split_id": "test",
        "aggregation_id": "seed_mean",
        "aggregation_contract_id": "agg-seed-1",
        "uncertainty_definition_id": "seed_sd",
        "value": 0.81,
        "evidence_role": "primary",
    }
    payload.update(overrides)
    return normalize_metric_evidence(payload, source_artifact="results/canonical_metrics.json", row_index=1)


def test_primary_metric_requires_exact_identity_and_ignores_compatibility_scalar() -> None:
    contract = {
        "contract_present": True,
        "metric_definition_id": "macro_f1",
        "task_id": "task-a",
        "cohort_id": "cohort-a",
        "sample_unit": "entity",
        "model_id": "model-a",
        "validation_design_id": "group-held-out",
        "split_id": "test",
        "aggregation_id": "seed_mean",
        "uncertainty_definition_id": "seed_sd",
    }
    records = [
        _metric(),
        _metric(model_id="model-b", value=0.95),
        _metric(validation_design_id="random-split", value=0.99),
        _metric(evidence_role="presentation_only", value=0.12),
    ]
    selected = select_primary_metric(records, contract)
    assert selected["status"] == "passed"
    assert selected["record"]["model_id"] == "model-a"
    assert selected["record"]["value"] == 0.81


def test_implicit_aggregate_is_not_identity_complete() -> None:
    record = _metric(aggregation_id="fold_mean", aggregation_contract_id="", aggregation_inferred=True)
    assert record["identity_complete"] is False
    assert "aggregation_contract_id" in record["missing_identity_fields"]


def test_comparison_checks_identity_before_value() -> None:
    same = _metric()
    different = _metric(validation_design_id="time-forward", value=0.81)
    conflict = _metric(value=0.82)
    assert compare_evidence(same, different)["status"] == "different_identity_non_comparable"
    assert compare_evidence(same, conflict)["status"] == "same_identity_value_conflict"


def test_missing_contract_is_legacy_unqualified_and_not_confirmable_evidence() -> None:
    report = build_metric_identity_report([_metric()], {"contract_present": False})
    assert report["status"] == "legacy_unqualified"
    assert report["primary_metric"]["status"] == "blocked_missing_primary_metric_contract"
