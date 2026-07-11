"""Versioned producer-to-consumer adapters for evolving Draftpaper artifacts."""

from __future__ import annotations

from typing import Any


def normalize_citation_audit(report: dict[str, Any], *, minimum_coverage: float = 0.95) -> dict[str, Any]:
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    coverage = report.get("reference_coverage") if isinstance(report.get("reference_coverage"), dict) else {}
    raw_status = str(report.get("status") or report.get("decision") or "").strip().lower()
    blocking_value = summary.get("blocking_issue_count", report.get("blocking_issue_count"))
    try:
        blocking_count = int(blocking_value) if blocking_value is not None else None
    except (TypeError, ValueError):
        blocking_count = None
    coverage_status = str(coverage.get("coverage_status") or "").strip().lower()
    try:
        uncited_count = int(coverage["summarized_but_uncited_count"]) if "summarized_but_uncited_count" in coverage else None
    except (TypeError, ValueError):
        uncited_count = None
    try:
        ratio = max(0.0, min(1.0, float(coverage["coverage_ratio"]))) if "coverage_ratio" in coverage else None
    except (TypeError, ValueError):
        ratio = None
    return {
        "producer_status": raw_status or "missing",
        "blocking_issue_count": blocking_count,
        "coverage_status": coverage_status or "missing",
        "summarized_but_uncited_count": uncited_count,
        "coverage_ratio": round(ratio, 4) if ratio is not None else None,
        "audit_passed": raw_status in {"passed", "pass"} and blocking_count == 0,
        "coverage_preserved": bool(coverage) and coverage_status in {"passed", "pass"} and uncited_count == 0 and (ratio is None or ratio >= minimum_coverage),
    }
