# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

"""Human-directed revision of the scientific objective before plan confirmation."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

from .project_scaffold import _write_json, utc_now
from .project_state import ProjectState, _save_project, load_project, update_stage_status
from .research_plan_confirmation import confirmation_state
from .state_kernel import atomic_write_text


OBJECTIVE_JSON = "idea/research_objective.json"
OBJECTIVE_HISTORY = "idea/research_objective_history"


class ResearchObjectiveError(RuntimeError):
    """Raised when a research-objective revision is incomplete or unsafe."""


def _clean_text(value: Any, field: str, *, required: bool = True) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if required and not text:
        raise ResearchObjectiveError(f"{field} is required.")
    return text


def _clean_list(value: Any, field: str, *, required: bool = True) -> list[str]:
    if value is None:
        values: list[Any] = []
    elif isinstance(value, list):
        values = value
    else:
        values = [value]
    cleaned = [_clean_text(item, field, required=False) for item in values]
    cleaned = list(dict.fromkeys(item for item in cleaned if item))
    if required and not cleaned:
        raise ResearchObjectiveError(f"{field} must contain at least one item.")
    return cleaned


def _normalize_panel(value: Any, *, claim_id: str, index: int) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ResearchObjectiveError(f"{claim_id}.figure_contract.panels[{index}] must be an object.")
    return {
        "label": _clean_text(value.get("label") or chr(97 + index), "panel.label"),
        "scientific_role": _clean_text(value.get("scientific_role"), "panel.scientific_role"),
        "required_method": _clean_text(value.get("required_method"), "panel.required_method"),
        "required_data_roles": _clean_list(value.get("required_data_roles"), "panel.required_data_roles"),
        "expected_content": _clean_text(value.get("expected_content"), "panel.expected_content"),
        "expected_content_zh_cn": _clean_text(
            value.get("expected_content_zh_cn"), "panel.expected_content_zh_cn", required=False
        ),
    }


def _normalize_figure_contract(value: Any, *, claim_id: str) -> dict[str, Any]:
    if value in (None, {}):
        return {}
    if not isinstance(value, dict):
        raise ResearchObjectiveError(f"{claim_id}.figure_contract must be an object.")
    panels = [
        _normalize_panel(panel, claim_id=claim_id, index=index)
        for index, panel in enumerate(value.get("panels") or [])
    ]
    return {
        "proposed_title": _clean_text(value.get("proposed_title"), "figure_contract.proposed_title"),
        "proposed_title_zh_cn": _clean_text(
            value.get("proposed_title_zh_cn"), "figure_contract.proposed_title_zh_cn", required=False
        ),
        "story_role": _clean_text(value.get("story_role") or "direct_scientific_signal", "figure_contract.story_role"),
        "required_data": _clean_list(value.get("required_data"), "figure_contract.required_data"),
        "required_method": _clean_list(value.get("required_method"), "figure_contract.required_method"),
        "suggested_plot_type": _clean_text(
            value.get("suggested_plot_type") or "scientific_comparison", "figure_contract.suggested_plot_type"
        ),
        "validation_metric": _clean_text(value.get("validation_metric"), "figure_contract.validation_metric"),
        "scientific_claim_boundary": _clean_text(
            value.get("scientific_claim_boundary"), "figure_contract.scientific_claim_boundary", required=False
        ),
        "scientific_claim_boundary_zh_cn": _clean_text(
            value.get("scientific_claim_boundary_zh_cn"),
            "figure_contract.scientific_claim_boundary_zh_cn",
            required=False,
        ),
        "panels": panels,
    }


def normalize_research_objective(payload: Any) -> dict[str, Any]:
    """Validate and normalize a discipline-independent science-first objective contract."""
    if not isinstance(payload, dict):
        raise ResearchObjectiveError("Research objective file must contain one JSON object.")
    questions = payload.get("primary_scientific_questions")
    if not isinstance(questions, list) or not 3 <= len(questions) <= 8:
        raise ResearchObjectiveError("primary_scientific_questions must contain 3 to 8 questions.")
    normalized_questions = []
    claim_ids: set[str] = set()
    for index, question in enumerate(questions, start=1):
        if not isinstance(question, dict):
            raise ResearchObjectiveError(f"primary_scientific_questions[{index - 1}] must be an object.")
        claim_id = _clean_text(question.get("claim_id") or f"claim_{index}", "claim_id")
        if not re.fullmatch(r"[a-z][a-z0-9_]{2,63}", claim_id):
            raise ResearchObjectiveError(f"Invalid claim_id: {claim_id}")
        if claim_id in claim_ids:
            raise ResearchObjectiveError(f"Duplicate claim_id: {claim_id}")
        claim_ids.add(claim_id)
        normalized_questions.append({
            "claim_id": claim_id,
            "research_question": _clean_text(question.get("research_question"), "research_question"),
            "research_question_zh_cn": _clean_text(
                question.get("research_question_zh_cn"), "research_question_zh_cn", required=False
            ),
            "expected_finding": _clean_text(question.get("expected_finding"), "expected_finding"),
            "expected_finding_zh_cn": _clean_text(
                question.get("expected_finding_zh_cn"), "expected_finding_zh_cn", required=False
            ),
            "figure_contract": _normalize_figure_contract(question.get("figure_contract"), claim_id=claim_id),
        })
    return {
        "schema_version": "dpl.research_objective.v1",
        "status": "human_revised",
        "revised_at": utc_now(),
        "working_title": _clean_text(payload.get("working_title"), "working_title"),
        "working_title_zh_cn": _clean_text(
            payload.get("working_title_zh_cn"), "working_title_zh_cn", required=False
        ),
        "scientific_objective": _clean_text(payload.get("scientific_objective"), "scientific_objective"),
        "scientific_objective_zh_cn": _clean_text(
            payload.get("scientific_objective_zh_cn"), "scientific_objective_zh_cn", required=False
        ),
        "primary_scientific_questions": normalized_questions,
        "methodological_hypothesis": _clean_text(
            payload.get("methodological_hypothesis"), "methodological_hypothesis"
        ),
        "methodological_hypothesis_zh_cn": _clean_text(
            payload.get("methodological_hypothesis_zh_cn"),
            "methodological_hypothesis_zh_cn",
            required=False,
        ),
        "data_scope": _clean_list(payload.get("data_scope"), "data_scope"),
        "data_scope_zh_cn": _clean_list(payload.get("data_scope_zh_cn"), "data_scope_zh_cn", required=False),
        "secondary_analyses": _clean_list(
            payload.get("secondary_analyses"), "secondary_analyses", required=False
        ),
        "secondary_analyses_zh_cn": _clean_list(
            payload.get("secondary_analyses_zh_cn"), "secondary_analyses_zh_cn", required=False
        ),
        "claim_boundary": _clean_text(payload.get("claim_boundary"), "claim_boundary"),
        "claim_boundary_zh_cn": _clean_text(
            payload.get("claim_boundary_zh_cn"), "claim_boundary_zh_cn", required=False
        ),
        "field": _clean_text(payload.get("field"), "field", required=False),
    }


def _render_idea(objective: dict[str, Any], target_journal: str) -> str:
    lines = [
        "# Research Idea",
        "",
        f"**Working title:** {objective['working_title']}",
        "",
        "## Scientific Objective",
        "",
        objective["scientific_objective"],
    ]
    if objective.get("scientific_objective_zh_cn"):
        lines.extend(["", "## 科学目标", "", objective["scientific_objective_zh_cn"]])
    lines.extend(["", "## Primary Scientific Questions", ""])
    for item in objective["primary_scientific_questions"]:
        lines.append(f"- `{item['claim_id']}`: {item['research_question']}")
        if item.get("research_question_zh_cn"):
            lines.append(f"  中文：{item['research_question_zh_cn']}")
    lines.extend([
        "",
        "## Methodological Hypothesis",
        "",
        objective["methodological_hypothesis"],
        "",
        "## Data Scope",
        "",
        *[f"- {item}" for item in objective["data_scope"]],
        "",
        "## Secondary Analyses",
        "",
        *([f"- {item}" for item in objective["secondary_analyses"]] or ["- None declared."]),
        "",
        "## Claim Boundary",
        "",
        objective["claim_boundary"],
        "",
        f"**Field:** {objective.get('field') or 'Not changed'}",
        "",
        f"**Target journal:** {target_journal}",
        "",
        "DINOv2 or any other model named above is a method unless the scientific objective explicitly makes method comparison the research question.",
        "",
    ])
    return "\n".join(lines)


def revise_research_objective(project: str | Path, *, objective_file: str | Path) -> dict[str, Any]:
    """Apply a human-directed objective revision and stale the full scientific chain."""
    state = load_project(project)
    confirmation = confirmation_state(state.path)
    if confirmation.get("status") == "confirmed":
        raise ResearchObjectiveError(
            "The current research plan is confirmed. Run reopen-research-plan before revising its scientific objective."
        )
    source = Path(objective_file).expanduser().resolve()
    if not source.is_file():
        raise ResearchObjectiveError(f"Research objective file not found: {source}")
    try:
        payload = json.loads(source.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResearchObjectiveError(f"Cannot read research objective JSON: {exc}") from exc
    objective = normalize_research_objective(payload)

    objective_path = state.path / OBJECTIVE_JSON
    if objective_path.is_file():
        history_dir = state.path / OBJECTIVE_HISTORY
        history_dir.mkdir(parents=True, exist_ok=True)
        stamp = utc_now().replace(":", "").replace("-", "")
        shutil.copy2(objective_path, history_dir / f"research_objective_{stamp}.json")

    _write_json(objective_path, objective)
    target_journal = str(state.metadata.get("target_journal") or "General Academic Journal")
    atomic_write_text(state.path / "idea" / "idea.md", _render_idea(objective, target_journal))

    state.metadata["title"] = objective["working_title"]
    state.metadata["idea"] = objective["scientific_objective"]
    if objective.get("field"):
        state.metadata["field"] = objective["field"]
    state.metadata["research_objective"] = objective
    _save_project(ProjectState(path=state.path, metadata=state.metadata))
    updated = update_stage_status(state.path, "idea", "draft")
    stale = [
        name
        for name, value in (updated.metadata.get("stages") or {}).items()
        if value.get("stale")
    ]
    return {
        "status": "revised",
        "project_path": str(state.path),
        "objective": OBJECTIVE_JSON,
        "working_title": objective["working_title"],
        "scientific_objective": objective["scientific_objective"],
        "primary_question_count": len(objective["primary_scientific_questions"]),
        "stale_stages": stale,
        "next_command": f'python -m draftpaper_cli.cli status --project "{state.path}"',
    }
