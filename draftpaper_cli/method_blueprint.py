# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .discipline import infer_discipline_profile
from .discipline_modules import get_discipline_module
from .html_utils import write_html_report
from .method_plan import MethodPlanError, validate_method_plan_for_methods
from .project_scaffold import _write_json, utc_now
from .project_state import load_project, update_stage_status
from .review_rule_runtime import assess_review_rules, review_rule_validation_checks


METHOD_BLUEPRINT_JSON = "methods/method_blueprint.json"
METHOD_BLUEPRINT_HTML = "methods/method_blueprint.html"
METHOD_DATA_CONTRACT_JSON = "methods/method_data_contract.json"
METHOD_CODE_PLAN_JSON = "methods/method_code_plan.json"
METHOD_FORMULA_PLAN_JSON = "methods/method_formula_plan.json"
METHOD_REVIEW_RULE_GATE_JSON = "methods/method_review_rule_gate.json"

METHOD_BLUEPRINT_OUTPUTS = [
    METHOD_BLUEPRINT_JSON,
    METHOD_BLUEPRINT_HTML,
    METHOD_DATA_CONTRACT_JSON,
    METHOD_CODE_PLAN_JSON,
    METHOD_FORMULA_PLAN_JSON,
    METHOD_REVIEW_RULE_GATE_JSON,
]

DERIVED_METHOD_OUTPUT_ROLES = {
    "predicted_label",
    "prediction_score",
    "prediction_probability",
    "class_support",
    "candidate_score",
    "anomaly_score",
    "residual",
    "model_output",
}

DATA_ROLE_ALIASES = {
    "source_catalog": {"source_catalog"},
    "image_availability": {"image_or_raster_data", "missingness_reason"},
    "valid_image_cohort": {"image_or_raster_data", "features"},
    "missingness_reason": {"missingness_reason"},
    "image_embedding": {"features"},
    "independent_target": {"label_or_response"},
    "confounder_variables": {"confounder_variables"},
    "group_validation_split": {"sample_group", "validation_design"},
    "class_label": {"label_or_response"},
    "catalog_baseline_features": {"tabular_data", "confounder_variables"},
    "image_cutout": {"image_or_raster_data"},
    "quality_flags": {"quality_flags"},
}


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
        aliases = DATA_ROLE_ALIASES.get(role, {role})
        if not (aliases & concrete) and f"missing:{role}" not in available:
            missing.append(role)
    return missing


def _tokenize(text: Any) -> set[str]:
    return {token for token in re.split(r"[^a-z0-9]+", str(text or "").lower()) if len(token) >= 3}


