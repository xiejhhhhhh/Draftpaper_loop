from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .project_scaffold import _write_json
from .project_state import load_project, update_stage_status


RESULT_VALIDITY_INPUTS = [
    "methods/run_manifest.yaml",
    "methods/method_requirements.json",
    "data/data_feasibility_report.json",
]

RESULT_VALIDITY_OUTPUTS = [
    "results/result_validity_report.json",
    "results/result_validity_report.md",
]


class ResultValidityError(RuntimeError):
    """Raised when result validity cannot be assessed or has not passed."""


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _to_float(value: Any) -> float | None:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _metric_semantics(metric: str) -> str:
    normalized = metric.strip().lower().replace("-", "_")
    if normalized in {"p", "p_value", "pvalue", "p_val", "pval"}:
        return "statistical_significance"
    if normalized in {"r2", "r_squared", "rsquared", "coefficient_of_determination"}:
        return "goodness_of_fit"
    if normalized in {"r", "pearson_r", "spearman_r", "correlation", "correlation_coefficient"}:
        return "effect_size_correlation"
    if normalized in {"rmse", "mse", "mae", "loss", "error", "error_rate"}:
        return "error_metric"
    return "performance_metric"


def _default_threshold(metric: str, configured_threshold: Any) -> float | None:
    threshold = _to_float(configured_threshold)
    if threshold is not None:
        return threshold
    semantics = _metric_semantics(metric)
    if semantics == "statistical_significance":
        return 0.05
    if semantics == "effect_size_correlation":
        return 0.30
    return None


def _interpret_metric(metric: str, observed: float | None, threshold: float | None) -> dict[str, Any]:
    semantics = _metric_semantics(metric)
    result = {
        "metric_semantics": semantics,
        "evidence_strength": "not_assessed",
        "statistical_interpretation": "",
        "metric_issues": [],
    }
    issues: list[str] = result["metric_issues"]
    if observed is None:
        issues.append(f"Primary metric {metric} is missing from parsed method metrics.")
        result["evidence_strength"] = "missing_metric"
        result["statistical_interpretation"] = "The declared primary metric could not be evaluated from method outputs."
        return result

    if semantics == "statistical_significance":
        alpha = threshold if threshold is not None else 0.05
        if observed <= alpha:
            result["evidence_strength"] = "statistically_significant"
            result["statistical_interpretation"] = f"The p-value {observed:.3g} is below alpha={alpha:.3g}, so the tested association is statistically significant under the declared test."
        else:
            result["evidence_strength"] = "not_statistically_significant"
            result["statistical_interpretation"] = f"The p-value {observed:.3g} is above alpha={alpha:.3g}, so the tested association is not statistically significant."
            issues.append(f"Primary metric {metric}={observed:.3g} is above the p-value threshold {alpha:.3g}.")
        return result

    if semantics == "goodness_of_fit":
        if threshold is not None and threshold <= 0.05:
            issues.append("R2 is a goodness-of-fit measure, not a p-value; 0.05 is not a valid statistical-significance threshold for R2.")
        if observed < 0.10:
            result["evidence_strength"] = "very_weak_fit"
            result["statistical_interpretation"] = f"R2={observed:.3g} explains less than 10% of the response variance and is too weak for a strong explanatory conclusion without additional evidence."
            issues.append(f"Primary metric r2={observed:.3g} indicates very weak fit and should trigger data-quality, proxy-variable, and feature-construction review.")
        elif observed < 0.25:
            result["evidence_strength"] = "weak_fit"
            result["statistical_interpretation"] = f"R2={observed:.3g} indicates weak explanatory fit; claims should remain exploratory unless robustness analyses justify the interpretation."
            issues.append(f"Primary metric r2={observed:.3g} is weak; confirm with robustness checks before using it as central evidence.")
        else:
            result["evidence_strength"] = "moderate_or_stronger_fit"
            result["statistical_interpretation"] = f"R2={observed:.3g} provides at least moderate explanatory support under the current heuristic."
            if threshold is not None and threshold > 0.05 and observed < threshold:
                issues.append(f"Primary metric r2={observed:.3g} is below the configured goodness-of-fit threshold {threshold:.3g}.")
        return result

    if semantics == "effect_size_correlation":
        minimum_abs_r = threshold if threshold is not None else 0.30
        abs_r = abs(observed)
        if abs_r < 0.10:
            result["evidence_strength"] = "negligible_effect"
            result["statistical_interpretation"] = f"|r|={abs_r:.3g} indicates a negligible association."
            issues.append(f"Primary correlation metric {metric}={observed:.3g} is negligible.")
        elif abs_r < minimum_abs_r:
            result["evidence_strength"] = "weak_effect"
            result["statistical_interpretation"] = f"|r|={abs_r:.3g} indicates a weak association below the configured effect-size threshold {minimum_abs_r:.3g}."
            issues.append(f"Primary correlation metric {metric}={observed:.3g} is below the effect-size threshold {minimum_abs_r:.3g}.")
        else:
            result["evidence_strength"] = "moderate_or_stronger_effect"
            result["statistical_interpretation"] = f"|r|={abs_r:.3g} meets the configured effect-size threshold {minimum_abs_r:.3g}."
        return result

    if semantics == "error_metric":
        if threshold is not None and observed > threshold:
            issues.append(f"Primary error metric {metric}={observed:.3g} is above threshold {threshold:.3g}.")
            result["evidence_strength"] = "error_too_high"
        else:
            result["evidence_strength"] = "error_within_threshold" if threshold is not None else "error_metric_without_threshold"
        result["statistical_interpretation"] = "Lower values indicate better fit for this error metric."
        return result

    if threshold is not None and observed < threshold:
        issues.append(f"Primary metric {metric}={observed:.3g} is below threshold {threshold:.3g}.")
        result["evidence_strength"] = "below_threshold"
    else:
        result["evidence_strength"] = "meets_threshold" if threshold is not None else "no_threshold_configured"
    result["statistical_interpretation"] = "Higher values are treated as better for this model-performance metric."
    return result


