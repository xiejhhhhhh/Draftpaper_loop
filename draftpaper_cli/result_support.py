# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any

from .html_utils import write_html_report
from .passport import utc_now
from .project_scaffold import _write_json
from .project_state import load_project, update_stage_status


RESULT_SUPPORT_JSON = "results/result_support_checkpoint.json"
RESULT_SUPPORT_MD = "results/result_support_checkpoint.md"
RESULT_SUPPORT_HTML = "results/result_support_checkpoint.html"

RESULT_SUPPORT_INPUTS = [
    "research_plan/research_plan.md",
    "research_plan/claim_contract.json",
    "research_plan/figure_storyboard.json",
    "results/figure_plan.json",
    "results/result_validity_report.json",
    "results/resolved_result_evidence.json",
    "results/result_manifest.yaml",
    "methods/run_manifest.yaml",
]

RESULT_SUPPORT_OUTPUTS = [RESULT_SUPPORT_JSON, RESULT_SUPPORT_MD, RESULT_SUPPORT_HTML]


class ResultSupportError(RuntimeError):
    """Raised when scientific result support cannot be assessed."""


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return default


def _read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8-sig", errors="ignore")


def _to_float(value: Any) -> float | None:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _normalise_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def _metric_rows_from_csv(path: Path) -> dict[str, float]:
    metrics: dict[str, float] = {}
    if not path.exists():
        return metrics
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                lowered = {str(k or "").strip().lower(): v for k, v in row.items()}
                metric = str(lowered.get("metric") or lowered.get("name") or lowered.get("key") or "").strip()
                value = _to_float(lowered.get("value") or lowered.get("score") or lowered.get("metric_value"))
                if metric and value is not None:
                    metrics[_normalise_key(metric)] = value
    except OSError:
        return metrics
    return metrics


def _collect_metrics(project_path: Path, run_manifest: dict[str, Any], result_manifest: dict[str, Any]) -> dict[str, float]:
    metrics: dict[str, float] = {}
    for key, value in (run_manifest.get("metrics") or {}).items():
        numeric = _to_float(value)
        if numeric is not None:
            metrics[_normalise_key(str(key))] = numeric
    for table in result_manifest.get("tables") or []:
        if not isinstance(table, dict):
            continue
        relative = str(table.get("path") or "")
        if relative.lower().endswith(".csv"):
            metrics.update(_metric_rows_from_csv(project_path / relative))
    for figure in result_manifest.get("figures") or []:
        if not isinstance(figure, dict):
            continue
        for key, value in (figure.get("metrics") or {}).items():
            numeric = _to_float(value)
            if numeric is not None:
                metrics.setdefault(_normalise_key(str(key)), numeric)
    resolved = _read_json(project_path / "results" / "resolved_result_evidence.json", {})
    for item in resolved.get("metrics") or [] if isinstance(resolved, dict) else []:
        if not isinstance(item, dict):
            continue
        numeric = _to_float(item.get("value"))
        metric_name = _normalise_key(str(item.get("metric_name") or ""))
        model_id = _normalise_key(str(item.get("model") or item.get("model_id") or ""))
        if numeric is None or not metric_name:
            continue
        key = f"{model_id}_{metric_name}" if model_id else metric_name
        metrics[key] = numeric
    primary = resolved.get("primary_metric") if isinstance(resolved, dict) else {}
    if isinstance(primary, dict):
        numeric = _to_float(primary.get("value"))
        metric_name = _normalise_key(str(primary.get("metric_name") or ""))
        if numeric is not None and metric_name:
            metrics[f"primary_{metric_name}"] = numeric
    return metrics


def _claim_texts_from_contract(contract: dict[str, Any]) -> list[dict[str, Any]]:
    claims: list[dict[str, Any]] = []
    for index, claim in enumerate(contract.get("claims") or [], start=1):
        if not isinstance(claim, dict):
            continue
        text = str(claim.get("active_claim") or claim.get("claim_text") or claim.get("planned_claim") or "").strip()
        if not text:
            continue
        claims.append({
            "claim_id": str(claim.get("claim_id") or f"claim_{index}"),
            "planned_claim": text,
            "strength": str(claim.get("active_strength") or claim.get("strength") or "unspecified"),
            "claim_boundary": str(claim.get("claim_boundary") or ""),
            "source": "research_plan/claim_contract.json",
        })
    return claims


