from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from draftpaper_cli.checkpoint_brief import build_human_decision_brief
from draftpaper_cli.checkpoint_fingerprint import build_scientific_decision_fingerprint, compare_scientific_decisions
from draftpaper_cli.checkpoint_html import render_checkpoint_decision_html
from draftpaper_cli.checkpoint_migration import audit_checkpoint_v5_migration
from draftpaper_cli.checkpoint_readability import build_checkpoint_readability_report
from draftpaper_cli.checkpoint_scope import build_checkpoint_scope
from draftpaper_cli.checkpoint_shadow import _summary_schema, shadow_checkpoint_v5
from draftpaper_cli.checkpoint_summary import show_checkpoint_summary, write_stage_summary_v4
from draftpaper_cli.confirmation_continuity import evaluate_confirmation_continuity
from draftpaper_cli.doctor import verify_next_action
from draftpaper_cli.evidence_repair_router import route_evidence_failures
from draftpaper_cli.figure_claim_map import build_figure_claim_map, validate_figure_claim_map
from draftpaper_cli.orchestrator import checkpoint_project
from draftpaper_cli.project_scaffold import create_project
from draftpaper_cli.reviewer_visibility import validate_reviewer_visible_frozen
from draftpaper_cli.stage_activity import build_stage_activity_bundle


def _summary(*, split_id: str = "split-a", cohort_id: str = "cohort-a", metric_value: float = 0.71, figure_sha: str = "figure-a") -> dict:
    return {
        "checkpoint_type": "core_evidence",
        "completed_stage": "core_evidence",
        "stage_purpose_zh": "确认核心结果、运行身份和论断边界。",
        "identity": {
            "plan_hash": "plan-a",
            "run_id": "run-a",
            "cohort_id": cohort_id,
            "sample_unit": "source",
            "cohort_label": "source-held-out",
            "evidence_snapshot_id": "snapshot-a",
            "analysis_spec_ids": ["analysis-a"],
            "method_analysis_contract_sha256": "method-contract-a",
        },
        "core_metrics": {
            "run_id": "run-a",
            "sample_unit": "source",
            "validation_design": "source-held-out",
            "metric": "macro_f1",
            "metric_definition_id": "macro-f1-v1",
            "value": metric_value,
            "uncertainty": "bootstrap-95ci",
            "split_id": split_id,
            "cohort_id": cohort_id,
            "model_id": "model-a",
            "aggregation_id": "macro-v1",
            "metric_source": "results/metrics.json",
            "sample_flow": [
                {
                    "count_definition_id": "test_sources",
                    "entity_type": "source",
                    "count_mode": "unique",
                    "cohort_id": cohort_id,
                    "filter_contract_id": "quality-v1",
                    "value": 20,
                }
            ],
        },
        "key_findings": [{"summary_zh": "主模型的 source-held-out macro-F1 已登记。", "summary_en": "The source-held-out macro-F1 for the primary model is registered.", "source_paths": ["results/metrics.json"]}],
        "claim_boundaries": [{"summary_zh": "结论仅适用于登记的 cohort 和 source-held-out 划分。", "summary_en": "The conclusion is limited to the registered cohort and source-held-out split.", "source_paths": ["core_evidence/core_evidence_report.json"]}],
        "stage_deliverables": [
            {
                "deliverable_group": "figure",
                "project_relative_path": "results/figures/main.png",
                "title_zh": "Figure 1",
                "after_semantic_sha256": figure_sha,
                "caption": "Source-held-out evaluation.",
                "caption_en": "Source-held-out evaluation.",
                "interpretation_summary": "该图展示主结果。",
                "interpretation_summary_en": "This figure shows the primary result.",
                "split_id": split_id,
                "cohort_id": cohort_id,
                "caption_split_id": split_id,
                "caption_cohort_id": cohort_id,
                "series_ids": ["primary"],
                "caption_series_ids": ["primary"],
                "claim_series_ids": ["primary"],
                "quantity_kind": "class_conditional_rate",
                "caption_quantity_kind": "class_conditional_rate",
                "claim_quantity_kind": "class_conditional_rate",
            }
        ],
        "inspection_targets": [{"project_relative_path": "results/figures/main.png", "purpose_zh": "主结果图。", "deliverable_group": "figure"}],
        "decision_routes": [],
        "review_state": "confirmable",
        "confirmation_meaning_zh": "确认后可以继续下游写作。",
    }


def _fingerprint(summary: dict) -> dict:
    brief = build_human_decision_brief(summary)
    return build_scientific_decision_fingerprint(summary, brief, figure_claim_map=build_figure_claim_map(summary, brief))


