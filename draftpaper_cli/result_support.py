# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import csv
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from .html_utils import write_html_report
from .passport import utc_now
from .project_scaffold import _write_json
from .project_state import load_project, update_project_state
from .result_support_signals import (
    RESULT_SUPPORT_INPUTS,
    build_result_support_input_bindings,
    collect_result_support_signals,
)
from .state_kernel import file_lock


RESULT_SUPPORT_JSON = "results/result_support_checkpoint.json"
RESULT_SUPPORT_MD = "results/result_support_checkpoint.md"
RESULT_SUPPORT_HTML = "results/result_support_checkpoint.html"
RESULT_SUPPORT_ROUTE_LOCK = "results/.result_support_route"

RESULT_SUPPORT_OUTPUTS = [RESULT_SUPPORT_JSON, RESULT_SUPPORT_MD, RESULT_SUPPORT_HTML]


class ResultSupportError(RuntimeError):
    """Raised when scientific result support cannot be assessed."""


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        try:
            value = yaml.safe_load(path.read_text(encoding="utf-8-sig"))
        except (OSError, yaml.YAMLError):
            return default
        return value if value is not None else default


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


def _claim_scientific_context(payload: dict[str, Any]) -> dict[str, str]:
    contexts = [payload]
    for key in ("evidence_context", "claim_context", "context", "active_context"):
        context = payload.get(key)
        if isinstance(context, dict):
            contexts.insert(0, context)

    def declared(*keys: str) -> str:
        for context in contexts:
            for key in keys:
                value = context.get(key)
                if value not in {None, ""}:
                    return str(value).strip()
        return ""

    return {
        "run_id": declared("run_id", "execution_id"),
        "cohort": declared("cohort", "cohort_id"),
        "split": declared("split", "data_split", "evaluation_split"),
        "sample_unit": declared("sample_unit", "unit_of_analysis"),
    }


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
            "metric_dimension": str(claim.get("metric_dimension") or ""),
            "scientific_context": _claim_scientific_context(claim),
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
            "scientific_context": _claim_scientific_context(figure),
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
            "scientific_context": _claim_scientific_context(figure),
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


_DIRECTION_ALIASES = {
    "higher": "higher_is_better",
    "higher_is_better": "higher_is_better",
    "increase": "higher_is_better",
    "increasing": "higher_is_better",
    "max": "higher_is_better",
    "maximize": "higher_is_better",
    "maximise": "higher_is_better",
    "lower": "lower_is_better",
    "lower_is_better": "lower_is_better",
    "decrease": "lower_is_better",
    "decreasing": "lower_is_better",
    "min": "lower_is_better",
    "minimize": "lower_is_better",
    "minimise": "lower_is_better",
}
_LOWER_IS_BETTER_METRICS = {
    "rmse", "root_mean_squared_error", "mae", "mean_absolute_error",
    "mse", "mean_squared_error", "loss", "error", "deviance",
    "lower_is_better",
}
_HIGHER_IS_BETTER_METRICS = {
    "accuracy", "f1", "f1_score", "auc", "roc_auc", "precision",
    "recall", "r2", "r_squared", "higher_is_better",
}


def _normalise_optimization_direction(value: Any) -> str:
    return _DIRECTION_ALIASES.get(_normalise_key(str(value or "")), "")


def _registry_optimization_direction(metric_dimension: str) -> str:
    dimension = _normalise_key(metric_dimension)

    def matches(registered: set[str]) -> bool:
        return any(
            dimension == name
            or dimension.startswith(name + "_")
            or dimension.endswith("_" + name)
            for name in registered
        )

    lower = matches(_LOWER_IS_BETTER_METRICS)
    higher = matches(_HIGHER_IS_BETTER_METRICS)
    if lower == higher:
        return ""
    return "lower_is_better" if lower else "higher_is_better"


def _comparison_optimization_direction(dimension: str, records: list[dict[str, Any]]) -> str:
    declarations = [
        record.get("optimization_direction")
        for record in records
        if record.get("optimization_direction") not in {None, ""}
    ]
    if declarations:
        directions = {_normalise_optimization_direction(value) for value in declarations}
        return directions.pop() if len(directions) == 1 and "" not in directions else ""
    return _registry_optimization_direction(dimension)


