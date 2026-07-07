# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

from pathlib import Path
from typing import Any

from .html_utils import write_html_report
from .project_scaffold import _write_json, utc_now


DATA_WRITING_BRIEF_JSON = "data/data_writing_brief.json"
DATA_WRITING_BRIEF_HTML = "data/data_writing_brief.html"
METHOD_WRITING_BRIEF_JSON = "methods/method_writing_brief.json"
METHOD_WRITING_BRIEF_HTML = "methods/method_writing_brief.html"


DATA_REQUIRED_COVERAGE = [
    "data_source",
    "raw_access_boundary",
    "processed_dataset",
    "sample_subsets",
    "feature_content_groups",
    "missingness_coverage",
    "claim_boundary",
]

METHOD_REQUIRED_STAGES = [
    "sample_construction",
    "feature_or_token_construction",
    "model_architecture",
    "training_objective",
    "validation_design",
    "metrics_and_ablation",
]

MANUSCRIPT_AVOID_CONTENT = [
    "local filesystem paths",
    "raw filenames or script names",
    "CLI commands and execution logs",
    "manifest field dumps",
    "Draftpaper-loop, gate, workflow, or internal audit terminology",
]


def _compact(text: Any, limit: int = 900) -> str:
    value = " ".join(str(text or "").split())
    if len(value) <= limit:
        return value
    return value[: limit - 3].rstrip() + "..."


def _list_dict_values(items: Any, key: str, limit: int = 6) -> list[str]:
    values: list[str] = []
    if not isinstance(items, list):
        return values
    for item in items:
        if not isinstance(item, dict):
            continue
        value = item.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text and text not in values:
            values.append(text)
        if len(values) >= limit:
            break
    return values


def _method_stage_briefs(context: dict[str, Any]) -> list[dict[str, Any]]:
    blueprint = context.get("method_blueprint") if isinstance(context.get("method_blueprint"), dict) else {}
    code_plan = blueprint.get("method_code_plan") if isinstance(blueprint.get("method_code_plan"), dict) else {}
    selected_templates = blueprint.get("selected_method_template_hints") or []
    families = list(code_plan.get("method_families") or [])
    stages: list[dict[str, Any]] = []
    for stage in METHOD_REQUIRED_STAGES:
        stages.append({
            "stage": stage,
            "writing_goal": _stage_goal(stage),
            "evidence_sources": [
                "method_requirements",
                "stage_code_manifest",
                "method_formula_manifest",
                "figure_code_trace",
            ],
            "formula_policy": "include a formula when this stage has an extracted expression; otherwise explain why the stage is operational rather than mathematical",
        })
    if isinstance(selected_templates, list) and selected_templates:
        for item in selected_templates[:6]:
            if not isinstance(item, dict):
                continue
            stages.append({
                "stage": str(item.get("template_id") or item.get("display_name") or "selected_method_template"),
                "writing_goal": "Use this selected discipline template only when it matches the project data and figures.",
                "method_family": item.get("method_family"),
                "input_roles": list(item.get("input_roles") or []),
                "figure_groups": list(item.get("figure_groups") or []),
                "formula_families": list(item.get("formula_families") or []),
            })
    elif families:
        stages.append({
            "stage": "selected_method_families",
            "writing_goal": "Connect the planned method families to the implemented code and result figures.",
            "method_families": families,
        })
    return stages


def _stage_goal(stage: str) -> str:
    goals = {
        "sample_construction": "Define the modeled samples, inclusion boundary, labels or responses, and train/evaluation split without exposing local files.",
        "feature_or_token_construction": "Explain how raw observations become scientific variables, features, tokens, or representations.",
        "model_architecture": "Describe the statistical model, machine-learning model, or analytical estimator at a scientific level.",
        "training_objective": "State the optimization target, loss, fitting criterion, or estimation objective.",
        "validation_design": "Describe held-out, blocked, temporal, spatial, or external validation logic as applicable.",
        "metrics_and_ablation": "Define the reported metrics, comparison baselines, ablations, and diagnostic checks.",
    }
    return goals.get(stage, "Describe the method stage using verified code and evidence only.")


