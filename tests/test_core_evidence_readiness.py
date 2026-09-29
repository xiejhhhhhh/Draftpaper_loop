"""Readiness is a separate question from scientific report validity."""

from __future__ import annotations

import hashlib
import json
from importlib.resources import files
from pathlib import Path

from jsonschema import Draft202012Validator

from draftpaper_cli.core_evidence_batch import prepare_core_evidence_batch
from draftpaper_cli.project_scaffold import create_project
from tests.test_orchestrator_passport import write_confirmable_core_evidence


def _task(task_id: str, *, status: str = "pending", receipt_hash: str | None = None) -> dict:
    return {
        "task_id": task_id,
        "title_zh": "完成图表绑定",
        "title_en": "Finish figure binding",
        "checkpoint_scope": "core_evidence",
        "origin_ref": "synthetic_request",
        "effect_class": "binding",
        "required_before_publication": True,
        "depends_on": [],
        "evidence_refs": ["results/figure_code_trace.json"],
        "expected_artifacts": ["results/figure_code_trace.json"],
        "completion_checks": ["matching_artifact_hash"],
        "completion_receipts": (
            [{"path": "results/figure_code_trace.json", "sha256": receipt_hash}]
            if receipt_hash else []
        ),
        "status": status,
    }


def _prepared_project(tmp_path: Path, task: dict) -> Path:
    project = create_project(root=tmp_path, idea="Readiness contract", field="generic").path
    changes = project / "batch_changes.json"
    changes.write_text(json.dumps({"tasks": [task]}), encoding="utf-8")
    prepare_core_evidence_batch(project, changes_path=changes)
    return project


def test_readiness_keeps_pending_task_even_without_a_core_report(tmp_path: Path) -> None:
    from draftpaper_cli.core_evidence_readiness import assess_core_evidence_readiness

    project = _prepared_project(tmp_path, _task("trace"))
    result = assess_core_evidence_readiness(project)
    assert result["publishable"] is False
    assert result["status"] == "collecting"
    assert result["blocking_tasks"] == ["trace"]
    assert "batch_tasks_pending" in result["reason_codes"]
    assert not (project / "review" / "revision_reconciliation" / "core_evidence_readiness.json").exists()


def test_completed_task_with_stale_receipt_is_not_ready(tmp_path: Path) -> None:
    from draftpaper_cli.core_evidence_readiness import assess_core_evidence_readiness

    project = _prepared_project(tmp_path, _task("trace", status="completed", receipt_hash="0" * 64))
    artifact = project / "results" / "figure_code_trace.json"
    artifact.write_text('{"trace": "current"}', encoding="utf-8")
    result = assess_core_evidence_readiness(project)
    assert result["publishable"] is False
    assert result["blocking_tasks"] == ["trace"]
    assert "stale_completion_receipt" in result["reason_codes"]


def test_completed_task_with_current_receipt_passes_task_check(tmp_path: Path) -> None:
    from draftpaper_cli.core_evidence_readiness import assess_core_evidence_readiness

    project = create_project(root=tmp_path, idea="Current receipt", field="generic").path
    artifact = project / "results" / "figure_code_trace.json"
    artifact.write_text('{"trace": "current"}', encoding="utf-8")
    task = _task("trace", status="completed", receipt_hash=hashlib.sha256(artifact.read_bytes()).hexdigest())
    changes = project / "batch_changes.json"
    changes.write_text(json.dumps({"tasks": [task]}), encoding="utf-8")
    prepare_core_evidence_batch(project, changes_path=changes)

    result = assess_core_evidence_readiness(project)
    assert result["blocking_tasks"] == []
    assert "stale_completion_receipt" not in result["reason_codes"]
    assert result["publishable"] is False


def test_structured_semantic_receipt_ignores_json_serialization_only_change(tmp_path: Path) -> None:
    from draftpaper_cli.artifact_identity import compute_artifact_identity
    from draftpaper_cli.core_evidence_readiness import assess_core_evidence_readiness

    project = create_project(root=tmp_path, idea="Structured semantic receipt", field="generic").path
    artifact = project / "results" / "figure_code_trace.json"
    artifact.write_text('{"source": "run-1", "rows": [1, 2]}\n', encoding="utf-8")
    semantic_hash = compute_artifact_identity(artifact, "results/figure_code_trace.json")["semantic_sha256"]
    task = _task("trace", status="completed")
    task["completion_receipts"] = [{
        "path": "results/figure_code_trace.json",
        "semantic_sha256": semantic_hash,
    }]
    changes = project / "batch_changes.json"
    changes.write_text(json.dumps({"tasks": [task]}), encoding="utf-8")
    prepare_core_evidence_batch(project, changes_path=changes)

    before = assess_core_evidence_readiness(project)
    artifact.write_text('{\n  "rows": [1, 2],\n  "source": "run-1"\n}\n', encoding="utf-8")
    after = assess_core_evidence_readiness(project)

    assert "stale_completion_receipt" not in after["reason_codes"]
    assert after["input_manifest_sha256"] == before["input_manifest_sha256"]