def _template_search_text(template: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ["template_id", "display_name", "discipline", "method_family"]:
        parts.append(str(template.get(key) or ""))
    for key in ["input_roles", "optional_roles", "figure_groups", "formula_families", "validation_checks", "aliases", "variants"]:
        value = template.get(key)
        if isinstance(value, list):
            parts.extend(str(item) for item in value)
    return " ".join(parts)


def _context_search_text(context: dict[str, Any]) -> str:
    pieces = [json.dumps(context.get("method_requirements") or {}, ensure_ascii=False, default=str)]
    storyboard = context.get("research_storyboard") if isinstance(context.get("research_storyboard"), dict) else {}
    method_plan = context.get("research_method_plan") if isinstance(context.get("research_method_plan"), dict) else {}
    pieces.append(json.dumps(storyboard.get("figures") or [], ensure_ascii=False, default=str))
    pieces.append(json.dumps(method_plan.get("method_tasks") or [], ensure_ascii=False, default=str))
    review_tasks = context.get("review_tasks") if isinstance(context.get("review_tasks"), dict) else {}
    pieces.append(json.dumps(review_tasks.get("tasks") or [], ensure_ascii=False, default=str))
    pieces.append(str(context.get("research_plan_excerpt") or ""))
    return " ".join(pieces)


def _select_method_templates(
    hints: dict[str, Any],
    context: dict[str, Any],
    *,
    max_templates: int = 8,
    strict_contract: bool = False,
) -> list[dict[str, Any]]:
    templates = [dict(item) for item in hints.get("method_template_hints") or [] if isinstance(item, dict)]
    if not templates:
        return []
    context_text = _context_search_text(context)
    context_tokens = _tokenize(context_text)
    requested_families = {
        str(item).lower()
        for item in (context.get("method_requirements") or {}).get("method_families") or []
    }
    scored: list[tuple[int, int, dict[str, Any]]] = []
    for index, template in enumerate(templates):
        template_text = _template_search_text(template)
        template_tokens = _tokenize(template_text)
        score = len(context_tokens & template_tokens)
        family = str(template.get("method_family") or "").lower()
        template_id = str(template.get("template_id") or "").lower()
        exact_contract_match = family in requested_families or template_id in requested_families
        if exact_contract_match:
            score += 8
        for alias in template.get("aliases") or []:
            alias_text = str(alias).lower()
            if alias_text and alias_text in context_text.lower():
                score += 5
        for group in template.get("figure_groups") or []:
            if str(group).lower().replace("_", " ") in context_text.lower().replace("_", " "):
                score += 4
        if score > 0 and (exact_contract_match or not strict_contract):
            scored.append((score, -index, template))
    if not scored:
        if strict_contract:
            return []
        primary_module = str((context.get("metadata") or {}).get("field") or "").lower()
        primary_matches = [template for template in templates if str(template.get("discipline") or "").lower() in primary_module]
        return primary_matches[:max_templates] if primary_matches else templates[: min(3, len(templates))]
    scored.sort(reverse=True, key=lambda item: (item[0], item[1]))
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for _, _, template in scored:
        template_id = str(template.get("template_id") or "")
        if template_id in seen:
            continue
        selected.append(template)
        seen.add(template_id)
        if len(selected) >= max_templates:
            break
    return selected


def _selected_template_values(templates: list[dict[str, Any]], key: str) -> list[str]:
    values: list[str] = []
    for template in templates:
        raw = template.get(key)
        if isinstance(raw, list):
            candidates = raw
        elif raw:
            candidates = [raw]
        else:
            candidates = []
        for item in candidates:
            text = str(item).strip()
            if text and text not in values:
                values.append(text)
    return values


def _formula_families_from_method_contract(method_families: list[str]) -> list[str]:
    """Derive formula roles from explicit methods when no reusable template is bound."""
    joined = " ".join(method_families).lower()
    rules = [
        ("coverage_rate", ("cohort", "missingness", "coverage")),
        ("principal_component_projection", ("representation_projection", "embedding")),
        ("multinomial_logistic_regression", ("baseline", "classification", "group_aware_validation")),
        ("balanced_accuracy", ("class_imbalance", "group_aware_validation", "confusion")),
        ("macro_f1", ("class_imbalance", "group_aware_validation", "confusion")),
        ("fold_dispersion_or_confidence_interval", ("uncertainty", "cross_validation")),
        ("incremental_metric_delta", ("ablation", "incremental", "confounder")),
        ("anomaly_score", ("anomaly", "candidate_score")),
        ("set_stability_jaccard", ("stability", "candidate")),
    ]
    return [name for name, triggers in rules if any(trigger in joined for trigger in triggers)]


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
    selected = code_plan.get("selected_method_templates") or []
    if selected:
        lines.append("Selected method templates: " + ", ".join(str(item) for item in selected))
        lines.append("")
    for family in code_plan.get("method_families") or []:
        lines.append(f"- {family}")
    lines.extend(["", "## Validation Checks", ""])
    for check in code_plan.get("validation_checks") or []:
        lines.append(f"- {check}")
    review_gate = blueprint.get("review_rule_gate_plan") or {}
    lines.extend(["", "## Review Rule Gate Plan", ""])
    lines.append(f"Decision: {review_gate.get('decision', 'not_assessed')}")
    lines.append("")
    for assessment in review_gate.get("rule_assessments") or []:
        lines.append(
            f"- {assessment.get('rule_id', 'review_rule')}: "
            f"{assessment.get('decision', 'unknown')} "
            f"({assessment.get('runtime_level', 'advisory')})"
        )
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
    role_coverage = _read_json(state.path / "data" / "data_role_coverage_report.json", {})
    acquisition_plan = _read_json(state.path / "data" / "data_acquisition_plan.json", {})
    review_tasks = _read_json(state.path / "review" / "actionable_analysis_tasks.json", {})
    research_storyboard = _read_json(state.path / "research_plan" / "figure_storyboard.json", {})
    research_method_plan = _read_json(state.path / "research_plan" / "method_plan.json", {})
    plugin_binding_plan = _read_json(state.path / "research_plan" / "plugin_binding_plan.json", {})
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
    review_rule_gate = assess_review_rules(state.path, stage="method_plan")
    available_roles = _available_data_roles(inventory, acquisition_plan)
    for role in role_coverage.get("available_roles") or []:
        value = str(role).strip()
        if value and value not in available_roles:
            available_roles.append(value)
    method_tasks = list(research_method_plan.get("method_tasks") or []) if isinstance(research_method_plan, dict) else []
    has_structured_method_contract = bool(method_tasks)
    bound_method_ids = {
        str(item.get("plugin_id"))
        for item in plugin_binding_plan.get("bindings") or []
        if isinstance(item, dict) and item.get("kind") == "method" and item.get("state") == "covered" and item.get("plugin_id")
    }
    selected_templates = [
        item for item in hints.get("method_template_hints") or []
        if isinstance(item, dict) and str(item.get("template_id") or "") in bound_method_ids
    ] if bound_method_ids else _select_method_templates(
        hints,
        context,
        strict_contract=has_structured_method_contract,
    )
    selected_roles = _selected_template_values(selected_templates, "input_roles")
    structured_required_roles = list(dict.fromkeys(
        str(role).strip()
        for task in method_tasks
        if isinstance(task, dict)
        for role in task.get("required_data") or []
        if str(role).strip() and str(role).strip().lower() not in DERIVED_METHOD_OUTPUT_ROLES
    ))
    required_roles = (
        structured_required_roles
        if has_structured_method_contract
        else selected_roles or list(hints.get("data_contract_hints") or [])
    )
    missing_roles = _missing_roles(required_roles, available_roles)
    selected_method_families = _selected_template_values(selected_templates, "method_family")
    selected_template_ids = _selected_template_values(selected_templates, "template_id")
    method_families = list(dict.fromkeys(list(requirements.get("method_families") or []) + selected_method_families + selected_template_ids))
    if not method_families:
        method_families = list(hints.get("method_code_hints") or [])
    storyboard_validation_checks = [
        str(task.get("validation_metric")).strip()
        for task in method_tasks
        if isinstance(task, dict) and str(task.get("validation_metric") or "").strip()
    ]
    validation_checks = list(dict.fromkeys(
        (_selected_template_values(selected_templates, "validation_checks")
         or storyboard_validation_checks
         if has_structured_method_contract
         else list(hints.get("validation_hints") or []))
        + review_rule_validation_checks(review_rule_gate)
    ))
    storyboard_figure_families = [
        str(item.get("suggested_plot_type")).strip()
        for item in research_storyboard.get("figures") or []
        if isinstance(item, dict) and str(item.get("suggested_plot_type") or "").strip()
    ] if isinstance(research_storyboard, dict) else []
    figure_families = list(dict.fromkeys(
        _selected_template_values(selected_templates, "figure_groups")
        or storyboard_figure_families
        if has_structured_method_contract
        else list(hints.get("figure_hints") or [])
    ))
    formula_families = list(dict.fromkeys(
        (
            _selected_template_values(selected_templates, "formula_families")
            or _formula_families_from_method_contract(method_families)
        )
        if has_structured_method_contract
        else list(hints.get("formula_hints") or [])
    ))
    method_data_contract = {
        "status": "conditional" if missing_roles else "ready",
        "required_roles": required_roles,
        "available_roles": available_roles,
        "missing_roles": missing_roles,
        "selected_input_hint": ((inventory.get("files") or [{}])[0].get("path") if isinstance(inventory, dict) and inventory.get("files") else ""),
        "data_to_method_principle": "Data artifacts must enter method code through declared roles before any figure or claim is generated.",
        "selection_policy": "Required roles are taken from method templates selected for this research plan, not from the full composite discipline catalog.",
        "structured_contract_precedence": has_structured_method_contract,
    }
    method_code_plan = {
        "status": "planned",
        "method_families": method_families,
        "validation_checks": validation_checks,
        "figure_families": figure_families,
        "selected_method_templates": selected_template_ids,
        "plugin_binding_plan": "research_plan/plugin_binding_plan.json" if plugin_binding_plan else None,
        "bound_method_plugin_ids": sorted(bound_method_ids),
        "storyboard_method_tasks": list(research_method_plan.get("method_tasks") or []) if isinstance(research_method_plan, dict) else [],
        "storyboard_figures": list(research_storyboard.get("figures") or []) if isinstance(research_storyboard, dict) else [],
        "figure_policy": hints.get("figure_policy") or {},
        "code_generation_constraints": list(hints.get("code_generation_constraints") or []),
        "stage_owned_code_locations": ["methods/scripts", "methods/src"],
        "compatibility_locations": ["code/scripts", "code/src"],
        "review_rule_gate_decision": review_rule_gate.get("decision"),
        "review_rule_validation_checks": review_rule_validation_checks(review_rule_gate),
    }
    method_formula_plan = {
        "status": "planned",
        "formula_families": formula_families,
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
        "selected_method_template_hints": selected_templates,
        "review_rule_hints": hints.get("review_rule_hints") or [],
        "review_rule_gate_plan": review_rule_gate,
        "plugin_binding_plan": plugin_binding_plan,
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
    _write_json(state.path / METHOD_REVIEW_RULE_GATE_JSON, review_rule_gate)
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
