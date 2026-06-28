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


def _render_plan_html(plan: dict[str, Any]) -> str:
    rows = []
    for issue in plan.get("issues") or []:
        rows.append(
            "<article class='issue'>"
            f"<h3>{escape(str(issue.get('citation_key') or ''))} · {escape(str(issue.get('action') or ''))}</h3>"
            f"<p><strong>Original claim</strong>: {escape(str(issue.get('original_claim') or ''))}</p>"
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
        verdict = str(usage.get("verdict") or "")
        score = float(usage.get("match_score") or 0)
        if verdict == "supported" or (verdict == "partially_supported" and score >= 0.55):
            continue
        action = "rewrite_claim" if verdict == "partially_supported" else "remove_unsupported_claim"
        issues.append({
            "issue_id": f"citation_repair_{len(issues) + 1:03d}",
            "usage_id": usage.get("usage_id"),
            "citation_key": usage.get("citation_key"),
            "section": usage.get("section"),
            "file": usage.get("file"),
            "verdict": verdict,
            "match_score": score,
            "original_passage": usage.get("passage"),
            "original_claim": usage.get("claim"),
            "supporting_evidence": usage.get("supporting_evidence"),
            "action": action,
            "repair_instruction": (
                "Rewrite the claim so it only states what the cited source supports."
                if action == "rewrite_claim"
                else "Remove the weak claim and its citation unless a stronger source is supplied."
            ),
            "reasoning": usage.get("reasoning"),
        })
    plan = {
        "status": "repair_plan_written",
        "generated_at": utc_now(),
        "project_path": str(state.path),
        "source_audit": "citation_audit/citation_audit_report.json",
        "issue_count": len(issues),
        "issues": issues,
    }
    audit_dir = state.path / "citation_audit"
    audit_dir.mkdir(parents=True, exist_ok=True)
    _write_json(audit_dir / "citation_repair_plan.json", plan)
    (audit_dir / "citation_repair_plan.html").write_text(_render_plan_html(plan), encoding="utf-8")
    return plan


def apply_citation_repair(project: str | Path, *, dry_run: bool = False) -> dict[str, Any]:
    """Apply safe citation repairs by removing unsupported citation-bearing sentences."""
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
        replacement = ""
        new_text, count = _sentence_pattern(passage).subn(replacement, text, count=1)
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
