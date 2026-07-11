# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

"""Aggregate figure, Results, section, and citation quality into one release score."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .project_scaffold import utc_now
from .project_state import load_project


REPORT = "quality_checks/paper_quality_parity_report.json"
MINIMUM_SCORE = 0.95


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError):
        return {}
    return value if isinstance(value, dict) else {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _section_text(project: Path, section: str) -> str:
    for relative in [f"{section}/{section}.tex", f"latex/sections/{section}.tex"]:
        path = project / relative
        if path.exists():
            return path.read_text(encoding="utf-8-sig", errors="replace")
    return ""


def _marker_score(text: str, groups: list[list[str]], *, minimum_citations: int = 0) -> float:
    lowered = text.lower()
    hits = sum(any(marker in lowered for marker in group) for group in groups)
    denominator = len(groups) + (1 if minimum_citations else 0)
    if minimum_citations:
        citations = len(re.findall(r"\\cite\w*\{", text))
        hits += citations >= minimum_citations
    score = hits / max(1, denominator)
    if re.search(r"(?:[A-Za-z]:[/\\]|results[/\\]figures|methods[/\\]|\.csv\b|\.py\b)", text, flags=re.I):
        score = max(0.0, score - 0.25)
    return round(score, 4)


def assess_paper_quality_parity(project: str | Path) -> dict[str, Any]:
    state = load_project(project)
    result_quality = _read_json(state.path / "review" / "results_manuscript_quality.json")
    if not result_quality:
        result_quality = _read_json(state.path / "review" / "result_discipline_review_report.json").get("manuscript_quality") or {}
    figure_quality = _read_json(state.path / "results" / "scientific_figure_quality_report.json")
    citation_quality = _read_json(state.path / "citation_audit" / "final_citation_audit_report.json")
    coverage = citation_quality.get("reference_coverage") if isinstance(citation_quality.get("reference_coverage"), dict) else {}
    citation_score = 1.0 if citation_quality.get("decision") == "pass" and int(citation_quality.get("blocking_issue_count") or 0) == 0 and float(coverage.get("coverage_ratio") or 1.0) >= 0.95 else 0.0

    section_scores = {
        "introduction": _marker_score(_section_text(state.path, "introduction"), [
            ["problem", "challenge", "unresolved"], ["gap", "however", "remains"], ["objective", "we therefore", "we investigate"], ["hypothesis", "test whether", "research question"],
        ], minimum_citations=2),
        "data": _marker_score(_section_text(state.path, "data"), [
            ["data source", "dataset", "observations"], ["cohort", "sample", "sources"], ["processing", "processed", "harmonized", "quality control"], ["missingness", "coverage", "availability", "boundary"],
        ]),
        "methods": _marker_score(_section_text(state.path, "methods"), [
            ["model", "method", "algorithm"], ["\\begin{equation}", "\\["], [" where ", " denotes ", " represents "], ["validation", "held-out", "cross-validation"], ["baseline", "ablation", "sensitivity"],
        ]),
        "discussion": _marker_score(_section_text(state.path, "discussion"), [
            ["compared with", "prior work", "previous studies"], ["innovation", "contribution", "novel"], ["limitation", "constraint", "caveat"], ["future", "external validation", "follow-up", "motivates"],
        ], minimum_citations=1),
    }
    dimensions = {
        "figures": float(figure_quality.get("score") or 0.0),
        "results": float(result_quality.get("score") or 0.0),
        **section_scores,
        "citations": citation_score,
    }
    weights = {"figures": 0.20, "results": 0.25, "methods": 0.15, "data": 0.10, "introduction": 0.10, "discussion": 0.15, "citations": 0.05}
    score = round(sum(dimensions[key] * weights[key] for key in weights), 4)
    repair_priorities = [
        {"section": key, "score": dimensions[key], "weight": weights[key]}
        for key in weights if dimensions[key] < MINIMUM_SCORE
    ]
    repair_priorities.sort(key=lambda item: (item["score"], -item["weight"]))
    report = {
        "status": "written",
        "schema_version": "v0.21.0",
        "generated_at": utc_now(),
        "project_id": state.metadata.get("project_id"),
        "score": score,
        "minimum_score": MINIMUM_SCORE,
        "decision": "pass" if score >= MINIMUM_SCORE and not repair_priorities else "repair_required",
        "dimensions": dimensions,
        "weights": weights,
        "repair_priorities": repair_priorities,
        "policy": "The release score measures scientific function and evidence consistency, not lexical similarity to a reference manuscript.",
    }
    _write_json(state.path / REPORT, report)
    return report
