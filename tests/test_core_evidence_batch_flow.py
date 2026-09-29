"""Synthetic workflow regressions for consolidated core-evidence confirmation."""

from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from draftpaper_cli.orchestrator import OrchestratorError, checkpoint_project, resume_project, status_project
from draftpaper_cli.project_scaffold import create_project
from draftpaper_cli.revision_cycle import begin_revision_cycle
from tests.test_orchestrator_passport import write_confirmable_core_evidence


def _project_with_known_work(tmp_path: Path) -> Path:
    project = create_project(root=tmp_path, idea="Batch confirmation regression", field="generic").path
    write_confirmable_core_evidence(project)
    validity = project / "results" / "result_validity_report.json"
    begin_revision_cycle(
        project,
        reason="three related core-evidence changes",
        requested_changes=("validate result", "bind figure", "check scientific prose"),
        pending_tasks=(
            {
                "task_id": "validate_result",
                "title_zh": "核验结果",
                "title_en": "Validate result",
                "checkpoint_scope": "core_evidence",
                "effect_class": "scientific",
                "required_before_publication": True,
                "status": "completed",
                "expected_artifacts": ["results/result_validity_report.json"],
                "completion_receipts": [
                    {
                        "path": "results/result_validity_report.json",
                        "sha256": hashlib.sha256(validity.read_bytes()).hexdigest(),
                    }
                ],
            },
            {
                "task_id": "bind_figure",
                "title_zh": "绑定图表",
                "title_en": "Bind figure",
                "checkpoint_scope": "core_evidence",
                "effect_class": "binding",
                "required_before_publication": True,
                "status": "pending",
                "depends_on": ["validate_result"],
                "expected_artifacts": ["results/figure_code_trace.json"],
            },
            {
                "task_id": "check_prose",
                "title_zh": "核对论断",
                "title_en": "Check prose",
                "checkpoint_scope": "core_evidence",
                "effect_class": "scientific",
                "required_before_publication": True,
                "status": "pending",
                "depends_on": ["bind_figure"],
                "expected_artifacts": ["writing/candidates/results.tex"],
            },
        ),
    )
    return project


def test_known_batch_does_not_publish_after_first_task(tmp_path: Path) -> None:
    project = _project_with_known_work(tmp_path)

    status = status_project(project)
    assert status["pipeline_state"] != "confirmation_required"
    assert status["next_action"]["command"] != "checkpoint"
    assert set(status["core_evidence_readiness"]["blocking_tasks"]) == {"bind_figure", "check_prose"}

    with pytest.raises(OrchestratorError, match="batch|task|ready"):
        checkpoint_project(project, stage="core_evidence")

    ledger = project / "checkpoint_ledger.jsonl"
    if ledger.exists():
        assert not any(
            row.get("kind") == "checkpoint" and row.get("stage") == "core_evidence"
            for row in (json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines() if line.strip())
        )


def test_checkpoint_fails_closed_if_ready_batch_record_is_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from draftpaper_cli import core_evidence_readiness

    project = create_project(root=tmp_path / "project", idea="Missing ready batch", field="generic").path
    write_confirmable_core_evidence(project)
    monkeypatch.setattr(
        core_evidence_readiness,
        "assess_core_evidence_readiness",
        lambda _: {
            "status": "ready",
            "publishable": True,
            "scope_sha256": "a" * 64,
            "input_manifest_sha256": "b" * 64,
            "candidate_generation": 1,
        },
    )

    with pytest.raises(OrchestratorError, match="Core-evidence batch is unavailable"):
        checkpoint_project(project, stage="core_evidence")


def test_unready_batch_has_bilingual_preview_without_confirmation_action(tmp_path: Path) -> None:
    from draftpaper_cli.core_evidence_batch import prepare_core_evidence_batch
    from draftpaper_cli.core_evidence_readiness import finalize_core_evidence_batch

    project = _ready_project(tmp_path)
    pending = {
        "task_id": "check_figure_provenance",
        "title_zh": "核验图表来源",
        "title_en": "Check figure provenance",
        "checkpoint_scope": "core_evidence",
        "origin_ref": "synthetic_validation_discovery",
        "effect_class": "binding",
        "required_before_publication": True,
        "status": "pending",
        "depends_on": ["validate_result"],
        "evidence_refs": ["results/figure_code_trace.json"],
        "expected_artifacts": ["results/figure_code_trace.json"],
        "completion_checks": ["matching_artifact_hash"],
        "completion_receipts": [],
    }
    changes = project / "unready_changes.json"
    changes.write_text(json.dumps({"tasks": [pending]}, ensure_ascii=False), encoding="utf-8")
    prepare_core_evidence_batch(project, changes_path=changes)

    result = finalize_core_evidence_batch(project)
    assert result["status"] == "needs_work"
    from draftpaper_cli.cli_output import prioritize_human_review

    prioritized = prioritize_human_review(result)
    assert next(iter(prioritized)) == "primary_human_review_html"
    assert prioritized["primary_human_review_html"]["absolute_path"] == result["preview_zh_html"]
    assert prioritized["preview_en_html"] == result["preview_en_html"]
    zh = Path(result["preview_zh_html"]).read_text(encoding="utf-8")
    en = Path(result["preview_en_html"]).read_text(encoding="utf-8")
    assert "核验图表来源" in zh
    assert "Check figure provenance" in en
    assert "validate_result" in zh
    assert "check_figure_provenance" in en
    assert "resume --checkpoint-hash" not in zh + en
    assert "确认此核心证据" not in zh

    preview_bytes = {
        key: Path(result[key]).read_bytes()
        for key in ("preview_zh_html", "preview_en_html")
    }
    status = status_project(project)
    assert status["next_action"]["command"] == "agent_action_required"
    assert status["primary_human_review_html"]["absolute_path"] == result["preview_zh_html"]
    assert status["next_action"]["primary_human_review_html"]["absolute_path"] == result["preview_zh_html"]

    from draftpaper_cli.doctor import verify_next_action

    verified = verify_next_action(project)
    assert verified["status"] == "passed"
    assert verified["primary_human_review_html"]["absolute_path"] == result["preview_zh_html"]
    assert verified["preview_en_html"] == result["preview_en_html"]
    assert preview_bytes == {
        key: Path(result[key]).read_bytes()
        for key in ("preview_zh_html", "preview_en_html")
    }

    from draftpaper_cli.core_evidence_readiness import existing_unready_preview_paths

    stale_readiness = dict(status["core_evidence_readiness"])
    stale_readiness["reason_codes"] = [*stale_readiness["reason_codes"], "candidate_changed"]
    assert existing_unready_preview_paths(project, stale_readiness) == {}