def test_v5_package_binds_the_readable_page_audit_and_scientific_request(tmp_path: Path) -> None:
    project = create_project(root=tmp_path / "project", idea="one canonical checkpoint package", field="generic").path
    checkpoint = checkpoint_project(project, stage="data")
    package = project / checkpoint["checkpoint_summary"]["project_relative_dir"]
    summary = json.loads((package / "stage_summary.json").read_text(encoding="utf-8"))
    request = json.loads((package / "confirmation_request.json").read_text(encoding="utf-8"))
    agent = json.loads((package / "agent_payload.json").read_text(encoding="utf-8"))
    decision_html = (package / "stage_summary.zh-CN.html").read_text(encoding="utf-8")
    audit_html = (package / "stage_audit.zh-CN.html").read_text(encoding="utf-8")

    assert summary["schema_version"] == "dpl.checkpoint_summary.v5"
    assert request["schema_version"] == "dpl.confirmation_request.v2"
    assert request["scientific_decision_sha256"] == summary["scientific_decision_fingerprint"]["scientific_decision_sha256"]
    assert request["human_brief_semantic_sha256"] == summary["human_brief_semantic_sha256"]
    assert "stage_summary_sha256" not in request
    assert (package / "human_decision_brief_v1.json").is_file()
    assert (package / "figure_claim_map_v1.json").is_file()
    assert summary["audit_bundle_ref"].endswith("stage_audit.zh-CN.html")
    assert "本次确认什么" in decision_html
    assert "Agent实际工作" not in decision_html
    assert "Agent实际工作" in audit_html
    assert list(agent)[:2] == ["primary_human_review_html", "human_decision_html"]
    assert list(agent)[-1] == "technical_audit_html"
    assert agent["primary_human_review_html"]["project_relative_path"].endswith("stage_summary.zh-CN.html")
    assert Path(agent["primary_human_review_html"]["absolute_path"]).is_relative_to(project)
    assert Path(agent["technical_audit_html"]["absolute_path"]).is_relative_to(project)
    assert agent["stage_completion_summary_zh"]
    assert agent["decision_question_zh"]
    assert agent["decision_summary_zh"]
    assert agent["semantic_delta_summary_zh"]
    assert 1 <= len(agent["review_points_zh"]) <= 5
    assert agent["decision_actor_type"]
    assert agent["decision_authority_reason_zh"]
    assert agent["confirmation_meaning_zh"]


def test_verify_next_action_returns_the_readable_page_for_pending_checkpoint(tmp_path: Path) -> None:
    project = create_project(root=tmp_path / "project", idea="next action review path", field="generic").path
    checkpoint = checkpoint_project(project, stage="data")

    verified = verify_next_action(project)

    assert verified["status"] == "passed"
    assert verified["command"] == "resume"
    assert verified["primary_human_review_html"]["project_relative_path"] == checkpoint["stage_summary_zh_html"]["project_relative_path"]
    assert Path(verified["primary_human_review_html"]["absolute_path"]).is_relative_to(project)
    assert Path(verified["technical_audit_html"]["absolute_path"]).is_relative_to(project)


def test_fingerprint_ignores_paths_order_and_presentation_but_detects_scientific_change() -> None:
    first_summary = _summary()
    first = _fingerprint(first_summary)
    presentation = copy.deepcopy(first_summary)
    presentation["core_metrics"]["metric_source"] = r"D:\other-machine\results\metrics.json"
    presentation["key_findings"][0]["source_paths"] = ["/srv/project/results/metrics.json"]
    presentation["stage_deliverables"][0]["project_relative_path"] = "exports/renamed-main.png"
    presentation["stage_narrative_zh"] = "仅改变页面措辞。"
    presentation["artifact_manifest"] = {"created_at": "2030-01-01T00:00:00Z", "order": ["b", "a"]}
    assert _fingerprint(presentation)["scientific_decision_sha256"] == first["scientific_decision_sha256"]

    cases = (
        _summary(metric_value=0.72),
        _summary(split_id="split-b"),
        _summary(cohort_id="cohort-b"),
        _summary(figure_sha="figure-b"),
    )
    for changed_summary in cases:
        assert compare_scientific_decisions(first, _fingerprint(changed_summary))["requires_reconfirmation"] is True
    claim_changed = _summary()
    claim_changed["claim_boundaries"][0]["summary_zh"] = "结论只适用于经过独立确认的子样本。"
    assert compare_scientific_decisions(first, _fingerprint(claim_changed))["requires_reconfirmation"] is True
    method_changed = _summary()
    method_changed["identity"]["method_analysis_contract_sha256"] = "method-contract-b"
    assert compare_scientific_decisions(first, _fingerprint(method_changed))["requires_reconfirmation"] is True