def test_completed_task_checks_evidence_refs_and_outputs(tmp_path: Path) -> None:
    from draftpaper_cli.core_evidence_readiness import assess_core_evidence_readiness

    project = create_project(root=tmp_path, idea="Both binding kinds", field="generic").path
    output = project / "results" / "figure_code_trace.json"
    output.write_text('{"trace": "current"}', encoding="utf-8")
    source = project / "results" / "result_validity_report.json"
    source.write_text('{"decision": "pass"}', encoding="utf-8")
    task = _task("trace", status="completed", receipt_hash=hashlib.sha256(output.read_bytes()).hexdigest())
    task["evidence_refs"] = ["results/result_validity_report.json"]
    changes = project / "batch_changes.json"
    changes.write_text(json.dumps({"tasks": [task]}), encoding="utf-8")
    prepare_core_evidence_batch(project, changes_path=changes)

    result = assess_core_evidence_readiness(project)
    assert result["blocking_tasks"] == ["trace"]
    assert "stale_completion_receipt" in result["reason_codes"]


def test_unknown_completion_check_is_not_silently_satisfied(tmp_path: Path) -> None:
    from draftpaper_cli.core_evidence_readiness import assess_core_evidence_readiness

    project = create_project(root=tmp_path, idea="Unknown check", field="generic").path
    output = project / "results" / "figure_code_trace.json"
    output.write_text('{"trace": "current"}', encoding="utf-8")
    task = _task("trace", status="completed", receipt_hash=hashlib.sha256(output.read_bytes()).hexdigest())
    task["completion_checks"] = ["external_validator_not_implemented"]
    changes = project / "batch_changes.json"
    changes.write_text(json.dumps({"tasks": [task]}), encoding="utf-8")
    prepare_core_evidence_batch(project, changes_path=changes)

    report = assess_core_evidence_readiness(project)
    assert report["blocking_tasks"] == ["trace"]
    assert "unsupported_completion_check" in report["reason_codes"]


def test_large_direct_artifact_requires_small_manifest_binding(tmp_path: Path) -> None:
    from draftpaper_cli.core_evidence_readiness import assess_core_evidence_readiness

    project = create_project(root=tmp_path, idea="Bounded evidence hash", field="generic").path
    output = project / "results" / "figure_code_trace.json"
    with output.open("wb") as stream:
        stream.truncate(65 * 1024 * 1024)
    task = _task("trace", status="completed", receipt_hash="0" * 64)
    changes = project / "batch_changes.json"
    changes.write_text(json.dumps({"tasks": [task]}), encoding="utf-8")
    prepare_core_evidence_batch(project, changes_path=changes)

    report = assess_core_evidence_readiness(project)
    assert report["blocking_tasks"] == ["trace"]
    assert "oversized_direct_evidence_ref" in report["reason_codes"]


def test_readiness_report_matches_packaged_schema(tmp_path: Path) -> None:
    from draftpaper_cli.core_evidence_readiness import assess_core_evidence_readiness

    project = _prepared_project(tmp_path, _task("trace"))
    report = assess_core_evidence_readiness(project)
    schema_path = files("draftpaper_cli").joinpath("resources", "schemas", "core_evidence_readiness_v1.json")
    validator = Draft202012Validator(json.loads(schema_path.read_text(encoding="utf-8")))
    assert list(validator.iter_errors(report)) == []


def test_finalized_candidate_is_stable_until_an_input_changes(tmp_path: Path) -> None:
    from draftpaper_cli.core_evidence_readiness import assess_core_evidence_readiness, finalize_core_evidence_batch

    project = create_project(root=tmp_path, idea="Frozen batch candidate", field="generic").path
    write_confirmable_core_evidence(project)
    validity = project / "results" / "result_validity_report.json"
    task = _task("validity", status="completed")
    task["expected_artifacts"] = ["results/result_validity_report.json"]
    task["evidence_refs"] = ["results/result_validity_report.json"]
    task["completion_receipts"] = [
        {"path": "results/result_validity_report.json", "sha256": hashlib.sha256(validity.read_bytes()).hexdigest()}
    ]
    changes = project / "batch_changes.json"
    changes.write_text(json.dumps({"tasks": [task]}), encoding="utf-8")
    prepare_core_evidence_batch(project, changes_path=changes)

    before = assess_core_evidence_readiness(project)
    assert before["status"] == "validating", before
    first = finalize_core_evidence_batch(project, expected_scope_sha256=before["scope_sha256"])
    assert first["status"] == "ready", first
    again = finalize_core_evidence_batch(project)
    assert again["readiness"]["input_manifest_sha256"] == first["readiness"]["input_manifest_sha256"]
    assert again["batch"]["batch_id"] == first["batch"]["batch_id"]

    validity.write_text('{"decision": "pass", "resolved_run_id": "a-different-run"}', encoding="utf-8")
    changed = assess_core_evidence_readiness(project)
    assert changed["publishable"] is False
    assert "frozen_candidate_changed" in changed["reason_codes"]