def _ready_project(tmp_path: Path, *, include_extra_input: bool = False, two_tasks: bool = False) -> Path:
    from draftpaper_cli.core_evidence_batch import prepare_core_evidence_batch
    from draftpaper_cli.core_evidence_readiness import finalize_core_evidence_batch

    project = create_project(root=tmp_path, idea="One confirmation request", field="generic").path
    write_confirmable_core_evidence(project)
    validity = project / "results" / "result_validity_report.json"
    batch_note = project / "results" / "batch_note.txt"
    if include_extra_input:
        batch_note.write_text("batch-specific evidence note\n", encoding="utf-8")
    task = {
        "task_id": "validate_result",
        "title_zh": "核验结果",
        "title_en": "Validate result",
        "checkpoint_scope": "core_evidence",
        "origin_ref": "synthetic_request",
        "effect_class": "scientific",
        "required_before_publication": True,
        "status": "completed",
        "depends_on": [],
        "evidence_refs": ["results/result_validity_report.json", *(["results/batch_note.txt"] if include_extra_input else [])],
        "expected_artifacts": ["results/result_validity_report.json", *(["results/batch_note.txt"] if include_extra_input else [])],
        "completion_checks": ["matching_artifact_hash"],
        "completion_receipts": [
            {"path": "results/result_validity_report.json", "sha256": hashlib.sha256(validity.read_bytes()).hexdigest()},
            *([{"path": "results/batch_note.txt", "sha256": hashlib.sha256(batch_note.read_bytes()).hexdigest()}] if include_extra_input else []),
        ],
    }
    changes = project / "batch_changes.json"
    tasks = [task]
    if two_tasks:
        tasks.append({
            **task,
            "task_id": "check_sample_boundary",
            "title_zh": "核对样本边界",
            "title_en": "Check sample boundary",
            "effect_class": "binding",
            "depends_on": ["validate_result"],
        })
    changes.write_text(json.dumps({"tasks": tasks}, ensure_ascii=False), encoding="utf-8")
    prepare_core_evidence_batch(project, changes_path=changes)
    assert finalize_core_evidence_batch(project)["status"] == "ready"
    return project


def test_same_frozen_candidate_has_one_pending_checkpoint(tmp_path: Path) -> None:
    from draftpaper_cli.core_evidence_batch import load_core_evidence_batch, shadow_core_evidence_batch_migration

    project = _ready_project(tmp_path)
    first = checkpoint_project(project, stage="core_evidence")
    awaiting_batch = load_core_evidence_batch(project)
    assert awaiting_batch["phase"] == "awaiting_decision"
    assert awaiting_batch["request_id"] == first["checkpoint_hash"]
    second = checkpoint_project(project, stage="core_evidence")

    assert second["checkpoint_hash"] == first["checkpoint_hash"]
    assert second["status"] == "checkpoint_existing"
    ledger = project / "checkpoint_ledger.jsonl"
    events = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len([row for row in events if row.get("kind") == "checkpoint" and row.get("stage") == "core_evidence"]) == 1
    shadow = shadow_core_evidence_batch_migration(project)
    assert shadow["pending_checkpoint"]["status"] == "scoped_pending"
    assert shadow["pending_checkpoint"]["scope_binding_status"] == "matched"
    assert shadow["pending_checkpoint"]["package_validation"]["status"] == "valid"
    assert shadow["pending_checkpoint"]["reuse_eligible"] is True
    assert shadow["candidate"]["status"] == "identity_match"
    assert shadow["candidate"]["reuse_eligible"] is True
    assert shadow["recovery"]["action"] == "reuse_exact_existing_request"


def test_other_gate_task_update_does_not_reopen_frozen_core_batch(tmp_path: Path) -> None:
    from draftpaper_cli.core_evidence_batch import load_core_evidence_batch, prepare_core_evidence_batch

    project = _ready_project(tmp_path)
    first = checkpoint_project(project, stage="core_evidence")
    batch_before = load_core_evidence_batch(project)
    changes_path = project / "batch_changes.json"
    changes = json.loads(changes_path.read_text(encoding="utf-8"))
    changes["tasks"].append({
        "task_id": "release_doi",
        "checkpoint_scope": "post_acceptance",
        "status": "pending",
        "title_en": "Add the final publication DOI",
    })
    changes_path.write_text(json.dumps(changes, ensure_ascii=False), encoding="utf-8")

    prepared = prepare_core_evidence_batch(project, changes_path=changes_path)

    batch_after = load_core_evidence_batch(project)
    assert prepared["other_scope_tasks_updated"] is True
    assert any(row.get("task_id") == "release_doi" for row in prepared["revision_cycle"]["pending_tasks"])
    assert batch_after["phase"] == "awaiting_decision"
    assert batch_after["request_id"] == first["checkpoint_hash"]
    second = checkpoint_project(project, stage="core_evidence")
    assert second["status"] == "checkpoint_existing"
    assert second["checkpoint_hash"] == first["checkpoint_hash"]
    assert batch_before["scope_sha256"] == batch_after["scope_sha256"]


