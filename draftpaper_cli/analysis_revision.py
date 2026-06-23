# Copyright (c) 2026 xiejhhhhhh
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .html_utils import write_html_report
from .project_scaffold import _write_json, utc_now
from .project_state import load_project, mark_stage_stale


ACTIONABLE_TASKS_JSON = "review/actionable_analysis_tasks.json"
ANALYSIS_REVISION_FEASIBILITY_JSON = "review/analysis_revision_feasibility.json"
ANALYSIS_REVISION_FEASIBILITY_HTML = "review/analysis_revision_feasibility.html"
ANALYSIS_REVISION_REQUIREMENTS_JSON = "methods/analysis_revision_requirements.json"
REVISION_FIGURE_PLAN_DELTA_JSON = "results/revision_figure_plan_delta.json"


class AnalysisRevisionError(RuntimeError):
    """Raised when review/rescue suggestions cannot be prepared for analysis reruns."""


ROLE_ALIASES: dict[str, tuple[str, ...]] = {
    "target": ("yield", "production", "suitability", "response", "label", "class", "biomass", "output"),
    "predictors": (
        "ndvi",
        "vegetation",
        "index",
        "temperature",
        "temp",
        "climate",
        "precip",
        "rain",
        "nitrogen",
        "soil",
        "feature",
        "predictor",
    ),
    "spatial_group_or_coordinates": (
        "longitude",
        "latitude",
        "lon",
        "lat",
        "region",
        "province",
        "county",
        "zone",
        "field",
        "plot",
        "grid",
        "spatial",
    ),
    "time": ("year", "date", "time", "month", "season", "doy", "phenology", "stage"),
    "quality_flag": ("quality", "qc", "cloud", "mask", "flag", "valid", "saturation"),
    "class_label": ("class", "label", "category", "type", "species"),
    "group": ("group", "region", "zone", "field", "plot", "site", "station", "cultivar", "management"),
}


