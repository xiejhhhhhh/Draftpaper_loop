"""Executable analysis specifications shared by code, figures, and Methods."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .project_scaffold import _write_json, utc_now


EXECUTABLE_ANALYSIS_SPEC = "methods/executable_analysis_spec.json"
ANALYSIS_FORMULA_AST = "methods/analysis_formula_ast.json"
RUN_SELECTION_POLICY = "methods/run_selection_policy.json"
RESAMPLING_CONTRACT = "methods/resampling_contract.json"


class AnalysisSpecError(RuntimeError):
    """Raised when declared statistical semantics cannot be executed safely."""


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return default


def _identifier(prefix: str, text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:48] or "analysis"
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]
    return f"{prefix}:{slug}:{digest}"


def render_formula_ast(node: dict[str, Any]) -> str:
    kind = str(node.get("type") or "")
    if kind == "symbol":
        return str(node.get("latex") or node.get("name") or "?")
    if kind == "number":
        return str(node.get("value"))
    if kind == "fraction":
        return rf"\frac{{{render_formula_ast(node.get('numerator') or {})}}}{{{render_formula_ast(node.get('denominator') or {})}}}"
    if kind == "absolute":
        return rf"\left|{render_formula_ast(node.get('value') or {})}\right|"
    if kind == "sum":
        lower = str(node.get("lower") or "")
        upper = str(node.get("upper") or "")
        return rf"\sum_{{{lower}}}^{{{upper}}} {render_formula_ast(node.get('body') or {})}"
    if kind == "product":
        return " ".join(render_formula_ast(item) for item in node.get("factors") or [])
    if kind == "difference":
        return " - ".join(render_formula_ast(item) for item in node.get("terms") or [])
    if kind == "function":
        return rf"\operatorname{{{node.get('name') or 'f'}}}\left({', '.join(render_formula_ast(item) for item in node.get('arguments') or [])}\right)"
    raise AnalysisSpecError(f"Unsupported formula AST node type: {kind or '<missing>'}")


def event_probability_ece_ast() -> dict[str, Any]:
    return {
        "type": "sum",
        "lower": "b=1",
        "upper": "B",
        "body": {
            "type": "product",
            "factors": [
                {"type": "fraction", "numerator": {"type": "symbol", "latex": "|I_b|"}, "denominator": {"type": "symbol", "latex": "n"}},
                {"type": "absolute", "value": {"type": "difference", "terms": [
                    {"type": "symbol", "latex": r"\bar{p}_b"},
                    {"type": "symbol", "latex": r"\bar{y}_b"},
                ]}},
            ],
        },
    }


def validate_analysis_spec(spec: dict[str, Any]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    spec_id = str(spec.get("analysis_spec_id") or "<unknown>")
    required = ("analysis_spec_id", "estimand_id", "cohort_view_id", "sample_unit", "split_id", "implementation_entry_point")
    for field in required:
        if not str(spec.get(field) or "").strip():
            issues.append({"code": f"missing_{field}", "analysis_spec_id": spec_id, "message": f"Analysis spec lacks {field}."})
    calibration = spec.get("calibration") if isinstance(spec.get("calibration"), dict) else {}
    if calibration:
        definition = str(calibration.get("definition") or "")
        if definition not in {"event_probability_ece", "confidence_accuracy_ece", "classwise_ece", "not_applicable"}:
            issues.append({"code": "unknown_calibration_definition", "analysis_spec_id": spec_id, "message": f"Unsupported calibration definition {definition}."})
        implementation = str(calibration.get("implementation_definition") or definition)
        if definition != implementation:
            issues.append({"code": "calibration_definition_implementation_mismatch", "analysis_spec_id": spec_id, "message": f"Declared {definition} but implementation computes {implementation}."})
    resampling = spec.get("resampling") if isinstance(spec.get("resampling"), dict) else {}
    uncertainty = str(resampling.get("uncertainty_semantics") or "")
    if "paired" in uncertainty:
        if resampling.get("paired") is not True or not str(resampling.get("pair_id") or "").strip():
            issues.append({"code": "paired_without_alignment", "analysis_spec_id": spec_id, "message": "Paired uncertainty requires paired=true and an explicit pair_id."})
        if not str(resampling.get("resampling_unit") or "").strip():
            issues.append({"code": "paired_without_resampling_unit", "analysis_spec_id": spec_id, "message": "Paired uncertainty requires a resampling unit."})
    if any(term in uncertainty for term in ("cluster", "group")) and not str(resampling.get("group_id") or "").strip():
        issues.append({"code": "grouped_without_group_id", "analysis_spec_id": spec_id, "message": "Grouped or clustered uncertainty requires group_id."})
    return issues


def validate_run_selection_policy(policy: dict[str, Any]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    role = str(policy.get("selection_role") or "")
    if role not in {"primary", "replicate", "sensitivity", "ablation", "post_hoc"}:
        issues.append({"code": "invalid_selection_role", "message": "Run selection role must be explicit."})
    aggregation = str(policy.get("aggregation_policy") or "")
    if aggregation in {"best", "max", "best_seed"} and role == "primary" and not policy.get("locked_before_test_access"):
        issues.append({"code": "post_hoc_best_seed_primary", "message": "An unlocked best seed cannot be the primary headline result."})
    if role == "primary" and not str(policy.get("test_access_policy") or "").strip():
        issues.append({"code": "missing_test_access_policy", "message": "Primary run selection requires a test-access policy."})
    return issues


def _formula_for_metric(metric: str) -> tuple[str, dict[str, Any], list[dict[str, str]], dict[str, Any]]:
    normalized = re.sub(r"[^a-z0-9]+", "_", metric.lower()).strip("_")
    if normalized in {"ece", "expected_calibration_error", "event_probability_ece"}:
        return (
            "event_probability_ece",
            event_probability_ece_ast(),
            [
                {"symbol": "I_b", "meaning": "events assigned to probability bin b"},
                {"symbol": "n", "meaning": "number of evaluated events"},
                {"symbol": "\\bar{p}_b", "meaning": "mean predicted event probability in bin b"},
                {"symbol": "\\bar{y}_b", "meaning": "observed positive-event fraction in bin b"},
            ],
            {"definition": "event_probability_ece", "implementation_definition": "event_probability_ece"},
        )
    ast = {"type": "function", "name": normalized or "metric", "arguments": [{"type": "symbol", "latex": "y"}, {"type": "symbol", "latex": r"\hat{y}"}]}
    return normalized or "metric", ast, [{"symbol": "y", "meaning": "observed outcome"}, {"symbol": r"\hat{y}", "meaning": "model output or prediction"}], {"definition": "not_applicable", "implementation_definition": "not_applicable"}


def compile_executable_analysis_specs(project: str | Path) -> dict[str, Any]:
    root = Path(project)
    requirements = _read_json(root / "methods" / "method_requirements.json", {})
    research_method = _read_json(root / "research_plan" / "method_plan.json", {})
    storyboard = _read_json(root / "research_plan" / "figure_storyboard.json", {})
    cohort_views = _read_json(root / "data" / "cohort_view_registry.json", {})
    default_view = next((item for item in cohort_views.get("views") or [] if isinstance(item, dict)), {})
    metric = str(requirements.get("primary_metric") or "primary_metric")
    method_tasks = [item for item in research_method.get("method_tasks") or [] if isinstance(item, dict)]
    if not method_tasks:
        method_tasks = [{"task_id": "primary_analysis", "method_family": (requirements.get("method_families") or ["verified_analysis"])[0]}]
    specs: list[dict[str, Any]] = []
    formulas: list[dict[str, Any]] = []
    resampling_contracts: list[dict[str, Any]] = []
    for index, task in enumerate(method_tasks, start=1):
        task_id = str(task.get("task_id") or task.get("method_id") or f"analysis_{index}")
        formula_id, ast, variables, calibration = _formula_for_metric(str(task.get("metric") or metric))
        analysis_spec_id = _identifier("analysis_spec", task_id)
        resampling = {
            "analysis_spec_id": analysis_spec_id,
            "method": str(task.get("resampling_method") or "none_declared"),
            "resampling_unit": str(task.get("resampling_unit") or ""),
            "paired": bool(task.get("paired")),
            "pair_id": str(task.get("pair_id") or ""),
            "group_id": str(task.get("group_id") or ""),
            "uncertainty_semantics": str(task.get("uncertainty_semantics") or "point_estimate_only"),
        }
        spec = {
            "analysis_spec_id": analysis_spec_id,
            "task_id": task_id,
            "estimand_id": str(task.get("estimand_id") or _identifier("estimand", task_id)),
            "outcome": task.get("outcome") or "declared_target",
            "exposure": task.get("exposure") or "declared_method_or_feature_set",
            "covariates": list(task.get("covariates") or []),
            "reference_direction": str(task.get("reference_direction") or "higher_is_better"),
            "unit": str(task.get("unit") or "dimensionless"),
            "cohort_view_id": str(task.get("cohort_view_id") or default_view.get("cohort_view_id") or ""),
            "sample_unit": str(task.get("sample_unit") or default_view.get("sample_unit") or ""),
            "split_id": str(task.get("split_id") or default_view.get("split_id") or "not_yet_assigned"),
            "preprocessing_fit_scope": str(task.get("preprocessing_fit_scope") or "training_partition_only"),
            "model_family": str(task.get("method_family") or "verified_analysis"),
            "hyperparameter_selection": str(task.get("hyperparameter_selection") or "declared_before_test_access"),
            "seed_policy": str(task.get("seed_policy") or "report_all_declared_replicates"),
            "formula_id": formula_id,
            "calibration": calibration,
            "resampling": resampling,
            "multiplicity_family": str(task.get("multiplicity_family") or "single_primary_estimand"),
            "threshold_selection": str(task.get("threshold_selection") or "not_applicable"),
            "implementation_entry_point": str(task.get("implementation_entry_point") or "methods/src/project_analysis.py"),
            "required_inputs": list(task.get("required_data") or requirements.get("required_data_features") or []),
            "declared_outputs": list(task.get("declared_outputs") or []),
            "figure_ids": [str(item.get("figure_id") or item.get("id")) for item in storyboard.get("figures") or [] if isinstance(item, dict) and task_id in [str(value) for value in item.get("required_method") or []]],
        }
        spec["validation_issues"] = validate_analysis_spec(spec)
        specs.append(spec)
        formulas.append({"formula_id": formula_id, "analysis_spec_id": analysis_spec_id, "ast": ast, "latex": render_formula_ast(ast), "variables": variables})
        resampling_contracts.append(resampling)
    selection_policy = {
        "schema_version": "dpl.run_selection_policy.v1",
        "selection_role": "primary",
        "selection_metric": metric,
        "selection_partition": "validation",
        "selection_locked_at": utc_now(),
        "locked_before_test_access": True,
        "test_access_policy": "test partition is evaluated only after model and selection policy are locked",
        "aggregation_policy": "report_all_declared_replicates",
        "headline_reporting_policy": "report the prespecified aggregate and disclose single-run estimates as such",
    }
    selection_policy["validation_issues"] = validate_run_selection_policy(selection_policy)
    all_issues = [issue for spec in specs for issue in spec["validation_issues"]] + selection_policy["validation_issues"]
    spec_payload = {"schema_version": "dpl.executable_analysis_spec.v1", "generated_at": utc_now(), "decision": "blocked" if all_issues else "pass", "analysis_specs": specs, "issues": all_issues}
    formula_payload = {"schema_version": "dpl.analysis_formula_ast.v1", "generated_at": utc_now(), "formulas": formulas}
    resampling_payload = {"schema_version": "dpl.resampling_contract.v1", "generated_at": utc_now(), "contracts": resampling_contracts}
    _write_json(root / EXECUTABLE_ANALYSIS_SPEC, spec_payload)
    _write_json(root / ANALYSIS_FORMULA_AST, formula_payload)
    _write_json(root / RUN_SELECTION_POLICY, selection_policy)
    _write_json(root / RESAMPLING_CONTRACT, resampling_payload)
    return {
        "decision": spec_payload["decision"],
        "analysis_spec_count": len(specs),
        "issue_count": len(all_issues),
        "executable_analysis_spec": EXECUTABLE_ANALYSIS_SPEC,
        "analysis_formula_ast": ANALYSIS_FORMULA_AST,
        "run_selection_policy": RUN_SELECTION_POLICY,
        "resampling_contract": RESAMPLING_CONTRACT,
    }