def build_data_writing_brief(project_path: str | Path, context: dict[str, Any]) -> dict[str, Any]:
    project_dir = Path(project_path)
    inventory = context.get("inventory") if isinstance(context.get("inventory"), dict) else {}
    files = inventory.get("files") if isinstance(inventory, dict) else []
    variable_groups = context.get("variable_groups") if isinstance(context.get("variable_groups"), dict) else {}
    brief = {
        "status": "written",
        "generated_at": utc_now(),
        "section": "data",
        "writing_mode": "brief_guided_natural_prose",
        "writing_goal": "Write the Data section as natural scientific prose that explains source, content, processing boundary, coverage, and claim limits without exposing internal artifact names.",
        "required_coverage": list(DATA_REQUIRED_COVERAGE),
        "coverage_guidance": {
            "data_source": _compact(context.get("source_summary")),
            "processed_dataset": _compact(context.get("content_summary")),
            "sample_subsets": "Mention scientifically meaningful sample subsets only when the context supports them; avoid project-specific verification labels.",
            "feature_content_groups": {key: list(values)[:10] for key, values in variable_groups.items()},
            "missingness_coverage": _compact(context.get("processing_summary")),
            "claim_boundary": _compact(context.get("claim_boundary")),
        },
        "allowed_evidence": [
            "data_inventory summary",
            "data_quality_report missingness and coverage",
            "data_feasibility_report claim boundary",
            "stage-owned data code summary when expressed as processing logic",
            "visible data observations recorded by Codex or the user",
        ],
        "avoid_content": list(MANUSCRIPT_AVOID_CONTENT),
        "internal_artifacts": _list_dict_values(files, "path"),
        "style_guidance": [
            "Prefer continuous paragraphs over bullets.",
            "Use scientific category labels instead of column names when a column name is a local processing artifact.",
            "Do not present result values or conclusions before the Results section.",
        ],
    }
    _write_json(project_dir / DATA_WRITING_BRIEF_JSON, brief)
    write_html_report(project_dir / DATA_WRITING_BRIEF_HTML, render_writing_brief_markdown(brief), title="Data Writing Brief")
    return brief


def build_method_writing_brief(project_path: str | Path, context: dict[str, Any]) -> dict[str, Any]:
    project_dir = Path(project_path)
    formula_manifest = context.get("formula_manifest") if isinstance(context.get("formula_manifest"), dict) else {}
    formulas = formula_manifest.get("formulas") if isinstance(formula_manifest.get("formulas"), list) else []
    brief = {
        "status": "written",
        "generated_at": utc_now(),
        "section": "methods",
        "writing_mode": "brief_guided_natural_prose",
        "writing_goal": "Write Methods as natural scientific prose grounded in verified method code, formulas, validation design, and figure-code trace.",
        "required_coverage": list(METHOD_REQUIRED_STAGES),
        "stage_briefs": _method_stage_briefs(context),
        "formula_policy": {
            "formula_count": len(formulas),
            "require_variable_explanations": True,
            "relationship_to_figures": "Each formula-bearing stage should state how it supports a planned result figure or validation output.",
        },
        "allowed_evidence": [
            "method_requirements",
            "method_blueprint selected templates",
            "method_code_manifest stage-owned code roles",
            "method_formula_manifest formulas and variable explanations",
            "figure_code_trace links between methods and figures",
            "run_manifest metrics and successful execution status",
        ],
        "avoid_content": list(MANUSCRIPT_AVOID_CONTENT),
        "style_guidance": [
            "Keep subsection headings only when they help a journal-style Methods section.",
            "Do not dump manifest names, paths, or script names.",
            "Explain variables immediately after displayed formulas.",
            "Frame limitations as design boundaries rather than workflow limitations.",
        ],
    }
    _write_json(project_dir / METHOD_WRITING_BRIEF_JSON, brief)
    write_html_report(project_dir / METHOD_WRITING_BRIEF_HTML, render_writing_brief_markdown(brief), title="Method Writing Brief")
    return brief


def render_writing_brief_markdown(brief: dict[str, Any]) -> str:
    lines = [
        f"# {str(brief.get('section') or 'Section').title()} Writing Brief",
        "",
        f"Status: {brief.get('status', 'unknown')}",
        "",
        "## Writing Goal",
        "",
        str(brief.get("writing_goal") or ""),
        "",
        "## Required Coverage",
        "",
    ]
    for item in brief.get("required_coverage") or []:
        lines.append(f"- {item}")
    if brief.get("stage_briefs"):
        lines.extend(["", "## Stage Briefs", ""])
        for item in brief.get("stage_briefs") or []:
            if isinstance(item, dict):
                lines.append(f"- {item.get('stage')}: {item.get('writing_goal')}")
    if brief.get("coverage_guidance"):
        lines.extend(["", "## Coverage Guidance", ""])
        for key, value in (brief.get("coverage_guidance") or {}).items():
            lines.append(f"- {key}: {_compact(value, 500)}")
    lines.extend(["", "## Avoid", ""])
    for item in brief.get("avoid_content") or []:
        lines.append(f"- {item}")
    return "\n".join(lines)