def test_checkpoint_retry_repairs_index_after_publish_interruption(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import draftpaper_cli.checkpoint_summary as checkpoint_summary

    project = _ready_project(tmp_path)
    original_publish = checkpoint_summary._publish_checkpoint_index

    def fail_index_publish(*args: object, **kwargs: object) -> None:
        raise RuntimeError("simulated interruption after batch publication")

    monkeypatch.setattr(checkpoint_summary, "_publish_checkpoint_index", fail_index_publish)
    with pytest.raises(RuntimeError, match="after batch publication"):
        checkpoint_project(project, stage="core_evidence")

    ledger = project / "checkpoint_ledger.jsonl"
    checkpoints = [
        json.loads(line)
        for line in ledger.read_text(encoding="utf-8").splitlines()
        if line.strip() and json.loads(line).get("stage") == "core_evidence"
    ]
    assert len(checkpoints) == 1
    index_path = project / "review" / "checkpoints" / "index.json"
    assert not index_path.exists()

    monkeypatch.setattr(checkpoint_summary, "_publish_checkpoint_index", original_publish)
    resumed = checkpoint_project(project, stage="core_evidence")
    assert resumed["status"] == "checkpoint_existing"
    index = json.loads(index_path.read_text(encoding="utf-8-sig"))
    assert [row["checkpoint_id"] for row in index["checkpoints"]] == [checkpoints[0]["checkpoint_id"]]


def test_confirmation_closes_batch_without_erasing_cycle_history(tmp_path: Path) -> None:
    from draftpaper_cli.core_evidence_batch import shadow_core_evidence_batch_migration
    from draftpaper_cli.passport import refresh_project_passport
    from draftpaper_cli.revision_cycle import ACTIVE_POINTER, _hash, load_active_revision_cycle

    project = _ready_project(tmp_path)
    checkpoint = checkpoint_project(project, stage="core_evidence")
    result = resume_project(project, checkpoint_hash=checkpoint["checkpoint_hash"])
    cycle = load_active_revision_cycle(project)
    assert result["status"] == "resumed"
    assert cycle["evidence_batch"]["phase"] == "closed"
    assert cycle["evidence_batch"]["request_id"] == checkpoint["checkpoint_hash"]
    assert cycle["evidence_batch"]["resolution_receipt_ref"]
    shadow = shadow_core_evidence_batch_migration(project)
    historical = shadow["latest_valid_user_confirmation"]
    assert historical["status"] == "found"
    assert historical["checkpoint_hash"] == checkpoint["checkpoint_hash"]
    assert historical["authorizes_current_candidate"] is False

    pointer_path = project / ACTIVE_POINTER
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    cycle_path = project / pointer["path"]
    legacy_cycle = load_active_revision_cycle(project)
    assert legacy_cycle is not None
    legacy_cycle.pop("evidence_batch", None)
    legacy_cycle["schema_version"] = "dpl.revision_cycle.v2"
    legacy_cycle.pop("revision_cycle_sha256", None)
    legacy_cycle["revision_cycle_sha256"] = _hash(legacy_cycle)
    cycle_path.write_text(json.dumps(legacy_cycle, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    pointer["revision_cycle_sha256"] = legacy_cycle["revision_cycle_sha256"]
    pointer_path.write_text(json.dumps(pointer, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    ledger_path = project / "checkpoint_ledger.jsonl"
    ledger_rows = [json.loads(line) for line in ledger_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    for row in ledger_rows:
        if row.get("kind") == "checkpoint" and row.get("hash") == checkpoint["checkpoint_hash"]:
            for key in ("batch_id", "scope_sha256", "input_manifest_sha256", "candidate_generation", "frozen_candidate_ref", "base_decision_receipt_id"):
                row.pop(key, None)
    ledger_path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in ledger_rows), encoding="utf-8")
    refresh_project_passport(project, event="legacy_history_fixture")
    legacy_shadow = shadow_core_evidence_batch_migration(project)
    assert legacy_shadow["status"] == "scope_registration_required"
    assert legacy_shadow["latest_valid_user_confirmation"]["status"] == "found"
    assert legacy_shadow["latest_valid_user_confirmation"]["receipt_id"] == historical["receipt_id"]
    assert legacy_shadow["latest_valid_user_confirmation"]["authorizes_current_candidate"] is False


def test_resume_recovers_after_decision_event_was_written(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import draftpaper_cli.orchestrator as orchestrator

    from draftpaper_cli.core_evidence_batch import load_core_evidence_batch
    from draftpaper_cli.review_policy import decision_receipt_for_checkpoint

    project = _ready_project(tmp_path)
    checkpoint = checkpoint_project(project, stage="core_evidence")
    checkpoint_hash = checkpoint["checkpoint_hash"]
    original_snapshot = orchestrator.create_evidence_snapshot

    def fail_after_decision_event(*args: object, **kwargs: object) -> dict[str, object]:
        raise RuntimeError("simulated interruption after resume event")

    monkeypatch.setattr(orchestrator, "create_evidence_snapshot", fail_after_decision_event)
    with pytest.raises(RuntimeError, match="simulated interruption"):
        resume_project(project, checkpoint_hash=checkpoint_hash)

    events = [
        json.loads(line)
        for line in (project / "checkpoint_ledger.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len([row for row in events if row.get("kind") == "resume" and row.get("consumes_hash") == checkpoint_hash]) == 1
    receipt = decision_receipt_for_checkpoint(project, checkpoint_hash)
    assert receipt and receipt["decision_status"] == "user_confirmed"
    assert load_core_evidence_batch(project)["phase"] == "awaiting_decision"

    monkeypatch.setattr(orchestrator, "create_evidence_snapshot", original_snapshot)
    recovered = resume_project(project, checkpoint_hash=checkpoint_hash)

    assert recovered["status"] == "resumed"
    assert recovered["decision_receipt"]["receipt_id"] == receipt["receipt_id"]
    assert load_core_evidence_batch(project)["phase"] == "closed"
    events = [
        json.loads(line)
        for line in (project / "checkpoint_ledger.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len([row for row in events if row.get("kind") == "resume" and row.get("consumes_hash") == checkpoint_hash]) == 1


def test_resume_recovery_rejects_batch_input_changed_after_decision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import draftpaper_cli.orchestrator as orchestrator

    from draftpaper_cli.core_evidence_batch import load_core_evidence_batch
    from draftpaper_cli.core_evidence_batch import prepare_core_evidence_batch
    from draftpaper_cli.core_evidence_readiness import finalize_core_evidence_batch
    from draftpaper_cli.review_policy import decision_receipt_for_checkpoint

    project = _ready_project(tmp_path)
    from draftpaper_cli.revision_cycle import load_active_revision_cycle

    task = dict(load_active_revision_cycle(project)["pending_tasks"][0])
    trace_path = project / "results" / "figure_code_trace.json"
    task["evidence_refs"] = [*task["evidence_refs"], "results/figure_code_trace.json"]
    task["completion_receipts"] = [
        *task["completion_receipts"],
        {"path": "results/figure_code_trace.json", "sha256": hashlib.sha256(trace_path.read_bytes()).hexdigest()},
    ]
    changes = project / "add_trace_binding.json"
    changes.write_text(json.dumps({"tasks": [task]}, ensure_ascii=False), encoding="utf-8")
    prepare_core_evidence_batch(project, changes_path=changes)
    assert finalize_core_evidence_batch(project)["status"] == "ready"
    checkpoint = checkpoint_project(project, stage="core_evidence")
    checkpoint_hash = checkpoint["checkpoint_hash"]

    def fail_after_decision_event(*args: object, **kwargs: object) -> dict[str, object]:
        raise RuntimeError("simulated interruption after resume event")

    monkeypatch.setattr(orchestrator, "create_evidence_snapshot", fail_after_decision_event)
    with pytest.raises(RuntimeError, match="simulated interruption"):
        resume_project(project, checkpoint_hash=checkpoint_hash)
    assert decision_receipt_for_checkpoint(project, checkpoint_hash)

    trace_path.write_text('{"trace_set_hash":"changed-after-confirmation"}\n', encoding="utf-8")
    with pytest.raises(OrchestratorError, match="batch changed|different candidate"):
        resume_project(project, checkpoint_hash=checkpoint_hash)
    assert load_core_evidence_batch(project)["phase"] == "awaiting_decision"


def test_resume_reuses_receipt_after_interruption_before_decision_event(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import draftpaper_cli.orchestrator as orchestrator

    from draftpaper_cli.review_policy import decision_receipt_for_checkpoint

    project = _ready_project(tmp_path)
    checkpoint = checkpoint_project(project, stage="core_evidence")
    checkpoint_hash = checkpoint["checkpoint_hash"]
    original_append = orchestrator.append_checkpoint_event

    def fail_before_resume_event(project_path: Path, event: dict[str, object]) -> None:
        if event.get("kind") == "resume":
            raise RuntimeError("simulated interruption before resume event")
        original_append(project_path, event)

    monkeypatch.setattr(orchestrator, "append_checkpoint_event", fail_before_resume_event)
    with pytest.raises(RuntimeError, match="before resume event"):
        resume_project(project, checkpoint_hash=checkpoint_hash)

    first_receipt = decision_receipt_for_checkpoint(project, checkpoint_hash)
    assert first_receipt and first_receipt["decision_status"] == "user_confirmed"
    monkeypatch.setattr(orchestrator, "append_checkpoint_event", original_append)
    resumed = resume_project(project, checkpoint_hash=checkpoint_hash)

    assert resumed["decision_receipt"]["receipt_id"] == first_receipt["receipt_id"]
    receipts = list((project / "review" / "checkpoints").rglob("review_decision_receipts"))
    receipt_files = [path for folder in receipts for path in folder.glob("*.json")]
    assert len(receipt_files) == 1


def test_resume_recovers_when_baseline_exists_but_batch_is_still_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import draftpaper_cli.core_evidence_batch as core_evidence_batch

    from draftpaper_cli.core_evidence_batch import load_core_evidence_batch
    from draftpaper_cli.scientific_baseline import BASELINE_DIR

    project = _ready_project(tmp_path)
    checkpoint = checkpoint_project(project, stage="core_evidence")
    checkpoint_hash = checkpoint["checkpoint_hash"]
    original_resolve = core_evidence_batch.resolve_core_evidence_batch

    def fail_before_batch_close(*args: object, **kwargs: object) -> dict[str, object]:
        raise RuntimeError("simulated interruption before batch close")

    monkeypatch.setattr(core_evidence_batch, "resolve_core_evidence_batch", fail_before_batch_close)
    with pytest.raises(RuntimeError, match="before batch close"):
        resume_project(project, checkpoint_hash=checkpoint_hash)

    from draftpaper_cli.review_policy import decision_receipt_for_checkpoint

    receipt = decision_receipt_for_checkpoint(project, checkpoint_hash)
    assert receipt
    baselines = [
        json.loads(path.read_text(encoding="utf-8-sig"))
        for path in (project / BASELINE_DIR).glob("*.json")
    ]
    assert len([row for row in baselines if row.get("decision_receipt_id") == receipt["receipt_id"]]) == 1
    assert load_core_evidence_batch(project)["phase"] == "awaiting_decision"

    monkeypatch.setattr(core_evidence_batch, "resolve_core_evidence_batch", original_resolve)
    recovered = resume_project(project, checkpoint_hash=checkpoint_hash)
    assert recovered["status"] == "resumed"
    assert load_core_evidence_batch(project)["phase"] == "closed"
    baselines = [
        json.loads(path.read_text(encoding="utf-8-sig"))
        for path in (project / BASELINE_DIR).glob("*.json")
    ]
    assert len([row for row in baselines if row.get("decision_receipt_id") == receipt["receipt_id"]]) == 1


def test_next_batch_after_confirmation_uses_new_candidate_generation(tmp_path: Path) -> None:
    from draftpaper_cli.core_evidence_batch import prepare_core_evidence_batch
    from draftpaper_cli.core_evidence_readiness import finalize_core_evidence_batch
    from draftpaper_cli.revision_cycle import load_active_revision_cycle

    project = _ready_project(tmp_path)
    first = checkpoint_project(project, stage="core_evidence")
    resume_project(project, checkpoint_hash=first["checkpoint_hash"])
    previous = load_active_revision_cycle(project)
    task = dict(previous["pending_tasks"][0])
    task["task_id"] = "next_round_validation"
    changes = project / "next_round_changes.json"
    changes.write_text(json.dumps({"tasks": [task]}, ensure_ascii=False), encoding="utf-8")

    prepared = prepare_core_evidence_batch(project, changes_path=changes)
    assert prepared["batch"]["batch_id"] != previous["evidence_batch"]["batch_id"]
    assert prepared["revision_cycle"]["candidate_generation"] == previous["candidate_generation"] + 1
    assert finalize_core_evidence_batch(project)["status"] == "ready"


def test_incomplete_identity_does_not_auto_preserve_prior_decision(tmp_path: Path) -> None:
    from draftpaper_cli.core_evidence_batch import load_core_evidence_batch, prepare_core_evidence_batch
    from draftpaper_cli.core_evidence_readiness import finalize_core_evidence_batch
    from draftpaper_cli.passport import load_project_passport
    from draftpaper_cli.revision_cycle import load_active_revision_cycle

    project = _ready_project(tmp_path)
    first = checkpoint_project(project, stage="core_evidence")
    resume_project(project, checkpoint_hash=first["checkpoint_hash"])
    task = dict(load_active_revision_cycle(project)["pending_tasks"][0])
    task["task_id"] = "equivalent_audit_refresh"
    changes = project / "equivalent_changes.json"
    changes.write_text(json.dumps({"tasks": [task]}, ensure_ascii=False), encoding="utf-8")
    prepare_core_evidence_batch(project, changes_path=changes)
    assert finalize_core_evidence_batch(project)["status"] == "ready"

    result = checkpoint_project(project, stage="core_evidence")
    assert result["status"] == "checkpoint_created"
    assert result["confirmation_continuity"]["eligible"] is False
    assert load_project_passport(project)["awaiting_checkpoint"]["hash"] == result["checkpoint_hash"]
    assert load_core_evidence_batch(project)["phase"] == "awaiting_decision"


def test_complete_equivalent_batch_closes_without_new_user_decision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import draftpaper_cli.core_evidence_batch as core_evidence_batch

    from draftpaper_cli.core_evidence_batch import load_core_evidence_batch, prepare_core_evidence_batch
    from draftpaper_cli.core_evidence_readiness import finalize_core_evidence_batch
    from draftpaper_cli.evidence_snapshot import reopen_evidence_snapshot
    from draftpaper_cli.passport import load_project_passport
    from draftpaper_cli.workflow_macros import continue_workflow
    from tests.test_core_confirmation_continuity_promotion import build_confirmed_continuity, system_resume

    case = build_confirmed_continuity(tmp_path)
    project = case[0]
    system_resume(case)
    reopen_evidence_snapshot(project, reason="synthetic binding refresh")
    report = project / "core_evidence" / "core_evidence_report.json"
    task = {
        "task_id": "refresh_core_binding",
        "title_zh": "刷新证据绑定",
        "title_en": "Refresh evidence binding",
        "checkpoint_scope": "core_evidence",
        "origin_ref": "synthetic_binding_refresh",
        "effect_class": "binding",
        "required_before_publication": True,
        "status": "completed",
        "depends_on": [],
        "evidence_refs": ["core_evidence/core_evidence_report.json"],
        "expected_artifacts": ["core_evidence/core_evidence_report.json"],
        "completion_checks": ["matching_artifact_hash"],
        "completion_receipts": [{"path": "core_evidence/core_evidence_report.json", "sha256": hashlib.sha256(report.read_bytes()).hexdigest()}],
    }
    changes = project / "binding_refresh.json"
    changes.write_text(json.dumps({"tasks": [task]}, ensure_ascii=False), encoding="utf-8")
    prepare_core_evidence_batch(project, changes_path=changes)
    assert finalize_core_evidence_batch(project)["status"] == "ready"

    result = checkpoint_project(project, stage="core_evidence")
    assert result["status"] == "checkpoint_created"
    assert result["confirmation_continuity"]["eligible"] is True
    assert result["confirmation_command"] is None
    assert status_project(project)["next_action"]["command"] == "continue"
    original_resolve = core_evidence_batch.resolve_core_evidence_batch

    def fail_before_batch_close(*args: object, **kwargs: object) -> dict[str, object]:
        raise RuntimeError("simulated continuity interruption before batch close")

    monkeypatch.setattr(core_evidence_batch, "resolve_core_evidence_batch", fail_before_batch_close)
    with pytest.raises(RuntimeError, match="continuity interruption"):
        continue_workflow(project)
    batch = load_core_evidence_batch(project)
    assert batch["phase"] == "awaiting_decision"

    from draftpaper_cli.review_policy import decision_receipt_for_checkpoint

    receipt = decision_receipt_for_checkpoint(project, result["checkpoint_hash"])
    assert receipt and receipt["decision_status"] == "system_acknowledged"
    monkeypatch.setattr(core_evidence_batch, "resolve_core_evidence_batch", original_resolve)
    from draftpaper_cli.orchestrator import resume_after_system_acknowledgement

    continued = resume_after_system_acknowledgement(
        project,
        checkpoint_hash=result["checkpoint_hash"],
        receipt_id=receipt["receipt_id"],
    )
    assert continued["status"] == "resumed_after_system_acknowledgement"
    assert load_project_passport(project)["awaiting_checkpoint"] is None
    assert load_core_evidence_batch(project)["phase"] == "closed"


def test_preserved_continuity_resume_recovers_before_batch_close(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import draftpaper_cli.core_evidence_batch as core_evidence_batch

    from draftpaper_cli.core_evidence_batch import load_core_evidence_batch, prepare_core_evidence_batch
    from draftpaper_cli.core_evidence_readiness import finalize_core_evidence_batch
    from draftpaper_cli.evidence_snapshot import reopen_evidence_snapshot
    from tests.test_core_confirmation_continuity_promotion import build_confirmed_continuity, system_resume

    case = build_confirmed_continuity(tmp_path)
    project = case[0]
    system_resume(case)
    reopen_evidence_snapshot(project, reason="synthetic binding refresh")
    report = project / "core_evidence" / "core_evidence_report.json"
    task = {
        "task_id": "refresh_core_binding",
        "title_zh": "刷新证据绑定",
        "title_en": "Refresh evidence binding",
        "checkpoint_scope": "core_evidence",
        "origin_ref": "synthetic_binding_refresh",
        "effect_class": "binding",
        "required_before_publication": True,
        "status": "completed",
        "depends_on": [],
        "evidence_refs": ["core_evidence/core_evidence_report.json"],
        "expected_artifacts": ["core_evidence/core_evidence_report.json"],
        "completion_checks": ["matching_artifact_hash"],
        "completion_receipts": [{"path": "core_evidence/core_evidence_report.json", "sha256": hashlib.sha256(report.read_bytes()).hexdigest()}],
    }
    changes = project / "binding_refresh.json"
    changes.write_text(json.dumps({"tasks": [task]}, ensure_ascii=False), encoding="utf-8")
    prepare_core_evidence_batch(project, changes_path=changes)
    assert finalize_core_evidence_batch(project)["status"] == "ready"
    checkpoint = checkpoint_project(project, stage="core_evidence")
    assert checkpoint["confirmation_continuity"]["eligible"] is True

    original_resolve = core_evidence_batch.resolve_core_evidence_batch

    def fail_before_batch_close(*args: object, **kwargs: object) -> dict[str, object]:
        raise RuntimeError("simulated continuity interruption before batch close")

    monkeypatch.setattr(core_evidence_batch, "resolve_core_evidence_batch", fail_before_batch_close)
    with pytest.raises(RuntimeError, match="continuity interruption"):
        resume_project(project, checkpoint_hash=checkpoint["checkpoint_hash"])
    assert load_core_evidence_batch(project)["phase"] == "awaiting_decision"

    monkeypatch.setattr(core_evidence_batch, "resolve_core_evidence_batch", original_resolve)
    recovered = resume_project(project, checkpoint_hash=checkpoint["checkpoint_hash"])
    assert recovered["status"] == "resumed_after_confirmation_continuity"
    assert load_core_evidence_batch(project)["phase"] == "closed"
    summary_dir = Path(checkpoint["checkpoint_summary"]["stage_summary_json"]).parent
    assert (summary_dir / "confirmation_continuity_receipt.json").is_file()
    assert not (summary_dir / "review_decision_receipt.json").exists()


def test_pending_checkpoint_rejects_changed_batch_input(tmp_path: Path) -> None:
    project = _ready_project(tmp_path)
    first = checkpoint_project(project, stage="core_evidence")
    (project / "results" / "result_validity_report.json").write_text(
        '{"decision": "pass", "new_scientific_result": true}', encoding="utf-8"
    )

    status = status_project(project)
    assert status["next_action"]["command"] != "resume"
    with pytest.raises(OrchestratorError, match="batch|candidate|changed"):
        resume_project(project, checkpoint_hash=first["checkpoint_hash"])
    ledger = project / "checkpoint_ledger.jsonl"
    assert not any(json.loads(line).get("kind") == "resume" for line in ledger.read_text(encoding="utf-8").splitlines())


def _make_unscoped_v2_pending_checkpoint(project: Path, checkpoint: dict[str, object]) -> tuple[Path, dict[str, object]]:
    from draftpaper_cli.passport import refresh_project_passport
    from draftpaper_cli.revision_cycle import ACTIVE_POINTER, _hash, load_active_revision_cycle

    checkpoint_hash = str(checkpoint["checkpoint_hash"])
    ledger_path = project / "checkpoint_ledger.jsonl"
    rows = [json.loads(line) for line in ledger_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    for row in rows:
        if row.get("kind") == "checkpoint" and row.get("hash") == checkpoint_hash:
            for key in ("batch_id", "scope_sha256", "input_manifest_sha256", "candidate_generation", "frozen_candidate_ref", "base_decision_receipt_id"):
                row.pop(key, None)
    ledger_path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    pointer_path = project / ACTIVE_POINTER
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    cycle_path = project / pointer["path"]
    cycle = load_active_revision_cycle(project)
    assert cycle is not None
    cycle.pop("evidence_batch", None)
    cycle["schema_version"] = "dpl.revision_cycle.v2"
    cycle["mode"] = "author_edit"
    cycle["automatic_upstream"] = False
    cycle.pop("revision_cycle_sha256", None)
    cycle["revision_cycle_sha256"] = _hash(cycle)
    cycle_path.write_text(json.dumps(cycle, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    pointer["revision_cycle_sha256"] = cycle["revision_cycle_sha256"]
    pointer_path.write_text(json.dumps(pointer, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    refresh_project_passport(project, event="legacy_checkpoint_fixture")
    event = next(row for row in rows if row.get("kind") == "checkpoint" and row.get("hash") == checkpoint_hash)
    package_path = project / str(event["stage_summary_json"])
    return ledger_path, {**cycle, "checkpoint_package_dir": str(package_path.parent)}


def test_shadow_quarantines_non_object_legacy_checkpoint_summary(tmp_path: Path) -> None:
    from draftpaper_cli.core_evidence_batch import shadow_core_evidence_batch_migration

    project = _ready_project(tmp_path)
    checkpoint = checkpoint_project(project, stage="core_evidence")
    _ledger_path, legacy = _make_unscoped_v2_pending_checkpoint(project, checkpoint)
    summary_path = Path(str(legacy["checkpoint_package_dir"])) / "stage_summary.json"
    summary_path.write_text("[]", encoding="utf-8")

    shadow = shadow_core_evidence_batch_migration(project)

    pending = shadow["pending_checkpoint"]
    assert pending["status"] == "unscoped_pending"
    assert pending["package_validation"]["status"] == "invalid"
    assert pending["package_validation"]["valid"] is False
    assert pending["association"]["eligible"] is False
    assert shadow["recovery"]["action"] == "register_new_explicit_core_evidence_batch"


def test_shadow_does_not_reopen_legacy_request_with_rejection_receipt(tmp_path: Path) -> None:
    from draftpaper_cli.core_evidence_batch import shadow_core_evidence_batch_migration
    from draftpaper_cli.review_policy import DECISION_RECEIPT_SCHEMA, _decision_hash

    project = _ready_project(tmp_path)
    checkpoint = checkpoint_project(project, stage="core_evidence")
    _ledger_path, legacy = _make_unscoped_v2_pending_checkpoint(project, checkpoint)
    package_dir = Path(str(legacy["checkpoint_package_dir"]))
    summary = json.loads((package_dir / "stage_summary.json").read_text(encoding="utf-8-sig"))
    receipt = {
        "schema_version": DECISION_RECEIPT_SCHEMA,
        "receipt_id": "rejected-legacy-decision",
        "checkpoint_hash": checkpoint["checkpoint_hash"],
        "summary_sha256": summary["stage_summary_sha256"],
        "decision": "reject",
        "decision_status": "rejected",
        "actor_type": "agent",
        "actor_id": "reviewer-agent",
        "created_at": "2026-09-29T00:00:00Z",
    }
    receipt["receipt_sha256"] = _decision_hash(receipt)
    (package_dir / "review_decision_receipt.json").write_text(
        json.dumps(receipt, ensure_ascii=False), encoding="utf-8"
    )

    shadow = shadow_core_evidence_batch_migration(project)

    pending = shadow["pending_checkpoint"]
    assert pending["decision_receipt"]["decision_status"] == "rejected"
    assert pending["association"]["eligible"] is False
    assert "checkpoint_has_non_user_confirmation_receipt" in pending["association"]["blockers"]
    assert pending["reuse_eligible"] is False
    assert shadow["recovery"]["action"] == "register_new_explicit_core_evidence_batch"


def test_legacy_core_checkpoint_without_batch_scope_never_routes_to_resume(tmp_path: Path) -> None:
    from draftpaper_cli.core_evidence_batch import prepare_core_evidence_batch, shadow_core_evidence_batch_migration
    from draftpaper_cli.doctor import verify_next_action
    from draftpaper_cli.passport import load_project_passport, read_jsonl
    from draftpaper_cli.review_policy import ReviewPolicyError, record_user_checkpoint_confirmation, review_checkpoint

    project = _ready_project(tmp_path)
    checkpoint = checkpoint_project(project, stage="core_evidence")
    checkpoint_hash = checkpoint["checkpoint_hash"]
    ledger_path, legacy = _make_unscoped_v2_pending_checkpoint(project, checkpoint)
    cycle = {key: value for key, value in legacy.items() if key != "checkpoint_package_dir"}
    cycle_path = project / json.loads((project / ".draftpaper" / "active_revision_cycle.json").read_text(encoding="utf-8"))["path"]
    before_ledger = ledger_path.read_bytes()
    before_cycle = cycle_path.read_bytes()
    shadow = shadow_core_evidence_batch_migration(project)
    assert shadow["task_scope"]["status"] == "known"
    assert shadow["task_scope"]["task_count"] == 1
    assert shadow["pending_checkpoint"]["status"] == "unscoped_pending"
    assert shadow["pending_checkpoint"]["scope_binding_status"] == "unscoped"
    assert shadow["pending_checkpoint"]["package_validation"]["status"] == "valid"
    assert shadow["pending_checkpoint"]["reuse_eligible"] is False
    assert shadow["pending_checkpoint"]["association"]["eligible"] is True
    assert shadow["recovery"]["action"] == "associate_complete_legacy_request"
    assert shadow["latest_valid_user_confirmation"]["status"] == "none"
    assert ledger_path.read_bytes() == before_ledger
    assert cycle_path.read_bytes() == before_cycle
    package_dir = Path(str(legacy["checkpoint_package_dir"]))
    package_files = {
        name: (package_dir / name).read_bytes()
        for name in ("stage_summary.json", "stage_summary.zh-CN.html", "stage_summary.en.html", "confirmation_request.json")
    }

    status = status_project(project)
    assert status["pipeline_state"] == "legacy_core_checkpoint_migration_required"
    assert status["core_evidence_batch_migration_shadow"]["runtime_identity"]["status"] == "unknown"
    assert status["next_action"]["command"] == "shadow-core-evidence-batch-migration"
    assert "resume" not in status["next_action"].get("cli", "")
    verified = verify_next_action(project)
    assert verified["status"] == "passed"
    assert verified["command"] == "shadow-core-evidence-batch-migration"
    with pytest.raises(OrchestratorError, match="(?i)legacy core-evidence checkpoint.*batch scope"):
        resume_project(project, checkpoint_hash=checkpoint_hash)
    with pytest.raises(ReviewPolicyError, match="(?i)legacy core-evidence checkpoint.*batch scope"):
        record_user_checkpoint_confirmation(project, checkpoint_hash=checkpoint_hash)
    with pytest.raises(ReviewPolicyError, match="(?i)legacy core-evidence checkpoint.*batch scope"):
        review_checkpoint(project, checkpoint_hash=checkpoint_hash)
    assert not any(row.get("kind") == "resume" for row in read_jsonl(ledger_path))

    new_task = {
        **cycle["pending_tasks"][0],
        "task_id": "explicit_legacy_scope_recovery",
        "title_zh": "补齐旧确认范围",
        "title_en": "Recover the explicit legacy confirmation scope",
        "origin_ref": "user_scope_manifest",
        "status": "pending",
        "depends_on": [],
        "completion_receipts": [],
    }
    changes_path = project / "legacy_scope_recovery.json"
    changes_path.write_text(json.dumps({"tasks": [new_task]}, ensure_ascii=False), encoding="utf-8")
    registered = prepare_core_evidence_batch(project, changes_path=changes_path)
    assert registered["status"] == "prepared"
    assert load_project_passport(project)["awaiting_checkpoint"] is None
    superseded = [row for row in read_jsonl(ledger_path) if row.get("kind") == "checkpoint_superseded" and row.get("supersedes_hash") == checkpoint_hash]
    assert len(superseded) == 1
    assert superseded[0]["old_request_reusable"] is False
    assert superseded[0]["source_cycle_sha256"] == cycle["revision_cycle_sha256"]
    assert {
        name: (package_dir / name).read_bytes()
        for name in package_files
    } == package_files
    with pytest.raises(OrchestratorError, match="(?i)legacy core-evidence checkpoint.*batch scope"):
        resume_project(project, checkpoint_hash=checkpoint_hash)
    assert prepare_core_evidence_batch(project, changes_path=changes_path)["status"] == "existing"
    assert len([row for row in read_jsonl(ledger_path) if row.get("kind") == "checkpoint_superseded" and row.get("supersedes_hash") == checkpoint_hash]) == 1


def test_complete_legacy_v2_package_can_be_linked_without_republishing_confirmation(tmp_path: Path) -> None:
    from draftpaper_cli.core_evidence_batch import prepare_core_evidence_batch, shadow_core_evidence_batch_migration
    from draftpaper_cli.passport import load_project_passport, read_jsonl, refresh_project_passport
    from draftpaper_cli.review_policy import ReviewPolicyError, record_user_checkpoint_confirmation

    project = _ready_project(tmp_path)
    checkpoint = checkpoint_project(project, stage="core_evidence")
    checkpoint_hash = checkpoint["checkpoint_hash"]
    ledger_path, legacy = _make_unscoped_v2_pending_checkpoint(project, checkpoint)
    shadow = shadow_core_evidence_batch_migration(project)
    assert shadow["pending_checkpoint"]["association"]["eligible"] is True
    assert shadow["recovery"]["action"] == "associate_complete_legacy_request"
    package_dir = Path(str(legacy["checkpoint_package_dir"]))
    before_package = (package_dir / "stage_summary.json").read_bytes()

    linked = prepare_core_evidence_batch(project)
    assert linked["status"] == "associated_existing_request"
    assert linked["batch"]["phase"] == "awaiting_decision"
    assert linked["batch"]["request_id"] == checkpoint_hash
    awaiting = load_project_passport(project)["awaiting_checkpoint"]
    assert awaiting["batch_id"] == linked["batch"]["batch_id"]
    associations = [row for row in read_jsonl(ledger_path) if row.get("kind") == "checkpoint_batch_associated"]
    assert len(associations) == 1
    assert associations[0]["checkpoint_hash"] == checkpoint_hash
    assert not any(row.get("kind") == "checkpoint_superseded" and row.get("supersedes_hash") == checkpoint_hash for row in read_jsonl(ledger_path))
    linked_shadow = shadow_core_evidence_batch_migration(project)
    assert linked_shadow["pending_checkpoint"]["status"] == "scoped_pending"
    assert linked_shadow["pending_checkpoint"]["reuse_eligible"] is True
    assert linked_shadow["recovery"]["action"] == "reuse_exact_existing_request"
    assert prepare_core_evidence_batch(project)["status"] == "existing"
    assert len([row for row in read_jsonl(ledger_path) if row.get("kind") == "checkpoint_batch_associated"]) == 1
    original_ledger = ledger_path.read_bytes()
    tampered_rows = read_jsonl(ledger_path)
    association_event = next(row for row in tampered_rows if row.get("kind") == "checkpoint_batch_associated")
    association_event["batch_id"] = "forged-batch"
    ledger_path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in tampered_rows), encoding="utf-8")
    refresh_project_passport(project, event="tampered_association_fixture")
    assert load_project_passport(project)["awaiting_checkpoint"].get("batch_id") is None
    with pytest.raises(ReviewPolicyError, match="(?i)legacy core-evidence checkpoint.*batch scope"):
        record_user_checkpoint_confirmation(project, checkpoint_hash=checkpoint_hash)
    ledger_path.write_bytes(original_ledger)
    refresh_project_passport(project, event="restored_association_fixture")
    frozen_path = project / linked["batch"]["frozen_candidate_ref"]
    frozen_bytes = frozen_path.read_bytes()
    frozen = json.loads(frozen_bytes.decode("utf-8-sig"))
    frozen["input_manifest_sha256"] = "0" * 64
    frozen_path.write_text(json.dumps(frozen, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ReviewPolicyError, match="batch candidate"):
        record_user_checkpoint_confirmation(project, checkpoint_hash=checkpoint_hash)
    frozen_path.write_bytes(frozen_bytes)
    confirmation = record_user_checkpoint_confirmation(project, checkpoint_hash=checkpoint_hash)
    assert confirmation["status"] == "user_confirmed"
    resumed = resume_project(project, checkpoint_hash=checkpoint_hash)
    assert resumed["status"] == "resumed"
    assert (package_dir / "stage_summary.json").read_bytes() == before_package


def test_newly_discovered_task_supersedes_pending_request(tmp_path: Path) -> None:
    from draftpaper_cli.core_evidence_batch import prepare_core_evidence_batch
    from draftpaper_cli.revision_cycle import load_active_revision_cycle
    from draftpaper_cli.passport import load_project_passport

    project = _ready_project(tmp_path)
    first = checkpoint_project(project, stage="core_evidence")
    old_cycle = load_active_revision_cycle(project)
    added = {
        "task_id": "verify_figure",
        "title_zh": "核验新增图表来源",
        "title_en": "Verify the added figure provenance",
        "checkpoint_scope": "core_evidence",
        "origin_ref": "validation_discovery",
        "effect_class": "binding",
        "required_before_publication": True,
        "depends_on": ["validate_result"],
        "evidence_refs": ["results/figure_code_trace.json"],
        "expected_artifacts": ["results/figure_code_trace.json"],
        "completion_checks": ["matching_artifact_hash"],
        "completion_receipts": [],
        "status": "pending",
    }
    changes = project / "more_changes.json"
    changes.write_text(json.dumps({"tasks": [added]}), encoding="utf-8")

    result = prepare_core_evidence_batch(project, changes_path=changes)
    assert result["batch"]["batch_id"] == old_cycle["evidence_batch"]["batch_id"]
    assert result["batch"]["phase"] == "collecting"
    assert result["batch"]["frozen_candidate_ref"] is None
    assert load_project_passport(project)["awaiting_checkpoint"] is None
    assert (project / "review" / "checkpoints").exists()
    assert status_project(project)["next_action"]["command"] != "resume"
    with pytest.raises(OrchestratorError, match="batch|candidate|changed"):
        resume_project(project, checkpoint_hash=first["checkpoint_hash"])


def test_confirmation_page_describes_the_whole_batch_in_both_languages(tmp_path: Path) -> None:
    project = _ready_project(tmp_path, two_tasks=True)
    checkpoint = checkpoint_project(project, stage="core_evidence")
    zh_path = project / checkpoint["stage_summary_zh_html"]["project_relative_path"]
    summary_dir = zh_path.parent
    zh = zh_path.read_text(encoding="utf-8")
    en = (summary_dir / "stage_summary.en.html").read_text(encoding="utf-8")
    summary = json.loads((summary_dir / "stage_summary.json").read_text(encoding="utf-8"))
    request = json.loads((summary_dir / "confirmation_request.json").read_text(encoding="utf-8"))
    agent = json.loads((summary_dir / "agent_payload.json").read_text(encoding="utf-8"))

    assert "核验结果" in zh and "核对样本边界" in zh
    assert "Validate result" in en and "Check sample boundary" in en
    assert '<h2>本阶段工作概述</h2>' in zh
    assert summary["stage_narrative_zh"] in zh
    assert '<h2>Round overview</h2>' in en
    assert "Validate result" in summary["core_evidence_batch"]["summary_en"]
    assert "Check sample boundary" in summary["core_evidence_batch"]["summary_en"]
    assert '<h2>确认后会继续什么</h2>' in zh
    assert "排版" in zh and "PDF" in zh
    assert "确认的数据、方法、验证身份、指标、图表语义和论断边界" in zh
    assert '<h2>What happens after confirmation</h2>' in en
    assert "typesetting" in en and "PDF" in en
    assert "dataset, method, validation identity, metrics, figure semantics, or claim boundaries" in en
    assert "result_validity_report.json" in zh
    assert 'href="stage_audit.json"' in zh
    assert 'href="confirmation_request.json"' in zh
    assert 'href="checkpoint_readability_report.json"' in zh
    assert 'href="stage_audit.json"' in en
    assert 'href="confirmation_request.json"' in en
    assert 'href="checkpoint_readability_report.en.json"' in en
    assert summary["core_evidence_batch"]["completed_task_count"] == 2
    assert request["batch_id"] == agent["batch_id"] == summary["core_evidence_batch"]["batch_id"]


def test_stale_rendered_packet_is_not_published_as_pending_checkpoint(tmp_path: Path) -> None:
    project = _ready_project(tmp_path, include_extra_input=True)
    with pytest.raises(OrchestratorError, match="blocked|stale|confirmable"):
        checkpoint_project(project, stage="core_evidence")
    ledger = project / "checkpoint_ledger.jsonl"
    assert not any(
        json.loads(line).get("kind") == "checkpoint" and json.loads(line).get("stage") == "core_evidence"
        for line in ledger.read_text(encoding="utf-8").splitlines() if line.strip()
    )
    assert status_project(project)["next_action"]["command"] != "resume"


def test_direct_review_api_cannot_confirm_superseded_batch(tmp_path: Path) -> None:
    from draftpaper_cli.core_evidence_batch import prepare_core_evidence_batch
    from draftpaper_cli.revision_cycle import load_active_revision_cycle
    from draftpaper_cli.review_policy import ReviewPolicyError, record_user_checkpoint_confirmation, review_checkpoint

    project = _ready_project(tmp_path)
    first = checkpoint_project(project, stage="core_evidence")
    task = dict(load_active_revision_cycle(project)["pending_tasks"][0])
    task["status"] = "pending"
    task["completion_receipts"] = []
    changes = project / "reopened_task.json"
    changes.write_text(json.dumps({"tasks": [task]}), encoding="utf-8")
    prepare_core_evidence_batch(project, changes_path=changes)

    with pytest.raises(ReviewPolicyError, match="batch|candidate|current"):
        record_user_checkpoint_confirmation(project, checkpoint_hash=first["checkpoint_hash"])
    with pytest.raises(ReviewPolicyError, match="batch|candidate|current"):
        review_checkpoint(project, checkpoint_hash=first["checkpoint_hash"])
    assert not (Path(first["checkpoint_summary"]["human_decision_brief"]).parent / "review_decision_receipt.json").exists()


def test_concurrent_checkpoint_calls_share_one_request(tmp_path: Path) -> None:
    project = _ready_project(tmp_path)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(checkpoint_project, project, stage="core_evidence") for _ in range(2)]
        replies = [future.result(timeout=90) for future in futures]
    assert {reply["checkpoint_hash"] for reply in replies} == {replies[0]["checkpoint_hash"]}
    events = [
        json.loads(line) for line in (project / "checkpoint_ledger.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len([row for row in events if row.get("kind") == "checkpoint" and row.get("stage") == "core_evidence"]) == 1