def test_figure_claim_series_binding_participates_in_the_scientific_fingerprint() -> None:
    first_summary = _summary()
    first = _fingerprint(first_summary)

    changed_summary = copy.deepcopy(first_summary)
    changed_figure = changed_summary["stage_deliverables"][0]
    changed_figure["series_ids"] = ["primary", "secondary"]
    changed_figure["caption_series_ids"] = ["secondary"]
    changed_figure["claim_series_ids"] = ["secondary"]
    changed = _fingerprint(changed_summary)

    assert compare_scientific_decisions(first, changed)["requires_reconfirmation"] is True


@pytest.mark.parametrize(
    ("review_state", "identity_complete", "delta_class", "reason_code"),
    [
        ("stale", True, "no_scientific_change", "checkpoint_not_confirmable"),
        ("confirmable", False, "no_scientific_change", "incomplete_scientific_identity"),
        ("confirmable", True, "unknown", "semantic_delta_unknown"),
        ("confirmable", True, "no_scientific_change", "evidence_conflict"),
    ],
)
def test_missing_stale_unknown_and_conflict_cannot_use_continuity(
    tmp_path: Path,
    review_state: str,
    identity_complete: bool,
    delta_class: str,
    reason_code: str,
) -> None:
    project = create_project(root=tmp_path, idea="continuity guard", field="generic").path
    fingerprint = _fingerprint(_summary())
    fingerprint["identity_complete"] = identity_complete
    result = evaluate_confirmation_continuity(
        project,
        checkpoint_type="core_evidence",
        scientific_fingerprint=fingerprint,
        brief_semantic_sha256="brief-a",
        review_state=review_state,
        semantic_delta_class=delta_class,
        blocked_reason_codes=[reason_code] if reason_code == "evidence_conflict" else [],
    )
    assert result["eligible"] is False
    assert result["classification"] == "blocked"
    assert reason_code in result["reason_codes"]


def test_bilingual_decision_pages_render_the_same_statement_and_fact_ids(tmp_path: Path) -> None:
    summary = _summary()
    brief = build_human_decision_brief(summary)
    brief["semantic_delta"] = {"classification": "first_scientific_decision", "summary_zh": "这是首次科学确认。", "changes": []}
    summary.update(
        {
            "schema_version": "dpl.checkpoint_summary.v5",
            "checkpoint_title_zh": "核心证据确认",
            "checkpoint_title_en": "Core evidence confirmation",
            "decision_brief": brief,
            "confirmation_continuity": {"eligible": False},
            "scientific_decision_fingerprint": _fingerprint(summary),
            "confirmation_contract": {"confirmation_command_allowed": False},
        }
    )
    zh_html = render_checkpoint_decision_html(tmp_path, tmp_path, summary, {})
    en_html = render_checkpoint_decision_html(tmp_path, tmp_path, summary, {}, locale="en")
    zh = build_checkpoint_readability_report(html=zh_html, brief=brief)
    en = build_checkpoint_readability_report(html=en_html, brief=brief, locale="en")
    assert zh["status"] == "passed"
    assert en["status"] == "passed"
    assert zh["rendered_statement_ids"] == en["rendered_statement_ids"]
    assert zh["rendered_fact_ids"] == en["rendered_fact_ids"]
    assert "@media (max-width:680px)" in zh_html
    assert "What this decision confirms" in en_html


def test_readability_gate_enforces_the_author_page_hard_budget(tmp_path: Path) -> None:
    summary = _summary()
    brief = build_human_decision_brief(summary)
    brief["semantic_delta"] = {"classification": "first_scientific_decision", "summary_zh": "这是首次科学确认。", "changes": []}
    summary.update(
        {
            "schema_version": "dpl.checkpoint_summary.v5",
            "checkpoint_title_zh": "核心证据确认",
            "decision_brief": brief,
            "confirmation_continuity": {"eligible": False},
            "scientific_decision_fingerprint": _fingerprint(summary),
            "confirmation_contract": {"confirmation_command_allowed": False},
        }
    )
    html = render_checkpoint_decision_html(tmp_path, tmp_path, summary, {})
    baseline = build_checkpoint_readability_report(html=html, brief=brief)
    assert baseline["status"] == "passed"
    assert baseline["checks"]["decision_state_present"] is True
    assert baseline["checks"]["priority_sections_in_order"] is True
    assert baseline["checks"]["html_bytes_within_budget"] is True

    oversized = html.replace("</body>", "<p>" + ("x" * 12001) + "</p></body>")
    blocked = build_checkpoint_readability_report(html=oversized, brief=brief)
    assert blocked["status"] == "blocked"
    assert "visible_chars_within_budget" in blocked["failure_codes"]


