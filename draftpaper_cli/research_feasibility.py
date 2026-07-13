# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .data_contracts import available_data_roles, assess_role_coverage, read_json, required_roles_from_storyboard
from .discipline import infer_discipline_profile
from .html_utils import write_html_report
from .project_scaffold import _write_json, utc_now
from .project_state import ProjectStateError, load_project, update_stage_status


PREFLIGHT_JSON = "research_plan/research_preflight_feasibility.json"
PREFLIGHT_HTML = "research_plan/research_preflight_feasibility.html"
PLAN_FEASIBILITY_JSON = "research_plan/research_plan_feasibility_report.json"
PLAN_FEASIBILITY_HTML = "research_plan/research_plan_feasibility_report.html"
DEGRADATION_OPTIONS_JSON = "research_plan/research_degradation_options.json"
REVISION_SUGGESTIONS_JSON = "research_plan/research_plan_revision_suggestions.json"
REVISION_SUGGESTIONS_MD = "research_plan/research_plan_revision_suggestions.md"
SCOPE_DECISION_JSON = "research_plan/research_scope_decision.json"


class ResearchFeasibilityError(RuntimeError):
    """Raised when research feasibility gates cannot be evaluated."""


def _read_text(path: Path, limit: int = 6000) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")[:limit]


def _tokens(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-zA-Z][a-zA-Z0-9_+-]{2,}", (text or "").lower())}


def _field_required_roles(meta: dict[str, Any], discipline: dict[str, Any]) -> list[str]:
    text = " ".join([str(meta.get("idea") or ""), str(meta.get("field") or ""), str(discipline.get("discipline") or ""), str(discipline.get("primary_discipline") or "")]).lower()
    roles: list[str] = []

    def add(role: str) -> None:
        if role not in roles:
            roles.append(role)

    if any(term in text for term in ["machine learning", "deep learning", "classification", "prediction", "transformer", "model"]):
        add("label_or_response")
        add("validation_design")
    if any(term in text for term in ["time", "temporal", "light curve", "long-term", "series"]):
        add("time_series")
    if any(term in text for term in ["geography", "remote sensing", "spatial", "gis", "agriculture", "environment"]):
        add("spatial_or_sky_coordinates")
        add("spectral_or_remote_sensing_features")
    if any(term in text for term in ["x-ray", "wxt", "flares", "transient", "light curve", "time-domain"]):
        add("time_series")
        add("spectral_or_remote_sensing_features")
    elif any(term in text for term in ["astronomy", "astrophysics", "euclid", "galaxy"]):
        add("spatial_or_sky_coordinates")
        if any(term in text for term in ["image", "imaging", "vis", "cutout", "morphology"]):
            add("image_or_raster_data")
    return roles


def _literature_count(project_path: Path) -> int:
    items = read_json(project_path / "references" / "literature_items.json", [])
    return len(items) if isinstance(items, list) else 0


def _method_roles_from_plan(method_plan: dict[str, Any]) -> list[str]:
    roles: list[str] = []
    for task in method_plan.get("method_tasks") or [] if isinstance(method_plan, dict) else []:
        if not isinstance(task, dict):
            continue
        for key in ["method_family", "validation", "required_method", "method_role"]:
            value = task.get(key)
            if value and str(value) not in roles:
                roles.append(str(value))
    return roles


def preflight_research_feasibility(project: str | Path) -> dict[str, Any]:
    state = load_project(project)
    discipline = infer_discipline_profile(state.path)
    inventory = read_json(state.path / "data" / "data_inventory.json", {})
    acquisition = read_json(state.path / "data" / "data_acquisition_plan.json", {})
    available_roles = available_data_roles(inventory if isinstance(inventory, dict) else {}, acquisition if isinstance(acquisition, dict) else {})
    expected_roles = _field_required_roles(state.metadata, discipline)
    coverage = assess_role_coverage(expected_roles, available_roles)
    literature_items = _literature_count(state.path)
    decision = "pass" if coverage["decision"] == "pass" else "conditional"
    if literature_items == 0:
        decision = "blocked"
    degradation = _degradation_options(coverage, stage="preflight")
    report = {
        "status": "written",
        "generated_at": utc_now(),
        "project_id": state.metadata.get("project_id"),
        "decision": decision,
        "discipline_profile": discipline,
        "literature_item_count": literature_items,
        "expected_data_roles": expected_roles,
        "available_data_roles": available_roles,
        "role_coverage": coverage,
        "research_planning_policy": "Proceed to research_plan only with explicit feasibility assumptions and degradation options.",
        "recommended_next_action": "generate-plan" if decision != "blocked" else "search-literature",
        "degradation_options": degradation,
    }
    _write_json(state.path / PREFLIGHT_JSON, report)
    write_html_report(state.path / PREFLIGHT_HTML, _render_report_md("Research Preflight Feasibility", report), title="Research Preflight Feasibility")
    update_stage_status(state.path, "research_feasibility", "draft" if decision != "blocked" else "failed")
    _set_stage_manifest(state.path, "research_feasibility", ["idea/idea.md", "references/literature_items.json", "journal_profile/journal_profile.json"], [PREFLIGHT_JSON, PREFLIGHT_HTML])
    return {
        "status": "written",
        "project_path": str(state.path),
        "decision": decision,
        "research_preflight_feasibility": str(state.path / PREFLIGHT_JSON),
        "recommended_next_action": report["recommended_next_action"],
    }


