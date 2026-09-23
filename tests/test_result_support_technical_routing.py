# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json

from draftpaper_cli.project_scaffold import create_project
from draftpaper_cli.result_support import assess_result_support


def test_binding_failure_is_not_presented_as_a_scientific_route(tmp_path) -> None:
    project = create_project(
        root=tmp_path,
        idea="Technical evidence binding",
        field="machine learning",
    ).path
    (project / "results" / "result_validity_report.json").write_text(
        json.dumps({"decision": "pass", "evidence_strength": "meets_threshold"}),
        encoding="utf-8",
    )
    (project / "research_plan" / "claim_contract.json").write_text(
        json.dumps({
            "claims": [{
                "claim_id": "bounded",
                "claim_text": "The current analysis is exploratory.",
            }],
        }),
        encoding="utf-8",
    )
    (project / "methods" / "run_manifest.yaml").write_text(
        json.dumps({"status": "success", "run_id": "run-current"}),
        encoding="utf-8",
    )
    (project / "results" / "metric_identity_report.json").write_text(
        json.dumps({
            "status": "blocked",
            "blocking_reasons": [{"status": "blocked_missing_primary_metric_contract"}],
        }),
        encoding="utf-8",
    )

    result = assess_result_support(project)
    report = json.loads(
        (project / "results" / "result_support_checkpoint.json").read_text(encoding="utf-8")
    )

    assert result["decision"] == "technical_repair_required"
    assert result["requires_user_decision"] is False
    assert report["scientific_route_required"] is False
    assert report["route_options"] == []
    assert report["technical_blockers"]
    assert report["technical_blockers"][0]["failure_type"] == "metric_identity_gate"
    assert all(
        item.get("assessment_kind") != "technical"
        for item in report["failed_claims"]
    )