def _metric_contract_key(metric_name: Any, model: Any = "") -> str:
    metric = _normalise_key(str(metric_name or ""))
    model_key = _normalise_key(str(model or ""))
    return f"{model_key}_{metric}" if model_key and metric else metric


def _attach_explicit_optimization_directions(
    project_path: Path,
    metric_records: list[dict[str, Any]],
) -> None:
    """Restore explicit direction fields retained by source metric contracts."""
    contracts: dict[tuple[str, str, float], set[str]] = {}

    def add(source: str, metric_name: Any, model: Any, value: Any, direction: Any) -> None:
        numeric = _to_float(value)
        if numeric is None or direction in {None, ""}:
            return
        identity = (source, _metric_contract_key(metric_name, model), numeric)
        contracts.setdefault(identity, set()).add(str(direction))

    resolved_source = "results/resolved_result_evidence.json"
    resolved = _read_json(project_path / resolved_source, {})
    if isinstance(resolved, dict):
        for item in resolved.get("metrics") or []:
            if isinstance(item, dict):
                add(
                    resolved_source,
                    item.get("metric_name") or item.get("name"),
                    item.get("model") or item.get("model_id"),
                    item.get("value"),
                    item.get("optimization_direction"),
                )
        primary = resolved.get("primary_metric")
        if isinstance(primary, dict):
            add(
                resolved_source,
                primary.get("metric_name") or primary.get("name"),
                primary.get("model") or primary.get("model_id") or "primary",
                primary.get("value"),
                primary.get("optimization_direction"),
            )

    manifest_source = "methods/run_manifest.yaml"
    run_manifest = _read_json(project_path / manifest_source, {})
    if isinstance(run_manifest, dict):
        for metric_name, raw in (run_manifest.get("metrics") or {}).items():
            if isinstance(raw, dict):
                add(
                    manifest_source,
                    metric_name,
                    raw.get("model") or raw.get("model_id"),
                    raw.get("value"),
                    raw.get("optimization_direction"),
                )
        table_paths: list[str] = []
        for field in ("tables_generated", "output_files", "declared_outputs"):
            values = run_manifest.get(field) or []
            values = [values] if isinstance(values, str) else values
            for value in values:
                relative = str(value or "").strip().replace("\\", "/").lstrip("./")
                if relative.lower().endswith(".csv") and relative not in table_paths:
                    table_paths.append(relative)
        for relative in table_paths:
            table_path = (project_path / relative).resolve()
            try:
                table_path.relative_to(project_path.resolve())
                with table_path.open("r", encoding="utf-8-sig", newline="") as handle:
                    rows = list(csv.DictReader(handle))
            except (OSError, ValueError):
                continue
            for row in rows:
                lowered = {_normalise_key(str(key)): value for key, value in row.items() if key}
                add(
                    relative,
                    lowered.get("metric") or lowered.get("metric_name") or lowered.get("name") or lowered.get("key"),
                    lowered.get("model") or lowered.get("model_id"),
                    lowered.get("value") or lowered.get("score") or lowered.get("metric_value"),
                    lowered.get("optimization_direction"),
                )

    for record in metric_records:
        numeric = _to_float(record.get("value"))
        identity = (str(record.get("source") or ""), str(record.get("key") or ""), numeric)
        directions = contracts.get(identity, set()) if numeric is not None else set()
        if len(directions) == 1:
            record["optimization_direction"] = next(iter(directions))


