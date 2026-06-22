from __future__ import annotations

from typing import Any

from .base import context_text, issue_payload


def _has_weak_fit(context: dict[str, Any]) -> bool:
    validity = context.get("result_validity") or {}
    if validity.get("evidence_strength") in {"very_weak_fit", "weak_fit", "weak_effect", "negligible_effect"}:
        return True
    for figure in context.get("figure_metadata") or []:
        stats = figure.get("statistics") or {}
        try:
            r2 = float(stats.get("r2"))
        except (TypeError, ValueError):
            r2 = None
        try:
            pearson_r = abs(float(stats.get("pearson_r")))
        except (TypeError, ValueError):
            pearson_r = None
        if r2 is not None and r2 < 0.10:
            return True
        if pearson_r is not None and pearson_r < 0.30:
            return True
    return False


def discover(context: dict[str, Any], discipline_profile: dict[str, Any]) -> list[dict[str, Any]]:
    text = context_text(context)
    gaps: list[dict[str, Any]] = []
    evidence = ["geography discipline profile", "project archive context"]

    gaps.append(issue_payload(
        code="geography_spatial_scale_alignment",
        title="Verify spatial and temporal scale alignment",
        severity="blocking",
        target_stage="data",
        rationale="Geography and remote-sensing reviewers expect predictors and response variables to be aligned by spatial support, temporal window, and aggregation level before interpreting associations.",
        actions=[
            "check coordinate reference systems, raster/vector resolution, and region identifiers",
            "verify that NDVI, climate proxies, yield, and nitrogen-related variables refer to compatible time windows",
            "summarize whether observations are field-level, county-level, pixel-level, or aggregated across mixed supports",
            "rerun data feasibility and result validity after correcting scale or temporal-window mismatches",
        ],
        requires_user_confirmation=True,
        confirmation_question="Does the project contain spatial identifiers, coordinates, year, region, growth-stage, or aggregation-level fields that can be used for alignment checks?",
        evidence=evidence,
    ))

    if any(token in text for token in ("ndvi", "vegetation index", "remote sensing", "raster", "sentinel", "modis", "landsat")):
        gaps.append(issue_payload(
            code="geography_remote_sensing_qc",
            title="Add remote-sensing quality control before interpreting weak effects",
            severity="blocking" if _has_weak_fit(context) else "major",
            target_stage="data",
            rationale="Remote-sensing associations can be weakened by cloud contamination, saturation, sensor artifacts, phenology-window mismatch, or mixed land-cover samples.",
            actions=[
                "screen NDVI or vegetation-index values for impossible ranges, saturation, cloud contamination, and sensor artifacts",
                "align vegetation indicators with crop growth stages rather than using an arbitrary pooled time window",
                "compare raw and quality-filtered samples before deciding whether weak R2/r values reflect real signal",
                "record the accepted QC policy before regenerating analysis code and figures",
            ],
            requires_user_confirmation=True,
            confirmation_question="May the loop apply or propose NDVI quality filters, phenology-window selection, or raw-vs-cleaned comparisons for this project?",
            evidence=evidence,
        ))

    gaps.append(issue_payload(
        code="geography_spatial_autocorrelation",
        title="Assess spatial autocorrelation and spatial validation risk",
        severity="major",
        target_stage="methods",
        rationale="Geographic samples are often spatially clustered, so random validation or pooled correlations can overstate evidence strength.",
        actions=[
            "check whether residuals, predictors, or errors show spatial clustering when coordinates or regions are available",
            "prefer spatial block, regional holdout, or time-sliced validation over a purely random split when spatial identifiers exist",
            "report whether spatial dependence changes the interpretation of fitted relationships",
        ],
        requires_user_confirmation=True,
        confirmation_question="Are coordinates, administrative regions, plots, or spatial blocks available for spatial autocorrelation or blocked validation?",
        evidence=evidence,
    ))

    gaps.append(issue_payload(
        code="geography_stratified_heterogeneity",
        title="Test geographic and agronomic heterogeneity through stratified analysis",
        severity="major",
        target_stage="methods",
        rationale="A pooled relationship can hide region-, year-, climate-zone-, or crop-stage-specific effects that geography reviewers commonly expect to see.",
        actions=[
            "run stratified summaries by year, region, climate zone, cultivar group, growth stage, or management zone when fields are available",
            "compare pooled and stratified effect sizes before writing broad spatial claims",
            "add figures that show where the relationship is stable and where it breaks down",
        ],
        requires_user_confirmation=True,
        confirmation_question="Which stratification variables are scientifically valid for this project: year, region, climate zone, crop stage, cultivar, management zone, or none?",
        evidence=evidence,
    ))

    if _has_weak_fit(context):
        gaps.append(issue_payload(
            code="geography_weak_fit_qc",
            title="Backtrack weak R2 or weak correlation to data QC and model form",
            severity="blocking",
            target_stage="data",
            rationale="Low R2 or weak correlation in a geography manuscript should not be treated as publishable evidence until data quality, proxy selection, outliers, scale mismatch, nonlinearity, and stratification have been checked.",
            actions=[
                "inspect outliers and high-leverage observations for weak-effect variables",
                "compare raw, cleaned, robust-regression, nonlinear, and stratified variants when scientifically justified",
                "test lagged, seasonal, cumulative, or threshold climate features instead of only one pooled linear proxy",
                "rerun result validity and figure planning after the QC/model-form audit",
            ],
            requires_user_confirmation=True,
            confirmation_question="Should weak R2/r results trigger a data-cleaning and model-form rebuild before Results and Discussion are regenerated?",
            evidence=evidence,
        ))

    return gaps
