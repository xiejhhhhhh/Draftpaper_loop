# Copyright (c) 2026 xiejhhhhhh
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from ..discipline import infer_discipline_from_text
from ..project_scaffold import _write_json, utc_now
from . import astronomy, default, geography, machine_learning
from .base import (
    REVIEW_ENGINEERING_PLAN_JSON,
    REVIEW_WORKFLOW_GAP_JSON,
    USER_CONFIRMATION_REQUESTS_JSON,
    ReviewEngineError,
    base_report,
    codex_enhancement_context,
    collect_review_context,
    context_text,
    write_engineering_plan,
    write_gap_report,
)


ENGINE_MODULES = {
    "astronomy": astronomy,
    "default": default,
    "geography": geography,
    "machine_learning": machine_learning,
}


def infer_review_discipline(project: str | Path) -> dict[str, Any]:
    context = collect_review_context(project)
    text = context_text(context)
    return infer_discipline_from_text(text)


def discover_review_workflow_gaps(project: str | Path) -> dict[str, Any]:
    context = collect_review_context(project)
    project_path = Path(context["project_path"])
    discipline_profile = infer_review_discipline(project_path)
    engine_name = discipline_profile.get("engine") or "default"
    engine = ENGINE_MODULES.get(str(engine_name), default)
    gaps = engine.discover(context, discipline_profile)
    report = base_report(
        project_path=project_path,
        discipline_profile=discipline_profile,
        engine=str(engine_name),
        gaps=gaps,
        context=context,
    )
    write_gap_report(project_path, report)
    return report


def _issue_id(code: str, target_stage: str, rationale: str) -> str:
    digest = hashlib.sha256(f"review_engineering|{code}|{target_stage}|{rationale}".encode("utf-8")).hexdigest()[:8]
    return f"E-{digest}"


def _commands_for_stage(target_stage: str) -> list[str]:
    mapping = {
        "data": ["inventory-data", "assess-data-quality", "assess-data-feasibility", "collect-method-plan", "plan-figures", "generate-analysis-code", "verify-methods", "assess-result-validity", "inventory-results", "write-results", "write-discussion", "assemble-latex", "run-integrity-gate", "quality-check"],
        "methods": ["plan-figures", "generate-analysis-code", "verify-methods", "write-methods", "assess-result-validity", "inventory-results", "write-results", "write-discussion", "assemble-latex", "run-integrity-gate", "quality-check"],
        "method_plan": ["collect-method-plan", "plan-figures", "generate-analysis-code", "verify-methods", "write-methods", "assess-result-validity", "inventory-results", "write-results", "write-discussion", "assemble-latex", "run-integrity-gate", "quality-check"],
        "result_validity": ["assess-result-validity", "inventory-results", "write-results", "write-discussion", "assemble-latex", "run-integrity-gate", "quality-check"],
        "research_plan": ["generate-plan", "write-introduction", "collect-method-plan", "plan-figures", "generate-analysis-code", "verify-methods", "assess-result-validity", "inventory-results", "write-results", "write-discussion", "assemble-latex", "run-integrity-gate", "quality-check"],
        "results": ["inventory-results", "write-results", "write-discussion", "assemble-latex", "run-integrity-gate", "quality-check"],
    }
    return mapping.get(target_stage, ["status", "run-pipeline"])


def _gap_to_revision_issue(gap: dict[str, Any]) -> dict[str, Any]:
    rationale = str(gap.get("rationale") or "")
    target_stage = str(gap.get("target_stage") or "research_plan")
    return {
        "issue_id": _issue_id(str(gap.get("code") or "review_engineering_gap"), target_stage, rationale),
        "source": "review_engineering",
        "code": gap.get("code"),
        "severity": gap.get("severity", "major"),
        "target_stage": target_stage,
        "title": gap.get("title"),
        "reason": rationale,
        "files_to_add_or_edit": [
            "review/review_workflow_gap_report.json",
            "review/review_engineering_plan.json",
        ],
        "recommended_commands": _commands_for_stage(target_stage),
        "required_user_input": gap.get("confirmation_question") or "Confirm whether this review-engineering workflow should be added before rerunning downstream stages.",
        "status": "pending",
    }


def propose_review_engineering_plan(project: str | Path) -> dict[str, Any]:
    context = collect_review_context(project)
    project_path = Path(context["project_path"])
    gap_report = discover_review_workflow_gaps(project_path)
    issues = [_gap_to_revision_issue(gap) for gap in gap_report.get("missing_review_workflows") or []]
    confirmation_requests = []
    for gap in gap_report.get("missing_review_workflows") or []:
        if gap.get("requires_user_confirmation"):
            confirmation_requests.append({
                "request_id": str(gap.get("code")),
                "target_stage": gap.get("target_stage"),
                "question": gap.get("confirmation_question"),
                "default_action": "ask_user_before_code_generation",
                "options": ["approve", "skip", "revise_scope"],
            })
    plan = {
        "status": "review_engineering_plan_written",
        "generated_at": utc_now(),
        "project_path": str(project_path),
        "discipline_profile": gap_report["discipline_profile"],
        "engine": gap_report.get("engine"),
        "issue_count": len(issues),
        "issues": issues,
        "user_confirmation_requests": confirmation_requests,
        "codex_enhancement_context": codex_enhancement_context(context, gap_report["discipline_profile"]),
        "fallback_engine": "default",
        "extension_contract": {
            "add_engine_file": "draftpaper_cli/review_engines/<discipline>.py",
            "required_function": "discover(context, discipline_profile) -> list[dict]",
            "register_in": "draftpaper_cli/review_engines/__init__.py ENGINE_MODULES and infer_review_discipline",
        },
    }
    write_engineering_plan(project_path, plan)
    return plan


__all__ = [
    "REVIEW_ENGINEERING_PLAN_JSON",
    "REVIEW_WORKFLOW_GAP_JSON",
    "ReviewEngineError",
    "USER_CONFIRMATION_REQUESTS_JSON",
    "discover_review_workflow_gaps",
    "infer_review_discipline",
    "propose_review_engineering_plan",
]
