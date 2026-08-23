from __future__ import annotations

import copy
import json
from pathlib import Path

from draftpaper_cli.checkpoint_brief import build_human_decision_brief
from draftpaper_cli.checkpoint_fingerprint import build_scientific_decision_fingerprint, compare_scientific_decisions
from draftpaper_cli.checkpoint_scope import build_checkpoint_scope
from draftpaper_cli.checkpoint_summary import validate_checkpoint_readability
from draftpaper_cli.evidence_repair_router import route_evidence_failures
from draftpaper_cli.figure_claim_map import build_figure_claim_map, validate_figure_claim_map
from draftpaper_cli.orchestrator import checkpoint_project, resume_project
from draftpaper_cli.project_scaffold import create_project
from draftpaper_cli.stage_activity import build_stage_activity_bundle
from draftpaper_cli.workflow_macros import continue_workflow


def _scientific_summary(*, split_id: str = "split-a", metric_value: float = 0.71) -> dict:
    return {
        "checkpoint_type": "core_evidence",
        "completed_stage": "core_evidence",
        "stage_purpose_zh": "确认关键图表、核心结果、运行身份和论断边界。",
        "identity": {
            "plan_hash": "plan-a",
            "run_id": "run-a",
            "cohort_id": "cohort-a",
            "sample_unit": "source",
            "cohort_label": "source-held-out",
            "evidence_snapshot_id": "snapshot-a",
        },
        "core_metrics": {
            "run_id": "run-a",
            "sample_unit": "source",
            "validation_design": "source-held-out",
            "metric": "macro_f1",
            "metric_definition_id": "macro-f1-v1",
            "value": metric_value,
            "split_id": split_id,
            "cohort_id": "cohort-a",
            "model_id": "model-a",
            "aggregation_id": "macro-v1",
            "metric_source": "results/metrics.json",
            "sample_flow": [
                {
                    "count_definition_id": "test_sources",
                    "entity_type": "source",
                    "count_mode": "unique",
                    "cohort_id": "cohort-a",
                    "filter_contract_id": "quality-v1",
                    "value": 20,
                }
            ],
        },
        "sample_flow": [],
        "key_findings": [{"summary_zh": "主模型在固定 source-held-out 划分上的 macro-F1 已登记。", "source_paths": ["results/metrics.json"]}],
        "claim_boundaries": [{"summary_zh": "结果只适用于已登记的 cohort 和 source-held-out 划分。", "source_paths": ["core_evidence/core_evidence_report.json"]}],
        "stage_deliverables": [
            {
                "deliverable_group": "figure",
                "project_relative_path": "results/figures/main.png",
                "title_zh": "Figure 1",
                "after_semantic_sha256": "figure-a",
                "caption": "Source-held-out evaluation.",
                "interpretation_summary": "该图展示固定 source-held-out 划分上的主结果。",
                "split_id": split_id,
            }
        ],
        "inspection_targets": [{"project_relative_path": "results/figures/main.png", "purpose_zh": "主结果图。", "deliverable_group": "figure"}],
        "decision_routes": [],
        "review_state": "confirmable",
        "confirmation_meaning_zh": "确认后可以继续下游写作。",
    }


def test_scientific_fingerprint_ignores_presentation_but_detects_split_and_metric_changes() -> None:
    first_summary = _scientific_summary()
    first = build_scientific_decision_fingerprint(first_summary, build_human_decision_brief(first_summary))

    presentation_only = copy.deepcopy(first_summary)
    presentation_only["stage_narrative_zh"] = "这是一段重新表述的页面文字。"
    presentation_only["artifact_manifest"] = {"reordered": True}
    presentation = build_scientific_decision_fingerprint(presentation_only, build_human_decision_brief(presentation_only))
    assert presentation["scientific_decision_sha256"] == first["scientific_decision_sha256"]

    changed_summary = _scientific_summary(split_id="split-b", metric_value=0.72)
    changed = build_scientific_decision_fingerprint(changed_summary, build_human_decision_brief(changed_summary))
    diff = compare_scientific_decisions(first, changed)
    assert diff["classification"] == "scientific_change"
    assert diff["requires_reconfirmation"] is True
    assert any("split_id" in item["field"] or "value" in item["field"] for item in diff["changes"])