def _project_relative_path(project_path: Path, relative: str) -> Path:
    candidate = (project_path / relative).resolve()
    try:
        candidate.relative_to(project_path.resolve())
    except ValueError as exc:
        raise ResultValidityError(f"Result path escapes project directory: {relative}") from exc
    return candidate


def _missing_outputs(project_path: Path, run_manifest: dict[str, Any]) -> list[str]:
    missing = []
    for relative in run_manifest.get("output_files") or []:
        if not _project_relative_path(project_path, str(relative)).exists():
            missing.append(str(relative))
    return missing


def _diagnose_failure(
    *,
    data_feasibility: dict[str, Any],
    run_manifest: dict[str, Any],
    metric_value: float | None,
    minimum_value: float | None,
    metric_semantics: str,
    evidence_strength: str,
    missing_outputs: list[str],
) -> tuple[list[str], list[str]]:
    causes: list[str] = []
    actions: list[str] = []
    data_decision = data_feasibility.get("decision")
    if data_decision not in {"pass", "conditional_pass"}:
        causes.append("data")
        actions.append("Return to data feasibility: add data, revise variables, or lower the research objective.")
    if data_decision == "conditional_pass":
        causes.append("data")
        actions.append("Treat conclusions as exploratory unless stronger data or external validation is added.")
    if run_manifest.get("status") != "success" or missing_outputs:
        causes.append("method")
        actions.append("Return to method verification: fix code execution and regenerate declared outputs.")
    if metric_semantics == "goodness_of_fit" and evidence_strength in {"very_weak_fit", "weak_fit"}:
        causes.append("data")
        causes.append("method")
        actions.append("Return to data quality control: inspect outliers, units, value ranges, proxy-variable validity, aggregation choices, and subgroup structure before accepting the weak fitted relationship.")
        actions.append("Return to method planning: test robust regression, nonlinear terms, stratified models, or domain-specific feature construction before rewriting Results.")
    elif metric_semantics == "effect_size_correlation" and evidence_strength in {"negligible_effect", "weak_effect"}:
        causes.append("data")
        causes.append("method")
        actions.append("Audit data quality and variable pairing because weak correlations can reflect outliers, scale mismatch, missing covariates, or unsuitable proxy variables.")
    elif metric_semantics == "statistical_significance" and evidence_strength == "not_statistically_significant":
        causes.append("method")
        actions.append("Do not treat the tested association as statistically significant; revise the hypothesis test, sample definition, covariates, or claim strength.")
    elif minimum_value is not None and metric_value is not None and metric_value < minimum_value:
        if "data" not in causes and data_decision == "pass":
            causes.append("method")
        actions.append("Inspect model design, feature construction, validation split, and class imbalance before writing Results.")
    if metric_value is None:
        causes.append("method")
        actions.append("Add a metric,value CSV output or set explicit validity criteria for non-tabular results.")
    if not causes:
        causes.append("research_plan")
        actions.append("Revise the expected claim strength or define a concrete result validity threshold.")
    return sorted(set(causes)), actions


def _render_md(report: dict[str, Any]) -> str:
    lines = [
        "# Result Validity Report",
        "",
        f"Decision: {report['decision']}",
        "",
        f"Primary metric: {report.get('primary_metric')}",
        "",
        f"Metric semantics: {report.get('metric_semantics')}",
        "",
        f"Observed value: {report.get('observed_value')}",
        "",
        f"Minimum acceptable value: {report.get('minimum_value')}",
        "",
        f"Evidence strength: {report.get('evidence_strength')}",
        "",
        f"Statistical interpretation: {report.get('statistical_interpretation')}",
        "",
        "## Diagnosis",
        "",
    ]
    for cause in report.get("failure_causes") or ["None."]:
        lines.append(f"- {cause}")
    lines.extend(["", "## Recommended Backtracking", ""])
    for action in report.get("recommended_actions") or ["Proceed to Results writing."]:
        lines.append(f"- {action}")
    lines.append("")
    return "\n".join(lines)


