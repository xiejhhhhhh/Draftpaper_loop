"""Pre-figure capability support loop for confirmed research blueprints."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .html_utils import write_html_report
from .project_scaffold import _write_json, utc_now
from .project_state import load_project
from .research_capabilities import assess_plugin_sufficiency
from .statistical_validation import assess_review_rule_coverage


REPORT_JSON = "research_plan/pre_execution_support_report.json"
REPORT_HTML = "research_plan/pre_execution_support_report.html"
PLUGIN_PREVIEW_JSON = "research_plan/plugin_sufficiency_preview.json"
RESCUE_TASKS_JSON = "research_plan/pre_execution_rescue_tasks.json"
RESCUE_TASKS_HTML = "research_plan/pre_execution_rescue_tasks.html"


class PreExecutionSupportError(RuntimeError):
    """Raised when pre-execution support cannot be assessed."""


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _render(report: dict[str, Any]) -> str:
    lines = [
        "# Research Blueprint Execution Support",
        "",
        f"Decision: `{report['decision']}`",
        "",
        "This report checks whether the planned data, methods, plugins, and statistical review coverage can support the confirmed figure storyboard. It does not authorize changing the scientific design.",
        "",
        "## Automatic Actions",
        "",
    ]
    for item in report.get("automatic_actions") or []:
        lines.append(f"- `{item.get('command')}`: {item.get('reason')}")
    lines.extend(["", "## Routes if Support Remains Insufficient", ""])
    for item in report.get("route_options") or []:
        lines.append(f"- `{item['route']}` -> `{item['command']}`: {item['effect']}")
    return "\n".join(lines)


def assess_pre_execution_support(project: str | Path) -> dict[str, Any]:
    state = load_project(project)
    if not (state.path / "research_plan" / "figure_storyboard.json").exists():
        raise PreExecutionSupportError("research_plan/figure_storyboard.json is required.")
    sufficiency_result = assess_plugin_sufficiency(state.path)
    sufficiency = _read_json(state.path / "research_plan" / "plugin_sufficiency_report.json")
    coverage_result = assess_review_rule_coverage(state.path)
    coverage = _read_json(state.path / "research_plan" / "review_rule_coverage_report.json")
    rescue_prepared = (state.path / RESCUE_TASKS_JSON).exists()
    sufficiency_decision = str(sufficiency.get("decision") or sufficiency_result.get("decision") or "unknown")
    exhausted = any(
        str(item.get("outcome") or item.get("status") or "").lower() in {"exhausted", "blocked_unavailable", "unavailable_after_search"}
        for item in (_read_json(state.path / "research_plan" / "plugin_rescue_outcomes.json").get("outcomes") or [])
        if isinstance(item, dict)
    )
    if exhausted:
        decision = "blocked_requires_user_route"
    elif sufficiency_decision == "pass" and coverage.get("decision") == "pass":
        decision = "ready_for_confirmation"
    elif rescue_prepared:
        decision = "conditional_ready_for_confirmation"
    else:
        decision = "automatic_rescue_required"
    automatic_actions = []
    if decision == "automatic_rescue_required":
        automatic_actions.append({
            "command": "prepare-pre-execution-rescue",
            "reason": "Prepare scoped project-local, plugin, AcademicForge, GitHub, and connector tasks before asking the user to confirm unresolved limitations.",
        })
    route_options = [
        {
            "route": "supplement_data_or_methods",
            "command": "prepare-pre-execution-rescue",
            "effect": "Keep the planned claims and produce scoped data, method, plugin, and review-rule rescue tasks before figure code generation.",
        },
        {
            "route": "downgrade_research_scope",
            "command": "revise-research-plan",
            "effect": "Revise claims and the storyboard, then generate a new plan hash for human confirmation; no results are rerun because execution has not started.",
        },
    ]
    report = {
        "schema_version": "dpl.pre_execution_support.v1",
        "status": "written",
        "generated_at": utc_now(),
        "project_id": state.metadata.get("project_id"),
        "decision": decision,
        "plugin_sufficiency_decision": sufficiency_decision,
        "review_rule_coverage_decision": coverage_result.get("decision"),
        "plugin_gap_count": len(sufficiency.get("rescue_tasks") or []),
        "missing_review_rule_families": coverage.get("missing_rule_families") or [],
        "automatic_actions": automatic_actions,
        "route_options": route_options,
        "requires_user_decision": decision == "blocked_requires_user_route",
        "confirmation_requires_accept_limitations": decision != "ready_for_confirmation",
        "policy": "Capability rescue may implement the confirmed design but may not replace its data roles, methods, validation, claims, figures, or panels.",
    }
    _write_json(state.path / REPORT_JSON, report)
    _write_json(state.path / PLUGIN_PREVIEW_JSON, {
        "schema_version": "dpl.plugin_sufficiency_preview.v1",
        "status": "written",
        "generated_at": utc_now(),
        "decision": sufficiency_decision,
        "requirement_assessments": sufficiency.get("requirement_assessments") or [],
        "rescue_tasks": sufficiency.get("rescue_tasks") or [],
        "preview_only": True,
    })
    write_html_report(state.path / REPORT_HTML, _render(report), title="Research Blueprint Execution Support")
    return {"status": "written", "project_path": str(state.path), "decision": decision, "report": REPORT_JSON, "requires_user_decision": report["requires_user_decision"]}


def prepare_pre_execution_rescue(project: str | Path) -> dict[str, Any]:
    state = load_project(project)
    report = _read_json(state.path / REPORT_JSON)
    if not report:
        assess_pre_execution_support(state.path)
        report = _read_json(state.path / REPORT_JSON)
    sufficiency = _read_json(state.path / "research_plan" / "plugin_sufficiency_report.json")
    coverage = _read_json(state.path / "research_plan" / "review_rule_coverage_report.json")
    tasks: list[dict[str, Any]] = []
    for index, item in enumerate(sufficiency.get("rescue_tasks") or [], start=1):
        tasks.append({
            "task_id": f"capability_rescue_{index:03d}",
            "kind": item.get("kind"),
            "requirement_id": item.get("requirement_id"),
            "figure_id": item.get("figure_id"),
            "target": (item.get("search_scope") or {}).get("role"),
            "search_order": ["project_local", "discipline_plugins", "AcademicForge", "GitHub_research_code", "external_connector_or_user_data"],
            "scientific_contract_change_forbidden": True,
            "recommended_command": item.get("recommended_command") or "prepare-plugin-rescue",
        })
    for index, family in enumerate(coverage.get("missing_rule_families") or [], start=1):
        tasks.append({
            "task_id": f"review_rule_rescue_{index:03d}",
            "kind": "review_rule",
            "target": family,
            "search_order": ["discipline_plugins", "shared_statistics_rules", "project_local_validated_code", "AcademicForge", "GitHub_research_code"],
            "scientific_contract_change_forbidden": True,
            "recommended_command": "extract-review-rule-signals",
        })
    payload = {
        "schema_version": "dpl.pre_execution_rescue_tasks.v1",
        "status": "prepared",
        "generated_at": utc_now(),
        "project_id": state.metadata.get("project_id"),
        "task_count": len(tasks),
        "tasks": tasks,
        "route_options": report.get("route_options") or [],
        "policy": "Repair implementation first. Any scientific design change reopens the research plan for human correction and confirmation.",
    }
    _write_json(state.path / RESCUE_TASKS_JSON, payload)
    lines = ["# Pre-execution Rescue Tasks", ""] + [f"- `{item['task_id']}`: {item.get('kind')} `{item.get('target') or item.get('requirement_id')}`" for item in tasks]
    write_html_report(state.path / RESCUE_TASKS_HTML, "\n".join(lines), title="Pre-execution Rescue Tasks")
    assess_pre_execution_support(state.path)
    return {"status": "prepared", "project_path": str(state.path), "task_count": len(tasks), "tasks": RESCUE_TASKS_JSON, "next_command": "review-research-plan"}
