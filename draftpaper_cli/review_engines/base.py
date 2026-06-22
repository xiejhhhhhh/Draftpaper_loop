from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..html_utils import write_html_report
from ..project_scaffold import _write_json, utc_now
from ..project_state import load_project


REVIEW_DISCIPLINE_PROFILE_JSON = "review/review_discipline_profile.json"
REVIEW_WORKFLOW_GAP_JSON = "review/review_workflow_gap_report.json"
REVIEW_WORKFLOW_GAP_HTML = "review/review_workflow_gap_report.html"
REVIEW_ENGINEERING_PLAN_JSON = "review/review_engineering_plan.json"
REVIEW_ENGINEERING_PLAN_HTML = "review/review_engineering_plan.html"
USER_CONFIRMATION_REQUESTS_JSON = "review/user_confirmation_requests.json"


class ReviewEngineError(RuntimeError):
    """Raised when discipline-specific review engineering cannot run."""


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def read_text(path: Path, limit: int = 3000) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


def read_figures(path: Path) -> list[dict[str, Any]]:
    payload = read_json(path)
    figures = payload.get("figures")
    if isinstance(figures, list):
        return [item for item in figures if isinstance(item, dict)]
    return []


def compact_json(value: Any, limit: int = 2000) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    except TypeError:
        text = str(value)
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


def collect_review_context(project: str | Path) -> dict[str, Any]:
    state = load_project(project)
    project_path = state.path
    return {
        "project_path": str(project_path),
        "metadata": {
            "project_id": state.metadata.get("project_id"),
            "project_slug": state.metadata.get("project_slug"),
            "idea": state.metadata.get("idea"),
            "field": state.metadata.get("field"),
            "target_journal": state.metadata.get("target_journal"),
        },
        "research_plan": read_text(project_path / "research_plan" / "research_plan.md"),
        "literature_review_notes": read_text(project_path / "references" / "literature_review_notes.html", 2200),
        "data_context": read_json(project_path / "data" / "data_writing_context.json"),
        "data_quality": read_json(project_path / "data" / "data_quality_report.json"),
        "data_feasibility": read_json(project_path / "data" / "data_feasibility_report.json"),
        "method_requirements": read_json(project_path / "methods" / "method_requirements.json"),
        "result_validity": read_json(project_path / "results" / "result_validity_report.json"),
        "figure_metadata": read_figures(project_path / "results" / "figure_metadata.json"),
        "results_text": read_text(project_path / "results" / "results.tex"),
        "discussion_text": read_text(project_path / "discussion" / "discussion.tex"),
        "journal_profile": read_json(project_path / "journal_profile" / "journal_profile.json"),
    }


def context_text(context: dict[str, Any]) -> str:
    chunks = [
        compact_json(context.get("metadata") or {}, 1600),
        str(context.get("research_plan") or ""),
        str(context.get("literature_review_notes") or ""),
        compact_json(context.get("data_context") or {}, 1800),
        compact_json(context.get("method_requirements") or {}, 1800),
        compact_json(context.get("result_validity") or {}, 1600),
        compact_json(context.get("figure_metadata") or [], 2200),
        str(context.get("results_text") or ""),
        compact_json(context.get("journal_profile") or {}, 1200),
    ]
    return " ".join(chunks).lower()


def issue_payload(
    *,
    code: str,
    title: str,
    severity: str,
    target_stage: str,
    rationale: str,
    actions: list[str],
    confirmation_question: str = "",
    requires_user_confirmation: bool = False,
    evidence: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "code": code,
        "title": title,
        "severity": severity,
        "target_stage": target_stage,
        "rationale": rationale,
        "recommended_actions": actions,
        "requires_user_confirmation": requires_user_confirmation,
        "confirmation_question": confirmation_question,
        "evidence": evidence or [],
    }