def assess_research_plan_feasibility(project: str | Path) -> dict[str, Any]:
    state = load_project(project)
    storyboard = read_json(state.path / "research_plan" / "figure_storyboard.json", {})
    method_plan = read_json(state.path / "research_plan" / "method_plan.json", {})
    if not isinstance(storyboard, dict) or not storyboard.get("figures"):
        raise ResearchFeasibilityError("research_plan/figure_storyboard.json with planned figures is required before research-plan feasibility can be assessed.")
    inventory = read_json(state.path / "data" / "data_inventory.json", {})
    acquisition = read_json(state.path / "data" / "data_acquisition_plan.json", {})
    required_roles = required_roles_from_storyboard(storyboard)
    available_roles = available_data_roles(inventory if isinstance(inventory, dict) else {}, acquisition if isinstance(acquisition, dict) else {})
    coverage = assess_role_coverage(required_roles, available_roles)
    method_roles = _method_roles_from_plan(method_plan if isinstance(method_plan, dict) else {})
    figure_assessments = _figure_assessments(storyboard, available_roles, method_roles)
    blocking_figures = [item for item in figure_assessments if item["feasibility"] == "blocked"]
    conditional_figures = [item for item in figure_assessments if item["feasibility"] == "conditional"]
    inventory_ready = bool(isinstance(inventory, dict) and inventory and (inventory.get("files") or inventory.get("datasets") or inventory.get("row_count") or inventory.get("summary")))
    acquisition_exhausted = bool(
        isinstance(acquisition, dict)
        and str(
            acquisition.get("decision")
            or acquisition.get("status")
            or acquisition.get("availability")
            or ""
        ).strip().lower() in {"blocked_unavailable", "unavailable_after_search", "exhausted"}
    )
    if blocking_figures and not acquisition_exhausted:
        # Missing roles are repairable gaps until the acquisition/rescue route has
        # been attempted and explicitly exhausted. Blocking here would recreate
        # the "missing data prevents the step that can acquire data" deadlock.
        decision = "conditional"
    elif blocking_figures:
        decision = "blocked"
    elif conditional_figures or coverage["decision"] != "pass":
        decision = "conditional"
    else:
        decision = "pass"
    degradation = _degradation_options(coverage, stage="research_plan", figures=figure_assessments)
    suggestions = {
        "status": "written",
        "generated_at": utc_now(),
        "decision": decision,
        "suggestions": [item["degradation_option"] for item in figure_assessments if item.get("degradation_option")],
        "policy": "Revise the research plan at the research-scope level; do not silently replace failed main figures downstream.",
    }
    acquisition_ready = bool(isinstance(acquisition, dict) and acquisition)
    next_action = (
        "inventory-data" if decision == "conditional" and acquisition_ready and not inventory_ready
        else "prepare-data-acquisition" if blocking_figures and not acquisition_exhausted
        else "prepare-data-acquisition" if decision != "blocked"
        else "revise-research-plan"
    )
    scope_decision = {
        "status": "written",
        "generated_at": utc_now(),
        "scope_level": _scope_level(decision, coverage, figure_assessments),
        "requires_user_confirmation": decision == "blocked",
        "next_action": next_action,
    }
    report = {
        "status": "written",
        "generated_at": utc_now(),
        "project_id": state.metadata.get("project_id"),
        "decision": decision,
        "role_coverage": coverage,
        "figure_assessments": figure_assessments,
        "degradation_options": degradation,
        "research_scope_decision": scope_decision,
        "recommended_next_action": scope_decision["next_action"],
    }
    _write_json(state.path / PLAN_FEASIBILITY_JSON, report)
    _write_json(state.path / DEGRADATION_OPTIONS_JSON, {"status": "written", "generated_at": utc_now(), "options": degradation})
    _write_json(state.path / REVISION_SUGGESTIONS_JSON, suggestions)
    (state.path / REVISION_SUGGESTIONS_MD).write_text(_render_revision_suggestions_md(suggestions), encoding="utf-8")
    _write_json(state.path / SCOPE_DECISION_JSON, scope_decision)
    write_html_report(state.path / PLAN_FEASIBILITY_HTML, _render_report_md("Research Plan Feasibility", report), title="Research Plan Feasibility")
    update_stage_status(state.path, "research_plan_feasibility", "draft" if decision != "blocked" else "failed")
    _set_stage_manifest(state.path, "research_plan_feasibility", ["research_plan/research_blueprint.json", "research_plan/figure_storyboard.json", "research_plan/method_plan.json", "data/data_inventory.json"], [PLAN_FEASIBILITY_JSON, PLAN_FEASIBILITY_HTML, DEGRADATION_OPTIONS_JSON, REVISION_SUGGESTIONS_JSON, REVISION_SUGGESTIONS_MD, SCOPE_DECISION_JSON])
    return {
        "status": "written",
        "project_path": str(state.path),
        "decision": decision,
        "research_plan_feasibility_report": str(state.path / PLAN_FEASIBILITY_JSON),
        "research_degradation_options": str(state.path / DEGRADATION_OPTIONS_JSON),
        "recommended_next_action": report["recommended_next_action"],
    }


