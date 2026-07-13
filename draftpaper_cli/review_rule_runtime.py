# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json
import importlib.util
import re
from pathlib import Path
from typing import Any

from .discipline import infer_discipline_profile
from .discipline_modules import get_discipline_module
from .project_scaffold import _write_json, utc_now
from .plugin_catalog import build_plugin_catalog_snapshot


REVIEW_RULE_RUNTIME_SCHEMA_VERSION = "v0.22.5"

MATURE_RULE_STATES = {"promoted_review_rule", "paper_integrated", "runtime_integrated"}
BLOCKING_LEVELS = {"block_claim", "block_writing", "block_pipeline", "block"}
RELIABLE_FIXED_THRESHOLD_SOURCES = {
    "journal_guideline",
    "reporting_guideline",
    "discipline_convention",
    "discipline_consensus",
    "public_benchmark",
    "benchmark_comparison",
    "benchmark",
    "challenge",
    "user_confirmation",
    "user_confirmed",
    "human_confirmed",
    "mature_discipline_rule",
}

STAGE_GROUPS = {
    "research_plan": {"research_plan", "generate-plan", "plan"},
    "method_plan": {"method_plan", "collect-method-plan", "prepare-method-blueprint", "generate-analysis-code", "verify-methods"},
    "figure_contract": {"figure_contract", "figure_contracts", "plan-figures", "assess-figure-contracts"},
    "assess_result_validity": {"assess_result_validity", "assess-result-validity", "result_validity", "verify-methods"},
    "result_support_checkpoint": {"result_support_checkpoint", "assess-result-support", "result_support"},
    "post_results": {"post_results", "review_results", "review-results-with-discipline-rules", "assess_result_validity", "result_support_checkpoint"},
    "citation_audit": {"citation_audit", "citation-audit", "write_results", "write_discussion"},
}

STAGE_RULE_FAMILY_HINTS = {
    "research_plan": {"data_validity", "model_validity", "statistical_validity", "figure_claim_validity"},
    "method_plan": {"data_validity", "model_validity", "statistical_validity", "reproducibility_and_operational_validity", "discipline_review"},
    "figure_contract": {"figure_claim_validity", "data_validity", "model_validity", "discipline_review"},
    "assess_result_validity": {"model_validity", "statistical_validity", "data_validity", "figure_claim_validity", "reproducibility_and_operational_validity", "discipline_review"},
    "result_support_checkpoint": {"figure_claim_validity", "model_validity", "statistical_validity", "citation_and_manuscript_validity", "discipline_review"},
    "post_results": {"figure_claim_validity", "model_validity", "statistical_validity", "data_validity", "reproducibility_and_operational_validity", "discipline_review"},
    "citation_audit": {"citation_and_manuscript_validity", "figure_claim_validity", "discipline_review"},
}

CHECK_ROLE_HINTS = {
    "baseline": "baseline_metric",
    "ablation": "ablation_result",
    "split": "validation_split",
    "held_out": "validation_split",
    "holdout": "validation_split",
    "out_of_sample": "validation_split",
    "external_validation": "validation_split",
    "spatial": "validation_split",
    "temporal": "validation_split",
    "leakage": "leakage_check",
    "lookahead": "leakage_check",
    "survivorship": "cohort_definition",
    "p_value": "p_value",
    "p-value": "p_value",
    "r2": "goodness_of_fit_metric",
    "rmse": "error_metric",
    "mae": "error_metric",
    "auc": "performance_metric",
    "f1": "performance_metric",
    "metric": "performance_metric",
    "sample_count": "sample_size",
    "sample": "sample_unit",
    "cohort": "cohort_definition",
    "calibration": "calibration_metric",
    "uncertainty": "uncertainty_evidence",
    "fdr": "multiple_testing_control",
    "multiple_testing": "multiple_testing_control",
    "batch": "batch_effect_check",
    "unit": "unit_consistency",
    "boundary": "boundary_condition",
    "convergence": "convergence_evidence",
    "sensitivity": "sensitivity_analysis",
    "privacy": "ethics_privacy_statement",
    "ethics": "ethics_privacy_statement",
    "figure": "figure_contract",
    "caption": "figure_contract",
    "claim": "claim_contract",
    "citation": "citation_evidence",
    "reference": "citation_evidence",
    "reproduc": "reproducibility_manifest",
}

EVIDENCE_ROLE_ALIASES = {
    "result_metric": {"performance_metric", "goodness_of_fit_metric", "error_metric", "p_value", "primary_metric"},
    "method_run": {"run_manifest", "method_output", "reproducibility_manifest"},
    "figure_contract": {"figure_contract_gate", "figure_metadata"},
    "claim_contract": {"planned_claim", "result_support"},
    "data_feasibility": {"data_validity", "missingness_report"},
}


REVIEW_RULE_RESCUE_COMMANDS = {
    "data_rescue": "prepare-data-acquisition",
    "method_rescue": "prepare-method-blueprint",
    "result_downgrade": "apply-result-downgrade",
    "supplement_data_and_method": "prepare-result-rescue",
    "manuscript_repair": "write-results",
    "citation_repair": "audit-citations",
    "human_checkpoint": "checkpoint",
}


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError):
        if path.suffix.lower() not in {".yaml", ".yml"}:
            return default
    try:
        parsed = _read_simple_yaml_mapping(path)
    except OSError:
        return default
    return parsed if parsed is not None else default


