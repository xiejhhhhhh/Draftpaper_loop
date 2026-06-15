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
    numeric = _numeric_columns(inventory)
    labels = _label_columns(inventory)
    selected_data = _selected_data(inventory)
    figures = _artifact_figures(inventory)
    generated_index = 1

    def generated(
        *,
        title: str,
        visualization_type: str,
        question: str,
        claim: str,
        required_columns: list[str] | None = None,
    ) -> None:
        nonlocal generated_index
        figure_id = _safe_id(title, f"figure_{generated_index}")
        generated_index += 1
        _add_unique(figures, {
            "id": figure_id,
            "title": title,
            "path": f"results/figures/{figure_id}.svg",
            "generation_mode": "generated_code",
            "visualization_type": visualization_type,
            "required_inputs": [selected_data],
            "required_columns": required_columns or [],
            "scientific_question": question,
            "caption_draft": f"{title}.",
            "result_claim_template": claim,
        })

    if any(term in blob for term in ["ndvi", "climate", "suitability", "zoning", "wheat", "yield"]):
        generated(
            title="Climate suitability zoning summary",
            visualization_type="spatial_or_ranked_scatter",
            question="How does the predicted suitability or production potential vary across the study units?",
            claim="The zoning figure shows the spatial or ranked distribution of the estimated suitability classes and highlights the areas supporting the main production-potential conclusion.",
            required_columns=numeric[:3],
        )
        generated(
            title="Environmental driver response",
            visualization_type="feature_response",
            question="Which environmental gradient most strongly explains the suitability or production-potential pattern?",
            claim="The response figure links the leading environmental predictor to the modeled suitability outcome, supporting the interpretation of dominant climatic constraints.",
            required_columns=numeric[:2],
        )
    elif any(term in blob for term in ["classification", "classifier", "cnn", "transformer", "tcn", "multimodal", "random forest", "xgboost"]):
        generated(
            title="Class distribution and sample support",
            visualization_type="class_balance",
            question="Are the available labeled samples sufficient and balanced enough to support the classification task?",
            claim="The class-support figure reports the observed sample distribution for the classification task and identifies whether result interpretation should be limited by class imbalance.",
            required_columns=labels[:1],
        )
        generated(
            title="Feature space structure",
            visualization_type="feature_relationship",
            question="Do the available features show separable structure relevant to the planned classification method?",
            claim="The feature-structure figure visualizes the leading numeric feature relationships used by the method and supports the interpretation of model-ready signal in the data.",
            required_columns=numeric[:2] + labels[:1],
        )
        generated(
            title="Verified method performance",
            visualization_type="metric_summary",
            question="Does the verified local method run satisfy the expected performance threshold?",
            claim="The performance figure summarizes the verified metric outputs and connects the observed result to the configured result-validity threshold.",
            required_columns=[],
        )
    else:
        generated(
            title="Data evidence overview",
            visualization_type="data_overview",
            question="What local or processed data evidence is available for the planned study?",
            claim="The data-evidence overview summarizes the available observations, variables, and local artifacts that bound the strength of downstream claims.",
            required_columns=numeric[:2] + labels[:1],
        )
        if len(numeric) >= 2:
            generated(
                title="Primary feature relationship",
                visualization_type="feature_relationship",
                question="What relationship among the main measured variables is visible before formal model interpretation?",
                claim="The primary feature relationship figure shows whether the available data contain visible structure relevant to the research question.",
                required_columns=numeric[:2],
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
            f"- Visualization type: `{item.get('visualization_type')}`",
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


def plan_figures(project: str | Path) -> dict[str, Any]:
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
    figures = _planned_figures(
        project_meta=state.metadata,
        research_plan=research_plan,
        requirements=requirements,
        inventory=inventory,
        literature_items=literature_items,
    )
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