def _set_result_validity_manifest(project_path: Path) -> None:
    manifest_path = project_path / "result_validity" / "stage_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["input_files"] = RESULT_VALIDITY_INPUTS
    manifest["output_files"] = RESULT_VALIDITY_OUTPUTS
    _write_json(manifest_path, manifest)


def assess_result_validity(
    project: str | Path,
    *,
    primary_metric: str | None = None,
    minimum_value: float | None = None,
) -> dict[str, Any]:
    """Assess whether observed method outputs support the expected result claim."""
    state = load_project(project)
    run_manifest = _read_json(state.path / "methods" / "run_manifest.yaml")
    requirements = _read_json(state.path / "methods" / "method_requirements.json")
    data_feasibility = _read_json(state.path / "data" / "data_feasibility_report.json")
    metric = (primary_metric or requirements.get("primary_metric") or "f1").strip().lower()
    threshold = minimum_value if minimum_value is not None else requirements.get("minimum_primary_metric")
    threshold_float = _default_threshold(metric, threshold)
    metrics = run_manifest.get("metrics") or {}
    observed = _to_float(metrics.get(metric))
    missing_outputs = _missing_outputs(state.path, run_manifest)
    metric_interpretation = _interpret_metric(metric, observed, threshold_float)
    issues = []
    if run_manifest.get("status") != "success":
        issues.append("Method run manifest is not successful.")
    if missing_outputs:
        issues.append("Declared method outputs are missing: " + ", ".join(missing_outputs))
    review_task_coverage_issues = list(run_manifest.get("review_task_coverage_issues") or [])
    if review_task_coverage_issues:
        issues.append("Review task coverage failed: " + "; ".join(str(item) for item in review_task_coverage_issues))
    issues.extend(metric_interpretation["metric_issues"])

    evidence_strength = str(metric_interpretation["evidence_strength"])
    if not issues and threshold_float is not None:
        decision = "pass"
    elif not issues and evidence_strength in {"moderate_or_stronger_fit", "moderate_or_stronger_effect", "error_metric_without_threshold"}:
        decision = "conditional_pass"
        issues.append("No explicit minimum result threshold was configured; result validity is conditional.")
    elif issues and evidence_strength in {"weak_fit", "weak_effect"} and run_manifest.get("status") == "success" and not missing_outputs:
        decision = "conditional_pass"
    elif not issues:
        decision = "conditional_pass"
        issues.append("No explicit minimum result threshold was configured; result validity is conditional.")
    else:
        decision = "revise_required"

    causes, actions = _diagnose_failure(
        data_feasibility=data_feasibility,
        run_manifest=run_manifest,
        metric_value=observed,
        minimum_value=threshold_float,
        metric_semantics=str(metric_interpretation["metric_semantics"]),
        evidence_strength=evidence_strength,
        missing_outputs=missing_outputs,
    ) if decision == "revise_required" else ([], ["Proceed to Results writing while keeping claim strength aligned with the validity decision."])

    report = {
        "project_id": state.metadata.get("project_id"),
        "decision": decision,
        "primary_metric": metric,
        "metric_semantics": metric_interpretation["metric_semantics"],
        "observed_value": observed,
        "minimum_value": threshold_float,
        "evidence_strength": evidence_strength,
        "statistical_interpretation": metric_interpretation["statistical_interpretation"],
        "issues": issues,
        "failure_causes": causes,
        "recommended_actions": actions,
        "missing_outputs": missing_outputs,
        "review_task_coverage_issues": review_task_coverage_issues,
        "data_feasibility_decision": data_feasibility.get("decision"),
        "stale_if_changed": ["results", "discussion", "latex", "quality_checks"],
    }
    results_dir = state.path / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    _write_json(results_dir / "result_validity_report.json", report)
    (results_dir / "result_validity_report.md").write_text(_render_md(report), encoding="utf-8")
    update_stage_status(state.path, "result_validity", "draft" if decision in {"pass", "conditional_pass"} else "failed")
    _set_result_validity_manifest(state.path)
    return {
        "status": "written",
        "project_path": str(state.path),
        "decision": decision,
        "failure_causes": causes,
        "result_validity_report": str(results_dir / "result_validity_report.json"),
        "outputs": RESULT_VALIDITY_OUTPUTS,
    }


def validate_result_validity_for_results(project_path: Path) -> dict[str, Any]:
    """Return validity report if Results may proceed; otherwise raise ResultValidityError."""
    report = _read_json(project_path / "results" / "result_validity_report.json")
    decision = report.get("decision")
    if decision not in {"pass", "conditional_pass"}:
        raise ResultValidityError(
            "Results writing requires result validity decision pass or conditional_pass. Current decision: "
            + str(decision)
        )
    return report
