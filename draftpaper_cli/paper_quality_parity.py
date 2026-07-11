# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

"""Calibrated functional-quality and hard-correctness release assessment."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .project_scaffold import utc_now
from .project_state import load_project


REPORT = "quality_checks/paper_quality_parity_report.json"
MINIMUM_SCORE = 0.95
CORE_SECTIONS = ("introduction", "data", "methods", "results", "discussion")


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


def _bounded_score(value: Any) -> float:
    try:
        return round(max(0.0, min(1.0, float(value))), 4)
    except (TypeError, ValueError):
        return 0.0


def _timestamp(value: Any) -> datetime | None:
    text = str(value or "").strip().replace("Z", "+00:00")
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _section_report(project: Path, section: str) -> dict[str, Any]:
    return _read_json(project / "writing" / "section_validation" / f"{section}.json")


def _section_function_score(report: dict[str, Any]) -> float:
    coverage = report.get("functional_job_coverage") if isinstance(report.get("functional_job_coverage"), dict) else {}
    return _bounded_score(coverage.get("score"))


def assess_paper_quality_parity(project: str | Path) -> dict[str, Any]:
    """Assess scientific function separately from non-negotiable correctness."""
    state = load_project(project)
    result_quality = _read_json(state.path / "review" / "results_manuscript_quality.json")
    if not result_quality:
        result_quality = _read_json(state.path / "review" / "result_discipline_review_report.json").get("manuscript_quality") or {}
    figure_quality = _read_json(state.path / "results" / "scientific_figure_quality_report.json")
    citation_quality = _read_json(state.path / "citation_audit" / "final_citation_audit_report.json")
    narrative = _read_json(state.path / "writing" / "paper_brief.json")
    lifecycles = _read_json(state.path / "writing" / "section_lifecycles.json")
    matrices = _read_json(state.path / "writing" / "argument_matrices.json")
    panel_contracts = _read_json(state.path / "results" / "panel_figure_contracts.json")
    section_reports = {section: _section_report(state.path, section) for section in CORE_SECTIONS}

    result_score = _bounded_score(result_quality.get("score"))
    figure_score = _bounded_score(figure_quality.get("score"))
    intro_score = _section_function_score(section_reports["introduction"])
    data_score = _section_function_score(section_reports["data"])
    methods_score = _section_function_score(section_reports["methods"])
    discussion_score = _section_function_score(section_reports["discussion"])
    narrative_inputs = [bool(narrative), bool(panel_contracts), result_score >= MINIMUM_SCORE]
    story_score = sum(float(item) for item in narrative_inputs) / len(narrative_inputs)
    lifecycle_score = (data_score + methods_score + float(bool(lifecycles))) / 3.0
    introduction_score = (intro_score + float(bool(matrices.get("introduction_gap_matrix")))) / 2.0
    discussion_dimension = (discussion_score + float(bool(matrices.get("discussion_finding_comparison_matrix")))) / 2.0

    snapshots = {str(report.get("evidence_snapshot_id") or "") for report in section_reports.values()}
    snapshots.discard("")
    all_free = all(
        report.get("composition_mode") == "codex_free_candidate"
        and str(report.get("decision") or report.get("status")) in {"pass", "accepted"}
        and report.get("quality_parity_eligible") is True
        for report in section_reports.values()
    )
    snapshot_consistent = len(snapshots) == 1
    coherence_score = (float(all_free) + float(snapshot_consistent)) / 2.0

    dimensions = {
        "scientific_story_and_main_figure_narrative": _bounded_score(story_score),
        "results_evidence_interpretation_and_comparison": result_score,
        "reproducible_data_and_methods_expression": _bounded_score(lifecycle_score),
        "introduction_problem_gap_and_contribution": _bounded_score(introduction_score),
        "discussion_comparison_mechanism_limitation_innovation": _bounded_score(discussion_dimension),
        "figure_readability_panel_logic_and_captions": figure_score,
        "prose_naturalness_and_cross_section_coherence": _bounded_score(coherence_score),
    }
    weights = {
        "scientific_story_and_main_figure_narrative": 0.20,
        "results_evidence_interpretation_and_comparison": 0.20,
        "reproducible_data_and_methods_expression": 0.15,
        "introduction_problem_gap_and_contribution": 0.15,
        "discussion_comparison_mechanism_limitation_innovation": 0.15,
        "figure_readability_panel_logic_and_captions": 0.10,
        "prose_naturalness_and_cross_section_coherence": 0.05,
    }
    functional_score = round(sum(dimensions[key] * weights[key] for key in weights), 4)

    coverage = citation_quality.get("reference_coverage") if isinstance(citation_quality.get("reference_coverage"), dict) else {}
    citation_time = _timestamp(citation_quality.get("generated_at"))
    section_times = [_timestamp(report.get("generated_at")) for report in section_reports.values()]
    known_section_times = [item for item in section_times if item is not None]
    citation_after_final_draft = citation_time is not None and bool(known_section_times) and citation_time >= max(known_section_times)
    registry = _read_json(state.path / "writing" / "scientific_evidence_registry.json")
    conflicts = registry.get("blocking_conflicts") or registry.get("conflicts") or []
    hard_checks = {
        "all_core_sections_validated_free_prose": all_free,
        "single_approved_evidence_snapshot": snapshot_consistent,
        "results_evidence_quality_passed": result_quality.get("decision") == "pass" and result_score >= MINIMUM_SCORE,
        "figure_scientific_quality_passed": figure_quality.get("decision") == "pass" and figure_score >= MINIMUM_SCORE,
        "no_blocking_evidence_conflicts": not bool(conflicts),
        "citation_audit_passed": citation_quality.get("decision") == "pass" and int(citation_quality.get("blocking_issue_count") or 0) == 0,
        "reference_coverage_preserved": _bounded_score(coverage.get("coverage_ratio", 1.0)) >= MINIMUM_SCORE,
        "citation_audit_after_final_draft": citation_after_final_draft,
    }
    hard_correctness_score = round(sum(float(value) for value in hard_checks.values()) / len(hard_checks), 4)
    hard_correctness_passed = all(hard_checks.values())
    repair_priorities = [
        {"dimension": key, "score": dimensions[key], "weight": weights[key]}
        for key in weights if dimensions[key] < MINIMUM_SCORE
    ]
    repair_priorities.sort(key=lambda item: (item["score"], -item["weight"]))
    decision = "pass" if functional_score >= MINIMUM_SCORE and hard_correctness_passed else "repair_required"
    report = {
        "status": "written",
        "schema_version": "v0.22.0",
        "generated_at": utc_now(),
        "project_id": state.metadata.get("project_id"),
        "score": functional_score,
        "functional_quality_score": functional_score,
        "minimum_score": MINIMUM_SCORE,
        "hard_correctness_score": hard_correctness_score,
        "hard_correctness_required": 1.0,
        "hard_correctness_passed": hard_correctness_passed,
        "hard_checks": hard_checks,
        "decision": decision,
        "dimensions": dimensions,
        "weights": weights,
        "repair_priorities": repair_priorities,
        "policy": "Release quality measures scientific function rather than lexical similarity; every hard scientific correctness check must pass independently.",
    }
    _write_json(state.path / REPORT, report)
    return report