def _compare_planned_improvement(
    metric_records: list[dict[str, Any]],
    *,
    required_dimension: str = "",
    required_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    dimension_filter = _normalise_key(required_dimension) if required_dimension else ""
    context_filter = {
        field: str((required_context or {}).get(field) or "").strip()
        for field in ("run_id", "cohort", "split", "sample_unit")
    }
    grouped: dict[tuple[str, str, str, str, str], dict[str, list[dict[str, Any]]]] = {}
    for record in metric_records:
        if not isinstance(record, dict):
            continue
        dimension = _normalise_key(str(record.get("metric_dimension") or ""))
        role = str(record.get("comparison_role") or "")
        if not dimension or role not in {"baseline", "proposed"}:
            continue
        if dimension_filter and dimension != dimension_filter:
            continue
        context = record.get("context") if isinstance(record.get("context"), dict) else {}
        run_id = str(context.get("run_id") or "").strip()
        cohort = str(context.get("cohort") or "").strip()
        split = str(context.get("split") or "").strip()
        sample_unit = str(context.get("sample_unit") or "").strip()
        if not run_id or not any((cohort, split, sample_unit)):
            continue
        observed_context = {
            "run_id": run_id,
            "cohort": cohort,
            "split": split,
            "sample_unit": sample_unit,
        }
        if any(
            expected and observed_context[field] != expected
            for field, expected in context_filter.items()
        ):
            continue
        key = (
            dimension,
            run_id,
            cohort,
            split,
            sample_unit,
        )
        grouped.setdefault(key, {"baseline": [], "proposed": []})[role].append(record)
    compatible = sorted(key for key, values in grouped.items() if values["baseline"] and values["proposed"])
    if not compatible:
        return {"status": "missing_compatible_pair", "compatible_dimensions": []}
    dimension, run_id, cohort, split, sample_unit = compatible[0]
    records = grouped[compatible[0]]
    direction = _comparison_optimization_direction(
        dimension,
        [*records["baseline"], *records["proposed"]],
    )
    if not direction:
        return {
            "status": "unknown_optimization_direction",
            "metric_dimension": dimension,
            "optimization_direction": None,
            "supports_improvement": False,
            "context": {
                "run_id": run_id,
                "cohort": cohort,
                "split": split,
                "sample_unit": sample_unit,
            },
        }
    select_best = min if direction == "lower_is_better" else max
    baseline_best = select_best(float(record["value"]) for record in records["baseline"])
    proposed_best = select_best(float(record["value"]) for record in records["proposed"])
    return {
        "status": "compared",
        "metric_dimension": dimension,
        "optimization_direction": direction,
        "baseline_best": baseline_best,
        "proposed_best": proposed_best,
        "supports_improvement": (
            proposed_best < baseline_best
            if direction == "lower_is_better"
            else proposed_best > baseline_best
        ),
        "context": {
            "run_id": run_id,
            "cohort": cohort,
            "split": split,
            "sample_unit": sample_unit,
        },
    }


def _assess_claim(
    claim: dict[str, Any],
    *,
    metric_records: list[dict[str, Any]],
    validity: dict[str, Any],
) -> dict[str, Any]:
    planned = str(claim.get("planned_claim") or "")
    lower_decision = str(validity.get("decision") or "").lower()
    evidence_strength = str(validity.get("evidence_strength") or "").lower()
    issue = ""
    failure_type = ""
    support_status = "supported"
    comparison: dict[str, Any] | None = None

    if lower_decision == "revise_required":
        support_status = "not_supported"
        failure_type = "technical_or_metric_validity_failed"
        issue = "Result validity is revise_required, so the planned claim cannot be used for manuscript writing yet."
    elif _STRONG_CLAIM_RE.search(planned) and not _LIMITED_CLAIM_RE.search(planned):
        comparison = _compare_planned_improvement(
            metric_records,
            required_dimension=str(claim.get("metric_dimension") or ""),
            required_context=(
                claim.get("scientific_context")
                if isinstance(claim.get("scientific_context"), dict)
                else {}
            ),
        )
        if comparison and comparison.get("status") == "unknown_optimization_direction":
            support_status = "partially_supported"
            failure_type = "unknown_metric_optimization_direction"
            issue = (
                "The comparative claim has a compatible metric pair, but its optimization direction "
                "is neither explicitly contracted nor present in the deterministic metric registry."
            )
        elif not comparison or comparison.get("status") != "compared":
            support_status = "partially_supported"
            failure_type = "missing_compatible_comparison_evidence"
            issue = "The comparative claim lacks compatible baseline and proposed metrics for the same metric dimension."
        elif not comparison["supports_improvement"]:
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
        "comparison": comparison,
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


def result_support_checkpoint_sha256(report: dict[str, Any]) -> str:
    """Return the stable identity of a checkpoint before any route is selected."""
    payload = {
        "schema_version": report.get("schema_version"),
        "project_id": report.get("project_id"),
        "assessment_decision": report.get("assessment_decision", report.get("decision")),
        "assessment_support_level": report.get("assessment_support_level", report.get("support_level")),
        "result_validity_decision": report.get("result_validity_decision"),
        "evidence_strength": report.get("evidence_strength"),
        "metrics": report.get("metrics") or {},
        "metric_records": report.get("metric_records") or [],
        "metric_sources": report.get("metric_sources") or {},
        "claim_assessments": report.get("claim_assessments") or [],
        "failed_claims": report.get("failed_claims") or [],
        "input_bindings": report.get("input_bindings") or {},
        "signals": report.get("signals") or {},
        "skipped_tasks": report.get("skipped_tasks") or [],
        "warnings": report.get("warnings") or [],
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _quoted_project(project_path: Path) -> str:
    return f'"{project_path}"' if " " in str(project_path) else str(project_path)


def result_route_command(project_path: Path, route: str, checkpoint_hash: str) -> str:
    command = {
        "downgrade_research_claim": "apply-result-downgrade",
        "supplement_data_and_method": "prepare-result-rescue",
    }[route]
    return (
        f"python -m draftpaper_cli.cli {command} --project {_quoted_project(project_path)} "
        f"--checkpoint-hash {checkpoint_hash}"
    )


def result_route_preflight(
    project_path: Path,
    report: dict[str, Any],
    *,
    route: str,
    checkpoint_hash: str | None,
) -> dict[str, Any] | None:
    """Validate one hash-bound route and return a non-mutating terminal response."""
    computed_hash = result_support_checkpoint_sha256(report)
    stored_hash = str(report.get("checkpoint_sha256") or "")
    if stored_hash and stored_hash != computed_hash:
        raise ResultSupportError("Result Support checkpoint content does not match checkpoint_sha256; reassess Result Support.")
    current_hash = stored_hash or computed_hash
    command = result_route_command(project_path, route, current_hash)
    if not checkpoint_hash:
        return {
            "status": "checkpoint_hash_required",
            "project_path": str(project_path),
            "route": route,
            "checkpoint_sha256": current_hash,
            "current_executable_command": command,
        }
    if str(checkpoint_hash) != current_hash:
        raise ResultSupportError(
            f"Result route checkpoint hash mismatch: expected {current_hash}, received {checkpoint_hash}."
        )
    selected_route = str(report.get("selected_route") or "")
    if selected_route and selected_route != route:
        return {
            "status": "mixed_route_not_supported",
            "project_path": str(project_path),
            "selected_route": selected_route,
            "requested_route": route,
            "checkpoint_sha256": current_hash,
            "route_receipt": report.get("route_receipt"),
        }
    if selected_route == route and report.get("route_receipt"):
        return {
            "status": "already_applied",
            "project_path": str(project_path),
            "route": route,
            "selected_route": route,
            "checkpoint_sha256": current_hash,
            "route_receipt": report.get("route_receipt"),
        }
    recorded_bindings = report.get("input_bindings") or {}
    if isinstance(recorded_bindings, dict) and recorded_bindings:
        current_bindings = build_result_support_input_bindings(project_path)
        changed = sorted(
            relative
            for relative in set(recorded_bindings) | set(current_bindings)
            if current_bindings.get(relative) != recorded_bindings.get(relative)
        )
        if changed:
            raise ResultSupportError(
                "Result Support inputs changed after checkpoint creation: " + ", ".join(changed)
            )
    return None


def bind_result_route_receipt(report: dict[str, Any], *, route: str) -> dict[str, Any]:
    checkpoint_hash = str(report.get("checkpoint_sha256") or result_support_checkpoint_sha256(report))
    receipt = {
        "status": "applied",
        "route": route,
        "checkpoint_sha256": checkpoint_hash,
        "applied_at": utc_now(),
    }
    receipt["receipt_sha256"] = hashlib.sha256(
        json.dumps(receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    report["checkpoint_sha256"] = checkpoint_hash
    report["selected_route"] = route
    report["route_receipt"] = receipt
    return receipt


def _route_options(project_path: Path, checkpoint_hash: str) -> list[dict[str, str]]:
    return [
        {
            "route": "downgrade_research_claim",
            "label": "Evidence-aligned claim downgrade",
            "description": "Keep the current result figures and metrics, then lower the research-plan claim strength before manuscript writing.",
            "current_executable_command": result_route_command(project_path, "downgrade_research_claim", checkpoint_hash),
            "stale_policy": "stale manuscript and claim boundary only; keep data, methods, figures, metrics, and current result artifacts frozen",
        },
        {
            "route": "supplement_data_and_method",
            "label": "Supplement data/method evidence",
            "description": "Keep the stronger research-plan claim, diagnose missing data or method support, and regenerate core result figures.",
            "current_executable_command": result_route_command(project_path, "supplement_data_and_method", checkpoint_hash),
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


def _set_manifest(project_path: Path, input_files: list[str]) -> None:
    manifest_path = project_path / "result_support" / "stage_manifest.json"
    manifest = _read_json(manifest_path, {})
    if not isinstance(manifest, dict):
        return
    manifest["input_files"] = list(dict.fromkeys([*RESULT_SUPPORT_INPUTS, *input_files]))
    manifest["output_files"] = RESULT_SUPPORT_OUTPUTS
    _write_json(manifest_path, manifest)


def _timestamp(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _fresh_passing_review(
    project_path: Path,
    request: dict[str, Any],
    review: dict[str, Any],
    review_sha256: str,
    *,
    evidence_blocking: bool,
) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if str(review.get("decision") or "").lower() not in {"pass", "passed"} or evidence_blocking:
        reasons.append("review_not_passing")
    requested_review_sha256 = str(request.get("result_discipline_review_sha256") or "")
    if not requested_review_sha256:
        reasons.append("requested_review_hash_missing")
    if not review_sha256 or review_sha256 == requested_review_sha256:
        reasons.append("review_hash_not_fresh")
    requested_at = _timestamp(request.get("generated_at"))
    reviewed_at = _timestamp(review.get("generated_at"))
    if requested_at is None or reviewed_at is None or reviewed_at <= requested_at:
        reasons.append("review_not_generated_after_request")

    declared = review.get("evidence_bindings")
    declared = declared if isinstance(declared, dict) else {}
    binding_contract = (
        ("results/results.tex", "results_sha256"),
        ("results/promoted_evidence_snapshot.json", "promoted_evidence_snapshot_sha256"),
        ("results/result_manifest.yaml", "result_manifest_sha256"),
        ("results/figure_plugin_trace_report.json", "figure_plugin_trace_sha256"),
    )
    for relative, legacy_field in binding_contract:
        path = project_path / relative
        current_sha256 = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else ""
        expected_sha256 = str(declared.get(relative) or review.get(legacy_field) or "")
        if not current_sha256:
            reasons.append(f"current_binding_missing:{relative}")
        elif expected_sha256 != current_sha256:
            reasons.append(f"current_binding_mismatch:{relative}")
    snapshot = _read_json(project_path / "results" / "promoted_evidence_snapshot.json", {})
    current_snapshot_id = str(snapshot.get("snapshot_id") or "") if isinstance(snapshot, dict) else ""
    if not current_snapshot_id:
        reasons.append("current_snapshot_id_missing")
    elif str(review.get("evidence_snapshot_id") or "") != current_snapshot_id:
        reasons.append("current_snapshot_id_mismatch")
    return not reasons, reasons


def _assess_result_support_unlocked(project: str | Path) -> dict[str, Any]:
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
    reopen_request_path = state.path / "review" / "result_support_reopen_request.json"
    reopen_request = _read_json(reopen_request_path, {})
    review_path = state.path / "review" / "result_discipline_review_report.json"
    review_report = _read_json(review_path, {})
    review_decision = str(review_report.get("decision") or "").lower()
    review_sha256 = hashlib.sha256(review_path.read_bytes()).hexdigest() if review_path.is_file() else ""
    review_evidence_blocking = (
        str((review_report.get("figure_publication_quality") or {}).get("decision") or "").lower() in {"repair_required", "revise_required", "blocked"}
        or str((review_report.get("review_rule_gate") or {}).get("decision") or "").lower() in {"repair_required", "revise_required", "blocked"}
        or bool(review_report.get("result_support_reopen_request"))
    )
    request_exists = reopen_request_path.is_file()
    review_resolves_request, reopen_blocking_reasons = _fresh_passing_review(
        state.path,
        reopen_request if isinstance(reopen_request, dict) else {},
        review_report if isinstance(review_report, dict) else {},
        review_sha256,
        evidence_blocking=review_evidence_blocking,
    ) if request_exists else (False, [])
    if request_exists:
        derived_status = "resolved" if review_resolves_request else "requested"
        request_changed = str(reopen_request.get("status") or "") != derived_status
        reopen_request["status"] = derived_status
        if review_resolves_request:
            if str(reopen_request.get("resolved_review_sha256") or "") != review_sha256:
                reopen_request["resolved_at"] = utc_now()
                reopen_request["resolved_review_sha256"] = review_sha256
                request_changed = True
        else:
            for field in ("resolved_at", "resolved_review_sha256"):
                if field in reopen_request:
                    reopen_request.pop(field, None)
                    request_changed = True
        if request_changed:
            _write_json(reopen_request_path, reopen_request)
    reopen_pending = (request_exists and not review_resolves_request) or review_evidence_blocking
    claims = _planned_claims(state.path, result_manifest if isinstance(result_manifest, dict) else {})
    signal_report = collect_result_support_signals(state.path)
    metrics = signal_report["metrics"]
    metric_records = signal_report["metric_records"]
    _attach_explicit_optimization_directions(state.path, metric_records)
    claim_assessments = [
        _assess_claim(claim, metric_records=metric_records, validity=validity)
        for claim in claims
    ]
    if not claim_assessments:
        claim_assessments.append({
            "claim_id": "claim_contract_missing",
            "planned_claim": "No structured claim contract or figure storyboard claim was found.",
            "source": "inferred",
            "support_status": "partially_supported",
            "failure_type": "missing_claim_contract",
            "diagnosis": "Draftpaper_loop cannot verify scientific support without a planned claim or storyboard finding.",
        })
    for task in signal_report["pending_tasks"]:
        task_id = str(task.get("task_id") or "current_bound_pending_task")
        claim_assessments.append({
            "claim_id": task_id,
            "planned_claim": "A current pending analysis/data task must be resolved before Result Support can pass.",
            "source": task.get("source") or "current_bound_pending_tasks",
            "support_status": "not_supported",
            "failure_type": "current_bound_pending_task",
            "diagnosis": f"Current pending task {task_id} is bound to the selected Result Support inputs.",
        })
    for task in signal_report["unbound_required_data_tasks"]:
        claim_assessments.append({
            "claim_id": task["task_id"],
            "planned_claim": f"Required data role {task['required_role']} must have a current evidence binding.",
            "source": "required_data_role_bindings",
            "support_status": "not_supported",
            "failure_type": "unbound_required_data_task",
            "diagnosis": f"Required data role {task['required_role']} has no current binding.",
            "route_task": task,
        })
    for task in signal_report["unbound_required_evidence_tasks"]:
        role = task["required_evidence_role"]
        claim_assessments.append({
            "claim_id": task["task_id"],
            "planned_claim": f"Required evidence role {role} must have a current evidence binding.",
            "source": "required_evidence_role_bindings",
            "support_status": "not_supported",
            "failure_type": "unbound_required_evidence_task",
            "diagnosis": f"Required evidence role {role} has no current binding.",
            "route_task": task,
        })
    for diagnostic in signal_report.get("blocking_diagnostics") or []:
        claim_assessments.append({
            "claim_id": f"result_support_diagnostic:{diagnostic.get('code')}:{diagnostic.get('source')}",
            "planned_claim": "Every consumed result metric must be explicitly bound to the selected run.",
            "source": diagnostic.get("source"),
            "support_status": "not_supported",
            "failure_type": diagnostic.get("code"),
            "diagnosis": diagnostic,
        })
    if reopen_pending:
        claim_assessments.append({
            "claim_id": "post_results_evidence_reopen_pending",
            "planned_claim": "Post-Results evidence findings must be resolved before Result Support can pass.",
            "source": "review/result_support_reopen_request.json",
            "support_status": "not_supported",
            "failure_type": "post_results_evidence_reopen_pending",
            "diagnosis": {
                "code": "post_results_evidence_reopen_pending",
                "blocking": True,
                "request_status": reopen_request.get("status"),
                "review_decision": review_report.get("decision"),
                "review_sha256": review_sha256,
                "requested_review_sha256": reopen_request.get("result_discipline_review_sha256"),
                "evidence_failure_reasons": reopen_request.get("evidence_failure_reasons") or [],
                "blocking_reasons": reopen_blocking_reasons,
            },
        })
    decision, support_level, requires_user_decision = _decision(claim_assessments, validity)
    failed_claims = [item for item in claim_assessments if item.get("support_status") in {"not_supported", "partially_supported"}]
    report = {
        "status": "written",
        "schema_version": "dpl.result_support_checkpoint.v3",
        "project_id": state.metadata.get("project_id"),
        "generated_at": utc_now(),
        "decision": decision,
        "support_level": support_level,
        "assessment_decision": decision,
        "assessment_support_level": support_level,
        "requires_user_decision": requires_user_decision,
        "result_validity_decision": validity.get("decision"),
        "evidence_strength": validity.get("evidence_strength"),
        "metrics": metrics,
        "metric_records": metric_records,
        "metric_sources": signal_report["metric_sources"],
        "claim_assessments": claim_assessments,
        "failed_claims": failed_claims,
        "route_options": [],
        "manuscript_may_proceed": decision == "pass",
        "stale_if_downgrade_route": ["results", "introduction", "data_writing", "methods_writing", "discussion", "latex", "quality_checks"],
        "stale_if_supplement_route": ["data", "method_plan", "figure_plan", "figure_contracts", "code", "methods", "result_validity", "result_support", "core_evidence", "results", "introduction", "data_writing", "methods_writing", "discussion", "latex", "quality_checks"],
        "input_bindings": signal_report["input_bindings"],
        "signals": signal_report["signals"],
        "skipped_tasks": signal_report.get("skipped_tasks") or [],
        "warnings": signal_report.get("warnings") or [],
        "selected_route": None,
        "route_receipt": None,
    }
    update_project_state(
        state.path,
        stage_updates={"result_support": "draft" if decision == "pass" else "failed"},
    )
    report["input_bindings"] = build_result_support_input_bindings(state.path)
    report["checkpoint_sha256"] = result_support_checkpoint_sha256(report)
    report["route_options"] = _route_options(state.path, report["checkpoint_sha256"]) if requires_user_decision else []
    results_dir = state.path / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    _write_json(results_dir / "result_support_checkpoint.json", report)
    markdown = _render_markdown(report)
    (results_dir / "result_support_checkpoint.md").write_text(markdown, encoding="utf-8")
    write_html_report(results_dir / "result_support_checkpoint.html", markdown, title="Result Support Checkpoint")
    _set_manifest(state.path, list(report["input_bindings"]))
    return {
        "status": "written",
        "project_path": str(state.path),
        "decision": decision,
        "support_level": support_level,
        "requires_user_decision": requires_user_decision,
        "result_support_checkpoint": str(results_dir / "result_support_checkpoint.json"),
        "checkpoint_sha256": report["checkpoint_sha256"],
        "route_options": report["route_options"],
    }


def assess_result_support(project: str | Path) -> dict[str, Any]:
    """Assess Result Support while excluding concurrent checkpoint route commits."""
    project_path = load_project(project).path
    with file_lock(project_path / RESULT_SUPPORT_ROUTE_LOCK):
        return _assess_result_support_unlocked(project_path)


def validate_result_support_for_manuscript(project_path: Path) -> dict[str, Any]:
    report = _read_json(project_path / RESULT_SUPPORT_JSON, {})
    if not report:
        return {}
    if report.get("decision") != "pass":
        raise ResultSupportError(
            "Manuscript writing requires result support decision pass. Current decision: "
            + str(report.get("decision"))
        )
    computed_hash = result_support_checkpoint_sha256(report)
    stored_hash = str(report.get("checkpoint_sha256") or "")
    if stored_hash != computed_hash:
        raise ResultSupportError(
            "Result Support checkpoint content does not match checkpoint_sha256; reassess Result Support."
        )
    recorded_bindings = report.get("input_bindings")
    if not isinstance(recorded_bindings, dict):
        recorded_bindings = {}
    current_bindings = build_result_support_input_bindings(project_path)
    changed = sorted(
        relative
        for relative in set(recorded_bindings) | set(current_bindings)
        if current_bindings.get(relative) != recorded_bindings.get(relative)
    )
    if changed:
        raise ResultSupportError(
            "Result Support inputs changed after checkpoint creation: " + ", ".join(changed)
        )
    return report


__all__ = [
    "RESULT_SUPPORT_JSON",
    "RESULT_SUPPORT_MD",
    "RESULT_SUPPORT_HTML",
    "RESULT_SUPPORT_ROUTE_LOCK",
    "RESULT_SUPPORT_INPUTS",
    "RESULT_SUPPORT_OUTPUTS",
    "ResultSupportError",
    "assess_result_support",
    "bind_result_route_receipt",
    "result_route_command",
    "result_route_preflight",
    "result_support_checkpoint_sha256",
    "validate_result_support_for_manuscript",
]