ACTION_LIBRARY: dict[str, dict[str, Any]] = {
    "agricultural_remote_sensing_feature_rebuild": {
        "source_codes": {
            "agricultural_remote_sensing_feature_rebuild",
            "geography_weak_fit_qc",
        },
        "discipline": "geography",
        "target_stage": "methods",
        "required_data_roles": ["target", "predictors"],
        "optional_data_roles": ["time", "spatial_group_or_coordinates", "quality_flag"],
        "figure_plan_hints": [
            "raw_vs_cleaned_remote_sensing_distribution",
            "phenology_or_feature_response_curve",
            "weak_effect_before_after_qc",
        ],
        "code_generation_hints": [
            "derive phenology-aware NDVI or vegetation-index features when temporal fields exist",
            "compare raw, cleaned, robust, and feature-rebuilt analyses",
            "write before/after metrics for result-validity comparison",
        ],
        "success_criteria": [
            "feature-rebuilt metrics exist",
            "before/after QC figure metadata exist",
        ],
        "fallback_if_missing": "If target or predictor columns are missing, ask the user for processed tables that include response and remote-sensing predictors.",
    },
    "agricultural_remote_sensing_qc_rebuild": {
        "source_codes": {
            "agricultural_remote_sensing_qc_rebuild",
            "weak_effect_data_quality_audit",
            "geography_remote_sensing_qc",
        },
        "discipline": "geography",
        "target_stage": "data",
        "required_data_roles": ["target", "predictors"],
        "optional_data_roles": ["time", "spatial_group_or_coordinates", "quality_flag"],
        "partial_without_roles": ["quality_flag"],
        "figure_plan_hints": [
            "raw_vs_cleaned_remote_sensing_distribution",
            "outlier_and_missingness_qc_panel",
            "qc_effect_on_primary_relationship",
        ],
        "code_generation_hints": [
            "screen impossible vegetation-index and response values before modeling",
            "compare complete-case, range-filtered, and robust variants",
            "record missingness and outlier decisions in metrics and summary tables",
        ],
        "success_criteria": [
            "data QC summary table exists",
            "raw-vs-cleaned comparison figure exists",
        ],
        "fallback_if_missing": "If quality flags are missing, run range, missingness, and outlier QC and ask the user whether sensor/cloud flags can be supplied.",
    },
    "spatial_block_validation": {
        "source_codes": {
            "spatial_ecological_validation",
            "spatial_data_quality_audit",
            "geography_spatial_autocorrelation",
            "geography_spatial_scale_alignment",
        },
        "discipline": "geography",
        "target_stage": "methods",
        "required_data_roles": ["target", "predictors", "spatial_group_or_coordinates"],
        "optional_data_roles": ["time", "group"],
        "figure_plan_hints": [
            "random_vs_spatial_block_validation",
            "spatial_or_regional_residual_diagnostic",
        ],
        "code_generation_hints": [
            "prefer region/group holdout when coordinates are unavailable",
            "compare random split metrics with grouped or spatially blocked validation metrics",
        ],
        "success_criteria": [
            "blocked validation metric exists",
            "random-vs-blocked comparison figure exists",
        ],
        "fallback_if_missing": "Spatial blocking requires coordinates or a scientifically meaningful region, field, grid, or plot identifier.",
    },
    "stratified_heterogeneity_analysis": {
        "source_codes": {"geography_stratified_heterogeneity"},
        "discipline": "geography",
        "target_stage": "methods",
        "required_data_roles": ["target", "predictors"],
        "optional_data_roles": ["time", "group", "spatial_group_or_coordinates"],
        "partial_without_roles": ["time", "group", "spatial_group_or_coordinates"],
        "figure_plan_hints": [
            "stratified_response_by_region_or_year",
            "pooled_vs_stratified_effect_size",
        ],
        "code_generation_hints": [
            "stratify by year, region, crop stage, management zone, or another available scientific group",
            "compare pooled and stratum-specific effect sizes",
        ],
        "success_criteria": ["stratified summary table exists"],
        "fallback_if_missing": "If no grouping or time fields exist, keep only pooled analysis and ask the user for scientifically valid strata.",
    },
    "baseline_ablation": {
        "source_codes": {
            "machine_learning_validation_rebuild",
            "machine_learning_baseline_ablation",
            "result_validity_rebuild",
        },
        "discipline": "generic",
        "target_stage": "methods",
        "required_data_roles": ["target", "predictors"],
        "optional_data_roles": ["group", "time"],
        "figure_plan_hints": ["baseline_vs_rebuilt_model_performance", "feature_group_ablation"],
        "code_generation_hints": [
            "compare simple baselines against rebuilt or proposed methods",
            "drop feature groups to test whether claimed data streams contribute evidence",
        ],
        "success_criteria": ["baseline metric exists", "ablation metric exists"],
        "fallback_if_missing": "Baseline and ablation require at least one target and predictor set.",
    },
}


def _read_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise AnalysisRevisionError(f"{path} is not valid JSON: {exc}") from exc


def _inventory_columns(inventory: dict[str, Any]) -> list[str]:
    columns: list[str] = []
    for item in inventory.get("files") or []:
        if item.get("readable") is False:
            continue
        for column in item.get("columns") or []:
            text = str(column).strip()
            if text and text not in columns:
                columns.append(text)
    return columns


def _data_role_map(inventory: dict[str, Any]) -> dict[str, list[str]]:
    columns = _inventory_columns(inventory)
    role_map: dict[str, list[str]] = {role: [] for role in ROLE_ALIASES}
    for column in columns:
        lowered = column.lower().replace("-", "_")
        for role, aliases in ROLE_ALIASES.items():
            if any(alias in lowered for alias in aliases):
                role_map[role].append(column)
    return {role: values for role, values in role_map.items() if values}


