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


FIGURE_CONTRACT_GATE_JSON = "results/figure_contract_gate_report.json"
FIGURE_CONTRACT_GATE_HTML = "results/figure_contract_gate_report.html"


class FigureContractGateError(RuntimeError):
    """Raised when the figure contract gate cannot be evaluated."""


def assess_figure_contracts(project: str | Path) -> dict[str, Any]:
    state = load_project(project)
    contracts = read_json(state.path / "results" / "figure_contracts.json", {})
    figure_plan = read_json(state.path / "results" / "figure_plan.json", {})
    alignment = read_json(state.path / "results" / "storyboard_alignment_report.json", {})
    method_feasibility = read_json(state.path / "methods" / "method_feasibility_report.json", {})
    data_coverage = read_json(state.path / "data" / "data_role_coverage_report.json", {})
    if not isinstance(contracts, dict) or not contracts:
        raise FigureContractGateError("results/figure_contracts.json is required. Run plan-figures first.")

    main_contracts = _main_contracts(contracts, figure_plan)
    available_data_roles = normalize_roles((data_coverage or {}).get("available_roles") or []) if isinstance(data_coverage, dict) else []
    method_status = str((method_feasibility or {}).get("decision") or "missing") if isinstance(method_feasibility, dict) else "missing"
    issues: list[dict[str, str]] = []
    contract_checks: list[dict[str, Any]] = []

    for index, contract in enumerate(main_contracts, start=1):
        figure_id = str(contract.get("figure_id") or contract.get("storyboard_id") or contract.get("id") or f"figure_{index}")
        required_data = normalize_roles(contract.get("required_data_roles") or contract.get("required_data") or contract.get("data_roles") or [])
        coverage = assess_role_coverage(required_data, available_data_roles)
        required_methods = [str(item) for item in (contract.get("required_method_roles") or contract.get("required_methods") or []) if str(item).strip()]
        expected_finding = str(contract.get("expected_finding") or contract.get("scientific_question") or contract.get("research_question") or "").strip()
        figure_issues: list[dict[str, str]] = []
        if coverage.get("blocking_missing_roles"):
            for role in coverage.get("blocking_missing_roles") or []:
                figure_issues.append({"severity": "blocking", "kind": "missing_data_role", "detail": role})
        if required_methods and method_status in {"blocked", "missing"}:
            figure_issues.append({"severity": "blocking", "kind": "missing_method_feasibility", "detail": method_status})
        if not expected_finding:
            figure_issues.append({"severity": "blocking", "kind": "missing_expected_finding", "detail": "Contracted main figure lacks an expected finding or research question."})
        if coverage.get("partial_missing_roles"):
            for role in coverage.get("partial_missing_roles") or []:
                figure_issues.append({"severity": "conditional", "kind": "partial_data_role", "detail": role})
        contract_checks.append({
            "figure_id": figure_id,
            "decision": "blocked" if any(item.get("severity") == "blocking" for item in figure_issues) else "conditional" if figure_issues else "pass",
            "required_data_roles": coverage.get("required_roles") or [],
            "missing_data_roles": coverage.get("missing_roles") or [],
            "required_method_roles": required_methods,
            "issues": figure_issues,
        })
        issues.extend({**item, "figure_id": figure_id} for item in figure_issues)

    if not main_contracts:
        issues.append({"severity": "blocking", "kind": "missing_main_figure_contract", "detail": "No main figure contracts were found."})

    figure_policy = figure_plan.get("figure_policy") if isinstance(figure_plan, dict) else {}
    if isinstance(figure_policy, dict) and figure_policy:
        minimum_groups = int(figure_policy.get("minimum_main_figures") or 5)
        main_group_count = int(
            figure_plan.get("main_figure_group_count")
            or contracts.get("main_figure_group_count")
            or len(main_contracts)
        )
        if main_group_count < minimum_groups:
            issues.append({
                "severity": "blocking",
                "kind": "insufficient_main_figure_groups",
                "detail": f"Research-plan evidence contract has {main_group_count} main figure group(s); expected at least {minimum_groups}. Supporting or appendix figures cannot fill this main-result contract.",
            })

    missing_storyboard = _missing_storyboard(alignment)
    for figure_id in missing_storyboard:
        issues.append({"severity": "blocking", "kind": "missing_storyboard_alignment", "detail": figure_id})

    if any(item.get("severity") == "blocking" for item in issues):
        decision = "blocked"
    elif issues:
        decision = "conditional"
    else:
        decision = "pass"
    next_action = _next_action(decision, issues)
    report = {
        "status": "written",
        "generated_at": utc_now(),
        "project_id": state.metadata.get("project_id"),
        "decision": decision,
        "main_contract_count": len(main_contracts),
        "main_figure_group_count": int(figure_plan.get("main_figure_group_count") or contracts.get("main_figure_group_count") or len(main_contracts)) if isinstance(figure_plan, dict) else len(main_contracts),
        "generated_figure_count": int(figure_plan.get("generated_figure_count") or 0) if isinstance(figure_plan, dict) else 0,
        "supporting_figure_count": int(figure_plan.get("supporting_figure_count") or 0) if isinstance(figure_plan, dict) else 0,
        "appendix_figure_count": int(figure_plan.get("appendix_figure_count") or 0) if isinstance(figure_plan, dict) else 0,
        "method_feasibility_decision": method_status,
        "contract_checks": contract_checks,
        "storyboard_alignment_missing": missing_storyboard,
        "issues": issues,
        "recommended_next_action": next_action,
        "policy": "Every planned main figure group must keep its research-plan contract before code generation. The contract is 5-6 main figure groups; generated PNG/panel count may exceed six when supporting or appendix diagnostics are scientifically useful. Validation or diagnostic figures cannot replace contracted main results.",
    }
    results_dir = state.path / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    _write_json(state.path / FIGURE_CONTRACT_GATE_JSON, report)
    write_html_report(state.path / FIGURE_CONTRACT_GATE_HTML, _render_report(report), title="Figure Contract Gate")
    _set_stage_manifest(state.path)
    update_stage_status(state.path, "figure_contracts", "draft" if decision != "blocked" else "failed")
    return {
        "status": "written",
        "project_path": str(state.path),
        "decision": decision,
        "figure_contract_gate_report": str(state.path / FIGURE_CONTRACT_GATE_JSON),
        "recommended_next_action": next_action.get("command"),
        "issue_count": len(issues),
    }


