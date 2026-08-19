"""Deterministic offline literature and parser-route quality benchmarks."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .literature_relevance import apply_relevance_gate
from .project_scaffold import _write_json
from .document_normalization import normalize_mineru_markdown, normalize_pypdf


BENCHMARK_RESOURCE = Path(__file__).resolve().parent / "resources" / "literature_benchmark.json"
PARSER_BENCHMARK_RESOURCE = Path(__file__).resolve().parent / "resources" / "document_parser_benchmark.json"


def _load(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def run_literature_quality_benchmark(output: str | Path | None = None) -> dict[str, Any]:
    resource = _load(BENCHMARK_RESOURCE)
    topic_reports: list[dict[str, Any]] = []
    for topic in resource.get("topics") or []:
        if not isinstance(topic, dict):
            continue
        contract = topic.get("query_contract") if isinstance(topic.get("query_contract"), dict) else {}
        candidates = topic.get("candidates") if isinstance(topic.get("candidates"), list) else []
        accepted, rejected = apply_relevance_gate(candidates, contract)
        relevant = {str(value) for value in topic.get("relevant_titles") or []}
        hard_negatives = {str(value) for value in topic.get("hard_negative_titles") or []}
        active = [item for item in accepted if item.get("gate_state") == "accepted"]
        review_required = [item for item in accepted if item.get("gate_state") == "review_required"]
        selected_titles = {str(item.get("title") or "") for item in active}
        true_positive = len(selected_titles & relevant)
        false_positive = len(selected_titles - relevant)
        hard_negative_active = len(selected_titles & hard_negatives)
        topic_reports.append({
            "topic_id": topic.get("topic_id"),
            "candidate_count": len(candidates),
            "selected_count": len(active),
            "review_required_count": len(review_required),
            "rejected_count": len(rejected),
            "precision_at_10": round(true_positive / max(1, len(active)), 4),
            "positive_recall": round(true_positive / max(1, len(relevant)), 4),
            "off_discipline_contamination_rate": round(false_positive / max(1, len(active)), 4),
            "hard_negative_active_count": hard_negative_active,
            "selected_titles": sorted(selected_titles),
            "review_required_titles": sorted(str(item.get("title") or "") for item in review_required),
        })
    precision = sum(report["precision_at_10"] for report in topic_reports) / max(1, len(topic_reports))
    recall = sum(report["positive_recall"] for report in topic_reports) / max(1, len(topic_reports))
    contamination = sum(report["off_discipline_contamination_rate"] for report in topic_reports) / max(1, len(topic_reports))
    hard_negative_active_count = sum(report["hard_negative_active_count"] for report in topic_reports)
    report = {
        "schema_version": "dpl.literature_quality_benchmark.v2",
        "status": (
            "passed"
            if precision >= 0.8 and recall >= 0.95 and contamination == 0.0 and hard_negative_active_count == 0
            else "review_required"
        ),
        "topic_count": len(topic_reports),
        "mean_precision_at_10": round(precision, 4),
        "mean_positive_recall": round(recall, 4),
        "mean_off_discipline_contamination_rate": round(contamination, 4),
        "hard_negative_active_count": hard_negative_active_count,
        "thresholds": {
            "precision_at_10": 0.8,
            "positive_recall": 0.95,
            "off_discipline_contamination_rate": 0.0,
            "hard_negative_active_count": 0,
        },
        "topics": topic_reports,
        "mode": "offline_frozen_fixture",
    }
    if output:
        _write_json(Path(output), report)
    return report


def run_document_parser_benchmark(output: str | Path | None = None) -> dict[str, Any]:
    resource = _load(PARSER_BENCHMARK_RESOURCE)
    routes = ["pypdf", "official-agent", "custom-endpoint"]
    cases = []
    route_totals = {route: {"expected": 0, "covered": 0, "schema_valid": 0, "locatable_passages": 0} for route in routes}
    for case in resource.get("cases") or []:
        if not isinstance(case, dict):
            continue
        expected = {str(value) for value in case.get("expected_capabilities") or []}
        route_capabilities = case.get("route_capabilities") if isinstance(case.get("route_capabilities"), dict) else {}
        route_results = {}
        for route in routes:
            provided = {str(value) for value in route_capabilities.get(route) or []}
            if route == "pypdf":
                normalized = normalize_pypdf(
                    "fixture.pdf",
                    [{"page": 1, "text": "Abstract\nMethods\nResults", "char_count": 24}],
                    document_id="fixture:pdf",
                    work_id="fixture:work",
                    quality={"status": "passed"},
                )
            else:
                normalized = normalize_mineru_markdown(
                    "# Methods\nA structured passage.\n# Results\nA result passage.",
                    document_id="fixture:pdf",
                    work_id="fixture:work",
                    mode=route,
                )
            schema_valid = normalized.get("schema_version") == "dpl.normalized_document.v1" and normalized.get("work_id") == "fixture:work"
            covered = len(expected & provided)
            route_totals[route]["expected"] += len(expected)
            route_totals[route]["covered"] += covered
            route_totals[route]["schema_valid"] += int(schema_valid)
            route_totals[route]["locatable_passages"] += sum(len(page.get("blocks") or []) for page in normalized.get("pages") or [] if isinstance(page, dict))
            route_results[route] = {
                "provided_capabilities": sorted(provided),
                "capability_recall": round(covered / max(1, len(expected)), 4),
                "normalized_schema": normalized.get("schema_version"),
                "schema_valid": schema_valid,
                "evidence_locator_count": sum(len(page.get("blocks") or []) for page in normalized.get("pages") or [] if isinstance(page, dict)),
                "mode": "frozen_route_contract",
            }
        cases.append({
            "case_id": case.get("case_id"),
            "expected_capabilities": sorted(expected),
            "routes": route_results,
        })
    route_summary = {}
    for route, totals in route_totals.items():
        route_summary[route] = {
            "capability_recall": round(totals["covered"] / max(1, totals["expected"]), 4),
            "schema_valid_case_rate": round(totals["schema_valid"] / max(1, len(cases)), 4),
            "evidence_locator_count": totals["locatable_passages"],
        }
    report = {
        "schema_version": "dpl.document_parser_benchmark.v1",
        "status": "passed" if cases and all(summary["schema_valid_case_rate"] == 1.0 for summary in route_summary.values()) else "review_required",
        "case_count": len(cases),
        "routes": routes,
        "route_summary": route_summary,
        "cases": cases,
        "deployment_required": False,
        "mode": "frozen_route_contract",
        "note": "This deterministic fixture measures route capability declarations and normalized-schema/evidence-locator contracts; it is not a live MinerU accuracy benchmark and does not require MinerU deployment.",
    }
    if output:
        _write_json(Path(output), report)
    return report
