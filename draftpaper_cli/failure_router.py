"""Classify failed release predicates and route the smallest valid repair."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


FAILURE_DOMAINS = {
    "artifact_stale",
    "citation_support",
    "manuscript_semantic",
    "reproducibility_package",
    "render_quality",
    "scientific_analysis",
    "figure_contract",
    "human_review_required",
}


@dataclass(frozen=True)
class FailureRoute:
    domain: str
    predicate: str
    artifact: str
    command: str
    reason: str
    prohibited_commands: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["prohibited_commands"] = list(self.prohibited_commands)
        return payload


_CITATION_CODES = {
    "citation_audit_missing",
    "citation_audit_stale",
    "citation_audit_failed",
    "citation_audit_not_final",
    "citation_audit_after_final_draft",
    "citation_audit_passed",
    "reference_coverage_preserved",
}
_REPRODUCIBILITY_CODES = {
    "reproducibility_bundle_missing",
    "reproducibility_bundle_incomplete",
    "reproducibility_smoke_failed",
    "two_independent_single_manuscript_reviews_passed",
}
_RENDER_CODES = {
    "pdf_missing",
    "pdf_invalid",
    "figure_render_quality",
    "figure_legibility",
    "latex_compile_failed",
}
_FIGURE_CODES = {
    "figure_scientific_quality_passed",
    "figure_contract_failed",
    "figure_semantic_contract_failed",
}
_ANALYSIS_CODES = {
    "results_evidence_quality_passed",
    "no_blocking_evidence_conflicts",
    "analysis_spec_failed",
    "result_validity_failed",
}


def classify_failure(predicate: str, artifact: str = "") -> str:
    """Return a stable, domain-neutral failure class for one true predicate."""
    code = str(predicate or "").strip().lower()
    path = str(artifact or "").replace("\\", "/").lower()
    if "stale" in code or path.endswith("stale_marker.json"):
        return "artifact_stale"
    if code in _CITATION_CODES or "citation" in code or path.startswith("citation_audit/"):
        return "citation_support"
    if code in _REPRODUCIBILITY_CODES or "reproduc" in code or "blind_review" in code:
        return "reproducibility_package"
    if code in _RENDER_CODES or "render" in code or "legib" in code:
        return "render_quality"
    if code in _FIGURE_CODES or "figure_contract" in code or "figure_semantic" in code:
        return "figure_contract"
    if code in _ANALYSIS_CODES or "analysis" in code or "evidence_conflict" in code:
        return "scientific_analysis"
    if "review" in code or "confirmation" in code or "human" in code:
        return "human_review_required"
    return "manuscript_semantic"


def route_failure(predicate: str, artifact: str = "", *, detail: str = "") -> FailureRoute:
    domain = classify_failure(predicate, artifact)
    routes = {
        "artifact_stale": ("sync-artifact-stale", "Synchronize the declared artifact dependency state before rerunning its owner."),
        "citation_support": ("audit-citations --final", "Refresh or repair citation support against the final assembled manuscript."),
        "manuscript_semantic": ("apply-section-revision", "Repair the affected manuscript claim without reopening scientific execution."),
        "reproducibility_package": ("prepare-independent-review", "Rebuild and smoke-test the dependency-closed anonymous review bundle."),
        "render_quality": ("compile-latex-pdf", "Repair publication rendering without changing scientific evidence."),
        "scientific_analysis": ("prepare-analysis-revision", "Repair or supplement the declared scientific analysis."),
        "figure_contract": ("plan-figures", "Reopen figure planning because the scientific figure contract itself changed or failed."),
        "human_review_required": ("review-final-manuscript", "Present the current immutable review packet for the required human decision."),
    }
    command, reason = routes[domain]
    prohibited = () if domain in {"scientific_analysis", "figure_contract"} else ("plan-figures",)
    return FailureRoute(
        domain=domain,
        predicate=str(predicate or "unknown_failure"),
        artifact=str(artifact or ""),
        command=command,
        reason=detail.strip() or reason,
        prohibited_commands=prohibited,
    )


def routes_from_quality_report(report: dict[str, Any]) -> list[dict[str, Any]]:
    """Compile deterministic routes from failed hard checks and concrete issues."""
    rows: list[FailureRoute] = []
    parity = report.get("paper_quality_parity") if isinstance(report.get("paper_quality_parity"), dict) else {}
    for predicate, passed in (parity.get("hard_checks") or {}).items():
        if passed is not True:
            rows.append(route_failure(str(predicate), "quality_checks/paper_quality_parity_report.json"))
    for issue in report.get("issues") or []:
        if not isinstance(issue, dict) or str(issue.get("severity")) != "error":
            continue
        rows.append(route_failure(str(issue.get("code") or "quality_error"), str(issue.get("path") or ""), detail=str(issue.get("message") or "")))
    unique: dict[tuple[str, str, str], FailureRoute] = {}
    for row in rows:
        unique[(row.domain, row.predicate, row.artifact)] = row
    return [row.as_dict() for row in unique.values()]


def primary_route(report: dict[str, Any]) -> dict[str, Any] | None:
    routes = routes_from_quality_report(report)
    if not routes:
        return None
    priority = {
        "artifact_stale": 0,
        "citation_support": 1,
        "reproducibility_package": 2,
        "render_quality": 3,
        "manuscript_semantic": 4,
        "scientific_analysis": 5,
        "figure_contract": 6,
        "human_review_required": 7,
    }
    return sorted(routes, key=lambda item: (priority.get(str(item.get("domain")), 99), str(item.get("predicate"))))[0]


def repair_artifact_for_domain(project: str | Path, domain: str) -> Path:
    root = Path(project)
    locations = {
        "citation_support": root / "citation_audit" / "final_citation_audit_report.json",
        "reproducibility_package": root / "quality_checks" / "blind_reviews" / "review_bundle_manifest.json",
        "render_quality": root / "latex" / "main.pdf",
        "figure_contract": root / "results" / "figure_contract_gate_report.json",
        "scientific_analysis": root / "results" / "result_validity_report.json",
    }
    return locations.get(domain, root / "review" / "revision_plan.json")
