from draftpaper_cli.cohort_semantics import validate_cohort_registries, validate_data_provenance


def _cohorts() -> dict:
    return {
        "cohorts": [
            {"cohort_id": "all", "parent_cohort_id": None, "sample_unit": "source", "count": 184},
            {"cohort_id": "reliable", "parent_cohort_id": "all", "sample_unit": "source", "count": 183},
        ]
    }


def _views() -> dict:
    return {
        "views": [
            {"cohort_view_id": "display_184", "parent_cohort_id": "all", "sample_unit": "source", "count": 184, "missingness_policy": "display_all", "allowed_uses": ["descriptive_display"]},
            {"cohort_view_id": "regression_183", "parent_cohort_id": "reliable", "sample_unit": "source", "count": 183, "missingness_policy": "complete_case_by_outcome", "allowed_uses": ["adjusted_regression"]},
        ]
    }


def test_distinct_184_display_and_183_regression_views_can_coexist() -> None:
    report = validate_cohort_registries(
        _cohorts(),
        _views(),
        [
            {"artifact_id": "panel:display", "cohort_view_id": "display_184", "sample_unit": "source", "count": 184},
            {"artifact_id": "estimand:regression", "cohort_view_id": "regression_183", "sample_unit": "source", "count": 183},
        ],
    )
    assert report["decision"] == "pass"


def test_missing_or_mismatched_view_blocks_artifact_binding() -> None:
    report = validate_cohort_registries(
        _cohorts(),
        _views(),
        [
            {"artifact_id": "panel:no_view", "count": 184},
            {"artifact_id": "panel:wrong_count", "cohort_view_id": "regression_183", "sample_unit": "source", "count": 184},
        ],
    )
    codes = {item["code"] for item in report["blocking_issues"]}
    assert report["decision"] == "blocked"
    assert {"artifact_missing_cohort_view", "artifact_cohort_count_mismatch"}.issubset(codes)


def test_provenance_requires_access_boundary_and_version_status() -> None:
    issues = validate_data_provenance({"sources": [{"data_source_id": "catalog", "source_type": "catalog"}]})
    assert {item["code"] for item in issues} == {"missing_access_boundary", "missing_version_status"}