def _main_contracts(contracts: dict[str, Any], figure_plan: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ["main_contracts", "contracts", "figures"]:
        value = contracts.get(key)
        if isinstance(value, list) and value:
            return [
                item for item in value
                if isinstance(item, dict)
                and item.get("counts_toward_main_figures") is not False
                and str(item.get("manuscript_role") or "main").lower() != "appendix"
            ]
    figures = figure_plan.get("figures") if isinstance(figure_plan, dict) else []
    return [
        item for item in figures or []
        if isinstance(item, dict)
        and str(item.get("role") or item.get("figure_role") or "main").lower() != "supporting"
        and item.get("counts_toward_main_figures") is not False
        and str(item.get("manuscript_role") or "main").lower() != "appendix"
    ]


def _missing_storyboard(alignment: dict[str, Any]) -> list[str]:
    if not isinstance(alignment, dict):
        return []
    for key in ["missing_storyboard_figures", "missing_contracts", "unmatched_storyboard_figures"]:
        value = alignment.get(key)
        if isinstance(value, list):
            return [str(item.get("figure_id") if isinstance(item, dict) else item) for item in value]
    if alignment.get("all_storyboard_figures_planned") is False:
        return ["storyboard_alignment_report"]
    return []


def _next_action(decision: str, issues: list[dict[str, str]]) -> dict[str, str]:
    if decision == "pass":
        return {"command": "generate-analysis-code", "reason": "Figure contracts are executable."}
    if any(item.get("kind") in {"missing_data_role", "partial_data_role"} for item in issues):
        return {"command": "repair-figure-data", "reason": "At least one contracted main figure lacks required data roles."}
    if any(item.get("kind") == "missing_method_feasibility" for item in issues):
        return {"command": "repair-figure-method", "reason": "At least one contracted main figure lacks executable method support."}
    if any(item.get("kind") == "insufficient_main_figure_groups" for item in issues):
        return {"command": "generate-plan", "reason": "The research plan must define enough main figure groups before figure execution."}
    return {"command": "revise-research-plan", "reason": "The research plan and figure contracts are misaligned."}


def _render_report(report: dict[str, Any]) -> str:
    lines = ["# Figure Contract Gate", "", f"Decision: `{report.get('decision')}`", "", "## Contract Checks", ""]
    for item in report.get("contract_checks") or []:
        lines.append(f"- {item.get('figure_id')}: {item.get('decision')}; missing data roles: {', '.join(item.get('missing_data_roles') or []) or 'none'}")
    if not report.get("contract_checks"):
        lines.append("- No main contracts were found.")
    lines.extend(["", "## Recommended Next Action", ""])
    action = report.get("recommended_next_action") or {}
    lines.append(f"`{action.get('command')}` -- {action.get('reason')}")
    return "\n".join(lines)


def _set_stage_manifest(project_path: Path) -> None:
    manifest_path = project_path / "figure_contracts" / "stage_manifest.json"
    if not manifest_path.exists():
        return
    manifest = read_json(manifest_path, {})
    manifest["input_files"] = [
        "results/figure_plan.json",
        "results/figure_contracts.json",
        "results/storyboard_alignment_report.json",
        "methods/method_feasibility_report.json",
        "data/data_role_coverage_report.json",
    ]
    manifest["output_files"] = [FIGURE_CONTRACT_GATE_JSON, FIGURE_CONTRACT_GATE_HTML]
    _write_json(manifest_path, manifest)