def _parse_scalar(value: str) -> Any:
    stripped = value.strip()
    lowered = stripped.lower()
    if not stripped:
        return ""
    if lowered in {"true", "false"}:
        return lowered == "true"
    if lowered in {"null", "none", "~"}:
        return None
    if stripped in {"[]", "{}"}:
        return [] if stripped == "[]" else {}
    if (stripped.startswith('"') and stripped.endswith('"')) or (stripped.startswith("'") and stripped.endswith("'")):
        return stripped[1:-1]
    try:
        return int(stripped)
    except ValueError:
        pass
    try:
        return float(stripped)
    except ValueError:
        return stripped


def _read_simple_yaml_mapping(path: Path) -> dict[str, Any] | None:
    """Read the small JSON-compatible YAML manifests Draftpaper-loop writes.

    This intentionally avoids adding a runtime dependency. It supports the simple
    mapping/nested-mapping shape used by run manifests, e.g. ``metrics:`` with
    indented scalar values. Complex YAML should still be converted upstream.
    """
    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, root)]
    for raw_line in path.read_text(encoding="utf-8-sig", errors="ignore").splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        line = raw_line.strip()
        if ":" not in line or line.startswith("-"):
            return None
        key, value = line.split(":", 1)
        key = key.strip().strip('"\'')
        if not key:
            return None
        while stack and indent <= stack[-1][0]:
            stack.pop()
        if not stack:
            return None
        parent = stack[-1][1]
        if value.strip():
            parent[key] = _parse_scalar(value)
            continue
        child: dict[str, Any] = {}
        parent[key] = child
        stack.append((indent, child))
    return root


