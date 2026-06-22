from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .html_utils import write_html_report
from .project_scaffold import _write_json, utc_now
from .project_state import load_project, mark_stage_stale
from .review_engines import propose_review_engineering_plan


REVIEW_DIR = "review"
GATE_DIAGNOSIS_JSON = "review/gate_failure_diagnosis.json"
GATE_DIAGNOSIS_MD = "review/gate_failure_diagnosis.md"
REVIEW_REPORT_MD = "review/review_report.md"
REVIEWER_ISSUES_JSON = "review/reviewer_issues.json"
PUBLICATION_READINESS_JSON = "review/publication_readiness_report.json"
PUBLICATION_READINESS_HTML = "review/publication_readiness_report.html"
CODEX_ARCHIVE_REVIEW_CONTEXT_JSON = "review/codex_archive_review_context.json"
CODEX_ARCHIVE_REVIEW_CONTEXT_HTML = "review/codex_archive_review_context.html"
STATISTICAL_RESCUE_JSON = "review/statistical_rescue_plan.json"
STATISTICAL_RESCUE_HTML = "review/statistical_rescue_plan.html"
CLAIM_EVIDENCE_MATRIX_CSV = "review/claim_evidence_matrix.csv"
JOURNAL_FIT_HTML = "review/journal_fit_report.html"
REVISION_PLAN_JSON = "review/revision_plan.json"
REVISION_PLAN_MD = "review/revision_plan.md"
COMMITMENT_LEDGER_CSV = "review/commitment_ledger.csv"
APPLY_REVISION_JSON = "review/apply_revision_report.json"
APPLY_REVISION_MD = "review/apply_revision_report.md"
RE_REVIEW_REPORT_MD = "review/re_review_report.md"
RE_REVIEW_REPORT_JSON = "review/re_review_report.json"


@dataclass
class RevisionIssue:
    issue_id: str
    source: str
    code: str
    severity: str
    target_stage: str
    title: str
    reason: str
    files_to_add_or_edit: list[str]
    recommended_commands: list[str]
    required_user_input: str
    status: str = "pending"


class ReviewRevisionError(RuntimeError):
    """Raised when the review/revision loop cannot load or write project artifacts."""


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig", errors="replace")
    except Exception:
        return ""


def _review_dir(project_path: Path) -> Path:
    path = project_path / REVIEW_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def _issue_id(source: str, code: str, target_stage: str, reason: str) -> str:
    digest = hashlib.sha256(f"{source}|{code}|{target_stage}|{reason}".encode("utf-8")).hexdigest()[:8]
    prefix = {
        "reviewer": "R",
        "publication_readiness": "P",
        "statistical_rescue": "S",
        "review_engineering": "E",
        "data_feasibility": "D",
        "methods": "M",
        "result_validity": "V",
        "integrity": "I",
        "quality": "Q",
    }.get(source, "X")
    return f"{prefix}-{digest}"


def _commands_from_stage(target_stage: str) -> list[str]:
    mapping = {
        "references": ["search-literature", "generate-plan", "write-introduction", "write-discussion", "assemble-latex", "run-integrity-gate", "quality-check"],
        "research_plan": ["generate-plan", "write-introduction", "collect-method-plan", "plan-figures", "generate-analysis-code", "verify-methods", "assess-result-validity", "inventory-results", "write-results", "write-discussion", "assemble-latex", "run-integrity-gate", "quality-check"],
        "data": ["inventory-data", "assess-data-quality", "assess-data-feasibility", "collect-method-plan", "plan-figures", "generate-analysis-code", "verify-methods", "assess-result-validity", "inventory-results", "write-results", "write-discussion", "assemble-latex", "run-integrity-gate", "quality-check"],
        "method_plan": ["collect-method-plan", "plan-figures", "generate-analysis-code", "verify-methods", "write-methods", "assess-result-validity", "inventory-results", "write-results", "write-discussion", "assemble-latex", "run-integrity-gate", "quality-check"],
        "figure_plan": ["plan-figures", "generate-analysis-code", "verify-methods", "write-methods", "assess-result-validity", "inventory-results", "write-results", "write-discussion", "assemble-latex", "run-integrity-gate", "quality-check"],
        "code": ["plan-figures", "generate-analysis-code", "verify-methods", "write-methods", "assess-result-validity", "inventory-results", "write-results", "write-discussion", "assemble-latex", "run-integrity-gate", "quality-check"],
        "methods": ["plan-figures", "generate-analysis-code", "verify-methods", "write-methods", "assess-result-validity", "inventory-results", "write-results", "write-discussion", "assemble-latex", "run-integrity-gate", "quality-check"],
        "result_validity": ["assess-result-validity", "inventory-results", "write-results", "write-discussion", "assemble-latex", "run-integrity-gate", "quality-check"],
        "results": ["inventory-results", "write-results", "write-discussion", "assemble-latex", "run-integrity-gate", "quality-check"],
        "discussion": ["write-discussion", "assemble-latex", "run-integrity-gate", "quality-check"],
        "latex": ["assemble-latex", "run-integrity-gate", "quality-check"],
        "quality_checks": ["run-integrity-gate", "quality-check"],
    }
    return mapping.get(target_stage, ["status", "run-pipeline"])


def _issue(
    *,
    source: str,
    code: str,
    severity: str,
    target_stage: str,
    title: str,
    reason: str,
    files: list[str],
    user_input: str,
) -> RevisionIssue:
    return RevisionIssue(
        issue_id=_issue_id(source, code, target_stage, reason),
        source=source,
        code=code,
        severity=severity,
        target_stage=target_stage,
        title=title,
        reason=reason,
        files_to_add_or_edit=files,
        recommended_commands=_commands_from_stage(target_stage),
        required_user_input=user_input,
    )


def _dedupe_issues(issues: list[RevisionIssue]) -> list[RevisionIssue]:
    seen: set[str] = set()
    result: list[RevisionIssue] = []
    for issue in issues:
        if issue.issue_id in seen:
            continue
        seen.add(issue.issue_id)
        result.append(issue)
    return result


def _stage_for_integrity_issue(issue: dict[str, Any]) -> str:
    code = str(issue.get("code") or "")
    section = str(issue.get("section") or "")
    file_name = str(issue.get("file") or "")
    if "citation" in code or "bib" in code:
        if section in {"introduction", "data", "methods", "discussion"} and "section" in code:
            return section
        return "references"
    if "result" in code or file_name.startswith("results/"):
        return "results"
    return "quality_checks"


def _stage_for_quality_issue(issue: dict[str, Any]) -> str:
    file_name = str(issue.get("file") or "")
    if file_name.startswith("data/"):
        return "data"
    if file_name.startswith("methods/"):
        return "methods"
    if file_name.startswith("results/"):
        return "results"
    if file_name.startswith("references/") or "citation" in str(issue.get("code") or ""):
        return "references"
    if file_name.startswith("latex/"):
        return "latex"
    return "quality_checks"


def _render_issue_md(title: str, issues: list[RevisionIssue]) -> str:
    lines = [f"# {title}", "", f"Generated at: {utc_now()}", "", f"Issue count: {len(issues)}", ""]
    if not issues:
        lines.append("No revision issues were found.")
    for issue in issues:
        lines.extend([
            f"## {issue.issue_id}: {issue.title}",
            "",
            f"- Source: {issue.source}",
            f"- Severity: {issue.severity}",
            f"- Target stage: {issue.target_stage}",
            f"- Reason: {issue.reason}",
            f"- Files: {', '.join(issue.files_to_add_or_edit) or 'none'}",
            f"- Recommended commands: {', '.join(issue.recommended_commands)}",
            f"- User input: {issue.required_user_input}",
            "",
        ])
    return "\n".join(lines)


