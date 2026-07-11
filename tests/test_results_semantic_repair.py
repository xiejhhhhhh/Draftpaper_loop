# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json

from draftpaper_cli.project_scaffold import create_project


def test_prepare_semantic_repair_prefers_claim_rewrite_over_full_results_regeneration(tmp_path) -> None:
    from draftpaper_cli.results_semantic_repair import prepare_results_semantic_repair

    project = create_project(root=tmp_path, idea="Model result", field="machine learning", target_journal="Test").path
    (project / "results" / "results.tex").write_text("The baseline reached ROC AUC of 0.9422.\n", encoding="utf-8")
    review_dir = project / "review"
    review_dir.mkdir(exist_ok=True)
    review_dir.joinpath("result_discipline_review_report.json").write_text(json.dumps({
        "decision": "repair_required",
        "results_semantic_audit": {"issues": [{
            "kind": "untraceable_metric_claim", "severity": "repair_required", "detail": "AUC of 0.9422 is not present in verified result evidence."
        }]},
        "manuscript_quality": {"score": 0.85, "issues": [{"kind": "untraceable_metric_claim", "metric_name": "auc", "value": 0.9422}]},
    }), encoding="utf-8")
    (project / "methods" / "run_manifest.yaml").write_text(json.dumps({"status": "success", "metrics": {"f1_macro": 0.8667}}), encoding="utf-8")

    result = prepare_results_semantic_repair(project)
    plan = json.loads((project / "review" / "results_semantic_repair_plan.json").read_text(encoding="utf-8"))

    assert result["task_count"] == 1
    assert plan["tasks"][0]["repair_priority"] == ["rewrite_claim", "narrow_claim", "remove_unsupported_metric_clause"]
    assert plan["tasks"][0]["forbid_full_section_regeneration"] is True
    assert plan["recommended_next_command"] == "prepare-section-writing"
