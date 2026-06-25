# Copyright (c) 2026 xiejhhhhhh
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

from typing import Mapping


def assess_model_statistical_validity(
    *,
    metrics: Mapping[str, float],
    thresholds: Mapping[str, float],
) -> dict[str, object]:
    issues: list[str] = []
    r2 = metrics.get("r2")
    p_value = metrics.get("p_value")
    sample_count = metrics.get("sample_count")
    train_score = metrics.get("train_score")
    test_score = metrics.get("test_score")
    if r2 is not None and r2 < thresholds.get("minimum_r2", 0.0):
        issues.append("effect_size_or_fit_is_weak")
    if p_value is not None and p_value > thresholds.get("maximum_p_value", 1.0):
        issues.append("statistical_confidence_is_weak")
    if sample_count is not None and sample_count < thresholds.get("minimum_sample_count", 0.0):
        issues.append("sample_size_is_low")
    if train_score is not None and test_score is not None:
        gap = train_score - test_score
        if gap > thresholds.get("maximum_generalization_gap", 1.0):
            issues.append("generalization_gap_is_large")
    return {
        "rule_group_id": "model_statistical_validity_gate",
        "passes_gate": not issues,
        "issues": issues,
        "recommendations": _recommendations_for(issues),
    }


def _recommendations_for(issues: list[str]) -> list[str]:
    mapping = {
        "effect_size_or_fit_is_weak": "Revisit feature construction, data quality control, nonlinear baselines, and claim scope.",
        "statistical_confidence_is_weak": "Report confidence intervals or resampling and avoid significance claims without adequate evidence.",
        "sample_size_is_low": "Assess data completeness and consider adding samples, external data, or reducing model complexity.",
        "generalization_gap_is_large": "Check leakage, spatial/temporal blocking, regularization, and external validation.",
    }
    return [mapping[item] for item in issues if item in mapping]
