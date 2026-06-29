# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .discipline import infer_discipline_profile
from .discipline_modules import get_discipline_module
from .html_utils import write_html_report
from .method_plan import MethodPlanError, validate_method_plan_for_methods
from .project_scaffold import _write_json, utc_now
from .project_state import load_project, update_stage_status


METHOD_BLUEPRINT_JSON = "methods/method_blueprint.json"
METHOD_BLUEPRINT_HTML = "methods/method_blueprint.html"
METHOD_DATA_CONTRACT_JSON = "methods/method_data_contract.json"
METHOD_CODE_PLAN_JSON = "methods/method_code_plan.json"
METHOD_FORMULA_PLAN_JSON = "methods/method_formula_plan.json"

METHOD_BLUEPRINT_OUTPUTS = [
    METHOD_BLUEPRINT_JSON,
    METHOD_BLUEPRINT_HTML,
    METHOD_DATA_CONTRACT_JSON,
    METHOD_CODE_PLAN_JSON,
    METHOD_FORMULA_PLAN_JSON,
]


class MethodBlueprintError(RuntimeError):
    """Raised when method blueprint generation cannot run."""


def _read_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return fallback


def _read_text(path: Path, limit: int = 4000) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    text = " ".join(text.split())
    return text[:limit]


def _available_data_roles(inventory: dict[str, Any], acquisition: dict[str, Any]) -> list[str]:
    roles: list[str] = []
    files = inventory.get("files") if isinstance(inventory, dict) else []
    if files:
        roles.append("analysis_ready_table")
    columns = " ".join(
        " ".join(str(column).lower() for column in item.get("columns") or [])
        for item in files or []
        if isinstance(item, dict)
    )
    role_rules = {
        "spatial_group_or_coordinates": ["lat", "lon", "longitude", "latitude", "x_coord", "y_coord", "region", "province", "county", "grid"],
        "temporal_window": ["year", "date", "time", "season", "month"],
        "target_or_response": ["target", "yield", "response", "label", "class", "outcome"],
        "predictors": ["ndvi", "feature", "temperature", "precip", "covariate", "hardness", "flux"],
        "quality_flag": ["quality", "qc", "flag", "cloud", "mask"],
        "class_label": ["label", "class", "target", "source_class"],
    }
    for role, terms in role_rules.items():
        if any(term in columns for term in terms) and role not in roles:
            roles.append(role)
    for task in ((acquisition.get("data_acquisition_tasks") or {}).get("tasks") or []):
        for role in task.get("needed_data") or []:
            marker = f"missing:{role}"
            if marker not in roles:
                roles.append(marker)
    return roles


def _missing_roles(required: list[str], available: list[str]) -> list[str]:
    concrete = {role for role in available if not role.startswith("missing:")}
    missing = []
    for role in required:
        if role not in concrete and f"missing:{role}" not in available:
            missing.append(role)
    return missing


def _render_blueprint_markdown(blueprint: dict[str, Any]) -> str:
    module = blueprint.get("discipline_module") or {}
    lines = [
        "# Method Blueprint",
        "",
        f"Status: {blueprint.get('status')}",
        "",
        f"Discipline: {(blueprint.get('discipline_profile') or {}).get('discipline', 'default')}",
        "",
        f"Module: {module.get('display_name', module.get('module_id', 'default'))}",
        "",
        "## Data Contract",
        "",
    ]
    contract = blueprint.get("method_data_contract") or {}
    lines.append(f"Available roles: {', '.join(contract.get('available_roles') or []) or 'none'}")
    lines.append("")
    lines.append(f"Missing roles: {', '.join(contract.get('missing_roles') or []) or 'none'}")
    lines.extend(["", "## Method Code Plan", ""])
    code_plan = blueprint.get("method_code_plan") or {}
    for family in code_plan.get("method_families") or []:
        lines.append(f"- {family}")
    lines.extend(["", "## Validation Checks", ""])
    for check in code_plan.get("validation_checks") or []:
        lines.append(f"- {check}")
    lines.extend(["", "## Figure Families", ""])
    for figure in code_plan.get("figure_families") or []:
        lines.append(f"- {figure}")
    lines.extend(["", "## Formula Families", ""])
    for formula in (blueprint.get("method_formula_plan") or {}).get("formula_families") or []:
        lines.append(f"- {formula}")
    return "\n".join(lines)


def _set_method_plan_manifest(project_path: Path) -> None:
    manifest_path = project_path / "method_plan" / "stage_manifest.json"
    if not manifest_path.exists():
        return
    manifest = _read_json(manifest_path, {})
    outputs = list(manifest.get("output_files") or [])
    for relative in METHOD_BLUEPRINT_OUTPUTS:
        if relative not in outputs:
            outputs.append(relative)
    manifest["output_files"] = outputs
    _write_json(manifest_path, manifest)