def revise_research_plan(project: str | Path) -> dict[str, Any]:
    state = load_project(project)
    report = read_json(state.path / PLAN_FEASIBILITY_JSON, {})
    if not report:
        report = read_json(state.path / PREFLIGHT_JSON, {})
    if not report:
        raise ResearchFeasibilityError("No research feasibility report exists. Run preflight-research-feasibility or assess-research-plan-feasibility first.")
    suggestions = {
        "status": "written",
        "generated_at": utc_now(),
        "source_report_decision": report.get("decision"),
        "revision_mode": "scope_level_revision_packet",
        "instructions": [
            "Revise the research question before data/method/code generation if main figures cannot be supported.",
            "Prefer data acquisition or method repair first; lower claims only when required roles cannot be supplied.",
            "Do not replace a failed main-result figure with a workflow diagram or unrelated validation plot.",
        ],
        "degradation_options": report.get("degradation_options") or [],
    }
    _write_json(state.path / REVISION_SUGGESTIONS_JSON, suggestions)
    (state.path / REVISION_SUGGESTIONS_MD).write_text(_render_revision_suggestions_md(suggestions), encoding="utf-8")
    _write_json(state.path / SCOPE_DECISION_JSON, {
        "status": "written",
        "generated_at": utc_now(),
        "scope_level": "requires_user_or_codex_research_plan_revision",
        "requires_user_confirmation": True,
        "next_action": "generate-plan after revising idea/data/method scope",
    })
    return {
        "status": "written",
        "project_path": str(state.path),
        "research_plan_revision_suggestions": str(state.path / REVISION_SUGGESTIONS_JSON),
        "research_plan_revision_suggestions_md": str(state.path / REVISION_SUGGESTIONS_MD),
        "research_scope_decision": str(state.path / SCOPE_DECISION_JSON),
    }


def _render_revision_suggestions_md(suggestions: dict[str, Any]) -> str:
    lines = [
        "# Research Plan Revision Suggestions",
        "",
        f"Source decision: `{suggestions.get('source_report_decision')}`",
        "",
        "## Revision Policy",
        "",
    ]
    for item in suggestions.get("instructions") or []:
        lines.append(f"- {item}")
    lines.extend(["", "## Data/Method Repair Before Scope Reduction", ""])
    options = suggestions.get("degradation_options") or []
    if not options:
        lines.append("No degradation option was reported. Keep the original research scope.")
    for option in options:
        lines.extend([
            f"### {option.get('missing_role') or option.get('level') or 'scope item'}",
            "",
            f"- Level: `{option.get('level') or 'unspecified'}`",
            f"- Stage: `{option.get('stage') or 'unspecified'}`",
            f"- First action: {option.get('recommendation') or 'Repair data or methods before rewriting the plan.'}",
            f"- Scope fallback: {option.get('fallback') or 'Narrow the affected research claim only after repair fails.'}",
            "",
        ])
    lines.extend([
        "## Required Next Step",
        "",
        "Run `prepare-data-acquisition` or `assess-method-feasibility` when repair is possible. Use `generate-plan` again only after the research scope, data availability, and method feasibility are aligned.",
        "",
    ])
    return "\n".join(lines)