def _numeric(value: Any) -> float | None:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _bounded_score(score: int) -> int:
    return max(0, min(100, int(score)))


def _read_list_payload(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return []
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ["figures", "items", "records"]:
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def _weak_effect_records(figures: list[dict[str, Any]], *, r2_threshold: float = 0.10, abs_r_threshold: float = 0.30) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for figure in figures:
        statistics = figure.get("statistics") or {}
        if not isinstance(statistics, dict):
            continue
        r2 = _numeric(statistics.get("r2"))
        pearson_r = _numeric(statistics.get("pearson_r"))
        if r2 is None and pearson_r is None:
            continue
        weak_reasons: list[str] = []
        if r2 is not None and r2 < r2_threshold:
            weak_reasons.append(f"R2={r2:.4g} is below {r2_threshold:.2f}")
        if pearson_r is not None and abs(pearson_r) < abs_r_threshold:
            weak_reasons.append(f"|r|={abs(pearson_r):.4g} is below {abs_r_threshold:.2f}")
        if not weak_reasons:
            continue
        variables = figure.get("variables") if isinstance(figure.get("variables"), dict) else {}
        records.append({
            "figure_id": figure.get("figure_id") or figure.get("id") or figure.get("path") or "unknown_figure",
            "title": figure.get("title") or figure.get("caption_draft") or "Untitled figure",
            "figure_type": figure.get("figure_type") or figure.get("type") or "",
            "variables": variables,
            "n": figure.get("n"),
            "pearson_r": pearson_r,
            "r2": r2,
            "weak_reasons": weak_reasons,
            "interpretation_summary": figure.get("interpretation_summary") or "",
        })
    return records


def _weak_effect_summary(records: list[dict[str, Any]], limit: int = 3) -> str:
    parts: list[str] = []
    for record in records[:limit]:
        variables = record.get("variables") or {}
        variable_text = ", ".join(f"{key}={value}" for key, value in variables.items()) if variables else "variables not declared"
        metrics = []
        if record.get("pearson_r") is not None:
            metrics.append(f"r={record['pearson_r']:.3g}")
        if record.get("r2") is not None:
            metrics.append(f"R2={record['r2']:.3g}")
        parts.append(f"{record.get('title')} ({variable_text}; {', '.join(metrics)})")
    if not parts:
        return "weak figure-level statistical effects"
    suffix = "" if len(records) <= limit else f"; {len(records) - limit} additional weak-effect figure(s)"
    return "; ".join(parts) + suffix


def _readiness_band(score: int) -> str:
    if score >= 80:
        return "near_submission_ready"
    if score >= 65:
        return "promising_with_major_checks"
    if score >= 50:
        return "major_revision_needed"
    return "not_ready_for_submission"


def _publication_recommendation(score: int) -> str:
    if score >= 80:
        return "The draft is close to a reviewable submission package after normal polishing and journal-format checks."
    if score >= 65:
        return "The draft has publication potential, but the current evidence chain should be strengthened before submission."
    if score >= 50:
        return "The draft should be treated as a major-revision candidate rather than a submission-ready paper."
    return "The draft should not be submitted in its current state; revise data, methods, or claim strength first."


def _score_to_reviewer_decision(score: int) -> str:
    if score >= 80:
        return "minor_revision_or_submit_after_polish"
    if score >= 65:
        return "major_revision_likely"
    if score >= 50:
        return "major_revision_required"
    return "reject_or_rebuild_before_submission"


def _target_from_validity(validity: dict[str, Any]) -> str:
    causes = {str(item) for item in validity.get("failure_causes") or []}
    if "data" in causes:
        return "data"
    if "method" in causes or "methods" in causes:
        return "methods"
    return "research_plan"


def _route_commands(target_stage: str) -> list[str]:
    return _commands_from_stage(target_stage)


def _render_publication_readiness_md(report: dict[str, Any]) -> str:
    lines = [
        "# Publication Readiness Report",
        "",
        f"Generated at: {report['generated_at']}",
        "",
        f"Readiness score: {report['readiness_score']}/100",
        "",
        f"Readiness band: {report['readiness_band']}",
        "",
        f"Reviewer-style decision: {report['reviewer_style_decision']}",
        "",
        f"Recommendation: {report['recommendation']}",
        "",
        "## Reviewer Narrative",
        "",
        report.get("reviewer_narrative", ""),
        "",
        "## Journal Fit",
        "",
        report.get("journal_fit_summary", ""),
        "",
        "## Evidence Signals",
        "",
    ]
    for signal in report.get("evidence_signals") or []:
        lines.append(f"- {signal}")
    lines.extend(["", "## Major Risks", ""])
    for issue in report.get("issues") or []:
        lines.append(f"- {issue['title']}: {issue['reason']}")
    if not report.get("issues"):
        lines.append("- No major deterministic readiness issues were detected.")
    lines.append("")
    return "\n".join(lines)


def _trim_text(text: str, limit: int = 1800) -> str:
    text = " ".join(str(text or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _artifact_text(project_path: Path, relative: str, limit: int = 1800) -> str:
    return _trim_text(_read_text(project_path / relative), limit=limit)


def _compact_json(value: Any, limit: int = 1800) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    except TypeError:
        text = str(value)
    return _trim_text(text, limit=limit)


def _collect_codex_archive_context(project_path: Path, metadata: dict[str, Any]) -> dict[str, Any]:
    """Collect a bounded, explicit project-archive packet for Codex/LLM review."""
    artifacts = {
        "project_metadata": {
            "project_id": metadata.get("project_id"),
            "project_slug": metadata.get("project_slug"),
            "idea": metadata.get("idea"),
            "field": metadata.get("field"),
            "target_journal": metadata.get("target_journal"),
        },
        "research_plan": _artifact_text(project_path, "research_plan/research_plan.md", 2400),
        "literature_review_notes": _artifact_text(project_path, "references/literature_review_notes.html", 2200),
        "data_context": _compact_json(_read_json(project_path / "data" / "data_writing_context.json"), 2200),
        "data_quality": _compact_json(_read_json(project_path / "data" / "data_quality_report.json"), 1400),
        "data_feasibility": _compact_json(_read_json(project_path / "data" / "data_feasibility_report.json"), 1600),
        "method_context": _compact_json(_read_json(project_path / "methods" / "method_writing_context.json"), 2200),
        "method_requirements": _compact_json(_read_json(project_path / "methods" / "method_requirements.json"), 1600),
        "method_run_manifest": _compact_json(_read_json(project_path / "methods" / "run_manifest.yaml"), 1600),
        "result_validity": _compact_json(_read_json(project_path / "results" / "result_validity_report.json"), 1600),
        "figure_metadata": _compact_json(_read_list_payload(project_path / "results" / "figure_metadata.json"), 2200),
        "figure_quality": _compact_json(_read_json(project_path / "results" / "figure_quality_report.json"), 1600),
        "results_text": _artifact_text(project_path, "results/results.tex", 2200),
        "discussion_text": _artifact_text(project_path, "discussion/discussion.tex", 2200),
        "journal_profile": _compact_json(_read_json(project_path / "journal_profile" / "journal_profile.json"), 1600),
        "integrity_report": _compact_json(_read_json(project_path / "integrity" / "integrity_report.json"), 1600),
        "quality_report": _compact_json(_read_json(project_path / "quality_checks" / "quality_report.json"), 1600),
    }
    present = [key for key, value in artifacts.items() if value]
    missing = [key for key, value in artifacts.items() if not value]
    return {
        "generated_at": utc_now(),
        "project_path": str(project_path),
        "purpose": "Codex/LLM reviewer context assembled only from explicit project files, not hidden reasoning.",
        "present_sections": present,
        "missing_sections": missing,
        "artifacts": artifacts,
        "reviewer_prompt": (
            "Act as a target-journal reviewer. Use only this archived project context. "
            "Assess publication readiness, data/method/result weaknesses, statistical rescue options, "
            "claim strength, and required upstream reruns."
        ),
    }


def _render_codex_context_md(context: dict[str, Any]) -> str:
    lines = [
        "# Codex Archive Review Context",
        "",
        context.get("purpose", ""),
        "",
        "## Reviewer Prompt",
        "",
        context.get("reviewer_prompt", ""),
        "",
        "## Present Sections",
        "",
    ]
    for key in context.get("present_sections") or []:
        lines.append(f"- {key}")
    lines.extend(["", "## Archive Excerpts", ""])
    for key, value in (context.get("artifacts") or {}).items():
        if not value:
            continue
        lines.extend([f"### {key}", "", str(value), ""])
    return "\n".join(lines)


def _reviewer_narrative(report: dict[str, Any], context: dict[str, Any]) -> str:
    artifacts = context.get("artifacts") or {}
    field = (artifacts.get("project_metadata") or {}).get("field") or "the stated field"
    journal = report.get("target_journal") or "the target journal"
    band = report.get("readiness_band")
    score = report.get("readiness_score")
    decision = report.get("reviewer_style_decision")
    signals = report.get("evidence_signals") or []
    issue_titles = [issue.get("title", "") for issue in report.get("issues") or [] if issue.get("title")]
    weak_signal = next((signal for signal in signals if "weak explanatory effects" in str(signal).lower()), None)
    main_risk = weak_signal or (issue_titles[0] if issue_titles else (signals[0] if signals else "the evidence chain needs normal reviewer scrutiny"))
    return (
        f"From a reviewer perspective for {journal}, this draft currently reads as {band} with a readiness score of {score}/100 "
        f"and a likely editorial posture of {decision}. The assessment is based on the archived project files rather than a fresh chat-only impression. "
        f"For {field}, the main risk is {main_risk}. "
        "If the authors want to preserve the current study direction, the next revision should first repair the data-method-result evidence chain, "
        "then rerun figure planning, method verification, result validity, Results writing, Discussion writing, LaTeX assembly, integrity, and quality checks. "
        "If stronger evidence cannot be produced, the safer route is to reframe the work as exploratory and make that claim boundary explicit throughout the manuscript."
    )


def _render_statistical_rescue_md(plan: dict[str, Any]) -> str:
    lines = [
        "# Statistical Rescue Plan",
        "",
        f"Generated at: {plan['generated_at']}",
        "",
        f"Diagnosis: {plan['diagnosis']}",
        "",
        f"Status: {plan['status']}",
        "",
        "## Likely Failure Sources",
        "",
    ]
    for source in plan.get("likely_failure_sources") or ["none"]:
        lines.append(f"- {source}")
    lines.extend(["", "## Recommended Routes", ""])
    for route in plan.get("recommended_routes") or []:
        lines.extend([
            f"### {route['route_id']}: {route['title']}",
            "",
            f"- Target stage: {route['target_stage']}",
            f"- Rationale: {route['rationale']}",
            f"- Actions: {', '.join(route['actions'])}",
            f"- Rerun commands: {', '.join(route['rerun_commands'])}",
            "",
        ])
    lines.extend(["", "## Revision Issues", ""])
    for issue in plan.get("issues") or []:
        lines.append(f"- {issue['issue_id']}: {issue['title']} ({issue['target_stage']})")
    if not plan.get("issues"):
        lines.append("- No statistical rescue issue was generated.")
    lines.append("")
    return "\n".join(lines)


def _write_claim_evidence_matrix(project_path: Path, report: dict[str, Any], rescue_plan: dict[str, Any] | None = None) -> None:
    path = project_path / CLAIM_EVIDENCE_MATRIX_CSV
    fieldnames = ["claim_area", "evidence_source", "decision", "risk", "recommended_action"]
    rows = []
    for signal in report.get("evidence_signals") or []:
        rows.append({
            "claim_area": "publication_readiness",
            "evidence_source": "deterministic_review",
            "decision": report.get("readiness_band", ""),
            "risk": signal,
            "recommended_action": report.get("recommendation", ""),
        })
    if rescue_plan:
        for route in rescue_plan.get("recommended_routes") or []:
            rows.append({
                "claim_area": "statistical_rescue",
                "evidence_source": route.get("target_stage", ""),
                "decision": rescue_plan.get("status", ""),
                "risk": route.get("rationale", ""),
                "recommended_action": "; ".join(route.get("actions") or []),
            })
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def assess_publication_readiness(project: str | Path) -> dict[str, Any]:
    """Assess journal-facing submission readiness from saved loop artifacts."""
    try:
        state = load_project(project)
    except Exception as exc:
        raise ReviewRevisionError(str(exc)) from exc
    project_path = state.path
    metadata = state.metadata
    data_quality = _read_json(project_path / "data" / "data_quality_report.json")
    data_report = _read_json(project_path / "data" / "data_feasibility_report.json")
    run_manifest = _read_json(project_path / "methods" / "run_manifest.yaml")
    validity = _read_json(project_path / "results" / "result_validity_report.json")
    quality = _read_json(project_path / "quality_checks" / "quality_report.json")
    integrity = _read_json(project_path / "integrity" / "integrity_report.json")
    journal = _read_json(project_path / "journal_profile" / "journal_profile.json")
    figure_quality = _read_json(project_path / "results" / "figure_quality_report.json")
    figures = _read_list_payload(project_path / "results" / "figure_metadata.json")
    main_tex = _read_text(project_path / "latex" / "main.tex")

    score = 100
    signals: list[str] = []
    issues: list[RevisionIssue] = []

    data_decision = data_report.get("decision")
    observed_rows = int(data_report.get("observed_rows") or data_quality.get("total_rows") or 0)
    missing_ratio = _numeric(data_quality.get("overall_missing_cell_ratio")) or 0.0
    if data_decision in {"blocked", "revise_required"}:
        score -= 35
        issues.append(_issue(
            source="publication_readiness",
            code="data_not_submission_ready",
            severity="blocking",
            target_stage="data",
            title="Data evidence is not submission-ready",
            reason="The data feasibility gate does not support the current scientific goal.",
            files=["data/data_feasibility_report.json", "data/data_quality_report.json"],
            user_input="Decide whether to add data, change variables, or reframe the study before submission.",
        ))
    elif data_decision == "conditional_pass":
        score -= 12
        issues.append(_issue(
            source="publication_readiness",
            code="data_claim_boundary_conditional",
            severity="major",
            target_stage="research_plan",
            title="Data support is conditional",
            reason="The manuscript should be framed as exploratory or claim-limited unless stronger data are added.",
            files=["data/data_feasibility_report.json", "research_plan/research_plan.md"],
            user_input="Confirm the acceptable claim boundary for the target journal.",
        ))
    if observed_rows and observed_rows < int(data_report.get("min_rows") or 30):
        score -= 8
        signals.append(f"Observed rows are below the configured minimum ({observed_rows} observed).")
    if missing_ratio > 0.2:
        score -= 10
        signals.append(f"Missing-cell ratio is high ({missing_ratio:.3f}).")

    if run_manifest.get("status") != "success":
        score -= 25
        issues.append(_issue(
            source="publication_readiness",
            code="methods_not_reproducible_for_review",
            severity="blocking",
            target_stage="methods",
            title="Method verification is not reproducible",
            reason="A submission-quality draft needs a successful local method run manifest.",
            files=["methods/run_manifest.yaml", "code/scripts/run_analysis.py"],
            user_input="Fix method execution or revise the method plan before submission.",
        ))

    validity_decision = validity.get("decision")
    if validity_decision == "revise_required":
        score -= 35
        target = _target_from_validity(validity)
        issues.append(_issue(
            source="publication_readiness",
            code="result_claim_not_supported",
            severity="blocking",
            target_stage=target,
            title="Result evidence does not support submission claims",
            reason="The result validity gate requires revision, so reviewer rejection risk is high.",
            files=["results/result_validity_report.json", "methods/run_manifest.yaml"],
            user_input="Choose between statistical/method revision, additional data, or weaker claims.",
        ))
    elif validity_decision == "conditional_pass":
        score -= 15
        issues.append(_issue(
            source="publication_readiness",
            code="result_claim_conditional",
            severity="major",
            target_stage="results",
            title="Result claims need exploratory framing",
            reason="Result validity is conditional rather than confirmatory.",
            files=["results/result_validity_report.json", "results/results.tex", "discussion/discussion.tex"],
            user_input="Confirm whether the paper should be submitted as an exploratory study.",
        ))

    if figure_quality and figure_quality.get("status") not in {"passed", "pass"}:
        score -= 12
        signals.append("Figure quality report is not passed.")
    if figures and len(figures) < 5:
        score -= 8
        signals.append(f"Only {len(figures)} figure metadata record(s) were found; many journal drafts need 5-6 substantive figures.")
    weak_effects = _weak_effect_records(figures)
    if weak_effects:
        score -= min(18, 6 + 4 * len(weak_effects))
        summary = _weak_effect_summary(weak_effects)
        signals.append(f"Figure-level statistics show weak explanatory effects: {summary}.")
        issues.append(_issue(
            source="publication_readiness",
            code="weak_statistical_effect_needs_qc",
            severity="major",
            target_stage="data",
            title="Weak statistical effects need data-quality and modeling audit",
            reason=(
                "One or more manuscript figures report low explanatory power or weak correlations. "
                "A reviewer is likely to ask whether these weak effects reflect true scientific signal, "
                "data-quality problems, unsuitable proxy variables, scale mismatch, outliers, or insufficient feature engineering."
            ),
            files=["results/figure_metadata.json", "data/data_quality_report.json", "data/data_feasibility_report.json"],
            user_input="Decide whether to clean data, revise proxy variables, rebuild features, add robustness analysis, or lower the claim strength.",
        ))
    if integrity and integrity.get("status") != "passed":
        score -= 15
        signals.append("Integrity gate is not passed.")
    if quality and quality.get("status") != "passed":
        score -= 18
        signals.append("Final quality gate is not passed.")
    if not main_tex.strip():
        score -= 12
        signals.append("No assembled LaTeX manuscript was found.")

    journal_name = journal.get("target_journal") or metadata.get("target_journal") or "the target journal"
    journal_fit_summary = (
        f"The readiness estimate is calibrated against {journal_name}. "
        "A journal-specific profile is available." if journal else
        f"The readiness estimate is provisional because no journal profile was found for {journal_name}."
    )
    if not journal:
        score -= 8

    score = _bounded_score(score)
    archive_context = _collect_codex_archive_context(project_path, metadata)
    report = {
        "status": "reviewed",
        "generated_at": utc_now(),
        "project_path": str(project_path),
        "target_journal": journal_name,
        "readiness_score": score,
        "readiness_band": _readiness_band(score),
        "reviewer_style_decision": _score_to_reviewer_decision(score),
        "recommendation": _publication_recommendation(score),
        "journal_fit_summary": journal_fit_summary,
        "reviewer_narrative": "",
        "codex_archive_review_context": CODEX_ARCHIVE_REVIEW_CONTEXT_JSON,
        "evidence_signals": signals,
        "issue_count": len(issues),
        "issues": [asdict(issue) for issue in _dedupe_issues(issues)],
        "inputs": [
            "data/data_quality_report.json",
            "data/data_feasibility_report.json",
            "methods/run_manifest.yaml",
            "results/result_validity_report.json",
            "results/figure_metadata.json",
            "results/figure_quality_report.json",
            "journal_profile/journal_profile.json",
            "quality_checks/quality_report.json",
        ],
    }
    report["reviewer_narrative"] = _reviewer_narrative(report, archive_context)
    review_dir = _review_dir(project_path)
    _write_json(review_dir / "codex_archive_review_context.json", archive_context)
    write_html_report(
        review_dir / "codex_archive_review_context.html",
        _render_codex_context_md(archive_context),
        title="Codex Archive Review Context",
    )
    _write_json(review_dir / "publication_readiness_report.json", report)
    markdown = _render_publication_readiness_md(report)
    write_html_report(review_dir / "publication_readiness_report.html", markdown, title="Publication Readiness Report")
    write_html_report(review_dir / "journal_fit_report.html", "## Journal Fit\n\n" + journal_fit_summary + "\n", title="Journal Fit Report")
    _write_claim_evidence_matrix(project_path, report)
    return report


def _rescue_route(route_id: str, title: str, target_stage: str, rationale: str, actions: list[str]) -> dict[str, Any]:
    return {
        "route_id": route_id,
        "title": title,
        "target_stage": target_stage,
        "rationale": rationale,
        "actions": actions,
        "rerun_commands": _route_commands(target_stage),
    }


def _domain_context_text(metadata: dict[str, Any], archive_context: dict[str, Any]) -> str:
    artifacts = archive_context.get("artifacts") or {}
    chunks = [
        str(metadata.get("idea") or ""),
        str(metadata.get("field") or ""),
        str(metadata.get("target_journal") or ""),
    ]
    for key in (
        "research_plan",
        "data_context",
        "method_context",
        "method_requirements",
        "result_validity",
        "figure_metadata",
        "results_text",
    ):
        value = artifacts.get(key)
        if value:
            chunks.append(str(value))
    return " ".join(chunks).lower()


def _domain_statistical_routes(metadata: dict[str, Any], archive_context: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    """Build discipline-aware rescue routes from saved project artifacts."""
    text = _domain_context_text(metadata, archive_context)
    routes: list[dict[str, Any]] = []
    sources: list[str] = []

    if any(token in text for token in ("ndvi", "wheat", "crop", "agriculture", "yield", "vegetation index", "remote sensing")):
        sources.append("agricultural_remote_sensing_signal")
        routes.append(_rescue_route(
            "agricultural_remote_sensing_feature_rebuild",
            "Rebuild crop and remote-sensing features before strengthening claims",
            "methods",
            "The archived project context points to crop, NDVI, yield, or remote-sensing evidence; weak conclusions may improve after agronomic feature construction and stratified validation.",
            [
                "derive phenology-aware NDVI indicators such as seasonal maximum, seasonal integral, early-season slope, and key growth-stage summaries",
                "join or stratify observations by year, agro-climatic zone, cultivar group, irrigation status, soil class, or management region when such metadata are available",
                "test yield or suitability relationships with climate and soil covariates rather than relying on raw vegetation-index correlations alone",
                "use spatial or temporal blocked validation to check whether patterns generalize beyond nearby fields or adjacent dates",
                "regenerate figure plans around agronomic evidence: NDVI time-series profiles, feature-response curves, spatial residual maps, and robustness panels",
            ],
        ))

    if any(token in text for token in ("gis", "spatial", "geographic", "geospatial", "raster", "longitude", "latitude", "map", "ecology", "habitat")):
        sources.append("spatial_or_ecological_signal")
        routes.append(_rescue_route(
            "spatial_ecological_validation",
            "Add spatial structure and ecological validation checks",
            "methods",
            "The project context contains spatial, GIS, or ecological signals, so ordinary random splits and unstratified summaries may overstate evidence strength.",
            [
                "check spatial autocorrelation in predictors, residuals, or classification errors",
                "prefer spatial block, regional holdout, or time-sliced validation over purely random validation when coordinates or regions are available",
                "summarize effects by ecological zone or spatial stratum before claiming broad generality",
                "add maps or stratified response plots that show where the result is stable and where it fails",
            ],
        ))

    if any(token in text for token in ("light curve", "x-ray", "flare", "astronom", "source classification", "catalog", "photometric", "spectral")):
        sources.append("astronomy_time_series_signal")
        routes.append(_rescue_route(
            "astronomy_time_series_feature_rebuild",
            "Rebuild astronomical source features and validation",
            "methods",
            "The project context suggests astronomical source or time-series classification, where result quality often depends on variability features, catalog cross-matching, and leakage-aware validation.",
            [
                "derive variability descriptors, hardness or color ratios, flux percentiles, and uncertainty-aware summary features",
                "separate training and validation by survey field, source family, or observation campaign when possible",
                "audit class imbalance and report macro metrics, calibrated probabilities, and confusion structure",
                "cross-match with trusted catalogs or external labels before making strong source-population claims",
            ],
        ))

    if any(token in text for token in ("machine learning", "deep learning", "cnn", "transformer", "random forest", "classifier", "classification", "regression model")):
        sources.append("machine_learning_validation_signal")
        routes.append(_rescue_route(
            "machine_learning_validation_rebuild",
            "Strengthen model validation and baseline comparison",
            "methods",
            "The project context contains machine-learning methods, so weak results should be diagnosed through baseline, leakage, metric, and ablation checks before manuscript claims are strengthened.",
            [
                "compare the proposed model with simple baselines and domain-standard models on the same split",
                "audit leakage from duplicated samples, spatial proximity, temporal adjacency, or preprocessing fitted before splitting",
                "report uncertainty across repeated splits or cross-validation folds",
                "add ablation analysis for the main data modalities or feature groups",
            ],
        ))

    return routes, sources


def _weak_effect_rescue_routes(
    metadata: dict[str, Any],
    archive_context: dict[str, Any],
    weak_effects: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    if not weak_effects:
        return [], []
    text = _domain_context_text(metadata, archive_context)
    summary = _weak_effect_summary(weak_effects)
    routes = [
        _rescue_route(
            "weak_effect_data_quality_audit",
            "Audit data quality before using weak statistical effects as evidence",
            "data",
            (
                "Figure-level statistics show weak explanatory effects "
                f"({summary}). Before accepting the weak result as a scientific conclusion, "
                "the loop should test whether it is caused by data-quality problems, proxy mismatch, outliers, aggregation choices, or unsuitable preprocessing."
            ),
            [
                "inspect outliers and high-leverage observations for the variables used in weak-effect figures",
                "check units, value ranges, transformations, and impossible values before rerunning the analysis",
                "compare raw, cleaned, winsorized, and robust-regression variants where the discipline permits it",
                "stratify or group the analysis by scientifically meaningful subsets instead of relying only on one pooled correlation",
                "rerun figure planning, generated analysis code, method verification, result validity, and Results writing after the data-quality audit",
            ],
        )
    ]
    sources = ["weak_effect_statistics"]

    if any(token in text for token in ("ndvi", "wheat", "crop", "agriculture", "yield", "vegetation index", "remote sensing")):
        sources.append("agricultural_remote_sensing_qc_signal")
        routes.append(_rescue_route(
            "agricultural_remote_sensing_qc_rebuild",
            "Clean and re-derive agricultural remote-sensing variables",
            "data",
            "Weak NDVI, yield, or environmental-driver effects are common when crop data mix phenological stages, cloud-contaminated observations, incompatible spatial scales, management heterogeneity, or proxy variables that are not aligned with the response.",
            [
                "screen NDVI or vegetation-index values for cloud contamination, saturation, sensor artifacts, and phenological-window mismatch",
                "check yield, nitrogen, climate, and environmental proxies for unit consistency, impossible values, and extreme observations before modeling",
                "aggregate or align predictors by crop growth stage, year, region, field, or agro-climatic zone when those identifiers are available",
                "test whether temperature or climate proxies need lagged, seasonal, cumulative, or threshold features rather than a single pooled linear term",
                "rerun the weak-effect figures after QC and report whether r, R2, confidence intervals, and residual structure improve enough to support the claim",
            ],
        ))

    if any(token in text for token in ("gis", "spatial", "geographic", "geospatial", "raster", "longitude", "latitude", "map", "ecology", "habitat")):
        sources.append("spatial_qc_signal")
        routes.append(_rescue_route(
            "spatial_data_quality_audit",
            "Audit spatial alignment and sampling structure",
            "data",
            "Weak spatial or ecological associations may reflect coordinate mismatch, raster resampling artifacts, spatial autocorrelation, or uneven sampling coverage rather than absence of scientific signal.",
            [
                "verify coordinate reference systems, raster-vector alignment, cell resolution, and temporal matching",
                "summarize sampling density and missing coverage by region or ecological stratum",
                "check whether spatial autocorrelation or clustered samples make pooled correlations misleading",
                "rerun spatially stratified or blocked analyses after correcting alignment issues",
            ],
        ))

    if any(token in text for token in ("light curve", "x-ray", "flare", "astronom", "source classification", "catalog", "photometric", "spectral")):
        sources.append("astronomy_qc_signal")
        routes.append(_rescue_route(
            "astronomy_measurement_qc_rebuild",
            "Audit astronomical measurement quality and source matching",
            "data",
            "Weak astronomical associations can arise from uncertain cross-matches, flux calibration differences, low signal-to-noise measurements, cadence gaps, or mixed source populations.",
            [
                "check source matching radius, duplicate matches, photometric or spectral quality flags, and signal-to-noise thresholds",
                "separate analyses by source class, observation campaign, cadence, or instrument where possible",
                "derive uncertainty-aware variability or spectral features before judging the scientific signal",
                "rerun figures with quality-filtered and unfiltered samples to expose sensitivity",
            ],
        ))

    return routes, sources


def recommend_statistical_revision(project: str | Path) -> dict[str, Any]:
    """Recommend statistical rescue routes when data or results are weak."""
    try:
        state = load_project(project)
    except Exception as exc:
        raise ReviewRevisionError(str(exc)) from exc
    project_path = state.path
    metadata = state.metadata
    data_quality = _read_json(project_path / "data" / "data_quality_report.json")
    data_report = _read_json(project_path / "data" / "data_feasibility_report.json")
    validity = _read_json(project_path / "results" / "result_validity_report.json")
    method_requirements = _read_json(project_path / "methods" / "method_requirements.json")
    readiness = _read_json(project_path / PUBLICATION_READINESS_JSON)
    if not readiness:
        readiness = assess_publication_readiness(project_path)
    archive_context = _collect_codex_archive_context(project_path, metadata)
    figures = _read_list_payload(project_path / "results" / "figure_metadata.json")
    weak_effects = _weak_effect_records(figures)

    routes: list[dict[str, Any]] = []
    issues: list[RevisionIssue] = []
    likely_sources: list[str] = []
    observed_rows = int(data_report.get("observed_rows") or data_quality.get("total_rows") or 0)
    min_rows = int(data_report.get("min_rows") or 30)
    missing_ratio = _numeric(data_quality.get("overall_missing_cell_ratio")) or 0.0
    validity_decision = validity.get("decision")
    data_decision = data_report.get("decision")

    if observed_rows and observed_rows < min_rows:
        likely_sources.append("limited_sample_size")
        routes.append(_rescue_route(
            "small_sample_robustness",
            "Use small-sample and uncertainty-aware statistics",
            "methods",
            "The available table has fewer observations than the configured data gate expects.",
            [
                "report effect sizes with confidence intervals",
                "use bootstrap uncertainty estimates where appropriate",
                "avoid confirmatory language and emphasize exploratory evidence",
                "add sensitivity analysis for influential observations",
            ],
        ))
    if missing_ratio > 0.0:
        likely_sources.append("missing_data")
        routes.append(_rescue_route(
            "missingness_and_imputation_audit",
            "Audit missingness before strengthening claims",
            "data",
            "Missing values can change the interpretation of weak associations and model outputs.",
            [
                "summarize missingness by variable and subgroup",
                "compare complete-case and imputed analyses",
                "state whether missingness is plausibly random or structurally biased",
            ],
        ))
    if validity_decision == "revise_required":
        likely_sources.extend(str(item) for item in validity.get("failure_causes") or ["result_validity"])
        target = _target_from_validity(validity)
        routes.append(_rescue_route(
            "result_validity_rebuild",
            "Rebuild the analysis around result validity failure",
            target,
            "The observed method outputs do not currently support the expected claim strength.",
            [
                "inspect feature construction, validation split, and primary metric definition",
                "compare baseline, robust, and simplified models",
                "rerun figure planning after changing the analysis route",
                "lower the research claim if stronger evidence cannot be produced",
            ],
        ))
    elif validity_decision == "conditional_pass" or data_decision == "conditional_pass":
        likely_sources.append("claim_overreach")
        routes.append(_rescue_route(
            "claim_reframing",
            "Reframe the manuscript around a defensible exploratory claim",
            "research_plan",
            "The current evidence is usable only if the manuscript avoids stronger-than-supported conclusions.",
            [
                "rewrite the research objective as exploratory or hypothesis-generating",
                "remove causal or generalizable language unless external validation is added",
                "align Introduction, Results, and Discussion with the supported claim boundary",
            ],
        ))
    if method_requirements and not method_requirements.get("minimum_primary_metric"):
        likely_sources.append("unclear_success_threshold")
        routes.append(_rescue_route(
            "explicit_success_threshold",
            "Define statistical success thresholds before rerunning results",
            "method_plan",
            "The method contract does not define a minimum primary metric, making result validity hard to judge.",
            [
                "set a primary metric and minimum acceptable value",
                "justify the threshold from literature or target-journal expectations",
                "rerun result validity after regenerating method outputs",
            ],
        ))

    weak_routes, weak_sources = _weak_effect_rescue_routes(metadata, archive_context, weak_effects)
    if weak_routes:
        likely_sources.extend(weak_sources)
        existing_route_ids = {route["route_id"] for route in routes}
        routes.extend(route for route in weak_routes if route["route_id"] not in existing_route_ids)

    domain_routes, domain_sources = _domain_statistical_routes(metadata, archive_context)
    if domain_routes and (routes or issues or validity_decision in {"revise_required", "conditional_pass"} or data_decision in {"revise_required", "conditional_pass"}):
        likely_sources.extend(domain_sources)
        existing_route_ids = {route["route_id"] for route in routes}
        routes.extend(route for route in domain_routes if route["route_id"] not in existing_route_ids)

    if not routes:
        routes.append(_rescue_route(
            "normal_revision",
            "Proceed with normal reviewer-driven refinement",
            "results",
            "No deterministic statistical rescue trigger was detected.",
            [
                "keep figure interpretation aligned with metadata",
                "use reviewer feedback to decide whether additional robustness analysis is needed",
            ],
        ))

    for route in routes:
        if route["route_id"] == "normal_revision":
            continue
        severity = "blocking" if route["target_stage"] in {"data", "methods"} and validity_decision == "revise_required" else "major"
        issues.append(_issue(
            source="statistical_rescue",
            code=route["route_id"],
            severity=severity,
            target_stage=route["target_stage"],
            title=route["title"],
            reason=route["rationale"],
            files=[
                "data/data_quality_report.json",
                "data/data_feasibility_report.json",
                "methods/method_requirements.json",
                "results/result_validity_report.json",
            ],
            user_input="Choose whether to revise data, revise methods, add robustness analysis, or lower the manuscript claim strength.",
        ))

    status = "rescue_recommended" if issues else "no_rescue_needed"
    diagnosis = (
        "The current evidence chain has data/result weaknesses that may be improved through statistical processing, method revision, or claim reframing."
        if issues else
        "No deterministic statistical-rescue trigger was found; continue normal reviewer-guided revision."
    )
    plan = {
        "status": status,
        "generated_at": utc_now(),
        "project_path": str(project_path),
        "diagnosis": diagnosis,
        "likely_failure_sources": sorted(set(likely_sources)),
        "recommended_routes": routes,
        "issue_count": len(issues),
        "issues": [asdict(issue) for issue in _dedupe_issues(issues)],
        "readiness_score": readiness.get("readiness_score"),
        "readiness_band": readiness.get("readiness_band"),
    }
    review_dir = _review_dir(project_path)
    _write_json(review_dir / "statistical_rescue_plan.json", plan)
    write_html_report(review_dir / "statistical_rescue_plan.html", _render_statistical_rescue_md(plan), title="Statistical Rescue Plan")
    _write_claim_evidence_matrix(project_path, readiness, plan)
    return plan


def diagnose_gate_failures(project: str | Path) -> dict[str, Any]:
    """Convert failed gate reports into actionable revision issues."""
    try:
        state = load_project(project)
    except Exception as exc:
        raise ReviewRevisionError(str(exc)) from exc
    project_path = state.path
    issues: list[RevisionIssue] = []

    data_report = _read_json(project_path / "data" / "data_feasibility_report.json")
    if data_report and data_report.get("decision") not in {"pass", "conditional_pass"}:
        reason = "; ".join(str(item) for item in data_report.get("blocking_issues") or []) or f"Data feasibility decision is {data_report.get('decision')}."
        issues.append(_issue(
            source="data_feasibility",
            code=str(data_report.get("decision") or "data_gate_failed"),
            severity="blocking",
            target_stage="data",
            title="Data cannot support the current scientific goal",
            reason=reason,
            files=["data/raw", "data/processed", "data/data_feasibility_report.json", "research_plan/research_plan.md"],
            user_input="Decide whether to add data, revise variables, reduce claim strength, or change the research question.",
        ))

    run_manifest = _read_json(project_path / "methods" / "run_manifest.yaml")
    if run_manifest and run_manifest.get("status") != "success":
        missing = ", ".join(str(item) for item in run_manifest.get("missing_outputs") or [])
        reason = f"Method verification status is {run_manifest.get('status')}."
        if missing:
            reason += f" Missing outputs: {missing}."
        issues.append(_issue(
            source="methods",
            code="method_run_failed",
            severity="blocking",
            target_stage="methods",
            title="Method verification did not complete successfully",
            reason=reason,
            files=["code/scripts/run_analysis.py", "methods/run_manifest.yaml", "methods/method_requirements.json"],
            user_input="Confirm whether to fix generated code, change method requirements, or provide missing input data.",
        ))

    validity_report = _read_json(project_path / "results" / "result_validity_report.json")
    if validity_report and validity_report.get("decision") not in {"pass", "conditional_pass"}:
        causes = set(str(item) for item in validity_report.get("failure_causes") or [])
        target = "data" if "data" in causes else "methods" if "method" in causes else "research_plan"
        reason = "; ".join(str(item) for item in validity_report.get("issues") or validity_report.get("recommended_actions") or [])
        if not reason:
            reason = f"Result validity decision is {validity_report.get('decision')}."
        issues.append(_issue(
            source="result_validity",
            code=str(validity_report.get("decision") or "result_validity_failed"),
            severity="blocking",
            target_stage=target,
            title="Results do not support the planned claim strength",
            reason=reason,
            files=["results/result_validity_report.json", "methods/run_manifest.yaml", "methods/method_requirements.json"],
            user_input="Decide whether to revise the method/data route or lower the manuscript claim strength.",
        ))

    integrity_report = _read_json(project_path / "integrity" / "integrity_report.json")
    if integrity_report and integrity_report.get("status") != "passed":
        for raw in integrity_report.get("issues") or []:
            if str(raw.get("severity") or "") not in {"error", "blocking"}:
                continue
            target = _stage_for_integrity_issue(raw)
            issues.append(_issue(
                source="integrity",
                code=str(raw.get("code") or "integrity_failed"),
                severity="blocking",
                target_stage=target,
                title="Traceability or result-artifact integrity failed",
                reason=str(raw.get("message") or "Integrity gate failed."),
                files=[str(raw.get("file") or "integrity/integrity_report.json")],
                user_input="Fix the traceability table, section citations, result manifest, or missing local artifacts.",
            ))

    quality_report = _read_json(project_path / "quality_checks" / "quality_report.json")
    if quality_report and quality_report.get("status") != "passed":
        for raw in quality_report.get("issues") or []:
            if str(raw.get("severity") or "") != "error":
                continue
            target = _stage_for_quality_issue(raw)
            issues.append(_issue(
                source="quality",
                code=str(raw.get("code") or "quality_failed"),
                severity="major",
                target_stage=target,
                title="Final quality gate failed",
                reason=str(raw.get("message") or "Quality gate failed."),
                files=[str(raw.get("file") or "quality_checks/quality_report.json")],
                user_input="Repair the affected upstream stage, rerun assembly, then rerun integrity and quality checks.",
            ))

    issues = _dedupe_issues(issues)
    review_dir = _review_dir(project_path)
    report = {
        "status": "issues_found" if issues else "passed",
        "generated_at": utc_now(),
        "project_path": str(project_path),
        "issue_count": len(issues),
        "issues": [asdict(issue) for issue in issues],
    }
    _write_json(review_dir / "gate_failure_diagnosis.json", report)
    (review_dir / "gate_failure_diagnosis.md").write_text(_render_issue_md("Gate Failure Diagnosis", issues), encoding="utf-8")
    return report


def review_draft(project: str | Path) -> dict[str, Any]:
    """Run a deterministic reviewer-style pass and emit review issues."""
    try:
        state = load_project(project)
    except Exception as exc:
        raise ReviewRevisionError(str(exc)) from exc
    project_path = state.path
    issues: list[RevisionIssue] = []
    main_tex = _read_text(project_path / "latex" / "main.tex")
    results_tex = _read_text(project_path / "results" / "results.tex")
    discussion_tex = _read_text(project_path / "discussion" / "discussion.tex")
    methods_manifest = _read_json(project_path / "methods" / "run_manifest.yaml")
    validity = _read_json(project_path / "results" / "result_validity_report.json")

    if not main_tex.strip():
        issues.append(_issue(
            source="reviewer",
            code="missing_assembled_latex",
            severity="major",
            target_stage="latex",
            title="No assembled manuscript was found for review",
            reason="latex/main.tex is missing or empty, so the reviewer pass cannot inspect the full draft.",
            files=["latex/main.tex"],
            user_input="Run LaTeX assembly after upstream sections are current.",
        ))
    if methods_manifest.get("status") != "success":
        issues.append(_issue(
            source="reviewer",
            code="methods_not_reproducible",
            severity="blocking",
            target_stage="methods",
            title="Methods are not yet reproducible from a successful run manifest",
            reason="A reviewer would not accept a Methods section whose local verification manifest is missing or failed.",
            files=["methods/run_manifest.yaml", "code/scripts/run_analysis.py"],
            user_input="Fix or rerun method verification before relying on the method narrative.",
        ))
    if validity.get("decision") == "conditional_pass":
        issues.append(_issue(
            source="reviewer",
            code="claim_strength_conditional",
            severity="major",
            target_stage="results",
            title="Result claims should be framed as exploratory or conditional",
            reason="The result validity gate is conditional, so Results and Discussion should avoid confirmatory language.",
            files=["results/result_validity_report.json", "results/results.tex", "discussion/discussion.tex"],
            user_input="Confirm whether to lower the claim strength or improve data/method evidence.",
        ))
    elif validity and validity.get("decision") not in {"pass", "conditional_pass"}:
        issues.append(_issue(
            source="reviewer",
            code="unsupported_result_claim",
            severity="blocking",
            target_stage="results",
            title="Results do not yet support the manuscript claims",
            reason="The reviewer layer sees a failed result-validity decision, so the draft should not proceed as a completed manuscript.",
            files=["results/result_validity_report.json", "results/results.tex"],
            user_input="Revise method/data or lower the research claim before final review.",
        ))
    if results_tex.strip() and not discussion_tex.strip():
        issues.append(_issue(
            source="reviewer",
            code="missing_discussion",
            severity="major",
            target_stage="discussion",
            title="Discussion is missing after Results exist",
            reason="A reviewer expects the Discussion to compare findings, limitations, and implications after Results are drafted.",
            files=["discussion/discussion.tex", "results/results.tex"],
            user_input="Run or revise Discussion writing after Results are current.",
        ))

    issues = _dedupe_issues(issues)
    review_dir = _review_dir(project_path)
    payload = {
        "status": "reviewed",
        "generated_at": utc_now(),
        "project_path": str(project_path),
        "issue_count": len(issues),
        "issues": [asdict(issue) for issue in issues],
    }
    _write_json(review_dir / "reviewer_issues.json", payload)
    (review_dir / "review_report.md").write_text(_render_issue_md("Reviewer Draft Report", issues), encoding="utf-8")
    return payload


def _load_issue_payload(path: Path) -> list[RevisionIssue]:
    payload = _read_json(path)
    issues: list[RevisionIssue] = []
    for raw in payload.get("issues") or []:
        try:
            issues.append(RevisionIssue(**{field: raw.get(field) for field in RevisionIssue.__dataclass_fields__}))
        except TypeError:
            continue
    return issues


def _write_commitment_ledger(path: Path, issues: list[RevisionIssue]) -> None:
    fieldnames = ["issue_id", "source", "target_stage", "decision", "status", "commitment", "updated_at"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for issue in issues:
            writer.writerow({
                "issue_id": issue.issue_id,
                "source": issue.source,
                "target_stage": issue.target_stage,
                "decision": "revise",
                "status": issue.status,
                "commitment": issue.required_user_input,
                "updated_at": utc_now(),
            })


def generate_revision_plan(project: str | Path) -> dict[str, Any]:
    """Merge gate diagnosis, reviewer issues, readiness issues, and statistical rescue issues."""
    try:
        state = load_project(project)
    except Exception as exc:
        raise ReviewRevisionError(str(exc)) from exc
    project_path = state.path
    review_dir = _review_dir(project_path)
    if not (review_dir / "gate_failure_diagnosis.json").exists():
        diagnose_gate_failures(project_path)
    if not (review_dir / "publication_readiness_report.json").exists():
        assess_publication_readiness(project_path)
    if not (review_dir / "review_engineering_plan.json").exists():
        propose_review_engineering_plan(project_path)
    if not (review_dir / "statistical_rescue_plan.json").exists():
        recommend_statistical_revision(project_path)

    issues = []
    issues.extend(_load_issue_payload(review_dir / "gate_failure_diagnosis.json"))
    issues.extend(_load_issue_payload(review_dir / "reviewer_issues.json"))
    issues.extend(_load_issue_payload(review_dir / "publication_readiness_report.json"))
    issues.extend(_load_issue_payload(review_dir / "review_engineering_plan.json"))
    issues.extend(_load_issue_payload(review_dir / "statistical_rescue_plan.json"))
    issues = _dedupe_issues(issues)
    by_stage: dict[str, list[dict[str, Any]]] = {}
    for issue in issues:
        by_stage.setdefault(issue.target_stage, []).append(asdict(issue))
    plan = {
        "status": "revision_required" if issues else "no_revision_needed",
        "generated_at": utc_now(),
        "project_path": str(project_path),
        "issue_count": len(issues),
        "issues": [asdict(issue) for issue in issues],
        "by_stage": by_stage,
        "recommended_stage_order": _recommended_stage_order(issues),
    }
    _write_json(review_dir / "revision_plan.json", plan)
    (review_dir / "revision_plan.md").write_text(_render_issue_md("Revision Plan", issues), encoding="utf-8")
    _write_commitment_ledger(review_dir / "commitment_ledger.csv", issues)
    return plan


def _recommended_stage_order(issues: list[RevisionIssue]) -> list[str]:
    order = ["references", "research_plan", "data", "method_plan", "figure_plan", "code", "methods", "result_validity", "results", "discussion", "latex", "quality_checks"]
    present = {issue.target_stage for issue in issues}
    return [stage for stage in order if stage in present]


def apply_revision(project: str | Path, *, issue_ids: list[str] | None = None, dry_run: bool = False) -> dict[str, Any]:
    """Apply the safe part of a revision plan by marking affected stages stale."""
    try:
        state = load_project(project)
    except Exception as exc:
        raise ReviewRevisionError(str(exc)) from exc
    project_path = state.path
    plan_path = project_path / "review" / "revision_plan.json"
    if not plan_path.exists():
        generate_revision_plan(project_path)
    plan = _read_json(plan_path)
    selected = set(issue_ids or [])
    issues = [issue for issue in plan.get("issues") or [] if not selected or issue.get("issue_id") in selected]
    target_stages = sorted({str(issue.get("target_stage")) for issue in issues if issue.get("target_stage")})
    stale_changes: dict[str, list[str]] = {}
    if not dry_run:
        for stage in target_stages:
            stale_changes[stage] = mark_stage_stale(project_path, stage, include_self=True)
    report = {
        "status": "dry_run" if dry_run else "applied",
        "generated_at": utc_now(),
        "project_path": str(project_path),
        "issue_count": len(issues),
        "target_stages": target_stages,
        "stale_changes": stale_changes,
        "message": "Scientific content was not edited automatically; affected stages were marked stale for explicit rerun.",
    }
    review_dir = _review_dir(project_path)
    _write_json(review_dir / "apply_revision_report.json", report)
    (review_dir / "apply_revision_report.md").write_text(_render_apply_md(report), encoding="utf-8")
    return report


def _render_apply_md(report: dict[str, Any]) -> str:
    lines = [
        "# Apply Revision Report",
        "",
        f"Status: {report['status']}",
        f"Generated at: {report['generated_at']}",
        "",
        "Scientific content was not edited automatically. The CLI marked affected stages stale so the normal staged workflow can rerun them.",
        "",
        "## Target Stages",
        "",
    ]
    for stage in report.get("target_stages") or ["none"]:
        lines.append(f"- {stage}")
    lines.append("")
    return "\n".join(lines)


def re_review(project: str | Path) -> dict[str, Any]:
    """Rerun gate diagnosis, reviewer pass, and revision planning after revisions."""
    diagnosis = diagnose_gate_failures(project)
    review = review_draft(project)
    readiness = assess_publication_readiness(project)
    rescue = recommend_statistical_revision(project)
    plan = generate_revision_plan(project)
    project_path = Path(plan["project_path"])
    report = {
        "status": "passed" if plan.get("issue_count") == 0 else "revision_required",
        "generated_at": utc_now(),
        "project_path": str(project_path),
        "gate_issue_count": diagnosis.get("issue_count", 0),
        "reviewer_issue_count": review.get("issue_count", 0),
        "publication_readiness_score": readiness.get("readiness_score"),
        "publication_readiness_band": readiness.get("readiness_band"),
        "statistical_rescue_issue_count": rescue.get("issue_count", 0),
        "revision_issue_count": plan.get("issue_count", 0),
        "revision_plan": REVISION_PLAN_JSON,
    }
    review_dir = _review_dir(project_path)
    _write_json(review_dir / "re_review_report.json", report)
    (review_dir / "re_review_report.md").write_text(_render_re_review_md(report), encoding="utf-8")
    return report


def _render_re_review_md(report: dict[str, Any]) -> str:
    return (
        "# Re-review Report\n\n"
        f"Status: {report['status']}\n\n"
        f"Gate issues: {report['gate_issue_count']}\n\n"
        f"Reviewer issues: {report['reviewer_issue_count']}\n\n"
        f"Publication readiness: {report.get('publication_readiness_score')} ({report.get('publication_readiness_band')})\n\n"
        f"Statistical rescue issues: {report['statistical_rescue_issue_count']}\n\n"
        f"Revision issues: {report['revision_issue_count']}\n\n"
        f"Revision plan: {report['revision_plan']}\n"
    )
