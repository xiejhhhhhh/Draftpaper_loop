# Copyright (c) 2026 xiejhhhhhh
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .html_utils import write_html_report
from .method_plan import MethodPlanError, validate_method_plan_for_methods
from .project_scaffold import _write_json, utc_now
from .project_state import load_project, update_stage_status


FIGURE_PLAN_INPUTS = [
    "project.json",
    "research_plan/research_plan.md",
    "references/literature_items.json",
    "journal_profile/journal_profile.json",
    "data/data_inventory.json",
    "methods/method_requirements.json",
]

FIGURE_PLAN_OUTPUTS = [
    "results/figure_plan.json",
    "results/figure_plan.html",
]


class FigurePlanError(RuntimeError):
    """Raised when project-specific figure planning cannot proceed."""


def _read_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return fallback


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def _safe_id(text: str, fallback: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", text.lower()).strip("_")
    return cleaned[:48] or fallback


def _scoped_inventory(inventory: dict[str, Any], requirements: dict[str, Any]) -> dict[str, Any]:
    files = list(inventory.get("files") or [])
    if not files:
        return inventory
    user_method = str(requirements.get("user_method") or "").replace("\\", "/").lower()
    mentioned = [
        item for item in files
        if str(item.get("path") or "").replace("\\", "/").lower() in user_method
    ]
    if mentioned:
        scoped = dict(inventory)
        scoped["files"] = mentioned
        return scoped
    processed = [item for item in files if "/processed/" in str(item.get("path") or "").replace("\\", "/").lower()]
    if processed:
        processed.sort(key=lambda item: (int(item.get("row_count") or 0), int(item.get("column_count") or 0)), reverse=True)
        scoped = dict(inventory)
        scoped["files"] = processed[:1]
        return scoped
    files.sort(key=lambda item: (int(item.get("row_count") or 0), int(item.get("column_count") or 0)), reverse=True)
    scoped = dict(inventory)
    scoped["files"] = files[:1]
    return scoped


def _numeric_columns(inventory: dict[str, Any]) -> list[str]:
    columns: list[str] = []
    for item in inventory.get("files") or []:
        for column in item.get("columns") or []:
            text = str(column)
            lowered = text.lower()
            if any(token in lowered for token in ["id", "name", "label", "class", "target"]):
                continue
            if text not in columns:
                columns.append(text)
    return columns[:8]


def _column_lookup(inventory: dict[str, Any]) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for item in inventory.get("files") or []:
        for column in item.get("columns") or []:
            text = str(column)
            lookup[text.lower()] = text
    return lookup


def _match_column(lookup: dict[str, str], tokens: list[str], fallback: str | None = None) -> str | None:
    for key, original in lookup.items():
        normalized = key.replace("_", " ").replace("-", " ")
        if any(token in normalized for token in tokens):
            return original
    return fallback


def _label_columns(inventory: dict[str, Any]) -> list[str]:
    labels: list[str] = []
    for item in inventory.get("files") or []:
        for column in item.get("columns") or []:
            lowered = str(column).lower()
            if any(token in lowered for token in ["target", "label", "class", "category", "type"]):
                labels.append(str(column))
    return labels[:3]


def _selected_data(inventory: dict[str, Any]) -> str:
    files = list(inventory.get("files") or [])
    files.sort(key=lambda item: (int(item.get("row_count") or 0), int(item.get("column_count") or 0)), reverse=True)
    return str((files[0] or {}).get("path") or "data/processed")


def _method_blob(requirements: dict[str, Any], research_plan: str, project_meta: dict[str, Any]) -> str:
    return " ".join([
        project_meta.get("idea", ""),
        project_meta.get("field", ""),
        research_plan,
        " ".join(str(item) for item in requirements.get("method_families") or []),
        str(requirements.get("user_method") or ""),
    ]).lower()


def _artifact_figures(inventory: dict[str, Any]) -> list[dict[str, Any]]:
    figures = []
    for artifact in inventory.get("result_artifacts") or []:
        path = str(artifact.get("path") or "")
        if not path or not path.lower().startswith("results/figures/"):
            continue
        normalized_path = path.replace("\\", "/")
        figures.append({
            "id": _safe_id(Path(path).stem, f"provided_figure_{len(figures) + 1}"),
            "title": Path(path).stem.replace("_", " ").title(),
            "path": normalized_path,
            "generation_mode": "provided_artifact",
            "visualization_type": "provided_figure",
            "required_inputs": [normalized_path],
            "scientific_question": "What result is already supported by the user-provided figure artifact?",
            "caption_draft": f"User-provided result artifact: {Path(path).stem.replace('_', ' ')}.",
            "result_claim_template": (
                f"The supplied figure {normalized_path} provides direct visual evidence; "
                "the Results text must interpret only what is visible in this artifact."
            ),
        })
    return figures


def _add_unique(figures: list[dict[str, Any]], item: dict[str, Any]) -> None:
    paths = {str(existing.get("path")) for existing in figures}
    if item["path"] not in paths:
        figures.append(item)


def _planned_figures(
    *,
    project_meta: dict[str, Any],
    research_plan: str,
    requirements: dict[str, Any],
    inventory: dict[str, Any],
    literature_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    blob = _method_blob(requirements, research_plan, project_meta)
    figure_inventory = _scoped_inventory(inventory, requirements)
    numeric = _numeric_columns(figure_inventory)
    labels = _label_columns(figure_inventory)
    selected_data = _selected_data(figure_inventory)
    lookup = _column_lookup(figure_inventory)
    figures = _artifact_figures(inventory)
    generated_index = 1

    def generated(
        *,
        title: str,
        visualization_type: str,
        question: str,
        claim: str,
        required_columns: list[str] | None = None,
        x: str | None = None,
        y: str | None = None,
        group: str | None = None,
        statistical_transform: list[str] | None = None,
    ) -> None:
        nonlocal generated_index
        figure_id = _safe_id(title, f"figure_{generated_index}")
        generated_index += 1
        _add_unique(figures, {
            "id": figure_id,
            "title": title,
            "path": f"results/figures/{figure_id}.png",
            "generation_mode": "generated_code",
            "figure_type": visualization_type,
            "visualization_type": visualization_type,
            "required_inputs": [selected_data],
            "required_columns": required_columns or [],
            "x": x,
            "y": y,
            "group": group,
            "statistical_transform": statistical_transform or [],
            "backend_preference": ["matplotlib_scienceplots", "matplotlib", "png_stdlib_fallback"],
            "no_flowchart_fallback": True,
            "scientific_question": question,
            "caption_draft": f"{title}.",
            "result_claim_template": claim,
        })

    if any(term in blob for term in ["ndvi", "climate", "suitability", "zoning", "wheat", "yield"]):
        ndvi_col = _match_column(lookup, ["ndvi", "vegetation"], numeric[0] if numeric else None)
        yield_col = _match_column(lookup, ["yield", "production", "potential"], numeric[1] if len(numeric) > 1 else None)
        climate_col = _match_column(lookup, ["temp", "precip", "climate", "rain"], numeric[2] if len(numeric) > 2 else None)
        generated(
            title="NDVI and production-potential relationship",
            visualization_type="scatter_regression",
            question="How is the vegetation index associated with the production-potential or yield proxy across the study units?",
            claim="The relationship figure quantifies the observed association between the vegetation indicator and the production-potential outcome, supporting the direction and strength of the main result.",
            required_columns=[column for column in [ndvi_col, yield_col] if column],
            x=ndvi_col,
            y=yield_col,
            statistical_transform=["pearson_r", "linear_fit", "r2"],
        )
        generated(
            title="Environmental driver response",
            visualization_type="scatter_regression",
            question="Which environmental gradient most strongly explains the suitability or production-potential pattern?",
            claim="The response figure links the leading environmental predictor to the modeled suitability outcome, supporting the interpretation of dominant climatic constraints.",
            required_columns=[column for column in [climate_col, yield_col or ndvi_col] if column],
            x=climate_col,
            y=yield_col or ndvi_col,
            statistical_transform=["pearson_r", "linear_fit", "r2"],
        )
        if len(numeric) >= 3:
            generated(
                title="Predictor correlation structure",
                visualization_type="correlation_heatmap",
                question="Are the main predictor variables redundant or complementary before model interpretation?",
                claim="The correlation heatmap reports the dependence structure among the main predictors and helps constrain interpretation of variable effects.",
                required_columns=numeric[:6],
                statistical_transform=["pearson_correlation_matrix"],
            )
        elif numeric:
            generated(
                title="Primary variable distribution",
                visualization_type="histogram",
                question="What is the empirical distribution of the main measured variable?",
                claim="The distribution figure shows the support and range of the primary variable used in the downstream analysis.",
                required_columns=numeric[:1],
                x=numeric[0],
                statistical_transform=["mean", "range", "histogram"],
            )
    elif any(term in blob for term in ["classification", "classifier", "cnn", "transformer", "tcn", "multimodal", "random forest", "xgboost"]):
        generated(
            title="Class distribution and sample support",
            visualization_type="class_balance",
            question="Are the available labeled samples sufficient and balanced enough to support the classification task?",
            claim="The class-support figure reports the observed sample distribution for the classification task and identifies whether result interpretation should be limited by class imbalance.",
            required_columns=labels[:1],
            group=labels[0] if labels else None,
            statistical_transform=["class_counts", "imbalance_ratio"],
        )
        generated(
            title="Feature space structure",
            visualization_type="scatter_regression",
            question="Do the available features show separable structure relevant to the planned classification method?",
            claim="The feature-structure figure visualizes the leading numeric feature relationships used by the method and supports the interpretation of model-ready signal in the data.",
            required_columns=numeric[:2] + labels[:1],
            x=numeric[0] if numeric else None,
            y=numeric[1] if len(numeric) > 1 else None,
            group=labels[0] if labels else None,
            statistical_transform=["pearson_r", "linear_fit", "r2"],
        )
        generated(
            title="Verified method performance",
            visualization_type="metric_summary",
            question="Does the verified local method run satisfy the expected performance threshold?",
            claim="The performance figure summarizes the verified metric outputs and connects the observed result to the configured result-validity threshold.",
            required_columns=[],
            statistical_transform=["metric_summary"],
        )
    else:
        generated(
            title="Data evidence overview",
            visualization_type="histogram" if numeric else "class_balance",
            question="What local or processed data evidence is available for the planned study?",
            claim="The data-evidence overview summarizes the available observations, variables, and local artifacts that bound the strength of downstream claims.",
            required_columns=numeric[:2] + labels[:1],
            x=numeric[0] if numeric else None,
            group=labels[0] if labels else None,
            statistical_transform=["distribution_summary"],
        )
        if len(numeric) >= 2:
            generated(
                title="Primary feature relationship",
                visualization_type="scatter_regression",
                question="What relationship among the main measured variables is visible before formal model interpretation?",
                claim="The primary feature relationship figure shows whether the available data contain visible structure relevant to the research question.",
                required_columns=numeric[:2],
                x=numeric[0],
                y=numeric[1],
                statistical_transform=["pearson_r", "linear_fit", "r2"],
            )

    if literature_items and not figures:
        generated(
            title="Literature informed analysis target",
            visualization_type="data_overview",
            question="Which data and method evidence should be generated next according to the literature-informed plan?",
            claim="This planning figure records the data and method target implied by the literature-informed workflow; it should be replaced by a project-specific empirical figure after data are available.",
            required_columns=[],
        )
    return figures


def _review_task_figures(
    *,
    tasks_report: dict[str, Any],
    inventory: dict[str, Any],
    selected_data: str,
) -> list[dict[str, Any]]:
    figure_inventory = _scoped_inventory(inventory, {})
    numeric = _numeric_columns(figure_inventory)
    labels = _label_columns(figure_inventory)
    lookup = _column_lookup(figure_inventory)
    ndvi_col = _match_column(lookup, ["ndvi", "vegetation"], numeric[0] if numeric else None)
    yield_col = _match_column(lookup, ["yield", "production", "potential"], numeric[1] if len(numeric) > 1 else None)
    climate_col = _match_column(lookup, ["temp", "precip", "climate", "rain"], numeric[2] if len(numeric) > 2 else None)
    group_col = _match_column(lookup, ["region", "zone", "field", "plot", "county", "province"], labels[0] if labels else None)
    figures: list[dict[str, Any]] = []

    def add(task: dict[str, Any], *, title: str, figure_type: str, columns: list[str], x: str | None = None, y: str | None = None, group: str | None = None, transforms: list[str] | None = None) -> None:
        figure_id = _safe_id(title, f"review_{len(figures) + 1}")
        figures.append({
            "id": figure_id,
            "title": title,
            "path": f"results/figures/{figure_id}.png",
            "generation_mode": "generated_code",
            "source": "review_task",
            "review_task_id": task.get("task_id"),
            "operation_family": task.get("operation_family"),
            "figure_type": figure_type,
            "visualization_type": figure_type,
            "required_inputs": [selected_data],
            "required_columns": [column for column in columns if column],
            "x": x,
            "y": y,
            "group": group,
            "statistical_transform": transforms or [],
            "backend_preference": ["matplotlib_scienceplots", "matplotlib", "png_stdlib_fallback"],
            "no_flowchart_fallback": True,
            "scientific_question": f"How does the reviewer-requested {task.get('operation_family')} change the empirical evidence?",
            "caption_draft": f"{title}.",
            "result_claim_template": "This reviewer-driven figure reports whether the revised analysis changes the strength, stability, or interpretation of the empirical result.",
        })

    for task in tasks_report.get("tasks") or []:
        status = ((task.get("feasibility") or {}).get("status") or "")
        if status == "blocked_missing_data":
            continue
        family = task.get("operation_family")
        if family == "agricultural_remote_sensing_feature_rebuild":
            add(task, title="Reviewer-driven remote-sensing feature response", figure_type="scatter_regression", columns=[ndvi_col, yield_col], x=ndvi_col, y=yield_col, transforms=["pearson_r", "linear_fit", "r2", "review_task_feature_rebuild"])
        elif family == "agricultural_remote_sensing_qc_rebuild":
            add(task, title="Reviewer-driven raw versus QC remote-sensing evidence", figure_type="histogram", columns=[ndvi_col or yield_col], x=ndvi_col or yield_col, transforms=["missingness", "range_check", "outlier_screen"])
        elif family == "baseline_ablation":
            add(task, title="Reviewer-driven baseline and ablation comparison", figure_type="metric_summary", columns=[ndvi_col, yield_col, climate_col], transforms=["baseline_metric", "ablation_metric", "review_task_coverage"])
        elif family == "spatial_block_validation":
            add(task, title="Reviewer-driven random versus spatial-block validation", figure_type="metric_summary", columns=[yield_col, ndvi_col, group_col], group=group_col, transforms=["random_split_metric", "blocked_validation_metric"])
        elif family == "stratified_heterogeneity_analysis":
            add(task, title="Reviewer-driven stratified heterogeneity analysis", figure_type="class_balance", columns=[group_col or labels[0] if labels else "", yield_col], group=group_col or (labels[0] if labels else None), transforms=["stratified_summary", "pooled_vs_stratified_effect"])
    return figures


def _render_plan_html_markdown(plan: dict[str, Any]) -> str:
    lines = [
        "# Project-Specific Figure Plan",
        "",
        f"Project: {plan.get('project_id')}",
        "",
        "This plan is generated from the current idea, research plan, data inventory, method requirements, target-journal context, and literature metadata. It is not a fixed plotting template.",
        "",
        "## Loop Decision",
        "",
        str(plan.get("loop_decision") or ""),
        "",
        "## Planned Figures",
        "",
    ]
    for item in plan.get("figures") or []:
        lines.extend([
            f"### {item.get('title')}",
            "",
            f"- Path: `{item.get('path')}`",
            f"- Mode: `{item.get('generation_mode')}`",
            f"- Figure type: `{item.get('figure_type') or item.get('visualization_type')}`",
            f"- Variables: x=`{item.get('x') or ''}`, y=`{item.get('y') or ''}`, group=`{item.get('group') or ''}`",
            f"- Statistical transforms: `{', '.join(item.get('statistical_transform') or [])}`",
            f"- Backend preference: `{', '.join(item.get('backend_preference') or [])}`",
            f"- Scientific question: {item.get('scientific_question')}",
            f"- Claim boundary: {item.get('result_claim_template')}",
            "",
        ])
    lines.extend([
        "## Next Action",
        "",
        str(plan.get("next_action") or ""),
        "",
    ])
    return "\n".join(lines)


def _set_figure_plan_stage_manifest(project_path: Path) -> None:
    manifest_path = project_path / "figure_plan" / "stage_manifest.json"
    if not manifest_path.exists():
        return
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["input_files"] = FIGURE_PLAN_INPUTS
    manifest["output_files"] = FIGURE_PLAN_OUTPUTS
    _write_json(manifest_path, manifest)


def plan_figures(project: str | Path, *, use_review_tasks: bool = False) -> dict[str, Any]:
    """Observe project state and write a project-specific figure plan."""
    state = load_project(project)
    try:
        requirements = validate_method_plan_for_methods(state.path)
    except MethodPlanError as exc:
        raise FigurePlanError(str(exc)) from exc

    inventory = _read_json(state.path / "data" / "data_inventory.json", {})
    if not isinstance(inventory, dict) or not inventory:
        raise FigurePlanError("data/data_inventory.json is required before plan-figures.")
    literature_items = _read_json(state.path / "references" / "literature_items.json", [])
    if not isinstance(literature_items, list):
        literature_items = []
    research_plan = _read_text(state.path / "research_plan" / "research_plan.md")
    journal_profile = _read_json(state.path / "journal_profile" / "journal_profile.json", {})
    review_task_context = {}
    if use_review_tasks:
        review_task_context = _read_json(state.path / "results" / "revision_figure_plan_delta.json", {})
    figures = _planned_figures(
        project_meta=state.metadata,
        research_plan=research_plan,
        requirements=requirements,
        inventory=inventory,
        literature_items=literature_items,
    )
    if use_review_tasks:
        task_report = _read_json(state.path / "review" / "actionable_analysis_tasks.json", {})
        selected_data = _selected_data(_scoped_inventory(inventory, requirements))
        for item in _review_task_figures(tasks_report=task_report, inventory=inventory, selected_data=selected_data):
            _add_unique(figures, item)
    generated_count = sum(1 for item in figures if item.get("generation_mode") == "generated_code")
    provided_count = sum(1 for item in figures if item.get("generation_mode") == "provided_artifact")
    next_action = "Run generate-analysis-code, then verify-methods, inventory-results, and write-results."
    if generated_count == 0 and provided_count:
        next_action = "Skip generate-analysis-code unless new local analysis is needed; run inventory-results and write-results after result-validity is assessed from supplied artifacts."
    plan = {
        "status": "written",
        "project_id": state.metadata.get("project_id"),
        "generated_at": utc_now(),
        "generator": "draftpaper_cli.figure_plan.plan_figures",
        "target_journal": state.metadata.get("target_journal"),
        "journal_constraints": journal_profile.get("profile") or journal_profile,
        "loop_decision": (
            "The agent observed the current project state and selected figures from the research question, available data, method requirements, literature methods, and supplied artifacts."
        ),
        "review_task_context": review_task_context,
        "used_review_tasks": bool(use_review_tasks and review_task_context),
        "figures": figures,
        "generated_figure_count": generated_count,
        "provided_figure_count": provided_count,
        "next_action": next_action,
    }
    results_dir = state.path / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    _write_json(results_dir / "figure_plan.json", plan)
    write_html_report(results_dir / "figure_plan.html", _render_plan_html_markdown(plan), title="Project-Specific Figure Plan")
    update_stage_status(state.path, "figure_plan", "draft")
    _set_figure_plan_stage_manifest(state.path)
    return {
        "status": "written",
        "project_path": str(state.path),
        "figure_plan": str(results_dir / "figure_plan.json"),
        "figure_plan_html": str(results_dir / "figure_plan.html"),
        "generated_figure_count": generated_count,
        "provided_figure_count": provided_count,
        "next_command": f'python -m draftpaper_cli.cli generate-analysis-code --project "{state.path}"',
    }


def validate_figure_plan_for_codegen(project_path: Path) -> dict[str, Any]:
    state = load_project(project_path)
    stage = (state.metadata.get("stages") or {}).get("figure_plan") or {}
    if stage.get("stale") or stage.get("status") not in {"draft", "approved", "completed"}:
        raise FigurePlanError("Code generation requires a non-stale figure_plan stage. Run plan-figures first.")
    plan = _read_json(project_path / "results" / "figure_plan.json", {})
    if not isinstance(plan, dict) or not plan.get("figures"):
        raise FigurePlanError("results/figure_plan.json with at least one figure is required before generate-analysis-code.")
    return plan
