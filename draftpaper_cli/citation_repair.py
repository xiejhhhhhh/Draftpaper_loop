# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json
import re
from html import escape
from pathlib import Path
from typing import Any

from .citation_audit import CitationAuditError, audit_citations
from .metadata import GENERATOR_HTML_META
from .project_scaffold import _write_json, utc_now
from .project_state import load_project


class CitationRepairError(RuntimeError):
    """Raised when the citation repair loop cannot produce or apply a plan."""


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig", errors="replace")
    except Exception:
        return ""


def _sentence_pattern(passage: str) -> re.Pattern[str]:
    escaped = re.escape(passage.strip())
    return re.compile(escaped + r"(?=\s|$)", re.MULTILINE)


def _suggest_supported_claim(usage: dict[str, Any]) -> str:
    evidence = str(usage.get("supporting_evidence") or "").strip()
    if evidence:
        return evidence.rstrip(".。 ")
    citation_key = str(usage.get("citation_key") or "The cited source")
    return f"{citation_key} provides relevant background for this statement"


def _repair_action_for_usage(usage: dict[str, Any]) -> tuple[str, str, bool]:
    verdict = str(usage.get("verdict") or "")
    support_status = str(usage.get("support_status") or "")
    blocking = bool(usage.get("blocking"))
    if support_status in {"directly_supported"} or verdict == "supported":
        return "keep_citation", "No repair is required.", False
    if support_status == "partially_supported_rewrite_needed" and not blocking:
        return "keep_citation", "No immediate repair is required; the citation can be reviewed during prose editing.", False
    if not blocking:
        return (
            "rewrite_to_supported_claim",
            "Rewrite the local claim so it states only what the cited source directly supports, and keep the citation as context or provenance.",
            False,
        )
    if support_status == "unverifiable" or verdict == "unverifiable":
        return (
            "resolve_reference_metadata_or_evidence",
            "Resolve BibTeX metadata or add citation evidence so the retained reference can be checked before manuscript acceptance.",
            False,
        )
    return (
        "rewrite_to_supported_claim",
        "Rewrite the local claim so it matches the retained reference evidence; keep the reference and citation in the manuscript.",
        False,
    )