def _claim_texts_from_storyboard(storyboard: dict[str, Any]) -> list[dict[str, Any]]:
    claims: list[dict[str, Any]] = []
    for index, figure in enumerate(storyboard.get("figures") or [], start=1):
        if not isinstance(figure, dict):
            continue
        text = str(
            figure.get("expected_finding")
            or figure.get("result_claim_template")
            or figure.get("scientific_question")
            or ""
        ).strip()
        if not text:
            continue
        claims.append({
            "claim_id": str(figure.get("figure_id") or f"storyboard_claim_{index}"),
            "planned_claim": text,
            "strength": str(figure.get("claim_strength") or "figure_level"),
            "source": "research_plan/figure_storyboard.json",
        })
    return claims


def _claim_texts_from_result_manifest(result_manifest: dict[str, Any]) -> list[dict[str, Any]]:
    claims: list[dict[str, Any]] = []
    for index, figure in enumerate(result_manifest.get("figures") or [], start=1):
        if not isinstance(figure, dict):
            continue
        text = str(figure.get("expected_finding") or figure.get("result_claim") or figure.get("claim_boundary") or "").strip()
        if not text:
            continue
        claims.append({
            "claim_id": str(figure.get("storyboard_id") or figure.get("id") or f"result_claim_{index}"),
            "planned_claim": text,
            "strength": "result_manifest",
            "source": "results/result_manifest.yaml",
        })
    return claims


def _planned_claims(project_path: Path, result_manifest: dict[str, Any]) -> list[dict[str, Any]]:
    contract_claims = _claim_texts_from_contract(_read_json(project_path / "research_plan" / "claim_contract.json", {}))
    if contract_claims:
        return contract_claims
    storyboard_claims = _claim_texts_from_storyboard(_read_json(project_path / "research_plan" / "figure_storyboard.json", {}))
    if storyboard_claims:
        return storyboard_claims
    return _claim_texts_from_result_manifest(result_manifest)


_STRONG_CLAIM_RE = re.compile(
    r"\b(outperform|outperforms|improv(?:e|es|ed|ement)|superior|better than|higher than|substantial|robust|significant|significantly)\b",
    re.I,
)
_LIMITED_CLAIM_RE = re.compile(r"\b(exploratory|limited|weak|does not|did not|no clear|requires further|boundary)\b", re.I)


def _metric_groups(metrics: dict[str, float]) -> tuple[dict[str, float], dict[str, float]]:
    baseline: dict[str, float] = {}
    proposed: dict[str, float] = {}
    baseline_markers = ("baseline", "control", "reference", "traditional", "rf", "random_forest", "logistic")
    proposed_markers = ("proposed", "main", "transformer", "model", "ours", "candidate", "time_aware")
    for key, value in metrics.items():
        if any(marker in key for marker in baseline_markers):
            baseline[key] = value
        if any(marker in key for marker in proposed_markers):
            proposed[key] = value
    return baseline, proposed


def _best_metric_value(metrics: dict[str, float], suffixes: tuple[str, ...]) -> float | None:
    values = [value for key, value in metrics.items() if key.endswith(suffixes) or key in suffixes]
    return max(values) if values else None


def _compare_planned_improvement(metrics: dict[str, float]) -> dict[str, Any] | None:
    baseline, proposed = _metric_groups(metrics)
    if not baseline or not proposed:
        return None
    suffixes = ("f1", "f1_macro", "macro_f1", "accuracy", "auc", "roc_auc", "r2")
    baseline_best = _best_metric_value(baseline, suffixes)
    proposed_best = _best_metric_value(proposed, suffixes)
    if baseline_best is None or proposed_best is None:
        return None
    return {
        "baseline_best": baseline_best,
        "proposed_best": proposed_best,
        "supports_improvement": proposed_best > baseline_best,
    }


