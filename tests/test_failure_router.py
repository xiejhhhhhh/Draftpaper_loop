from draftpaper_cli.cli_output import compact_payload
from draftpaper_cli.failure_router import classify_failure, primary_route, route_failure


def test_failure_domains_do_not_route_citations_or_reproducibility_to_figures() -> None:
    citation = route_failure("citation_audit_stale", "citation_audit/stale_marker.json")
    reproducibility = route_failure("reproducibility_smoke_failed", "quality_checks/blind_reviews/manifest.json")
    assert citation.domain == "artifact_stale"
    assert citation.command == "sync-artifact-stale"
    assert "plan-figures" in citation.prohibited_commands
    assert reproducibility.domain == "reproducibility_package"
    assert reproducibility.command == "prepare-independent-review"
    assert "plan-figures" in reproducibility.prohibited_commands


def test_only_analysis_and_figure_contract_failures_may_reopen_figures() -> None:
    assert classify_failure("figure_semantic_contract_failed") == "figure_contract"
    assert route_failure("figure_semantic_contract_failed").command == "plan-figures"
    assert route_failure("results_evidence_quality_passed").command == "prepare-analysis-revision"
    assert route_failure("pdf_invalid").command == "compile-latex-pdf"


def test_primary_route_prefers_stale_then_citation_before_scientific_replanning() -> None:
    report = {
        "issues": [
            {"severity": "error", "code": "figure_contract_failed", "path": "results/figure_contract_gate_report.json", "message": "bad figure"},
            {"severity": "error", "code": "citation_audit_stale", "path": "citation_audit/stale_marker.json", "message": "old audit"},
        ]
    }
    route = primary_route(report)
    assert route is not None
    assert route["domain"] == "artifact_stale"
    assert route["command"] == "sync-artifact-stale"


def test_compact_cli_payload_keeps_decision_issues_artifacts_and_next_action() -> None:
    compact = compact_payload(
        {
            "status": "failed",
            "decision": "repair_required",
            "snapshot_id": "snapshot:1",
            "error_count": 1,
            "issues": [{"code": "citation_audit_stale", "message": "old", "path": "citation_audit/stale_marker.json"}],
            "quality_report": "quality_checks/quality_report.json",
            "recommended_next_action": {"command": "audit-citations"},
            "large_debug_payload": [{"value": index} for index in range(100)],
        }
    )
    assert compact["status"] == "failed"
    assert compact["current_snapshot"] == "snapshot:1"
    assert compact["blocking_issue_count"] == 1
    assert compact["artifact_paths"] == ["quality_checks/quality_report.json"]
    assert "large_debug_payload" not in compact
