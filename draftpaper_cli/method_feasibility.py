# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

from pathlib import Path
from typing import Any

from .data_contracts import assess_role_coverage, normalize_roles, read_json
from .html_utils import write_html_report
from .project_scaffold import _write_json, utc_now
from .project_state import load_project, update_stage_status


METHOD_FEASIBILITY_JSON = "methods/method_feasibility_report.json"
METHOD_FEASIBILITY_HTML = "methods/method_feasibility_report.html"
METHOD_REPAIR_PLAN_JSON = "methods/method_repair_plan.json"
METHOD_DEGRADATION_OPTIONS_JSON = "methods/method_degradation_options.json"


class MethodFeasibilityError(RuntimeError):
    """Raised when method feasibility cannot be assessed."""


def assess_method_feasibility(project: str | Path) -> dict[str, Any]:
    state = load_project(project)
    blueprint = read_json(state.path / "methods" / "method_blueprint.json", {})
    if not isinstance(blueprint, dict) or not blueprint:
        raise MethodFeasibilityError("methods/method_blueprint.json is required. Run prepare-method-blueprint first.")
    data_contract = read_json(state.path / "methods" / "method_data_contract.json", {})
    role_coverage = read_json(state.path / "data" / "data_role_coverage_report.json", {})
    code_plan = read_json(state.path / "methods" / "method_code_plan.json", {})
    formula_plan = read_json(state.path / "methods" / "method_formula_plan.json", {})
    storyboard = read_json(state.path / "research_plan" / "figure_storyboard.json", {})

    required_roles = normalize_roles((data_contract or {}).get("required_roles") or [])
    available_roles = normalize_roles((data_contract or {}).get("available_roles") or [])
    if isinstance(role_coverage, dict):
        available_roles = list(dict.fromkeys(available_roles + normalize_roles(role_coverage.get("available_roles") or [])))
    coverage = assess_role_coverage(required_roles, available_roles)

    method_families = [str(item) for item in (code_plan.get("method_families") or []) if str(item).strip()] if isinstance(code_plan, dict) else []
    validation_checks = [str(item) for item in (code_plan.get("validation_checks") or []) if str(item).strip()] if isinstance(code_plan, dict) else []
    formula_families = [str(item) for item in (formula_plan.get("formula_families") or []) if str(item).strip()] if isinstance(formula_plan, dict) else []
    storyboard_figures = storyboard.get("figures") if isinstance(storyboard, dict) else []
    main_figure_count = len([item for item in storyboard_figures or [] if isinstance(item, dict)])

    issues: list[dict[str, str]] = []
    if coverage.get("blocking_missing_roles"):
        for role in coverage.get("blocking_missing_roles") or []:
            issues.append({"severity": "blocking", "kind": "missing_data_role", "detail": role})
    if not method_families:
        issues.append({"severity": "blocking", "kind": "missing_method_plan", "detail": "No method family is declared for figure/code generation."})
    if main_figure_count and not validation_checks:
        issues.append({"severity": "conditional", "kind": "missing_validation_design", "detail": "Storyboard figures exist but no validation checks are declared."})
    if main_figure_count and not formula_families:
        issues.append({"severity": "conditional", "kind": "missing_formula_plan", "detail": "No formula family is declared for method writing."})

    blocking = [item for item in issues if item.get("severity") == "blocking"]
    conditional = [item for item in issues if item.get("severity") == "conditional"]
    if blocking:
        decision = "blocked"
        next_action = "prepare-data-acquisition" if any(item.get("kind") == "missing_data_role" for item in blocking) else "prepare-method-blueprint"
    elif conditional or coverage.get("decision") == "conditional":
        decision = "conditional"
        next_action = "plan-figures"
    else:
        decision = "pass"
        next_action = "plan-figures"

    repair_plan = _repair_plan(issues)
    degradation_options = _degradation_options(issues)
    report = {
        "status": "written",
        "generated_at": utc_now(),
        "project_id": state.metadata.get("project_id"),
        "decision": decision,
        "method_families": method_families,
        "validation_checks": validation_checks,
        "formula_families": formula_families,
        "main_storyboard_figure_count": main_figure_count,
        "data_role_coverage": coverage,
        "issues": issues,
        "repair_plan": repair_plan,
        "degradation_options": degradation_options,
        "recommended_next_action": next_action,
        "policy": "Repair missing data or method capability before code generation; narrow the research plan only after repair attempts fail.",
    }

    _write_json(state.path / METHOD_FEASIBILITY_JSON, report)
    _write_json(state.path / METHOD_REPAIR_PLAN_JSON, {"status": "written", "generated_at": utc_now(), "tasks": repair_plan})
    _write_json(state.path / METHOD_DEGRADATION_OPTIONS_JSON, {"status": "written", "generated_at": utc_now(), "options": degradation_options})
    write_html_report(state.path / METHOD_FEASIBILITY_HTML, _render_report(report), title="Method Feasibility")
    _set_stage_manifest(state.path)
    update_stage_status(state.path, "method_feasibility", "draft" if decision != "blocked" else "failed")
    return {
        "status": "written",
        "project_path": str(state.path),
        "decision": decision,
        "method_feasibility_report": str(state.path / METHOD_FEASIBILITY_JSON),
        "recommended_next_action": next_action,
        "issue_count": len(issues),
    }


