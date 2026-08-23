from __future__ import annotations

import json
from pathlib import Path

import pytest

from draftpaper_cli.checkpoint_summary import validate_checkpoint_summary, write_stage_summary_v4
from draftpaper_cli.longitudinal_consistency import audit_longitudinal_consistency
from draftpaper_cli.managed_change import ManagedChangeError, apply_managed_change, begin_managed_change
from draftpaper_cli.orchestrator import checkpoint_project
from draftpaper_cli.project_scaffold import create_project
from draftpaper_cli.revision_cycle import begin_revision_cycle, close_revision_cycle
from draftpaper_cli.review_policy import (
    ReviewPolicyError,
    configure_review_policy,
    evaluate_checkpoint_authority,
    grant_agent_review,
    revoke_agent_review,
    review_checkpoint,
)
from draftpaper_cli.scientific_baseline import create_scientific_baseline
from draftpaper_cli.workflow_macros import continue_workflow


def test_v5_checkpoint_separates_decision_page_from_activity_audit_and_is_hash_valid(tmp_path: Path) -> None:
    project = create_project(root=tmp_path / "project", idea="v5 checkpoint", field="generic").path
    checkpoint = checkpoint_project(project, stage="data")
    summary_path = project / checkpoint["checkpoint_summary"]["stage_summary_json"]
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["schema_version"] == "dpl.checkpoint_summary.v5"
    assert summary["stage_activity_bundle"]["actions"]
    assert summary["review_requirement"] == "agent_delegable"
    decision_html = (summary_path.parent / "stage_summary.zh-CN.html").read_text(encoding="utf-8")
    audit_html = (summary_path.parent / "stage_audit.zh-CN.html").read_text(encoding="utf-8")
    assert "本次确认什么" in decision_html
    assert "Agent实际工作" not in decision_html
    assert "Agent实际工作" in audit_html
    ledger_event = json.loads((project / "checkpoint_ledger.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert validate_checkpoint_summary(project, ledger_event)["valid"] is True


def test_c1_agent_review_is_distinct_from_user_confirmation(tmp_path: Path) -> None:
    project = create_project(root=tmp_path / "project", idea="delegated review", field="generic").path
    checkpoint = checkpoint_project(project, stage="data")
    delegation = grant_agent_review(project, scope="data", max_risk="C1", actor_id="producer")
    authority = evaluate_checkpoint_authority(project, checkpoint_hash=checkpoint["checkpoint_hash"])
    assert authority["can_agent_review"] is True
    result = review_checkpoint(
        project,
        checkpoint_hash=checkpoint["checkpoint_hash"],
        actor_id="reviewer",
        reviewer_agent_id="producer",
        delegation_hash=delegation["delegation"]["delegation_sha256"],
    )
    assert result["status"] == "agent_approved"
    receipt = result["receipt"]
    assert receipt["decision_status"] == "agent_approved"
    assert receipt["actor_type"] == "agent"
    assert receipt["decision_status"] != "user_confirmed"


def test_continue_consumes_only_delegated_c1_checkpoint(tmp_path: Path) -> None:
    project = create_project(root=tmp_path / "project", idea="automatic continuation", field="generic").path
    checkpoint = checkpoint_project(project, stage="data")
    grant_agent_review(project, scope="data", max_risk="C1")
    result = continue_workflow(project)
    assert result["automatic_review"]["status"] == "resumed_after_agent_review"
    events = [json.loads(line) for line in (project / "checkpoint_ledger.jsonl").read_text(encoding="utf-8").splitlines()]
    assert events[-1]["consumes_hash"] == checkpoint["checkpoint_hash"]
    assert events[-1]["decision_status"] == "agent_approved"
    assert events[-1]["actor_type"] == "agent"


def test_c3_checkpoint_cannot_be_agent_approved(tmp_path: Path) -> None:
    project = create_project(root=tmp_path / "project", idea="protected route", field="generic").path
    checkpoint = checkpoint_project(project, stage="research_plan")
    grant_agent_review(project, scope="research_plan", max_risk="C3", actor_id="agent")
    authority = evaluate_checkpoint_authority(project, checkpoint_hash=checkpoint["checkpoint_hash"])
    assert authority["review_requirement"] == "human_required"
    with pytest.raises(ReviewPolicyError):
        review_checkpoint(project, checkpoint_hash=checkpoint["checkpoint_hash"])


def test_revision_baselines_report_same_identity_conflicts(tmp_path: Path) -> None:
    project = create_project(root=tmp_path / "project", idea="baseline lineage", field="generic").path
    fact = {"fact_id": "fact-metric", "fact_type": "metric", "value": 0.7, "unit": "f1", "cohort_id": "cohort-a", "run_id": "run-a", "validation_design_id": "split-a"}
    first = create_scientific_baseline(project, facts=[fact], reason="first_confirmation")
    cycle = begin_revision_cycle(project, reason="author_update", requested_changes=["metric review"])
    changed = dict(fact)
    changed["value"] = 0.8
    second = create_scientific_baseline(project, facts=[changed], revision_cycle_id=cycle["revision_cycle"]["revision_cycle_id"], reason="revision_candidate")
    assert second["baseline"]["parent_baseline_id"] == first["baseline"]["baseline_id"]
    audit = audit_longitudinal_consistency(project)
    assert audit["status"] == "blocked"
    assert audit["report"]["conflicts"][0]["fact_id"] == "fact-metric"


def test_managed_change_requires_current_before_hash(tmp_path: Path) -> None:
    project = create_project(root=tmp_path / "project", idea="managed edits", field="generic").path
    target = project / "writing" / "paragraph.md"
    target.write_text("before\n", encoding="utf-8")
    source = tmp_path / "replacement.md"
    source.write_text("after\n", encoding="utf-8")
    packet = begin_managed_change(project, intent="replace paragraph", change_class="prose_only", paths=["writing/paragraph.md"], content_file=str(source))
    target.write_text("edited outside workflow\n", encoding="utf-8")
    with pytest.raises(ManagedChangeError):
        apply_managed_change(project, packet_id=packet["packet"]["packet_id"], packet_hash=packet["packet_hash"])


def test_managed_change_packet_remains_immutable_after_commit(tmp_path: Path) -> None:
    project = create_project(root=tmp_path / "project", idea="immutable packet", field="generic").path
    target = project / "writing" / "paragraph.md"
    target.write_text("before\n", encoding="utf-8")
    source = tmp_path / "replacement.md"
    source.write_text("after\n", encoding="utf-8")
    packet = begin_managed_change(
        project,
        intent="replace paragraph",
        change_class="prose_only",
        paths=["writing/paragraph.md"],
        content_file=str(source),
    )
    packet_path = Path(packet["packet_path"])
    packet_bytes_before = packet_path.read_bytes()

    result = apply_managed_change(
        project,
        packet_id=packet["packet"]["packet_id"],
        packet_hash=packet["packet_hash"],
    )

    assert packet_path.read_bytes() == packet_bytes_before
    assert target.read_text(encoding="utf-8") == "after\n"
    assert Path(result["receipt_path"]).is_file()
    with pytest.raises(ManagedChangeError, match="already been committed"):
        apply_managed_change(
            project,
            packet_id=packet["packet"]["packet_id"],
            packet_hash=packet["packet_hash"],
        )


def test_notify_checkpoint_auto_continues_with_system_receipt(tmp_path: Path) -> None:
    project = create_project(root=tmp_path / "project", idea="notification checkpoint", field="generic").path
    checkpoint = checkpoint_project(project, stage="idea")

    result = continue_workflow(project)

    assert result["automatic_review"]["status"] == "resumed_after_system_acknowledgement"
    event = json.loads((project / "checkpoint_ledger.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert event["decision_status"] == "system_acknowledged"
    assert event["actor_type"] == "system"
    receipt = json.loads(
        (project / checkpoint["checkpoint_summary"]["project_relative_dir"] / "review_decision_receipt.json").read_text(encoding="utf-8")
    )
    assert receipt["decision_status"] == "system_acknowledged"
    assert receipt["actor_type"] == "system"


def test_expired_and_tampered_delegations_are_not_eligible(tmp_path: Path) -> None:
    project = create_project(root=tmp_path / "project", idea="delegation integrity", field="generic").path
    checkpoint = checkpoint_project(project, stage="data")
    expired = grant_agent_review(
        project,
        scope="data",
        max_risk="C1",
        expires_at="2020-01-01T00:00:00Z",
    )
    assert evaluate_checkpoint_authority(project, checkpoint_hash=checkpoint["checkpoint_hash"])["can_agent_review"] is False

    path = Path(expired["delegation_path"])
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["expires_at"] = None
    path.write_text(json.dumps(payload), encoding="utf-8")
    authority = evaluate_checkpoint_authority(project, checkpoint_hash=checkpoint["checkpoint_hash"])
    assert authority["can_agent_review"] is False
    assert "delegation_tampered" in authority["delegation_rejection_reasons"]


def test_c2_requires_explicit_freeze_and_independent_reviewer(tmp_path: Path) -> None:
    project = create_project(root=tmp_path / "project", idea="c2 authority", field="generic").path
    checkpoint = checkpoint_project(project, stage="methods")
    grant_agent_review(project, scope="methods", max_risk="C2")
    assert evaluate_checkpoint_authority(project, checkpoint_hash=checkpoint["checkpoint_hash"])["can_agent_review"] is False
    grant = grant_agent_review(
        project,
        scope="methods",
        max_risk="C2",
        require_independent_agent=True,
        allow_scientific_freeze=True,
        producer_actor_id="producer-agent",
    )
    assert evaluate_checkpoint_authority(project, checkpoint_hash=checkpoint["checkpoint_hash"])["can_agent_review"] is True
    with pytest.raises(ReviewPolicyError, match="Independent reviewer"):
        review_checkpoint(
            project,
            checkpoint_hash=checkpoint["checkpoint_hash"],
            actor_id="producer-agent",
            delegation_hash=grant["delegation"]["delegation_sha256"],
        )
    reviewed = review_checkpoint(
        project,
        checkpoint_hash=checkpoint["checkpoint_hash"],
        actor_id="reviewer-agent",
        reviewer_agent_id="producer-agent",
        delegation_hash=grant["delegation"]["delegation_sha256"],
    )
    assert reviewed["receipt"]["decision_status"] == "agent_approved"
    assert reviewed["receipt"]["producer_actor_id"] == "producer-agent"


def test_revocation_preserves_original_delegation_and_blocks_future_review(tmp_path: Path) -> None:
    project = create_project(root=tmp_path / "project", idea="revocation", field="generic").path
    checkpoint = checkpoint_project(project, stage="data")
    delegation = grant_agent_review(project, scope="data", max_risk="C1")
    path = Path(delegation["delegation_path"])
    before = path.read_bytes()

    revoked = revoke_agent_review(project, reason="return to manual")

    assert delegation["delegation"]["delegation_id"] in revoked["revoked_delegations"]
    assert path.read_bytes() == before
    assert evaluate_checkpoint_authority(project, checkpoint_hash=checkpoint["checkpoint_hash"])["can_agent_review"] is False


def test_v5_checkpoint_requires_activity_companion(tmp_path: Path) -> None:
    project = create_project(root=tmp_path / "project", idea="v5 companion", field="generic").path
    checkpoint = checkpoint_project(project, stage="data")
    summary_dir = project / checkpoint["checkpoint_summary"]["project_relative_dir"]
    (summary_dir / "stage_activity_bundle.json").unlink()
    ledger = json.loads((project / "checkpoint_ledger.jsonl").read_text(encoding="utf-8").splitlines()[-1])

    assert validate_checkpoint_summary(project, ledger)["valid"] is False


def test_activity_narrative_names_recorded_work_and_outputs(tmp_path: Path) -> None:
    project = create_project(root=tmp_path / "project", idea="narrative detail", field="generic").path
    output = project / "data" / "quality_report.md"
    output.write_text("quality checked\n", encoding="utf-8")
    report = write_stage_summary_v4(
        project,
        stage="data",
        command="assess-data-quality",
        payload={
            "status": "checkpoint_created",
            "activity_rows": [
                {
                    "schema_version": "dpl.workflow_trace.v2",
                    "command": "assess-data-quality",
                    "stage": "data",
                    "actor_type": "agent",
                    "actor_id": "quality-agent",
                    "action_kind": "analyze",
                    "process_status": "completed",
                    "output_artifact_refs": ["artifact:data/quality_report.md"],
                    "user_visible_summary_fragment_zh": "检查了数据完整性并写出质量报告。",
                }
            ],
        },
        before_artifacts=[],
        checkpoint_id="data-narrative",
        checkpoint_hash="data-narrative-hash",
    )
    summary = json.loads(Path(report["absolute_stage_summary_json"]).read_text(encoding="utf-8"))
    html = Path(report["absolute_stage_summary_zh_html"]).read_text(encoding="utf-8")

    assert "assess-data-quality" in summary["stage_narrative_zh"]
    assert "data/quality_report.md" in summary["stage_narrative_zh"]
    assert "Agent实际工作与本阶段总结" in html
    assert "data/quality_report.md" in html


def test_policy_change_invalidates_existing_delegation(tmp_path: Path) -> None:
    project = create_project(root=tmp_path / "project", idea="policy binding", field="generic").path
    checkpoint = checkpoint_project(project, stage="data")
    grant_agent_review(project, scope="data", max_risk="C1")

    configure_review_policy(project, mode="delegated")

    authority = evaluate_checkpoint_authority(project, checkpoint_hash=checkpoint["checkpoint_hash"])
    assert authority["can_agent_review"] is False
    assert "policy_hash_mismatch" in authority["delegation_rejection_reasons"]


def test_runtime_fingerprint_change_invalidates_existing_delegation(tmp_path: Path) -> None:
    project = create_project(root=tmp_path / "project", idea="runtime binding", field="generic").path
    runtime_lock = project / ".draftpaper" / "runtime_lock.json"
    runtime_lock.write_text(json.dumps({"runtime_fingerprint": "runtime-a"}), encoding="utf-8")
    checkpoint = checkpoint_project(project, stage="data")
    grant_agent_review(project, scope="data", max_risk="C1")

    runtime_lock.write_text(json.dumps({"runtime_fingerprint": "runtime-b"}), encoding="utf-8")

    authority = evaluate_checkpoint_authority(project, checkpoint_hash=checkpoint["checkpoint_hash"])
    assert authority["can_agent_review"] is False
    assert "runtime_fingerprint_mismatch" in authority["delegation_rejection_reasons"]


def test_managed_change_rejects_new_baseline_and_closed_revision_cycle(tmp_path: Path) -> None:
    project = create_project(root=tmp_path / "project", idea="managed binding", field="generic").path
    target = project / "writing" / "paragraph.md"
    target.write_text("before\n", encoding="utf-8")
    source = tmp_path / "replacement.md"
    source.write_text("after\n", encoding="utf-8")
    first_fact = {"fact_id": "fact-metric", "fact_type": "metric", "value": 0.7, "unit": "f1"}
    create_scientific_baseline(project, facts=[first_fact], reason="seed")
    packet = begin_managed_change(
        project,
        intent="replace paragraph",
        change_class="prose_only",
        paths=["writing/paragraph.md"],
        content_file=str(source),
    )
    changed_fact = dict(first_fact)
    changed_fact["value"] = 0.8
    create_scientific_baseline(project, facts=[changed_fact], reason="new_baseline")
    with pytest.raises(ManagedChangeError, match="scientific baseline changed"):
        apply_managed_change(project, packet_id=packet["packet"]["packet_id"], packet_hash=packet["packet_hash"])

    cycle = begin_revision_cycle(project, reason="review_round", allowed_change_classes=["prose_only"])
    packet = begin_managed_change(
        project,
        intent="replace paragraph within revision",
        change_class="prose_only",
        paths=["writing/paragraph.md"],
        content_file=str(source),
    )
    close_revision_cycle(project, decision_receipt_id="test-close")
    with pytest.raises(ManagedChangeError, match="different or closed revision cycle"):
        apply_managed_change(project, packet_id=packet["packet"]["packet_id"], packet_hash=packet["packet_hash"])
    assert cycle["revision_cycle"]["status"] == "open"


def test_longitudinal_audit_blocks_protected_and_superseded_fact_consumers(tmp_path: Path) -> None:
    project = create_project(root=tmp_path / "project", idea="longitudinal consumers", field="generic").path
    protected = {
        "fact_id": "fact-protected",
        "fact_type": "metric",
        "value": 0.70,
        "unit": "f1",
        "must_preserve": True,
    }
    retired = {"fact_id": "fact-retired", "fact_type": "count", "value": 12, "unit": "objects"}
    create_scientific_baseline(project, facts=[protected, retired], reason="first")
    cycle = begin_revision_cycle(project, reason="review_round", protected_facts=["fact-protected"])
    manuscript = project / "writing" / "revision_notes.md"
    manuscript.write_text("fact-protected and fact-retired are cited here.\n", encoding="utf-8")
    changed = dict(protected)
    changed["value"] = 0.80
    create_scientific_baseline(
        project,
        facts=[changed],
        revision_cycle_id=cycle["revision_cycle"]["revision_cycle_id"],
        reason="second",
    )

    audit = audit_longitudinal_consistency(project)
    statuses = {row["status"] for row in audit["report"]["cross_artifact_conflicts"]}
    assert audit["status"] == "blocked"
    assert "protected_fact_changed" in statuses
    assert "superseded_fact_consumed" in statuses