def _source_items(statistical_rescue: dict[str, Any], review_engineering: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for route in statistical_rescue.get("recommended_routes") or []:
        if isinstance(route, dict):
            items.append({
                "source": "statistical_rescue",
                "code": route.get("route_id"),
                "title": route.get("title"),
                "target_stage": route.get("target_stage"),
                "rationale": route.get("rationale"),
                "recommended_actions": route.get("recommended_actions") or [],
            })
    for issue in review_engineering.get("issues") or []:
        if isinstance(issue, dict):
            items.append({
                "source": "review_engineering",
                "code": issue.get("code"),
                "title": issue.get("title"),
                "target_stage": issue.get("target_stage"),
                "rationale": issue.get("reason") or issue.get("rationale"),
                "recommended_actions": issue.get("recommended_actions") or issue.get("recommended_commands") or [],
            })
    return items


def _matched_actions(items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    matched: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        code = str(item.get("code") or "")
        for operation_family, spec in ACTION_LIBRARY.items():
            if code in spec["source_codes"]:
                matched.setdefault(operation_family, []).append(item)
    return matched


def _task_feasibility(spec: dict[str, Any], role_map: dict[str, list[str]]) -> dict[str, Any]:
    required = list(spec.get("required_data_roles") or [])
    optional = list(spec.get("optional_data_roles") or [])
    missing_required = [role for role in required if not role_map.get(role)]
    available_required = {role: role_map.get(role, []) for role in required if role_map.get(role)}
    available_optional = {role: role_map.get(role, []) for role in optional if role_map.get(role)}
    partial_without = [role for role in spec.get("partial_without_roles") or [] if not role_map.get(role)]
    if missing_required:
        status = "blocked_missing_data"
    elif partial_without:
        status = "partial"
    else:
        status = "executable"
    return {
        "status": status,
        "required_roles": required,
        "optional_roles": optional,
        "available_required_roles": available_required,
        "available_optional_roles": available_optional,
        "missing_required_roles": missing_required,
        "missing_optional_roles": [role for role in optional if not role_map.get(role)],
        "partial_without_roles": partial_without,
    }


def _build_task(operation_family: str, spec: dict[str, Any], sources: list[dict[str, Any]], role_map: dict[str, list[str]]) -> dict[str, Any]:
    feasibility = _task_feasibility(spec, role_map)
    source_codes = sorted({str(item.get("code") or "") for item in sources if item.get("code")})
    return {
        "task_id": f"T-{operation_family}",
        "operation_family": operation_family,
        "discipline": spec.get("discipline", "generic"),
        "source_codes": source_codes,
        "sources": sources,
        "target_stage": spec.get("target_stage", "methods"),
        "required_data_roles": list(spec.get("required_data_roles") or []),
        "optional_data_roles": list(spec.get("optional_data_roles") or []),
        "feasibility": feasibility,
        "figure_plan_hints": list(spec.get("figure_plan_hints") or []),
        "code_generation_hints": list(spec.get("code_generation_hints") or []),
        "success_criteria": list(spec.get("success_criteria") or []),
        "fallback_if_missing": spec.get("fallback_if_missing", ""),
    }


def _figure_delta(tasks: list[dict[str, Any]]) -> dict[str, Any]:
    hints = []
    for task in tasks:
        if task.get("feasibility", {}).get("status") == "blocked_missing_data":
            continue
        for hint in task.get("figure_plan_hints") or []:
            if hint not in hints:
                hints.append(hint)
    return {
        "status": "written",
        "generated_at": utc_now(),
        "purpose": "Figure-plan hints derived from reviewer/rescue analysis tasks.",
        "figure_plan_hints": hints,
        "source_task_ids": [task["task_id"] for task in tasks if task.get("feasibility", {}).get("status") != "blocked_missing_data"],
    }


def _requirements(tasks: list[dict[str, Any]], role_map: dict[str, list[str]]) -> dict[str, Any]:
    executable = [task for task in tasks if task.get("feasibility", {}).get("status") in {"executable", "partial"}]
    blocked = [task for task in tasks if task.get("feasibility", {}).get("status") == "blocked_missing_data"]
    return {
        "status": "written",
        "generated_at": utc_now(),
        "purpose": "Method/code-generation requirements derived from reviewer/rescue analysis tasks.",
        "data_role_map": role_map,
        "executable_task_ids": [task["task_id"] for task in executable],
        "blocked_task_ids": [task["task_id"] for task in blocked],
        "operation_families": [task["operation_family"] for task in executable],
        "code_generation_hints": [
            hint
            for task in executable
            for hint in task.get("code_generation_hints") or []
        ],
        "success_criteria": [
            criterion
            for task in executable
            for criterion in task.get("success_criteria") or []
        ],
    }


def _render_feasibility_md(report: dict[str, Any]) -> str:
    lines = [
        "# Analysis Revision Feasibility",
        "",
        f"Status: {report['status']}",
        "",
        f"Executable tasks: {report['executable_task_count']}",
        "",
        f"Partial tasks: {report['partial_task_count']}",
        "",
        f"Blocked tasks: {report['blocked_task_count']}",
        "",
        "## Data Roles",
        "",
    ]
    for role, columns in sorted((report.get("data_role_map") or {}).items()):
        lines.append(f"- {role}: {', '.join(columns)}")
    lines.extend(["", "## Tasks", ""])
    for task in report.get("tasks") or []:
        feasibility = task.get("feasibility") or {}
        lines.extend([
            f"### {task['task_id']}",
            "",
            f"- Operation: {task['operation_family']}",
            f"- Status: {feasibility.get('status')}",
            f"- Sources: {', '.join(task.get('source_codes') or [])}",
        ])
        missing = feasibility.get("missing_required_roles") or []
        if missing:
            lines.append(f"- Missing required roles: {', '.join(missing)}")
            lines.append(f"- Fallback: {task.get('fallback_if_missing')}")
        lines.append("")
    return "\n".join(lines)


def prepare_analysis_revision(project: str | Path) -> dict[str, Any]:
    state = load_project(project)
    project_path = state.path
    inventory = _read_json(project_path / "data" / "data_inventory.json", {})
    if not isinstance(inventory, dict) or not inventory:
        raise AnalysisRevisionError("data/data_inventory.json is required before prepare-analysis-revision.")
    statistical_rescue = _read_json(project_path / "review" / "statistical_rescue_plan.json", {})
    review_engineering = _read_json(project_path / "review" / "review_engineering_plan.json", {})
    if not statistical_rescue and not review_engineering:
        raise AnalysisRevisionError("review/statistical_rescue_plan.json or review/review_engineering_plan.json is required.")

    role_map = _data_role_map(inventory)
    source_items = _source_items(statistical_rescue, review_engineering)
    matched = _matched_actions(source_items)
    if "agricultural_remote_sensing_feature_rebuild" in matched and "baseline_ablation" not in matched:
        matched["baseline_ablation"] = list(matched["agricultural_remote_sensing_feature_rebuild"])
    tasks = [
        _build_task(operation_family, ACTION_LIBRARY[operation_family], sources, role_map)
        for operation_family, sources in sorted(matched.items())
    ]
    executable_count = sum(1 for task in tasks if task["feasibility"]["status"] == "executable")
    partial_count = sum(1 for task in tasks if task["feasibility"]["status"] == "partial")
    blocked_count = sum(1 for task in tasks if task["feasibility"]["status"] == "blocked_missing_data")
    status = "analysis_revision_prepared" if tasks else "no_actionable_analysis_task"
    report = {
        "status": status,
        "generated_at": utc_now(),
        "project_path": str(project_path),
        "data_role_map": role_map,
        "source_item_count": len(source_items),
        "task_count": len(tasks),
        "executable_task_count": executable_count,
        "partial_task_count": partial_count,
        "blocked_task_count": blocked_count,
        "tasks": tasks,
        "next_command": f'python -m draftpaper_cli.cli plan-figures --project "{project_path}" --use-review-tasks',
    }

    review_dir = project_path / "review"
    methods_dir = project_path / "methods"
    results_dir = project_path / "results"
    for directory in (review_dir, methods_dir, results_dir):
        directory.mkdir(parents=True, exist_ok=True)
    _write_json(project_path / ACTIONABLE_TASKS_JSON, report)
    _write_json(project_path / ANALYSIS_REVISION_FEASIBILITY_JSON, report)
    _write_json(project_path / ANALYSIS_REVISION_REQUIREMENTS_JSON, _requirements(tasks, role_map))
    _write_json(project_path / REVISION_FIGURE_PLAN_DELTA_JSON, _figure_delta(tasks))
    write_html_report(project_path / ANALYSIS_REVISION_FEASIBILITY_HTML, _render_feasibility_md(report), title="Analysis Revision Feasibility")
    if executable_count or partial_count:
        mark_stage_stale(project_path, "figure_plan", include_self=True)
    return report


__all__ = [
    "ACTIONABLE_TASKS_JSON",
    "ANALYSIS_REVISION_FEASIBILITY_JSON",
    "ANALYSIS_REVISION_FEASIBILITY_HTML",
    "ANALYSIS_REVISION_REQUIREMENTS_JSON",
    "REVISION_FIGURE_PLAN_DELTA_JSON",
    "AnalysisRevisionError",
    "prepare_analysis_revision",
]