def test_v5_checkpoint_page_is_readable_and_same_science_continues_without_new_user_hash(tmp_path: Path) -> None:
    project = create_project(root=tmp_path / "project", idea="continuity", field="generic scientific workflow").path
    first = checkpoint_project(project, stage="data")
    resume_project(project, checkpoint_hash=first["checkpoint_hash"])

    second = checkpoint_project(project, stage="data")
    package = project / second["checkpoint_summary"]["project_relative_dir"]
    summary = json.loads((package / "stage_summary.json").read_text(encoding="utf-8"))
    decision_html = (package / "stage_summary.zh-CN.html").read_text(encoding="utf-8")
    audit_html = (package / "stage_audit.zh-CN.html").read_text(encoding="utf-8")

    assert summary["schema_version"] == "dpl.checkpoint_summary.v5"
    assert summary["confirmation_continuity"]["eligible"] is True
    assert summary["review_requirement"] == "notify_only"
    assert "本次确认什么" in decision_html
    assert "Agent实际工作" not in decision_html
    assert "Agent实际工作" in audit_html
    assert validate_checkpoint_readability(project, checkpoint_package_id=summary["checkpoint_id"])["status"] == "passed"
    assert continue_workflow(project)["automatic_review"]["status"] == "resumed_after_system_acknowledgement"


def test_scope_does_not_promote_review_history_or_implicit_core_code(tmp_path: Path) -> None:
    project = create_project(root=tmp_path / "project", idea="scope", field="generic").path
    (project / "core_evidence").mkdir(parents=True, exist_ok=True)
    (project / "core_evidence" / "core_evidence_report.json").write_text("{}", encoding="utf-8")
    (project / "review" / "checkpoints" / "old").mkdir(parents=True, exist_ok=True)
    (project / "review" / "checkpoints" / "old" / "stage_summary.json").write_text("{}", encoding="utf-8")
    (project / "methods" / "historical").mkdir(parents=True, exist_ok=True)
    (project / "methods" / "historical" / "old_plot.py").write_text("print('old')\n", encoding="utf-8")

    scope = build_checkpoint_scope(project, stage="core_evidence")
    paths = {item["project_relative_path"] for item in scope["artifacts"]}
    assert "core_evidence/core_evidence_report.json" in paths
    assert "review/checkpoints/old/stage_summary.json" not in paths
    assert "methods/historical/old_plot.py" not in paths


def test_stage_activity_v2_starts_after_the_previous_checkpoint_boundary(tmp_path: Path) -> None:
    project = create_project(root=tmp_path / "project", idea="activity window", field="generic").path
    trace = project / "workflow_trace.jsonl"
    trace.parent.mkdir(parents=True, exist_ok=True)
    old = {
        "command_id": "old-data",
        "command": "assess-data-quality",
        "stage": "data",
        "action_kind": "analyze",
        "process_status": "completed",
        "completed_at": "2026-01-01T00:00:00+00:00",
    }
    current = {
        "command_id": "current-data",
        "command": "assess-data-quality",
        "stage": "data",
        "action_kind": "validate",
        "process_status": "completed",
        "completed_at": "2026-01-03T00:00:00+00:00",
    }
    trace.write_text("\n".join(json.dumps(item) for item in (old, current)) + "\n", encoding="utf-8")
    (project / "checkpoint_ledger.jsonl").write_text(
        json.dumps({"kind": "checkpoint", "stage": "data", "hash": "old-checkpoint", "created_at": "2026-01-02T00:00:00+00:00"}) + "\n",
        encoding="utf-8",
    )

    bundle = build_stage_activity_bundle(project, stage="data", command="checkpoint")
    action_ids = {item["activity_id"] for item in bundle["actions"]}
    assert bundle["schema_version"] == "dpl.stage_activity_bundle.v2"
    assert "current-data" in action_ids
    assert "old-data" not in action_ids
    assert bundle["activity_window"]["includes_historical_checkpoint_rows"] is False


def test_figure_claim_map_and_repair_order_fail_closed_on_identity_conflict() -> None:
    summary = _scientific_summary()
    summary["stage_deliverables"][0]["caption_split_id"] = "split-other"
    brief = build_human_decision_brief(summary)
    mapping = build_figure_claim_map(summary, brief)
    issues = validate_figure_claim_map(mapping)
    assert any(item["code"] == "split_identity_mismatch" for item in issues)

    route = route_evidence_failures(issues)
    assert route["recommended_repair_layer"] == "producer"
    assert route["repair_order"] == ["producer", "adapter", "prose", "figure", "rerun"]
