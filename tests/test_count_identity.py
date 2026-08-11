from __future__ import annotations

from draftpaper_cli.evidence_identity import (
    build_count_identity_report,
    compare_evidence,
    normalize_count_evidence,
)


def _count(**overrides):
    payload = {
        "count_definition_id": "model_unique_entity_count",
        "entity_type": "entity",
        "count_mode": "unique_entities",
        "cohort_id": "cohort-a",
        "filter_contract_id": "quality-v1",
        "sample_unit": "entity",
        "value": 1229,
        "evidence_role": "model_cohort",
    }
    payload.update(overrides)
    return normalize_count_evidence(payload, source_artifact="data/sample_flow.json", row_index=1)


def test_different_denominators_are_non_comparable() -> None:
    catalog = _count(count_definition_id="catalog_row_count", count_mode="rows", value=1671)
    model = _count(value=1229)
    assert compare_evidence(catalog, model, kind="count")["status"] == "different_identity_non_comparable"


def test_same_count_identity_with_different_values_is_blocking() -> None:
    first = _count(value=1229)
    second = _count(value=1230)
    assert compare_evidence(first, second, kind="count")["status"] == "same_identity_value_conflict"
    assert build_count_identity_report([first, second])["status"] == "blocked"


def test_unqualified_legacy_count_is_visible_but_not_complete() -> None:
    record = normalize_count_evidence(
        {"value": 1671, "entity_type": "row", "count_mode": "rows", "cohort_id": "cohort-a"},
        source_artifact="results/figure_code_trace.json",
    )
    report = build_count_identity_report([record])
    assert record["identity_complete"] is False
    assert report["status"] == "legacy_unqualified"