def test_legacy_v4_migration_audit_is_read_only_and_requires_explicit_v5_c3(tmp_path: Path) -> None:
    project = create_project(root=tmp_path / "project", idea="legacy migration", field="generic").path
    legacy = write_stage_summary_v4(
        project,
        stage="data",
        command="checkpoint",
        payload={"status": "checkpoint_created"},
        before_artifacts=[],
        checkpoint_id="legacy-v4",
        checkpoint_hash="legacy-hash",
    )
    summary_path = Path(legacy["absolute_stage_summary_json"])
    before = summary_path.read_bytes()
    audit = audit_checkpoint_v5_migration(project, checkpoint_hash="legacy-hash")
    assert audit["status"] == "legacy_read_only"
    assert audit["migration_action"] == "create_new_v5_checkpoint_and_request_c3"
    assert audit["source_files_mutated"] is False
    assert summary_path.read_bytes() == before
    assert not (summary_path.parent / "stage_summary.en.html").exists()
    shadow = shadow_checkpoint_v5(project, output_root=tmp_path / "legacy-shadow")
    assert shadow["status"] == "passed"
    assert shadow["report"]["checkpoints"][0]["status"] == "legacy_read_only"


def test_pre_figure_claim_v5_package_is_read_only_and_never_silently_reconfirmed(tmp_path: Path) -> None:
    project = create_project(root=tmp_path / "project", idea="pre figure map v5", field="generic").path
    checkpoint = checkpoint_project(project, stage="data")
    summary_path = project / checkpoint["checkpoint_summary"]["project_relative_dir"] / "stage_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["scientific_decision_fingerprint"]["canonical_payload"].pop("figure_claim_map", None)
    summary.pop("scientific_figure_claim_sha256", None)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    before = summary_path.read_bytes()

    audit = audit_checkpoint_v5_migration(project, checkpoint_hash=checkpoint["checkpoint_hash"])
    assert audit["status"] == "legacy_read_only"
    assert audit["migration_action"] == "create_new_v5_checkpoint_and_request_c3"
    assert audit["reason_codes"] == ["legacy_v5_pre_figure_claim_fingerprint"]

    shown = show_checkpoint_summary(project, checkpoint["checkpoint_hash"])
    assert shown["status"] == "legacy_summary"
    assert shown["migration_action"] == "create_new_v5_checkpoint_and_request_c3"
    assert shown["legacy_reason_codes"] == ["legacy_v5_pre_figure_claim_fingerprint"]
    assert shown["stage_summary_zh_html"]["absolute_path"].endswith("stage_summary.zh-CN.html")

    shadow = shadow_checkpoint_v5(project, output_root=tmp_path / "pre-figure-shadow")
    assert shadow["status"] == "passed"
    assert shadow["report"]["project_state_unchanged"] is True
    assert shadow["report"]["checkpoints"][0]["status"] == "legacy_read_only"
    assert summary_path.read_bytes() == before


def test_pre_method_analysis_v5_core_package_is_read_only_and_requires_new_c3(tmp_path: Path) -> None:
    project = create_project(root=tmp_path / "project", idea="pre method identity", field="generic").path
    checkpoint = checkpoint_project(project, stage="data")
    summary_path = project / checkpoint["checkpoint_summary"]["project_relative_dir"] / "stage_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["checkpoint_type"] = "core_evidence"
    summary["completed_stage"] = "core_evidence"
    fingerprint = _fingerprint(_summary())
    fingerprint["canonical_payload"]["scientific_identity"].pop("analysis_spec_ids", None)
    fingerprint["canonical_payload"]["scientific_identity"].pop("method_analysis_contract_sha256", None)
    summary["scientific_decision_fingerprint"] = fingerprint
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    before = summary_path.read_bytes()

    audit = audit_checkpoint_v5_migration(project, checkpoint_hash=checkpoint["checkpoint_hash"])
    shown = show_checkpoint_summary(project, checkpoint["checkpoint_hash"])

    assert audit["status"] == "legacy_read_only"
    assert audit["reason_codes"] == ["legacy_v5_pre_method_analysis_fingerprint"]
    assert shown["status"] == "legacy_summary"
    assert shown["legacy_reason_codes"] == ["legacy_v5_pre_method_analysis_fingerprint"]
    assert summary_path.read_bytes() == before


