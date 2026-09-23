"""Regression coverage for preserving an author decision through core resume.

Every project is a temporary software fixture, never scientific evidence.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from draftpaper_cli.artifact_identity import canonical_json
from draftpaper_cli.code_ownership import trace_figures_to_code
from draftpaper_cli.evidence_snapshot import (
    _artifact_hashes,
    reopen_evidence_snapshot,
    validate_promoted_snapshot_for_writing,
)
from draftpaper_cli.orchestrator import checkpoint_project, resume_project, status_project
from draftpaper_cli.passport import refresh_project_passport
from draftpaper_cli.project_scaffold import create_project
from draftpaper_cli.project_state import update_stage_status
from draftpaper_cli.result_evidence import resolve_result_evidence
from draftpaper_cli.review_policy import acknowledge_notification_checkpoint
from tests.test_orchestrator_passport import write_confirmable_core_evidence


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def ledger(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def build_confirmed_continuity(tmp_path):
    project = create_project(root=tmp_path, idea="core continuity regression", field="generic").path
    write_confirmable_core_evidence(project)
    write(project / "research_plan/research_plan_confirmation.json", {"status": "approved", "plan_hash": "fixture-plan"})
    write(project / "research_plan/confirmed_research_blueprint_snapshot.json", {"confirmed_plan_hash": "fixture-plan"})
    write(project / "results/figure_plan.json", {"confirmed_plan_hash": "fixture-plan"})
    metric = {
        "metric_definition_id": "score", "task_id": "task-core-test",
        "cohort_id": "cohort-core-test", "sample_unit": "source", "model_id": "fixture-model",
        "validation_design_id": "source-held-out", "split_id": "held-out",
        "aggregation_id": "none", "uncertainty_definition_id": "none",
    }
    write(project / "methods/primary_metric_contract.json", {"schema_version": "dpl.primary_metric_contract.v1", **metric})
    (project / "results/tables/metric_evidence.csv").write_text(
        "run_id,metric,value,model_id,task_id,cohort_id,sample_unit,validation_design_id,split_id,aggregation_id,uncertainty_definition_id\n"
        "run-core-test,score,0.81,fixture-model,task-core-test,cohort-core-test,source,source-held-out,held-out,none,none\n",
        encoding="utf-8",
    )
    run_path = project / "methods/run_manifest.yaml"
    run = read(run_path)
    run["output_files"] = ["results/tables/metric_evidence.csv"]
    run["count_evidence"] = [{
        "count_record_id": "count-core-test", "count_definition_id": "source_count",
        "entity_type": "source", "count_mode": "unique_entities", "cohort_id": "cohort-core-test",
        "filter_contract_id": "filter-core-test", "sample_unit": "source", "value": 12,
    }]
    write(run_path, run)
    resolve_result_evidence(project)
    trace_figures_to_code(project)
    resolve_result_evidence(project)
    for stage in ("code", "methods", "result_validity", "result_support", "core_evidence"):
        update_stage_status(project, stage, "completed")
    refresh_project_passport(project, event="test_core_continuity_fixture")
    core_path = project / "core_evidence/core_evidence_report.json"
    assessed_core = read(core_path)
    first = checkpoint_project(project, stage="core_evidence")
    resumed = resume_project(project, checkpoint_hash=first["checkpoint_hash"])
    user_receipt = resumed["decision_receipt"]
    reopen_evidence_snapshot(project, reason="Fixture-only derived audit refresh")
    # Reassessment regenerates the same scientific report without stale
    # mutable confirmation annotations, just as assess-core-evidence does.
    write(core_path, assessed_core)
    for stage in ("code", "methods", "result_validity", "result_support", "core_evidence"):
        update_stage_status(project, stage, "completed")
    second = checkpoint_project(project, stage="core_evidence")
    assert second["confirmation_continuity"]["eligible"] is True, second.get("unresolved_issues")
    record = next(row for row in ledger(project / "checkpoint_ledger.jsonl") if row.get("hash") == second["checkpoint_hash"])
    return project, first, second, record, user_receipt


@pytest.fixture(scope="module")
def continuity_template(tmp_path_factory):
    return build_confirmed_continuity(tmp_path_factory.mktemp("continuity"))


@pytest.fixture
def confirmed_continuity(continuity_template, tmp_path):
    template, first, second, record, user_receipt = continuity_template
    project = tmp_path / "project"
    # Clone only the temporary software fixture. Each destructive/negative
    # test receives private files; the original receipts remain hash-bound.
    shutil.copytree(template, project)
    return project, first, second, record, user_receipt


def system_resume(case):
    import draftpaper_cli.orchestrator as orchestrator
    project, _, second, _, _ = case
    acknowledged = acknowledge_notification_checkpoint(project, checkpoint_hash=second["checkpoint_hash"])
    return orchestrator.resume_after_system_acknowledgement(
        project, checkpoint_hash=second["checkpoint_hash"], receipt_id=acknowledged["receipt"]["receipt_id"]
    )


def test_cli_continuity_promotes_snapshot_without_new_user_confirmation(confirmed_continuity):
    project, first, second, record, user_receipt = confirmed_continuity
    before_science = _artifact_hashes(project)
    before_users = [r for r in ledger(project / ".draftpaper/review_decision_ledger.jsonl") if r.get("decision_status") == "user_confirmed"]
    process = subprocess.run(
        [sys.executable, "-B", "-m", "draftpaper_cli.cli", "continue", "--project", str(project)],
        capture_output=True, text=True, encoding="utf-8", timeout=120,
    )
    assert process.returncode == 0, process.stdout + process.stderr
    result = json.loads(process.stdout)
    assert result["automatic_review"]["status"] == "resumed_after_system_acknowledgement"
    snapshot = validate_promoted_snapshot_for_writing(project)
    assert snapshot["snapshot_id"] == record["evidence_snapshot_id"]
    assert _artifact_hashes(project) == before_science
    report = read(project / "core_evidence/core_evidence_report.json")
    assert report["human_confirmation_checkpoint_hash"] == first["checkpoint_hash"]
    assert report["promoted_evidence_snapshot_id"] == snapshot["snapshot_id"]
    after_users = [r for r in ledger(project / ".draftpaper/review_decision_ledger.jsonl") if r.get("decision_status") == "user_confirmed"]
    assert after_users == before_users
    event = ledger(project / "checkpoint_ledger.jsonl")[-1]
    assert event["actor_type"] == "system"
    assert event["decision_status"] == "system_acknowledged"
    assert event["preserved_user_decision_receipt_id"] == user_receipt["receipt_id"]
    assert status_project(project)["pipeline_state"] != "confirmation_required"
    assert status_project(project)["awaiting_checkpoint"] is None


@pytest.mark.parametrize("mode", ["missing", "invalid_digest", "rebound_previous_receipt"])
def test_continuity_receipt_failures_prevent_promotion(confirmed_continuity, mode):
    import draftpaper_cli.orchestrator as orchestrator
    project, _, second, record, _ = confirmed_continuity
    path = project / second["confirmation_continuity"]["receipt_path"]
    if mode == "missing":
        path.unlink()
    else:
        payload = read(path)
        if mode == "invalid_digest":
            payload["receipt_sha256"] = "bad"
        else:
            payload["previous_decision_receipt_id"] = "different-user-receipt"
            body = {k: v for k, v in payload.items() if k not in {"receipt_sha256", "created_at"}}
            payload["receipt_sha256"] = hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()
        write(path, payload)
    before = (project / "checkpoint_ledger.jsonl").read_bytes()
    with pytest.raises(orchestrator.OrchestratorError):
        orchestrator._validated_core_confirmation_continuity(project, record)
    assert not (project / "results/promoted_evidence_snapshot.json").exists()
    assert (project / "checkpoint_ledger.jsonl").read_bytes() == before


def test_missing_prior_user_receipt_prevents_promotion(confirmed_continuity):
    import draftpaper_cli.orchestrator as orchestrator
    project, _, _, record, _ = confirmed_continuity
    (project / ".draftpaper/review_decision_ledger.jsonl").write_text("", encoding="utf-8")
    with pytest.raises(orchestrator.OrchestratorError, match="valid user receipt"):
        orchestrator._validated_core_confirmation_continuity(project, record)
    assert not (project / "results/promoted_evidence_snapshot.json").exists()


def test_changed_scientific_artifact_prevents_promotion(confirmed_continuity):
    import draftpaper_cli.orchestrator as orchestrator
    project, _, _, record, _ = confirmed_continuity
    (project / "results/figures/main.png").write_bytes(b"changed scientific fixture")
    with pytest.raises(orchestrator.OrchestratorError, match="changed"):
        orchestrator._validated_core_confirmation_continuity(project, record)
    assert not (project / "results/promoted_evidence_snapshot.json").exists()


def test_repeated_consumption_is_rejected(confirmed_continuity):
    import draftpaper_cli.orchestrator as orchestrator
    result = system_resume(confirmed_continuity)
    project, _, second, _, _ = confirmed_continuity
    with pytest.raises(orchestrator.OrchestratorError, match="already been consumed"):
        orchestrator.resume_after_system_acknowledgement(
            project, checkpoint_hash=second["checkpoint_hash"], receipt_id=result["decision_receipt_id"]
        )


@pytest.mark.parametrize("failure", ["snapshot_mismatch", "core_write", "ledger_write"])
def test_failed_promotion_rolls_back_core_snapshot_and_resume(confirmed_continuity, monkeypatch, failure):
    import draftpaper_cli.orchestrator as orchestrator
    import draftpaper_cli.state_kernel as state_kernel
    project, _, second, _, _ = confirmed_continuity
    acknowledged = acknowledge_notification_checkpoint(project, checkpoint_hash=second["checkpoint_hash"])
    originals = {p: (project / p).read_bytes() for p in (
        "core_evidence/core_evidence_report.json", "checkpoint_ledger.jsonl", "project_passport.yaml", "artifact_ledger.jsonl"
    )}
    if failure == "snapshot_mismatch":
        original = orchestrator.create_evidence_snapshot
        def bad_snapshot(path):
            result = original(path)
            return {**result, "snapshot_id": "wrong-snapshot"}
        monkeypatch.setattr(orchestrator, "create_evidence_snapshot", bad_snapshot)
    elif failure == "core_write":
        original_write = state_kernel.atomic_write_json
        def bad_write(path, payload):
            if Path(path).name == "core_evidence_report.json":
                raise OSError("injected core write error")
            return original_write(path, payload)
        monkeypatch.setattr(state_kernel, "atomic_write_json", bad_write)
    else:
        original_append = orchestrator.append_checkpoint_event
        def bad_append(path, event):
            original_append(path, event)
            raise OSError("injected ledger write error")
        monkeypatch.setattr(orchestrator, "append_checkpoint_event", bad_append)
    with pytest.raises((orchestrator.OrchestratorError, OSError)):
        orchestrator.resume_after_system_acknowledgement(
            project, checkpoint_hash=second["checkpoint_hash"], receipt_id=acknowledged["receipt"]["receipt_id"]
        )
    assert not (project / "results/promoted_evidence_snapshot.json").exists()
    assert all((project / p).read_bytes() == before for p, before in originals.items())
