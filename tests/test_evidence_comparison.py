from __future__ import annotations

from draftpaper_cli.evidence_identity import compare_evidence, normalize_metric_evidence


def _record(**overrides):
    payload = {
        "metric_name": "accuracy",
        "task_id": "task",
        "cohort_id": "cohort",
        "sample_unit": "entity",
        "model_id": "model",
        "validation_design_id": "design",
        "split_id": "test",
        "aggregation_id": "none",
        "uncertainty_definition_id": "none",
        "value": 0.7,
    }
    payload.update(overrides)
    return normalize_metric_evidence(payload, source_artifact="results/canonical.json")


def test_parent_aggregate_relation_is_explicit_when_ref_is_declared() -> None:
    child = _record(metric_record_id="seed-1", aggregation_id="none")
    aggregate = _record(
        metric_record_id="seed-mean",
        aggregation_id="seed_mean",
        aggregation_contract_id="agg-1",
        parent_record_refs=["seed-1"],
    )
    assert compare_evidence(child, aggregate)["status"] == "parent_aggregate_relation"


def test_missing_required_identity_is_not_a_value_conflict() -> None:
    complete = _record()
    incomplete = _record(validation_design_id="")
    assert compare_evidence(complete, incomplete)["status"] == "missing_required_identity"