def _repair_plan(issues: list[dict[str, str]]) -> list[dict[str, str]]:
    tasks: list[dict[str, str]] = []
    for item in issues:
        kind = item.get("kind") or "issue"
        if kind == "missing_data_role":
            tasks.append({"issue": kind, "target": item.get("detail", ""), "command": "prepare-data-acquisition", "purpose": "Supplement the data role before method/code generation."})
        elif kind == "missing_method_plan":
            tasks.append({"issue": kind, "target": item.get("detail", ""), "command": "collect-method-plan", "purpose": "Add method intent or reusable method templates."})
        elif kind == "missing_validation_design":
            tasks.append({"issue": kind, "target": item.get("detail", ""), "command": "prepare-method-blueprint", "purpose": "Regenerate method blueprint with explicit validation checks."})
        elif kind == "missing_formula_plan":
            tasks.append({"issue": kind, "target": item.get("detail", ""), "command": "prepare-method-blueprint", "purpose": "Regenerate method blueprint with formula families for method writing."})
    return tasks


def _degradation_options(issues: list[dict[str, str]]) -> list[dict[str, str]]:
    if not issues:
        return [{"level": "level_0_original_scope", "recommendation": "Proceed with the current method scope.", "trigger": "none"}]
    return [
        {
            "level": "repair_first_then_scope_revision",
            "trigger": item.get("kind", "issue"),
            "recommendation": "Try data/method repair first. If the blocker remains, revise research_plan and regenerate figure_storyboard before code generation.",
        }
        for item in issues
    ]


def _render_report(report: dict[str, Any]) -> str:
    lines = ["# Method Feasibility", "", f"Decision: `{report.get('decision')}`", "", "## Issues", ""]
    for item in report.get("issues") or []:
        lines.append(f"- {item.get('severity')}: {item.get('kind')} -- {item.get('detail')}")
    if not report.get("issues"):
        lines.append("- None.")
    lines.extend(["", "## Method Families", ""])
    for item in report.get("method_families") or []:
        lines.append(f"- {item}")
    lines.extend(["", "## Repair Plan", ""])
    for item in report.get("repair_plan") or []:
        lines.append(f"- `{item.get('command')}`: {item.get('purpose')}")
    return "\n".join(lines)


def _set_stage_manifest(project_path: Path) -> None:
    manifest_path = project_path / "method_feasibility" / "stage_manifest.json"
    if not manifest_path.exists():
        return
    manifest = read_json(manifest_path, {})
    manifest["input_files"] = [
        "methods/method_blueprint.json",
        "methods/method_data_contract.json",
        "methods/method_code_plan.json",
        "methods/method_formula_plan.json",
        "data/data_role_coverage_report.json",
        "research_plan/figure_storyboard.json",
    ]
    manifest["output_files"] = [
        METHOD_FEASIBILITY_JSON,
        METHOD_FEASIBILITY_HTML,
        METHOD_REPAIR_PLAN_JSON,
        METHOD_DEGRADATION_OPTIONS_JSON,
    ]
    _write_json(manifest_path, manifest)