def _render_plan_html(plan: dict[str, Any]) -> str:
    rows = []
    for issue in plan.get("issues") or []:
        rows.append(
            "<article class='issue'>"
            f"<h3>{escape(str(issue.get('citation_key') or ''))} · {escape(str(issue.get('action') or ''))}</h3>"
            f"<p><strong>Original claim</strong>: {escape(str(issue.get('original_claim') or ''))}</p>"
            f"<p><strong>Suggested claim</strong>: {escape(str(issue.get('suggested_claim') or ''))}</p>"
            f"<p><strong>Intent/status</strong>: {escape(str(issue.get('citation_intent') or ''))} · {escape(str(issue.get('support_status') or ''))}</p>"
            f"<p><strong>Repair instruction</strong>: {escape(str(issue.get('repair_instruction') or ''))}</p>"
            f"<p><strong>Reason</strong>: {escape(str(issue.get('reasoning') or ''))}</p>"
            "</article>"
        )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
{GENERATOR_HTML_META.rstrip()}
  <title>Citation Repair Plan</title>
  <style>
    body {{ font-family: Georgia, 'Noto Serif SC', serif; max-width: 960px; margin: 36px auto; padding: 0 28px 72px; line-height: 1.7; color: #1a1d2a; background: #faf9f5; }}
    h1 {{ border-bottom: 2px solid #1a1d2a; padding-bottom: 12px; }}
    .issue {{ background: white; border: 1px solid #e7e4d9; border-radius: 8px; padding: 16px; margin: 14px 0; }}
    code {{ background: #f1f0ec; padding: 0.1rem 0.25rem; border-radius: 4px; }}
  </style>
</head>
<body>
  <h1>Citation Repair Plan</h1>
  <p>Generated at {escape(str(plan.get('generated_at') or ''))}. Issues: {len(plan.get('issues') or [])}.</p>
  {''.join(rows) if rows else '<p>No citation repair is required.</p>'}
</body>
</html>
"""


def generate_citation_repair_plan(project: str | Path) -> dict[str, Any]:
    """Create a deterministic repair plan from the latest citation audit report."""
    try:
        state = load_project(project)
    except Exception as exc:
        raise CitationRepairError(str(exc)) from exc
    report_path = state.path / "citation_audit" / "citation_audit_report.json"
    audit = _read_json(report_path)
    if not audit:
        audit = audit_citations(state.path)
    issues = []
    for usage in audit.get("usages") or []:
        action, instruction, deletion_allowed = _repair_action_for_usage(usage)
        if action == "keep_citation":
            continue
        score = float(usage.get("match_score") or 0)
        suggested_claim = _suggest_supported_claim(usage)
        issues.append({
            "issue_id": f"citation_repair_{len(issues) + 1:03d}",
            "usage_id": usage.get("usage_id"),
            "citation_key": usage.get("citation_key"),
            "section": usage.get("section"),
            "file": usage.get("file"),
            "verdict": usage.get("verdict"),
            "citation_intent": usage.get("citation_intent"),
            "support_status": usage.get("support_status"),
            "topic_relevance_score": usage.get("topic_relevance_score"),
            "claim_alignment_score": usage.get("claim_alignment_score"),
            "blocking": usage.get("blocking"),
            "match_score": score,
            "original_passage": usage.get("passage"),
            "original_claim": usage.get("claim"),
            "supporting_evidence": usage.get("supporting_evidence"),
            "action": action,
            "suggested_claim": suggested_claim,
            "deletion_allowed": deletion_allowed,
            "repair_instruction": instruction,
            "reasoning": usage.get("reasoning"),
        })
    coverage = audit.get("reference_coverage") or {}
    for key in coverage.get("summarized_but_uncited") or []:
        issues.append({
            "issue_id": f"citation_repair_{len(issues) + 1:03d}",
            "usage_id": "",
            "citation_key": key,
            "section": "references",
            "file": "references/reference_usage_plan.json",
            "verdict": "coverage_gap",
            "citation_intent": "required_reference_coverage",
            "support_status": "summarized_but_uncited",
            "topic_relevance_score": 0,
            "claim_alignment_score": 0,
            "blocking": True,
            "match_score": 0,
            "original_passage": "",
            "original_claim": "",
            "supporting_evidence": "",
            "action": "rerun_writers_for_reference_coverage",
            "suggested_claim": "",
            "deletion_allowed": False,
            "repair_instruction": "Regenerate or revise Introduction, Data, Methods, or Discussion from references/reference_usage_plan.json so this retained summary reference is cited at least once outside Results.",
            "reasoning": "The reference is retained in literature summaries but is absent from the manuscript citation set.",
        })
    removal_count = 0
    total_usages = int((audit.get("summary") or {}).get("total_usages") or 0)
    plan = {
        "status": "repair_plan_written",
        "generated_at": utc_now(),
        "project_path": str(state.path),
        "source_audit": "citation_audit/citation_audit_report.json",
        "issue_count": len(issues),
        "citation_retention_policy": {
            "initial_total_usages": total_usages,
            "planned_reference_removal_count": removal_count,
            "planned_retention_ratio": round((total_usages - removal_count) / total_usages, 3) if total_usages else 1.0,
            "policy": "Citation audit preserves retained references. Repairs narrow or rewrite manuscript claims, add evidence metadata, or rerun writers for coverage; they do not delete retained references or citation-bearing claims.",
        },
        "issues": issues,
    }
    audit_dir = state.path / "citation_audit"
    audit_dir.mkdir(parents=True, exist_ok=True)
    _write_json(audit_dir / "citation_repair_plan.json", plan)
    (audit_dir / "citation_repair_plan.html").write_text(_render_plan_html(plan), encoding="utf-8")
    return plan


def _replacement_for_issue(issue: dict[str, Any]) -> str:
    action = str(issue.get("action") or "")
    if action == "rewrite_to_supported_claim":
        suggested = str(issue.get("suggested_claim") or "").strip()
        citation_key = str(issue.get("citation_key") or "").strip()
        if suggested and citation_key:
            return f"{suggested.rstrip('.。 ')} \\citep{{{citation_key}}}."
    if action == "resolve_reference_metadata_or_evidence":
        return str(issue.get("original_passage") or "")
    return ""


def apply_citation_repair(project: str | Path, *, dry_run: bool = False) -> dict[str, Any]:
    """Apply safe citation repairs by narrowing claims before last-resort deletion."""
    try:
        state = load_project(project)
    except Exception as exc:
        raise CitationRepairError(str(exc)) from exc
    plan_path = state.path / "citation_audit" / "citation_repair_plan.json"
    plan = _read_json(plan_path)
    if not plan:
        plan = generate_citation_repair_plan(state.path)
    applied = []
    for issue in plan.get("issues") or []:
        file_relative = str(issue.get("file") or "")
        passage = str(issue.get("original_passage") or "").strip()
        if not file_relative or not passage:
            continue
        target = (state.path / file_relative).resolve()
        try:
            target.relative_to(state.path.resolve())
        except ValueError:
            continue
        text = _read_text(target)
        if not text:
            continue
        replacement = _replacement_for_issue(issue)
        new_text, count = _sentence_pattern(passage).subn(lambda _match: replacement, text, count=1)
        if count == 0:
            continue
        new_text = re.sub(r"\n{3,}", "\n\n", new_text)
        if not dry_run:
            target.write_text(new_text, encoding="utf-8")
        applied.append({
            "issue_id": issue.get("issue_id"),
            "file": file_relative,
            "action": issue.get("action"),
            "citation_key": issue.get("citation_key"),
        })
    ledger = {
        "status": "dry_run" if dry_run else "applied",
        "generated_at": utc_now(),
        "project_path": str(state.path),
        "applied_action_count": len(applied),
        "applied_actions": applied,
    }
    audit_dir = state.path / "citation_audit"
    _write_json(audit_dir / "citation_repair_ledger.json", ledger)
    return ledger


def re_audit_citations(project: str | Path) -> dict[str, Any]:
    """Run the final citation audit after repair."""
    return audit_citations(project, final=True)


def run_citation_repair_loop(project: str | Path, *, max_iterations: int = 3) -> dict[str, Any]:
    """Iterate audit, repair planning, repair application, and re-audit until strict pass."""
    if max_iterations < 1:
        raise CitationRepairError("max_iterations must be at least 1")
    last_audit: dict[str, Any] = {}
    for iteration in range(1, max_iterations + 1):
        last_audit = audit_citations(project, final=False)
        if last_audit.get("status") == "passed":
            final = audit_citations(project, final=True)
            final["iteration_count"] = iteration
            return final
        generate_citation_repair_plan(project)
        applied = apply_citation_repair(project)
        if not applied.get("applied_action_count"):
            break
    final_audit = audit_citations(project, final=True)
    if final_audit.get("status") != "passed":
        raise CitationAuditError("Citation repair loop stopped before the audit reached a strict pass.")
    return final_audit