def _normalise(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")


def _text_blob(rule: dict[str, Any]) -> str:
    values: list[str] = []
    for key in ["rule_id", "rule_group_id", "display_name", "rule_family", "metric_family", "model_family", "minimum_sample_policy", "sample_unit_policy", "metric_dimension_policy", "review_question", "scientific_risk", "provenance_notes"]:
        values.append(str(rule.get(key) or ""))
    for key in ["checks", "notes", "manual_review_triggers", "applicable_methods", "applicable_data_roles", "evidence_roles"]:
        raw = rule.get(key)
        if isinstance(raw, list):
            values.extend(str(item) for item in raw)
        elif raw:
            values.append(str(raw))
    return " ".join(values).lower().replace("-", "_")


def _role_matches(required: str, available: set[str]) -> bool:
    role = _normalise(required)
    if role in available:
        return True
    aliases = EVIDENCE_ROLE_ALIASES.get(role, set())
    if aliases and any(_normalise(alias) in available for alias in aliases):
        return True
    for parent, children in EVIDENCE_ROLE_ALIASES.items():
        if role in {_normalise(item) for item in children} and _normalise(parent) in available:
            return True
    return False


def _infer_required_evidence(rule: dict[str, Any], stage: str) -> list[str]:
    explicit = list(rule.get("minimum_evidence_required") or rule.get("evidence_roles") or [])
    roles = [_normalise(item) for item in explicit if str(item).strip()]
    blob = _text_blob(rule)
    for marker, role in CHECK_ROLE_HINTS.items():
        if marker in blob and role not in roles:
            roles.append(role)
    if not roles:
        if stage == "method_plan":
            roles.extend(["method_plan", "validation_design"])
        elif stage == "figure_contract":
            roles.extend(["figure_contract", "claim_contract"])
        elif stage == "assess_result_validity":
            roles.extend(["method_run", "result_metric"])
        elif stage == "result_support_checkpoint":
            roles.extend(["claim_contract", "result_metric", "figure_contract"])
        elif stage == "post_results":
            roles.extend(["method_run", "result_metric", "figure_contract", "results_prose"])
        elif stage == "citation_audit":
            roles.extend(["citation_evidence", "manuscript_claim"])
    return list(dict.fromkeys(roles))


def _binding_required_evidence(rule: dict[str, Any]) -> list[str]:
    binding = rule.get("evidence_binding") if isinstance(rule.get("evidence_binding"), dict) else {}
    required: list[str] = []
    for field in binding.get("required_fields") or []:
        value = _normalise(field)
        if value and value not in required:
            required.append(value)
    return required


def _collect_conflict_tokens(value: Any, conflicts: set[str]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized_key = _normalise(key)
            if normalized_key in {"conflict", "conflicts", "evidence_conflicts", "observed_conflicts", "semantic_conflicts", "forbidden_conflicts", "blocking_conflicts"}:
                _collect_conflict_tokens(item, conflicts)
            elif normalized_key in {"failure_causes", "problems", "issues"}:
                _collect_conflict_tokens(item, conflicts)
        return
    if isinstance(value, list):
        for item in value:
            _collect_conflict_tokens(item, conflicts)
        return
    if isinstance(value, str):
        token = _normalise(value)
        if token:
            conflicts.add(token)


def _collect_evidence_conflicts(project_path: Path, evidence_context: dict[str, Any] | None = None) -> set[str]:
    conflicts: set[str] = set()
    if evidence_context:
        _collect_conflict_tokens(evidence_context, conflicts)
    for relative in [
        "results/result_evidence_resolution.json",
        "results/figure_contract_gate_report.json",
        "results/result_support_checkpoint.json",
        "results/result_validity_report.json",
        "methods/method_review_rule_gate.json",
    ]:
        payload = _read_json(project_path / relative, {})
        if payload:
            _collect_conflict_tokens(payload, conflicts)
    return conflicts


def _review_rule_rescue_command(failure_route: str) -> str:
    normalized = _normalise(failure_route)
    return REVIEW_RULE_RESCUE_COMMANDS.get(normalized, "checkpoint")


def _review_rule_rescue_task(project_path: Path, assessment: dict[str, Any]) -> dict[str, Any] | None:
    decision = str(assessment.get("decision") or "")
    if decision in {"satisfied"} or str(assessment.get("runtime_level") or "") in {"advisory_ready", "warn_ready", "blocking_ready"}:
        return None
    if str(assessment.get("runtime_level") or "") == "advisory" or decision == "advisory_missing_evidence":
        return None
    route = str(assessment.get("failure_route") or "human_checkpoint")
    command = _review_rule_rescue_command(route)
    rule_id = str(assessment.get("rule_id") or "review_rule")
    missing = list(assessment.get("missing_evidence_roles") or [])
    conflicts = list(assessment.get("observed_forbidden_conflicts") or [])
    semantic_failure = decision in {"threshold_failed", "scientific_anomaly", "plugin_rule_failed"}
    trigger = "scientific_anomaly" if semantic_failure else "forbidden_conflict" if conflicts else "missing_evidence" if missing else "threshold_or_confirmation"
    if route == "supplement_data_and_method":
        command = "prepare-result-rescue"
    if trigger == "forbidden_conflict" and route in {"method_rescue", "supplement_data_and_method"}:
        command = "prepare-result-rescue" if route == "supplement_data_and_method" else "prepare-method-blueprint"
    if trigger == "scientific_anomaly":
        command = "prepare-results-semantic-repair"
    return {
        "task_id": f"review_rule:{rule_id}:{trigger}",
        "source": "review_rule_runtime",
        "stage": assessment.get("stage"),
        "rule_id": rule_id,
        "rule_family": assessment.get("rule_family") or "discipline_review",
        "decision": decision,
        "runtime_level": assessment.get("runtime_level"),
        "blocking": assessment.get("runtime_level") == "blocking",
        "failure_route": route,
        "recommended_command": command,
        "recommended_cli": f"python -m draftpaper_cli.cli {command} --project {project_path}",
        "missing_evidence_roles": missing,
        "observed_forbidden_conflicts": conflicts,
        "scientific_findings": list(assessment.get("scientific_findings") or []),
        "threshold_evaluation": dict(assessment.get("threshold_evaluation") or {}),
        "repair_priority": list(assessment.get("repair_priority") or []),
        "review_question": assessment.get("review_question") or "",
        "scientific_risk": assessment.get("scientific_risk") or "",
        "reason": _review_rule_rescue_reason(assessment, trigger),
    }


def _review_rule_rescue_reason(assessment: dict[str, Any], trigger: str) -> str:
    rule_id = str(assessment.get("rule_id") or "review_rule")
    if trigger == "missing_evidence":
        missing = ", ".join(str(item) for item in assessment.get("missing_evidence_roles") or []) or "declared evidence"
        return f"Review rule {rule_id} requires evidence roles that are not available yet: {missing}."
    if trigger == "forbidden_conflict":
        conflicts = ", ".join(str(item) for item in assessment.get("observed_forbidden_conflicts") or []) or "declared forbidden conflict"
        return f"Review rule {rule_id} observed forbidden evidence conflicts: {conflicts}."
    if trigger == "scientific_anomaly":
        return f"Review rule {rule_id} found a result-level threshold, dimension, binding, baseline, ablation, or uncertainty anomaly; repair the affected Results claim locally before escalating to new data or methods."
    if assessment.get("decision") == "threshold_requires_context":
        return f"Review rule {rule_id} uses a threshold that must remain contextual until a reliable source or human confirmation is recorded."
    if assessment.get("decision") == "human_confirmation_required":
        return f"Review rule {rule_id} requires human confirmation before it can support a blocking or strong-claim decision."
    return f"Review rule {rule_id} requires repair or manual confirmation before this stage can be treated as fully supported."


def build_review_rule_rescue_tasks(project: str | Path, report: dict[str, Any]) -> list[dict[str, Any]]:
    project_path = Path(project)
    tasks: list[dict[str, Any]] = []
    for assessment in report.get("rule_assessments") or []:
        if not isinstance(assessment, dict):
            continue
        task = _review_rule_rescue_task(project_path, assessment)
        if task:
            tasks.append(task)
    tasks.sort(key=_review_rule_rescue_task_sort_key)
    return tasks


def _review_rule_rescue_task_sort_key(task: dict[str, Any]) -> tuple[int, int, str]:
    trigger = str(task.get("task_id") or "")
    if task.get("blocking"):
        severity_rank = 0
    elif task.get("runtime_level") == "warn_and_repair":
        severity_rank = 1
    else:
        severity_rank = 2
    if "forbidden_conflict" in trigger:
        trigger_rank = 0
    elif "missing_evidence" in trigger:
        trigger_rank = 1
    else:
        trigger_rank = 2
    return (severity_rank, trigger_rank, str(task.get("rule_id") or ""))


def _threshold_policy(rule: dict[str, Any]) -> tuple[str, str, bool, list[str]]:
    policy = rule.get("threshold_policy") if isinstance(rule.get("threshold_policy"), dict) else {}
    source = rule.get("threshold_source") if isinstance(rule.get("threshold_source"), dict) else {}
    mode = _normalise(policy.get("mode") or policy.get("type") or "contextual") or "contextual"
    source_type = _normalise(source.get("type") or source.get("source_type") or "project_context") or "project_context"
    warnings: list[str] = []
    hard = mode == "fixed" and source_type in {_normalise(item) for item in RELIABLE_FIXED_THRESHOLD_SOURCES}
    if mode == "fixed" and not hard:
        warnings.append(
            "Fixed threshold is not backed by journal guidance, discipline consensus, public benchmark, mature rule provenance, or user confirmation; treating it as contextual."
        )
    return mode, source_type, hard, warnings


def _stage_matches(rule: dict[str, Any], stage: str) -> bool:
    hooks = rule.get("pipeline_hooks") if isinstance(rule.get("pipeline_hooks"), dict) else {}
    normalized_stage = _normalise(stage)
    accepted = {_normalise(item) for item in STAGE_GROUPS.get(normalized_stage, {normalized_stage})}
    if hooks:
        hook_values = {_normalise(key) for key in hooks.keys()} | {_normalise(value) for value in hooks.values()}
        if hook_values & accepted:
            return True
    family = _normalise(rule.get("rule_family") or "discipline_review")
    if family in {_normalise(item) for item in STAGE_RULE_FAMILY_HINTS.get(normalized_stage, set())}:
        return True
    blob = _text_blob(rule)
    if normalized_stage == "method_plan" and any(term in blob for term in ["baseline", "ablation", "split", "validation", "leakage", "sample", "cohort"]):
        return True
    if normalized_stage == "figure_contract" and any(term in blob for term in ["figure", "caption", "axis", "panel", "claim"]):
        return True
    if normalized_stage == "assess_result_validity" and any(term in blob for term in ["metric", "p_value", "r2", "f1", "auc", "rmse", "baseline", "ablation", "sample_count"]):
        return True
    if normalized_stage == "result_support_checkpoint" and any(term in blob for term in ["claim", "baseline", "ablation", "figure", "metric", "validation"]):
        return True
    if normalized_stage == "post_results" and any(term in blob for term in ["claim", "baseline", "ablation", "figure", "metric", "validation", "uncertainty", "unit"]):
        return True
    if normalized_stage == "citation_audit" and any(term in blob for term in ["citation", "reference", "claim", "manuscript"]):
        return True
    return not hooks and family == "discipline_review"


def _available_metric_roles(run_manifest: dict[str, Any], result_evidence: dict[str, Any]) -> set[str]:
    roles: set[str] = set()
    metric_names = {_normalise(key) for key in (run_manifest.get("metrics") or {}).keys()}
    model_names: set[str] = set()
    for item in list(result_evidence.get("metrics") or []) + list(result_evidence.get("evidence_records") or []):
        if isinstance(item, dict):
            metric_names.add(_normalise(
                item.get("metric_name") or item.get("name")
                or str(item.get("entity_role") or "").removeprefix("result_metric_")
            ))
            model_names.add(_normalise(" ".join(str(item.get(key) or "") for key in (
                "model_id", "model", "cohort_id", "cohort", "source_artifact",
            ))))
    if metric_names:
        roles.update({"result_metric", "performance_metric", "primary_metric"})
    if any("r2" in item or "r_squared" in item for item in metric_names):
        roles.add("goodness_of_fit_metric")
    if any(item in {"p", "p_value", "pvalue"} for item in metric_names):
        roles.add("p_value")
    if any(item in {"rmse", "mae", "mse", "error"} for item in metric_names):
        roles.add("error_metric")
    if any("baseline" in item for item in metric_names | model_names):
        roles.add("baseline_metric")
    if any("ablation" in item or item.startswith("no_") or "without" in item for item in metric_names | model_names):
        roles.add("ablation_result")
    if any("calibration" in item for item in metric_names):
        roles.add("calibration_metric")
    if any("sample" in item or item in {"n", "count"} for item in metric_names):
        roles.add("sample_size")
    return roles


def build_review_evidence_bundle(project: str | Path, extra_context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build the domain-neutral evidence object consumed by executable review rules."""
    project_path = Path(project)
    run_manifest = _read_json(project_path / "methods" / "run_manifest.yaml", {})
    resolved = _read_json(project_path / "results" / "resolved_result_evidence.json", {})
    if not resolved:
        resolved = _read_json(project_path / "results" / "result_evidence_resolution.json", {})
    registry = _read_json(project_path / "writing" / "scientific_evidence_registry.json", {})
    records = [item for item in registry.get("records") or [] if isinstance(item, dict)]
    metrics: list[dict[str, Any]] = []
    for item in resolved.get("evidence_records") or []:
        if isinstance(item, dict) and str(item.get("entity_role") or "").startswith("result_metric_"):
            metrics.append(dict(item))
    if not metrics:
        run_id = str(run_manifest.get("run_id") or run_manifest.get("execution_id") or "run_summary")
        for name, value in (run_manifest.get("metrics") or {}).items():
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                continue
            metrics.append({
                "evidence_id": f"run:{run_id}:{_normalise(name)}",
                "entity_role": f"result_metric_{_normalise(name)}",
                "metric_name": _normalise(name),
                "value": numeric,
                "metric_dimension": "count" if any(token in _normalise(name) for token in ("count", "_n", "sample")) else "score",
                "run_id": run_id,
                "cohort_id": str(run_manifest.get("cohort_id") or "main"),
                "sample_unit": str(run_manifest.get("sample_unit") or "model_evaluation"),
                "split": str(run_manifest.get("evaluation_split") or "run_summary"),
                "model_id": str(run_manifest.get("model_id") or "run_summary"),
            })
    metric_map = {
        _normalise(item.get("metric_name") or str(item.get("entity_role") or "").removeprefix("result_metric_")): item.get("value")
        for item in metrics
    }
    conflicts = sorted(_collect_evidence_conflicts(project_path, extra_context))
    return {
        "schema_version": "v0.22.5",
        "project_path": str(project_path),
        "roles": collect_review_rule_evidence_roles(project_path, extra_context),
        "records": records,
        "metrics": metrics,
        "metric_values": metric_map,
        "run_manifest": run_manifest,
        "conflicts": conflicts,
        "baseline_metrics": [
            item for item in metrics
            if "baseline" in _normalise(" ".join(str(item.get(key) or "") for key in ("model_id", "entity_role", "cohort_id", "source_artifact")))
        ],
        "ablation_metrics": [item for item in metrics if "ablation" in _normalise(item.get("model_id") or item.get("entity_role")) or any(token in _normalise(item.get("model_id")) for token in ("no_", "without"))],
        "uncertainty_records": [item for item in records + metrics if any(token in _normalise(item.get("entity_role")) for token in ("confidence_interval", "uncertainty", "standard_error", "bootstrap"))],
        "results_text": (project_path / "results" / "results.tex").read_text(encoding="utf-8-sig", errors="replace") if (project_path / "results" / "results.tex").exists() else "",
    }


def _threshold_evaluation(rule: dict[str, Any], bundle: dict[str, Any], enabled: bool) -> dict[str, Any]:
    policy = rule.get("threshold_policy") if isinstance(rule.get("threshold_policy"), dict) else {}
    if not enabled or policy.get("value") in {None, ""}:
        return {"status": "not_applicable"}
    metric_hint = _normalise(rule.get("metric_name") or rule.get("metric_family") or "")
    values = bundle.get("metric_values") or {}
    if metric_hint:
        candidates = [(name, value) for name, value in values.items() if metric_hint == name or metric_hint in name or name in metric_hint]
    else:
        candidates = list(values.items())
    if not candidates:
        return {"status": "missing_metric", "metric_hint": metric_hint}
    metric_name, observed = candidates[0]
    try:
        observed_value = float(observed)
        threshold = float(policy["value"])
    except (TypeError, ValueError):
        return {"status": "invalid_threshold"}
    comparator = str(policy.get("comparator") or ">=").strip()
    comparisons = {
        ">=": observed_value >= threshold, ">": observed_value > threshold,
        "<=": observed_value <= threshold, "<": observed_value < threshold,
        "==": abs(observed_value - threshold) <= 1e-12,
    }
    passed = comparisons.get(comparator)
    if passed is None:
        return {"status": "invalid_comparator", "comparator": comparator}
    return {
        "status": "passed" if passed else "failed", "metric_name": metric_name,
        "observed": observed_value, "comparator": comparator, "threshold": threshold,
    }


def _scientific_bundle_findings(rule: dict[str, Any], bundle: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    blob = _text_blob(rule)
    metrics = list(bundle.get("metrics") or [])
    for item in metrics:
        missing = [field for field in ("evidence_id", "run_id", "cohort_id", "sample_unit", "split", "model_id", "metric_dimension") if not str(item.get(field) or "").strip()]
        if missing:
            findings.append({"code": "incomplete_metric_binding", "severity": "repair_required", "evidence_id": item.get("evidence_id"), "missing_fields": missing})
    dimensions: dict[str, set[str]] = {}
    for item in metrics:
        name = _normalise(item.get("metric_name") or str(item.get("entity_role") or "").removeprefix("result_metric_"))
        dimensions.setdefault(name, set()).add(_normalise(item.get("metric_dimension")))
    for name, values in dimensions.items():
        canonical_values = {
            "score" if value in {"score", "dimensionless", "dimensionless_score"} else value
            for value in values if value
        }
        if len(canonical_values) > 1:
            findings.append({"code": "mixed_metric_dimension", "severity": "repair_required", "metric_name": name, "dimensions": sorted(canonical_values)})
    if "baseline" in blob and not bundle.get("baseline_metrics"):
        findings.append({"code": "baseline_evidence_missing", "severity": "repair_required"})
    if "ablation" in blob and not bundle.get("ablation_metrics"):
        findings.append({"code": "ablation_evidence_missing", "severity": "repair_required"})
    if any(token in blob for token in ("uncertainty", "confidence_interval", "bootstrap")) and not bundle.get("uncertainty_records"):
        findings.append({"code": "uncertainty_evidence_missing", "severity": "repair_required"})
    return findings


def _execute_review_plugin(rule: dict[str, Any], bundle: dict[str, Any]) -> dict[str, Any]:
    rule_id = str(rule.get("rule_id") or rule.get("rule_group_id") or "")
    if not rule_id:
        return {"status": "not_available"}
    root = Path(__file__).resolve().parent / "discipline_modules"
    matches = list(root.glob(f"*/review_rules/{rule_id}/template.py"))
    if not matches:
        return {"status": "not_available"}
    path = matches[0]
    try:
        spec = importlib.util.spec_from_file_location(f"draftpaper_review_{rule_id}", path)
        if not spec or not spec.loader:
            return {"status": "load_failed"}
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        evaluator = getattr(module, "evaluate_rule", None)
        if callable(evaluator):
            result = evaluator({
                "roles": bundle.get("roles") or [], "evidence_roles": bundle.get("roles") or [],
                "metrics": bundle.get("metric_values") or {}, "records": bundle.get("records") or [],
                "conflicts": bundle.get("conflicts") or [],
            })
            return {"status": "executed", "template": str(path), "result": result if isinstance(result, dict) else {"value": result}}
    except Exception as exc:
        return {"status": "execution_failed", "template": str(path), "error": str(exc)}
    return {"status": "no_evaluator", "template": str(path)}


def collect_review_rule_evidence_roles(project: str | Path, extra_context: dict[str, Any] | None = None) -> list[str]:
    project_path = Path(project)
    run_manifest = _read_json(project_path / "methods" / "run_manifest.yaml", {})
    result_evidence = _read_json(project_path / "results" / "resolved_result_evidence.json", {})
    if not result_evidence:
        result_evidence = _read_json(project_path / "results" / "result_evidence_resolution.json", {})
    roles: set[str] = set()
    if (project_path / "research_plan" / "research_plan.md").exists():
        roles.add("research_plan")
    if (project_path / "research_plan" / "method_plan.json").exists() or (project_path / "methods" / "method_blueprint.json").exists():
        roles.update({"method_plan", "validation_design"})
    if (project_path / "research_plan" / "claim_contract.json").exists():
        roles.update({"claim_contract", "planned_claim"})
    if (project_path / "data" / "data_feasibility_report.json").exists():
        roles.update({"data_feasibility", "data_validity"})
    if (project_path / "data" / "data_inventory.json").exists():
        roles.update({"data_inventory", "sample_unit"})
    if run_manifest:
        roles.update({"method_run", "run_manifest", "method_output", "reproducibility_manifest"})
        if run_manifest.get("run_id") or result_evidence.get("run_id"):
            roles.add("run_id")
        if run_manifest.get("status") == "success":
            roles.add("successful_method_run")
        text = json.dumps(run_manifest, ensure_ascii=False, default=str).lower().replace("-", "_")
        if any(term in text for term in ["split", "holdout", "held_out", "test", "validation"]):
            roles.add("validation_split")
        if "leakage" in text:
            roles.add("leakage_check")
    roles.update(_available_metric_roles(run_manifest if isinstance(run_manifest, dict) else {}, result_evidence if isinstance(result_evidence, dict) else {}))
    if (project_path / "results" / "figure_contracts.json").exists():
        roles.update({"figure_contract", "figure_metadata"})
    if (project_path / "results" / "figure_contract_gate_report.json").exists():
        roles.add("figure_contract_gate")
    if (project_path / "results" / "result_manifest.yaml").exists():
        roles.update({"result_manifest", "figure_metadata"})
    if (project_path / "results" / "result_support_checkpoint.json").exists():
        roles.add("result_support")
    if result_evidence:
        evidence_records = [item for item in result_evidence.get("evidence_records") or [] if isinstance(item, dict)]
        if any(any(token in str(item.get("split") or "").lower() for token in ("held", "holdout", "test", "validation")) for item in evidence_records):
            roles.add("held_out_metrics")
        if any("uncert" in str(item.get("entity_role") or item.get("metric_name") or "").lower() or "confidence_interval" in str(item.get("entity_role") or "").lower() for item in evidence_records):
            roles.add("uncertainty")
    if (project_path / "citation_audit" / "final_citation_audit_report.html").exists() or (project_path / "citation_audit" / "reference_coverage_report.html").exists():
        roles.add("citation_evidence")
    if extra_context:
        for role in extra_context.get("available_evidence_roles") or []:
            roles.add(_normalise(role))
    return sorted(role for role in roles if role)


def load_discipline_review_rules(project: str | Path) -> dict[str, Any]:
    profile = infer_discipline_profile(Path(project))
    module = get_discipline_module(profile)
    return {
        "discipline_profile": profile,
        "discipline_module": module.spec.as_dict(),
        "review_rules": module.spec.review_rule_dicts(),
    }


def _rule_matches_active_plugins(rule: dict[str, Any], active_plugin_ids: list[str]) -> bool:
    if not active_plugin_ids:
        return True
    declared: list[str] = []
    for key in ["applicable_plugins", "applicable_methods", "applicable_data_roles"]:
        value = rule.get(key)
        if isinstance(value, list):
            declared.extend(str(item) for item in value if str(item).strip())
        elif value:
            declared.append(str(value))
    if not declared:
        return True
    active = {_normalise(item) for item in active_plugin_ids if _normalise(item)}
    expected = {_normalise(item) for item in declared if _normalise(item)}
    return any(
        left == right or left in right or right in left
        for left in active
        for right in expected
    )


def select_review_rules_for_stage(
    rules: list[dict[str, Any]],
    stage: str,
    *,
    active_plugin_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    return [
        rule for rule in rules
        if isinstance(rule, dict)
        and _stage_matches(rule, stage)
        and _rule_matches_active_plugins(rule, list(active_plugin_ids or []))
    ]


def assess_review_rules(
    project: str | Path,
    *,
    stage: str,
    evidence_context: dict[str, Any] | None = None,
    write_path: str | Path | None = None,
) -> dict[str, Any]:
    project_path = Path(project)
    loaded = load_discipline_review_rules(project_path)
    active_plugin_ids = [
        str(item) for item in (evidence_context or {}).get("active_plugin_ids") or []
        if str(item).strip()
    ]
    rules = select_review_rules_for_stage(
        list(loaded.get("review_rules") or []),
        stage,
        active_plugin_ids=active_plugin_ids,
    )
    available = set(collect_review_rule_evidence_roles(project_path, evidence_context))
    observed_conflicts = _collect_evidence_conflicts(project_path, evidence_context)
    evidence_bundle = build_review_evidence_bundle(project_path, evidence_context)
    evidence_bundle["roles"] = sorted(available)
    evidence_bundle["stage"] = stage
    assessments: list[dict[str, Any]] = []
    blocking_count = 0
    warn_count = 0
    advisory_count = 0
    for rule in rules:
        binding = rule.get("evidence_binding") if isinstance(rule.get("evidence_binding"), dict) else {}
        binding_required = _binding_required_evidence(rule)
        profile_required = []
        profile_stages = {str(item) for item in rule.get("runnable_profile_applicable_stages") or ["post_results"]}
        if stage in profile_stages:
            profile_required = [str(item) for item in rule.get("runnable_profile_required_fields") or []]
        required = list(dict.fromkeys(_infer_required_evidence(rule, stage) + binding_required + profile_required))
        missing = [role for role in required if not _role_matches(role, available)]
        forbidden_conflicts = [_normalise(item) for item in binding.get("forbidden_conflicts") or [] if _normalise(item)]
        conflict_hits = [conflict for conflict in forbidden_conflicts if conflict in observed_conflicts]
        threshold_mode, threshold_source_type, hard_threshold, threshold_warnings = _threshold_policy(rule)
        maturity = _normalise(rule.get("maturity") or "candidate")
        deployment_state = _normalise(rule.get("deployment_state") or "review_rule_candidate")
        blocking_level = _normalise(rule.get("blocking_level") or "warn_and_repair")
        evidence_bound = not missing
        profile_stage_limited = bool(rule.get("runnable_profile_applicable_stages")) and stage not in profile_stages
        mature_enough = maturity in {"runnable", "mature", "paper_integrated", "runtime_integrated"} and not profile_stage_limited
        formally_deployed = deployment_state in {_normalise(item) for item in MATURE_RULE_STATES}
        may_block = mature_enough and formally_deployed and blocking_level in {_normalise(item) for item in BLOCKING_LEVELS}
        threshold_evaluation = _threshold_evaluation(rule, evidence_bundle, hard_threshold)
        scientific_findings = _scientific_bundle_findings(rule, evidence_bundle)
        plugin_evaluation = _execute_review_plugin(rule, evidence_bundle)
        plugin_result = plugin_evaluation.get("result") if isinstance(plugin_evaluation.get("result"), dict) else {}
        plugin_failed = plugin_result.get("passes_gate") is False or plugin_result.get("decision") in {"failed", "revise_required"}
        if conflict_hits:
            if may_block:
                decision = "blocked_evidence_conflict"
                runtime_level = "blocking"
                blocking_count += 1
            else:
                decision = "evidence_conflict_requires_review"
                runtime_level = "warn_and_repair"
                warn_count += 1
        elif not evidence_bound:
            if may_block:
                decision = "blocked_missing_evidence"
                runtime_level = "blocking"
                blocking_count += 1
            elif mature_enough and blocking_level in {"warn_and_repair", "block_claim"}:
                decision = "needs_evidence"
                runtime_level = "warn_and_repair"
                warn_count += 1
            else:
                decision = "advisory_missing_evidence"
                runtime_level = "advisory"
                advisory_count += 1
        elif threshold_evaluation.get("status") == "failed":
            decision = "threshold_failed"
            runtime_level = "blocking" if may_block else "warn_and_repair"
            if may_block:
                blocking_count += 1
            else:
                warn_count += 1
        elif plugin_failed:
            decision = "plugin_rule_failed"
            runtime_level = "blocking" if may_block else "warn_and_repair"
            if may_block:
                blocking_count += 1
            else:
                warn_count += 1
        elif scientific_findings:
            decision = "scientific_anomaly"
            runtime_level = "blocking" if may_block else "warn_and_repair"
            if may_block:
                blocking_count += 1
            else:
                warn_count += 1
        elif threshold_warnings:
            decision = "threshold_requires_context"
            if mature_enough:
                runtime_level = "warn_and_repair"
                warn_count += 1
            else:
                runtime_level = "advisory"
                advisory_count += 1
        elif rule.get("human_confirmation_required") and not hard_threshold and threshold_mode in {"fixed", "human_confirmed", "human_confirmation"}:
            decision = "human_confirmation_required"
            runtime_level = "warn_and_repair"
            warn_count += 1
        else:
            decision = "satisfied"
            runtime_level = "blocking_ready" if may_block else "advisory_ready" if blocking_level == "advisory" else "warn_ready"
        assessments.append({
            "rule_id": rule.get("rule_id") or rule.get("rule_group_id") or "unnamed_review_rule",
            "display_name": rule.get("display_name") or rule.get("rule_id") or rule.get("rule_group_id") or "Unnamed review rule",
            "rule_family": rule.get("rule_family") or "discipline_review",
            "stage": stage,
            "maturity": rule.get("maturity") or "candidate",
            "deployment_state": rule.get("deployment_state") or "review_rule_candidate",
            "blocking_level": rule.get("blocking_level") or "warn_and_repair",
            "failure_route": rule.get("failure_route") or "human_checkpoint",
            "threshold_mode": threshold_mode,
            "threshold_source_type": threshold_source_type,
            "hard_threshold_enabled": hard_threshold,
            "required_evidence_roles": required,
            "schema_required_evidence_roles": binding_required,
            "missing_evidence_roles": missing,
            "evidence_binding": binding,
            "observed_forbidden_conflicts": conflict_hits,
            "evidence_bound": evidence_bound,
            "runtime_level": runtime_level,
            "decision": decision,
            "warnings": threshold_warnings,
            "threshold_evaluation": threshold_evaluation,
            "scientific_findings": scientific_findings,
            "plugin_evaluation": plugin_evaluation,
            "checks": list(rule.get("checks") or []),
            "repair_priority": list(rule.get("repair_priority") or []),
            "review_question": rule.get("review_question") or "",
            "scientific_risk": rule.get("scientific_risk") or "",
        })
    if blocking_count:
        decision = "revise_required"
    elif warn_count:
        decision = "warn_and_repair"
    else:
        decision = "pass"
    rescue_tasks = build_review_rule_rescue_tasks(project_path, {"rule_assessments": assessments})
    report = {
        "schema_version": REVIEW_RULE_RUNTIME_SCHEMA_VERSION,
        "generated_at": utc_now(),
        "stage": stage,
        "plugin_catalog_hash": build_plugin_catalog_snapshot().get("catalog_hash"),
        "decision": decision,
        "discipline_profile": loaded.get("discipline_profile") or {},
        "discipline_module_id": (loaded.get("discipline_module") or {}).get("module_id"),
        "available_evidence_roles": sorted(available),
        "selected_rule_count": len(assessments),
        "active_plugin_ids": active_plugin_ids,
        "blocking_count": blocking_count,
        "warn_count": warn_count,
        "advisory_count": advisory_count,
        "rule_assessments": assessments,
        "evidence_bundle_summary": {
            "metric_count": len(evidence_bundle.get("metrics") or []),
            "record_count": len(evidence_bundle.get("records") or []),
            "baseline_metric_count": len(evidence_bundle.get("baseline_metrics") or []),
            "ablation_metric_count": len(evidence_bundle.get("ablation_metrics") or []),
            "uncertainty_record_count": len(evidence_bundle.get("uncertainty_records") or []),
            "conflicts": evidence_bundle.get("conflicts") or [],
        },
        "rescue_task_count": len(rescue_tasks),
        "rescue_tasks": rescue_tasks,
        "recommended_next_commands": list(dict.fromkeys(
            str(task.get("recommended_cli"))
            for task in rescue_tasks
            if task.get("recommended_cli")
        )),
        "runtime_policy": {
            "candidate_or_foundation_rules_are_advisory_unless_promoted_and_evidence_bound": True,
            "fixed_thresholds_require_reliable_source_or_user_confirmation": True,
            "support_layer_signals_must_backflow_as_review_rule_candidates_before_runtime_blocking": True,
            "plugin_evaluators_are_executed_when_available": True,
            "scientific_anomalies_route_to_local_results_repair_before_data_or_method_rescue": True,
        },
    }
    if write_path is not None:
        destination = Path(write_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        _write_json(destination, report)
    return report


def review_rule_validation_checks(report: dict[str, Any]) -> list[str]:
    checks: list[str] = []
    for assessment in report.get("rule_assessments") or []:
        if not isinstance(assessment, dict):
            continue
        rule_id = str(assessment.get("rule_id") or "review_rule")
        if assessment.get("decision") in {"blocked_missing_evidence", "needs_evidence"}:
            missing = ", ".join(str(item) for item in assessment.get("missing_evidence_roles") or []) or "declared evidence"
            checks.append(f"review_rule:{rule_id}:provide {missing}")
        if assessment.get("decision") in {"blocked_evidence_conflict", "evidence_conflict_requires_review"}:
            conflicts = ", ".join(str(item) for item in assessment.get("observed_forbidden_conflicts") or []) or "declared forbidden conflict"
            checks.append(f"review_rule:{rule_id}:resolve {conflicts}")
        for check in assessment.get("checks") or []:
            text = str(check).strip()
            if text and text not in checks:
                checks.append(text)
    return checks
