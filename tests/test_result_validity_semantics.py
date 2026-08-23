from __future__ import annotations

from draftpaper_cli.result_validity import _interpret_metric


def test_controlled_anomaly_injection_f1_is_not_model_performance() -> None:
    result = _interpret_metric(
        "f1",
        1.0,
        None,
        metric_context={
            "task_id": "audit_detection",
            "cohort_id": "cohort:anomaly_injection_2023",
            "sample_unit": "anomaly_instance",
            "validation_design_id": "controlled_anomaly_injection",
            "interpretation": "F1 for detecting controlled audit anomalies, not crop-classification accuracy or yield prediction.",
        },
    )

    assert result["metric_semantics"] == "controlled_implementation_check"
    assert result["evidence_strength"] == "controlled_implementation_recovery"
    assert "model-performance" not in result["statistical_interpretation"]
    assert "not crop-classification" in result["interpretation_scope"]


def test_ordinary_f1_remains_a_performance_metric() -> None:
    result = _interpret_metric(
        "f1",
        0.81,
        0.80,
        metric_context={
            "task_id": "crop_classification",
            "validation_design_id": "spatial_holdout",
        },
    )

    assert result["metric_semantics"] == "performance_metric"
    assert result["evidence_strength"] == "meets_threshold"