def _figure_assessments(storyboard: dict[str, Any], available_roles: list[str], method_roles: list[str]) -> list[dict[str, Any]]:
    assessments: list[dict[str, Any]] = []
    for index, item in enumerate(storyboard.get("figures") or [], start=1):
        if not isinstance(item, dict):
            continue
        figure_id = str(item.get("figure_id") or item.get("id") or f"figure_{index}")
        required_data = []
        required_data.extend(item.get("required_data") or [])
        required_data.extend(item.get("required_data_roles") or [])
        required_method = [str(value) for value in (item.get("required_method") or item.get("required_method_roles") or [])]
        data_coverage = assess_role_coverage(required_data, available_roles)
        missing_methods = [role for role in required_method if role and role not in method_roles]
        if data_coverage["blocking_missing_roles"]:
            feasibility = "blocked"
            repair_route = "prepare-data-acquisition"
        elif missing_methods:
            feasibility = "conditional"
            repair_route = "assess-method-feasibility"
        else:
            feasibility = "pass" if data_coverage["decision"] == "pass" else "conditional"
            repair_route = "plan-figures"
        assessments.append({
            "figure_id": figure_id,
            "title": item.get("title"),
            "scientific_question": item.get("scientific_question") or item.get("research_question"),
            "expected_finding": item.get("expected_finding"),
            "required_data_roles": data_coverage["required_roles"],
            "missing_data_roles": data_coverage["missing_roles"],
            "required_method_roles": required_method,
            "missing_method_roles": missing_methods,
            "feasibility": feasibility,
            "repair_route": repair_route,
            "degradation_option": _figure_degradation(figure_id, data_coverage["missing_roles"], missing_methods),
        })
    return assessments


def _figure_degradation(figure_id: str, missing_data: list[str], missing_methods: list[str]) -> str:
    missing = missing_data + missing_methods
    if not missing:
        return ""
    return f"{figure_id}: supply {', '.join(missing)} or revise the research plan so this main result is narrowed before figure/code generation."


def _degradation_options(coverage: dict[str, Any], *, stage: str, figures: list[dict[str, Any]] | None = None) -> list[dict[str, str]]:
    options: list[dict[str, str]] = []
    for role in coverage.get("missing_roles") or []:
        options.append({
            "level": "data_or_method_repair_first",
            "missing_role": role,
            "stage": stage,
            "recommendation": "Try connector-based data acquisition or method repair before reducing the research claim.",
            "fallback": "If the role cannot be supplied, narrow the affected research question and remove dependent main-figure claims from the plan.",
        })
    for item in figures or []:
        if item.get("degradation_option"):
            options.append({"level": "figure_scope_revision", "missing_role": item.get("figure_id", "figure"), "stage": stage, "recommendation": item["degradation_option"], "fallback": "Revise research_plan, then regenerate figure_storyboard."})
    if not options:
        options.append({"level": "level_0", "missing_role": "none", "stage": stage, "recommendation": "Proceed with the planned research scope.", "fallback": "No scope degradation is required."})
    return options


def _scope_level(decision: str, coverage: dict[str, Any], figures: list[dict[str, Any]]) -> str:
    if decision == "pass":
        return "level_0_original_plan_executable"
    if coverage.get("missing_roles") or any(item.get("missing_data_roles") for item in figures):
        return "level_1_data_supplement_required"
    if any(item.get("missing_method_roles") for item in figures):
        return "level_2_method_supplement_required"
    if decision == "blocked":
        return "level_3_research_scope_must_be_narrowed"
    return "level_1_or_2_conditional_execution"


def _render_report_md(title: str, report: dict[str, Any]) -> str:
    lines = [f"# {title}", "", f"Decision: `{report.get('decision')}`", ""]
    if report.get("recommended_next_action"):
        lines.extend(["## Recommended Next Action", "", f"`{report.get('recommended_next_action')}`", ""])
    if report.get("role_coverage"):
        coverage = report["role_coverage"]
        lines.extend(["## Role Coverage", "", f"Missing roles: `{', '.join(coverage.get('missing_roles') or []) or 'none'}`", ""])
    if report.get("figure_assessments"):
        lines.extend(["## Figure Assessments", ""])
        for item in report.get("figure_assessments") or []:
            lines.append(f"- {item.get('figure_id')}: {item.get('feasibility')} ({item.get('repair_route')})")
    if report.get("degradation_options"):
        lines.extend(["", "## Degradation Options", ""])
        for item in report.get("degradation_options") or []:
            lines.append(f"- {item.get('level')}: {item.get('recommendation')}")
    return "\n".join(lines)


def _set_stage_manifest(project_path: Path, stage: str, inputs: list[str], outputs: list[str]) -> None:
    manifest_path = project_path / stage / "stage_manifest.json"
    if not manifest_path.exists():
        return
    manifest = read_json(manifest_path, {})
    manifest["input_files"] = inputs
    manifest["output_files"] = outputs
    _write_json(manifest_path, manifest)