def codex_enhancement_context(context: dict[str, Any], discipline_profile: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "available_for_codex_or_llm_enhancement",
        "purpose": (
            "Use this context to add discipline-specific reviewer-engineering suggestions on top of the deterministic "
            "engine. Do not overwrite deterministic blocking issues; append traceable suggestions with evidence."
        ),
        "discipline_profile": discipline_profile,
        "context_excerpts": {
            "research_plan": context.get("research_plan", ""),
            "literature_review_notes": context.get("literature_review_notes", ""),
            "data_context": compact_json(context.get("data_context") or {}, 1600),
            "method_requirements": compact_json(context.get("method_requirements") or {}, 1600),
            "result_validity": compact_json(context.get("result_validity") or {}, 1200),
            "figure_metadata": compact_json(context.get("figure_metadata") or [], 1800),
            "results_text": context.get("results_text", ""),
        },
    }


def render_gap_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Review Workflow Gap Report",
        "",
        f"Discipline: {report['discipline_profile'].get('discipline')}",
        "",
        f"Engine: {report.get('engine')}",
        "",
        "## Missing Review Workflows",
        "",
    ]
    for gap in report.get("missing_review_workflows") or []:
        lines.extend([
            f"### {gap['code']}: {gap['title']}",
            "",
            f"- Severity: {gap['severity']}",
            f"- Target stage: {gap['target_stage']}",
            f"- Rationale: {gap['rationale']}",
            f"- Requires user confirmation: {gap['requires_user_confirmation']}",
            "",
        ])
        for action in gap.get("recommended_actions") or []:
            lines.append(f"- {action}")
        lines.append("")
    return "\n".join(lines)


def render_plan_markdown(plan: dict[str, Any]) -> str:
    lines = [
        "# Review Engineering Plan",
        "",
        f"Discipline: {plan['discipline_profile'].get('discipline')}",
        "",
        "## Issues",
        "",
    ]
    for issue in plan.get("issues") or []:
        lines.extend([
            f"### {issue['issue_id']}: {issue['title']}",
            "",
            f"- Severity: {issue['severity']}",
            f"- Target stage: {issue['target_stage']}",
            f"- Reason: {issue['reason']}",
            f"- User input: {issue['required_user_input']}",
            "",
        ])
    lines.extend(["", "## User Confirmation Requests", ""])
    for request in plan.get("user_confirmation_requests") or []:
        lines.append(f"- {request['request_id']}: {request['question']}")
    lines.append("")
    return "\n".join(lines)


def write_gap_report(project_path: Path, report: dict[str, Any]) -> None:
    review_dir = project_path / "review"
    review_dir.mkdir(parents=True, exist_ok=True)
    _write_json(project_path / REVIEW_DISCIPLINE_PROFILE_JSON, report["discipline_profile"])
    _write_json(project_path / REVIEW_WORKFLOW_GAP_JSON, report)
    write_html_report(project_path / REVIEW_WORKFLOW_GAP_HTML, render_gap_markdown(report), title="Review Workflow Gap Report")


def write_engineering_plan(project_path: Path, plan: dict[str, Any]) -> None:
    review_dir = project_path / "review"
    review_dir.mkdir(parents=True, exist_ok=True)
    _write_json(project_path / REVIEW_ENGINEERING_PLAN_JSON, plan)
    _write_json(project_path / USER_CONFIRMATION_REQUESTS_JSON, plan.get("user_confirmation_requests") or [])
    write_html_report(project_path / REVIEW_ENGINEERING_PLAN_HTML, render_plan_markdown(plan), title="Review Engineering Plan")


def base_report(
    *,
    project_path: Path,
    discipline_profile: dict[str, Any],
    engine: str,
    gaps: list[dict[str, Any]],
    context: dict[str, Any],
) -> dict[str, Any]:
    return {
        "status": "review_workflow_gaps_found" if gaps else "no_review_workflow_gap_found",
        "generated_at": utc_now(),
        "project_path": str(project_path),
        "engine": engine,
        "discipline_profile": discipline_profile,
        "missing_review_workflows": gaps,
        "gap_count": len(gaps),
        "codex_enhancement_context": codex_enhancement_context(context, discipline_profile),
    }
