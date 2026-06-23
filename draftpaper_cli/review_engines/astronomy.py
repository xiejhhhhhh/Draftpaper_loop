# Copyright (c) 2026 xiejhhhhhh
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

from typing import Any

from .base import context_text, issue_payload


def discover(context: dict[str, Any], discipline_profile: dict[str, Any]) -> list[dict[str, Any]]:
    text = context_text(context)
    evidence = ["astronomy discipline profile", "project archive context"]
    gaps: list[dict[str, Any]] = [
        issue_payload(
            code="astronomy_catalog_crossmatch_qc",
            title="Audit catalog cross-match and label reliability",
            severity="blocking",
            target_stage="data",
            rationale="Astronomy reviewers commonly expect source labels, catalog joins, duplicate matches, positional uncertainty, and quality flags to be checked before physical or classification claims are made.",
            actions=[
                "record the source catalog, reference catalog, match radius, coordinate system, epoch, and duplicate-match policy",
                "check whether labels are spectroscopic, photometric, literature-derived, or weak labels",
                "summarize missing, ambiguous, or conflicting labels before regenerating analysis code",
                "rerun data feasibility and method verification after the cross-match policy is confirmed",
            ],
            requires_user_confirmation=True,
            confirmation_question="Which catalogs, match radius, source labels, and quality flags are available for this astronomy project?",
            evidence=evidence,
        ),
        issue_payload(
            code="astronomy_uncertainty_selection_effects",
            title="Add uncertainty and selection-effect checks",
            severity="major",
            target_stage="methods",
            rationale="Flux limits, exposure depth, photometric errors, spectral uncertainty, sky coverage, and survey selection effects can change the interpretation of astronomy results.",
            actions=[
                "include measurement uncertainties or quality flags in the analysis when available",
                "check whether flux limits, detection thresholds, sky coverage, or exposure differences bias the sample",
                "separate descriptive source trends from population-level claims when selection effects cannot be corrected",
            ],
            requires_user_confirmation=True,
            confirmation_question="Are photometric, spectral, exposure, detection-threshold, or survey-selection metadata available?",
            evidence=evidence,
        ),
    ]

    if any(term in text for term in ("light curve", "flare", "time series", "variability", "cadence")):
        gaps.append(issue_payload(
            code="astronomy_time_series_sampling_qc",
            title="Verify light-curve sampling and variability-feature reliability",
            severity="major",
            target_stage="data",
            rationale="Light-curve and flare analyses are sensitive to cadence, gaps, exposure changes, background treatment, and signal-to-noise differences.",
            actions=[
                "summarize cadence, missing intervals, observation length, exposure variation, and signal-to-noise filters",
                "check whether variability features remain stable under minimum-observation and quality-threshold rules",
                "avoid interpreting irregularly sampled light curves as uniformly sampled series unless the method supports it",
            ],
            requires_user_confirmation=True,
            confirmation_question="May the loop require cadence, exposure, missingness, and signal-to-noise diagnostics before rewriting Methods and Results?",
            evidence=evidence,
        ))

    if any(term in text for term in ("classification", "classifier", "machine learning", "deep learning", "random forest", "transformer", "cnn")):
        gaps.append(issue_payload(
            code="astronomy_class_imbalance_validation",
            title="Add astronomy classification imbalance and external-validation checks",
            severity="major",
            target_stage="methods",
            rationale="Astronomical source-classification studies often have imbalanced classes, uncertain labels, survey-specific biases, and poor transfer across fields or instruments.",
            actions=[
                "report class counts, rare-class handling, macro metrics, calibrated probabilities, and confusion patterns",
                "prefer field-wise, catalog-wise, temporal, or survey-holdout validation when metadata allow",
                "compare model performance against a transparent baseline before emphasizing complex architectures",
            ],
            requires_user_confirmation=True,
            confirmation_question="Which source classes, validation split, and external catalog or field-holdout options are scientifically valid?",
            evidence=evidence,
        ))

    return gaps