def _assess_claim(claim: dict[str, Any], *, metrics: dict[str, float], validity: dict[str, Any]) -> dict[str, Any]:
    planned = str(claim.get("planned_claim") or "")
    lower_decision = str(validity.get("decision") or "").lower()
    evidence_strength = str(validity.get("evidence_strength") or "").lower()
    issue = ""
    failure_type = ""
    support_status = "supported"

    if lower_decision == "revise_required":
        support_status = "not_supported"
        failure_type = "technical_or_metric_validity_failed"
        issue = "Result validity is revise_required, so the planned claim cannot be used for manuscript writing yet."
    elif _STRONG_CLAIM_RE.search(planned) and not _LIMITED_CLAIM_RE.search(planned):
        comparison = _compare_planned_improvement(metrics)
        if comparison and not comparison["supports_improvement"]:
            support_status = "not_supported"
            failure_type = "claim_overreach"
            issue = (
                "The planned improvement claim is contradicted by the parsed comparison metrics: "
                f"proposed={comparison['proposed_best']:.4g}, baseline={comparison['baseline_best']:.4g}."
            )
        elif evidence_strength in {"weak_fit", "very_weak_fit", "weak_effect", "negligible_effect", "below_threshold"}:
            support_status = "partially_supported"
            failure_type = "claim_strength_too_high"
            issue = f"The planned claim uses strong language, but result validity reports {evidence_strength}."

    return {
        **claim,
        "support_status": support_status,
        "failure_type": failure_type,
        "diagnosis": issue,
    }


def _decision(claim_assessments: list[dict[str, Any]], validity: dict[str, Any]) -> tuple[str, str, bool]:
    validity_decision = str(validity.get("decision") or "").lower()
    if validity_decision == "revise_required":
        return "route_decision_required", "failed", True
    statuses = {str(item.get("support_status") or "") for item in claim_assessments}
    if "not_supported" in statuses:
        return "route_decision_required", "failed", True
    if "partially_supported" in statuses:
        return "route_decision_required", "partial", True
    return "pass", "supported", False


def _route_options(project_path: Path) -> list[dict[str, str]]:
    quoted = f'"{project_path}"' if " " in str(project_path) else str(project_path)
    return [
        {
            "route": "downgrade_research_claim",
            "label": "Evidence-aligned claim downgrade",
            "description": "Keep the current result figures and metrics, then lower the research-plan claim strength before manuscript writing.",
            "current_executable_command": f"python -m draftpaper_cli.cli apply-result-downgrade --project {quoted}",
            "stale_policy": "stale manuscript and claim boundary only; keep data, methods, figures, metrics, and current result artifacts frozen",
        },
        {
            "route": "supplement_data_and_method",
            "label": "Supplement data/method evidence",
            "description": "Keep the stronger research-plan claim, diagnose missing data or method support, and regenerate core result figures.",
            "current_executable_command": f"python -m draftpaper_cli.cli prepare-result-rescue --project {quoted}",
            "stale_policy": "stale data, method, figure, evidence, and manuscript chain before rerunning results",
        },
    ]


def _render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Result Support Checkpoint",
        "",
        f"Decision: {report.get('decision')}",
        f"Support level: {report.get('support_level')}",
        f"Requires user decision: {'yes' if report.get('requires_user_decision') else 'no'}",
        "",
        "## Claim Assessments",
        "",
    ]
    for item in report.get("claim_assessments") or []:
        lines.append(f"- {item.get('claim_id')}: {item.get('support_status')}")
        lines.append(f"  - Planned claim: {item.get('planned_claim')}")
        if item.get("diagnosis"):
            lines.append(f"  - Diagnosis: {item.get('diagnosis')}")
    lines.extend(["", "## Recommended Routes", ""])
    if report.get("requires_user_decision"):
        for route in report.get("route_options") or []:
            lines.append(f"- {route.get('route')}: {route.get('description')}")
            lines.append(f"  - Command now: `{route.get('current_executable_command')}`")
    else:
        lines.append("- Proceed to core evidence review and manuscript writing.")
    lines.append("")
    return "\n".join(lines)


