# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

from typing import Any, Mapping


def evaluate_rule(evidence: Mapping[str, Any] | None = None) -> dict[str, Any]:
    evidence = dict(evidence or {})
    issues: list[str] = []
    if not evidence.get("coordinate_definition"):
        issues.append("coordinate_definition_missing")
    if not evidence.get("partition_unit"):
        issues.append("partition_unit_missing")
    if evidence.get("exact_source_overlap_count") is None:
        issues.append("exact_source_overlap_not_reported")
    if evidence.get("minimum_cross_partition_separation_arcsec") is None:
        issues.append("angular_overlap_not_reported")
    support = evidence.get("cutout_support_arcsec")
    minimum = evidence.get("minimum_cross_partition_separation_arcsec")
    if support is not None and minimum is not None and float(minimum) < float(support):
        issues.append("cross_partition_cutout_overlap_detected")
    if evidence.get("shared_acquisition_group_count") is None:
        issues.append("shared_acquisition_groups_not_reported")
    if evidence.get("claims_spatial_generalization") and not evidence.get("grouped_validation_reported"):
        issues.append("grouped_validation_required_for_spatial_generalization")
    if evidence.get("claims_leakage_free") and set(evidence.get("tested_leakage_modes") or []) <= {"exact_source_identity"}:
        issues.append("identifier_only_leakage_free_claim")
    return {
        "rule_id": "sky_partition_overlap_validation",
        "rule_family": "spatial_validation",
        "passes_gate": not issues,
        "issues": issues,
        "allowed_claim_strength": "bounded_to_tested_leakage_modes",
        "recommendations": _recommendations(issues),
    }


def _recommendations(issues: list[str]) -> list[str]:
    mapping = {
        "coordinate_definition_missing": "Declare coordinate frame and angular units.",
        "partition_unit_missing": "Declare whether the split unit is source, cutout, tile, field, exposure, or another acquisition group.",
        "exact_source_overlap_not_reported": "Report exact source duplication across every partition pair.",
        "angular_overlap_not_reported": "Compute nearest cross-partition separation and compare it with image support.",
        "cross_partition_cutout_overlap_detected": "Remove or group overlapping image support before evaluation.",
        "shared_acquisition_groups_not_reported": "Report shared tiles, fields, exposures, or acquisition groups.",
        "grouped_validation_required_for_spatial_generalization": "Add tile, field, or spatially blocked validation.",
        "identifier_only_leakage_free_claim": "Replace leakage-free wording with the exact leakage modes tested."
    }
    return [mapping[item] for item in issues if item in mapping]