def prepare_method_blueprint(project: str | Path) -> dict[str, Any]:
    state = load_project(project)
    try:
        requirements = validate_method_plan_for_methods(state.path)
    except MethodPlanError as exc:
        raise MethodBlueprintError(str(exc)) from exc
    discipline_profile = infer_discipline_profile(state.path)
    module = get_discipline_module(discipline_profile)
    inventory = _read_json(state.path / "data" / "data_inventory.json", {})
    acquisition_plan = _read_json(state.path / "data" / "data_acquisition_plan.json", {})
    review_tasks = _read_json(state.path / "review" / "actionable_analysis_tasks.json", {})
    research_storyboard = _read_json(state.path / "research_plan" / "figure_storyboard.json", {})
    research_method_plan = _read_json(state.path / "research_plan" / "method_plan.json", {})
    context = {
        "metadata": state.metadata,
        "method_requirements": requirements,
        "inventory": inventory,
        "data_acquisition_plan": acquisition_plan,
        "review_tasks": review_tasks,
        "research_storyboard": research_storyboard,
        "research_method_plan": research_method_plan,
        "research_plan_excerpt": _read_text(state.path / "research_plan" / "research_plan.md"),
    }
    hints = module.method_blueprint_hints(context)
    available_roles = _available_data_roles(inventory, acquisition_plan)
    required_roles = list(hints.get("data_contract_hints") or [])
    missing_roles = _missing_roles(required_roles, available_roles)
    method_families = list(dict.fromkeys(list(requirements.get("method_families") or []) + list(hints.get("method_code_hints") or [])))
    method_data_contract = {
        "status": "conditional" if missing_roles else "ready",
        "required_roles": required_roles,
        "available_roles": available_roles,
        "missing_roles": missing_roles,
        "selected_input_hint": ((inventory.get("files") or [{}])[0].get("path") if isinstance(inventory, dict) and inventory.get("files") else ""),
        "data_to_method_principle": "Data artifacts must enter method code through declared roles before any figure or claim is generated.",
    }
    method_code_plan = {
        "status": "planned",
        "method_families": method_families,
        "validation_checks": list(hints.get("validation_hints") or []),
        "figure_families": list(hints.get("figure_hints") or []),
        "storyboard_method_tasks": list(research_method_plan.get("method_tasks") or []) if isinstance(research_method_plan, dict) else [],
        "storyboard_figures": list(research_storyboard.get("figures") or []) if isinstance(research_storyboard, dict) else [],
        "figure_policy": hints.get("figure_policy") or {},
        "code_generation_constraints": list(hints.get("code_generation_constraints") or []),
        "stage_owned_code_locations": ["methods/scripts", "methods/src"],
        "compatibility_locations": ["code/scripts", "code/src"],
    }
    method_formula_plan = {
        "status": "planned",
        "formula_families": list(hints.get("formula_hints") or []),
        "source": "discipline_module_and_verified_method_outputs",
    }
    blueprint = {
        "status": "written",
        "generated_at": utc_now(),
        "generator": "draftpaper_cli.method_blueprint.prepare_method_blueprint",
        "project_id": state.metadata.get("project_id"),
        "discipline_profile": discipline_profile,
        "discipline_module": module.spec.as_dict(),
        "method_requirements": requirements,
        "research_storyboard": research_storyboard if isinstance(research_storyboard, dict) else {},
        "research_method_plan": research_method_plan if isinstance(research_method_plan, dict) else {},
        "method_data_contract": method_data_contract,
        "method_code_plan": method_code_plan,
        "method_formula_plan": method_formula_plan,
        "data_acquisition_hints": hints.get("data_acquisition_hints") or [],
        "method_template_hints": hints.get("method_template_hints") or [],
        "review_rule_hints": hints.get("review_rule_hints") or [],
        "composite_discipline": hints.get("composite_discipline") or {},
        "review_task_count": len(review_tasks.get("tasks") or []) if isinstance(review_tasks, dict) else 0,
        "next_command": f'python -m draftpaper_cli.cli generate-analysis-code --project "{state.path}"',
    }
    methods_dir = state.path / "methods"
    methods_dir.mkdir(parents=True, exist_ok=True)
    _write_json(state.path / METHOD_BLUEPRINT_JSON, blueprint)
    write_html_report(state.path / METHOD_BLUEPRINT_HTML, _render_blueprint_markdown(blueprint), title="Method Blueprint")
    _write_json(state.path / METHOD_DATA_CONTRACT_JSON, method_data_contract)
    _write_json(state.path / METHOD_CODE_PLAN_JSON, method_code_plan)
    _write_json(state.path / METHOD_FORMULA_PLAN_JSON, method_formula_plan)
    _set_method_plan_manifest(state.path)
    update_stage_status(state.path, "method_plan", "draft")
    return {
        "status": "written",
        "project_path": str(state.path),
        "discipline": discipline_profile.get("discipline"),
        "primary_discipline": discipline_profile.get("primary_discipline"),
        "secondary_disciplines": discipline_profile.get("secondary_disciplines") or [],
        "method_blueprint": str(state.path / METHOD_BLUEPRINT_JSON),
        "method_blueprint_html": str(state.path / METHOD_BLUEPRINT_HTML),
        "method_data_contract": str(state.path / METHOD_DATA_CONTRACT_JSON),
        "method_code_plan": str(state.path / METHOD_CODE_PLAN_JSON),
        "method_formula_plan": str(state.path / METHOD_FORMULA_PLAN_JSON),
        "missing_roles": missing_roles,
        "next_command": blueprint["next_command"],
    }