def test_shadow_legacy_schema_probe_tolerates_a_utf8_window_boundary(tmp_path: Path) -> None:
    path = tmp_path / "stage_summary.json"
    header = b'{\n  "schema_version": "dpl.checkpoint_summary.v4",\n  "title": "'
    # Place a multi-byte Chinese character across the 64 KiB read boundary.
    path.write_bytes(header + (b"x" * (64 * 1024 - len(header) - 1)) + "中".encode() + b'"\n}')
    assert _summary_schema(path) == "dpl.checkpoint_summary.v4"


def test_shadow_checkpoint_v5_writes_only_outside_project(tmp_path: Path) -> None:
    project = create_project(root=tmp_path / "project", idea="shadow", field="generic").path
    checkpoint = checkpoint_project(project, stage="data")
    summary_path = project / checkpoint["checkpoint_summary"]["project_relative_dir"] / "stage_summary.json"
    before = summary_path.read_bytes()
    output = tmp_path / "shadow-output"
    result = shadow_checkpoint_v5(project, output_root=output)
    assert result["status"] == "passed"
    assert result["report"]["project_state_unchanged"] is True
    assert summary_path.read_bytes() == before
    assert Path(result["report_json"]).is_file()
    assert Path(result["report_html"]).is_file()
    with pytest.raises(ValueError):
        shadow_checkpoint_v5(project, output_root=project / "shadow-output")


def test_scope_and_activity_remain_bounded_after_long_history(tmp_path: Path) -> None:
    project = create_project(root=tmp_path / "project", idea="bounded", field="generic").path
    trace = project / "workflow_trace.jsonl"
    historic = [
        {
            "command_id": f"old-{index}",
            "command": "assess-data-quality",
            "stage": "data",
            "action_kind": "analyze",
            "process_status": "completed",
            "completed_at": "2026-01-01T00:00:00+00:00",
        }
        for index in range(50)
    ]
    current = {
        "command_id": "current",
        "command": "assess-data-quality",
        "stage": "data",
        "action_kind": "validate",
        "process_status": "completed",
        "completed_at": "2026-01-03T00:00:00+00:00",
    }
    trace.write_text("\n".join(json.dumps(item) for item in [*historic, current]) + "\n", encoding="utf-8")
    (project / "checkpoint_ledger.jsonl").write_text(
        json.dumps({"kind": "checkpoint", "stage": "data", "hash": "boundary", "created_at": "2026-01-02T00:00:00+00:00"}) + "\n",
        encoding="utf-8",
    )
    (project / "data" / "cache").mkdir(exist_ok=True)
    (project / "data" / "cache" / "failed.json").write_text("{}", encoding="utf-8")
    bundle = build_stage_activity_bundle(project, stage="data", command="checkpoint")
    scope = build_checkpoint_scope(project, stage="data")
    assert [item["activity_id"] for item in bundle["actions"]] == ["current"]
    assert "data/cache/failed.json" not in {item["project_relative_path"] for item in scope["artifacts"]}


def test_figure_claim_map_and_repair_router_block_semantic_mismatch_and_looping() -> None:
    summary = _summary()
    summary["stage_deliverables"][0]["claim_series_ids"] = ["not-plotted"]
    summary["stage_deliverables"][0]["caption_quantity_kind"] = "absolute_count"
    mapping = build_figure_claim_map(summary, build_human_decision_brief(summary))
    codes = {item["code"] for item in validate_figure_claim_map(mapping)}
    assert {"manuscript_series_not_plotted", "caption_quantity_kind_mismatch"} <= codes
    route = route_evidence_failures(
        [{"code": "split_identity_mismatch", "detail_zh": "split mismatch"}],
        failure_history=["producer"],
    )
    assert route["loop_guard"]["stop_and_report"] is True
    assert route["revision_intent"]["allowed_change_classes"] == ["evidence_repair"]


def test_reviewer_visible_bundle_rejects_internal_audit_material() -> None:
    issues = validate_reviewer_visible_frozen(
        {
            "manuscript": [{"path": "latex/main.pdf"}],
            "audit": [{"path": "review/checkpoints/core/stage_audit.zh-CN.html"}],
        }
    )
    assert issues == [{"path": "review/checkpoints/core/stage_audit.zh-CN.html", "code": "internal_audit_path_in_reviewer_bundle"}]