def _set_manifest(project_path: Path) -> None:
    manifest_path = project_path / "result_support" / "stage_manifest.json"
    manifest = _read_json(manifest_path, {})
    if not isinstance(manifest, dict):
        return
    manifest["input_files"] = RESULT_SUPPORT_INPUTS
    manifest["output_files"] = RESULT_SUPPORT_OUTPUTS
    _write_json(manifest_path, manifest)


def assess_result_support(project: str | Path) -> dict[str, Any]:
    """Assess whether current figures/metrics can support the planned research claims."""
    state = load_project(project)
    validity = _read_json(state.path / "results" / "result_validity_report.json", {})
    if not isinstance(validity, dict) or not validity:
        raise ResultSupportError("Run assess-result-validity before assess-result-support.")
    results_stage = (state.metadata.get("stages") or {}).get("results") or {}
    result_manifest = (
        _read_json(state.path / "results" / "result_manifest.yaml", {})
        if results_stage.get("status") in {"draft", "approved", "completed"} and not results_stage.get("stale")
        else {}
    )
    run_manifest = _read_json(state.path / "methods" / "run_manifest.yaml", {})
    claims = _planned_claims(state.path, result_manifest if isinstance(result_manifest, dict) else {})
    metrics = _collect_metrics(state.path, run_manifest if isinstance(run_manifest, dict) else {}, result_manifest if isinstance(result_manifest, dict) else {})
    claim_assessments = [_assess_claim(claim, metrics=metrics, validity=validity) for claim in claims]
    if not claim_assessments:
        claim_assessments.append({
            "claim_id": "claim_contract_missing",
            "planned_claim": "No structured claim contract or figure storyboard claim was found.",
            "source": "inferred",
            "support_status": "partially_supported",
            "failure_type": "missing_claim_contract",
            "diagnosis": "Draftpaper_loop cannot verify scientific support without a planned claim or storyboard finding.",
        })
    decision, support_level, requires_user_decision = _decision(claim_assessments, validity)
    failed_claims = [item for item in claim_assessments if item.get("support_status") in {"not_supported", "partially_supported"}]
    report = {
        "status": "written",
        "schema_version": "dpl.result_support_checkpoint.v2",
        "project_id": state.metadata.get("project_id"),
        "generated_at": utc_now(),
        "decision": decision,
        "support_level": support_level,
        "requires_user_decision": requires_user_decision,
        "result_validity_decision": validity.get("decision"),
        "evidence_strength": validity.get("evidence_strength"),
        "metrics": metrics,
        "claim_assessments": claim_assessments,
        "failed_claims": failed_claims,
        "route_options": _route_options(state.path) if requires_user_decision else [],
        "manuscript_may_proceed": decision == "pass",
        "stale_if_downgrade_route": ["results", "introduction", "data_writing", "methods_writing", "discussion", "latex", "quality_checks"],
        "stale_if_supplement_route": ["data", "method_plan", "figure_plan", "figure_contracts", "code", "methods", "result_validity", "result_support", "core_evidence", "results", "introduction", "data_writing", "methods_writing", "discussion", "latex", "quality_checks"],
    }
    results_dir = state.path / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    _write_json(results_dir / "result_support_checkpoint.json", report)
    markdown = _render_markdown(report)
    (results_dir / "result_support_checkpoint.md").write_text(markdown, encoding="utf-8")
    write_html_report(results_dir / "result_support_checkpoint.html", markdown, title="Result Support Checkpoint")
    update_stage_status(state.path, "result_support", "draft" if decision == "pass" else "failed")
    _set_manifest(state.path)
    return {
        "status": "written",
        "project_path": str(state.path),
        "decision": decision,
        "support_level": support_level,
        "requires_user_decision": requires_user_decision,
        "result_support_checkpoint": str(results_dir / "result_support_checkpoint.json"),
        "route_options": report["route_options"],
    }


def validate_result_support_for_manuscript(project_path: Path) -> dict[str, Any]:
    report = _read_json(project_path / RESULT_SUPPORT_JSON, {})
    if not report:
        return {}
    if report.get("decision") != "pass":
        raise ResultSupportError(
            "Manuscript writing requires result support decision pass. Current decision: "
            + str(report.get("decision"))
        )
    return report
