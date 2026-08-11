from __future__ import annotations

import json
from pathlib import Path

from draftpaper_cli.checkpoint_summary import (
    show_checkpoint_summary,
    validate_checkpoint_summary,
    write_stage_summary,
)
from draftpaper_cli.passport import refresh_project_passport
from draftpaper_cli.project_scaffold import create_project


def test_v3_summary_has_same_source_confirmation_contract_and_sample_flow(tmp_path: Path) -> None:
    project = create_project(root=tmp_path / "project", idea="v3 contract", field="generic scientific workflow").path
    (project / "data" / "sample_flow.json").parent.mkdir(parents=True, exist_ok=True)
    (project / "data" / "sample_flow.json").write_text(
        json.dumps(
            {
                "run_id": "run-v3",
                "sample_unit": "entity",
                "count_evidence": [
                    {
                        "count_definition_id": "eligible_entity_count",
                        "entity_type": "entity",
                        "count_mode": "unique",
                        "cohort_id": "cohort-v3",
                        "filter_contract_id": "filter-v3",
                        "value": 12,
                        "identity_complete": True,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    before = refresh_project_passport(project)["artifacts"]
    report = write_stage_summary(
        project,
        stage="data",
        command="test-v3-summary",
        payload={
            "status": "checkpoint_created",
            "test_mode": True,
            "test_auto_confirmation": True,
            "run_id": "run-v3",
            "sample_unit": "entity",
        },
        before_artifacts=before,
        checkpoint_id="v3-data",
        checkpoint_hash="v3-hash",
        publish_index=False,
    )

    summary_path = project / report["stage_summary_json"]
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    request = json.loads((summary_path.parent / "confirmation_request.json").read_text(encoding="utf-8"))
    agent = json.loads((summary_path.parent / "agent_payload.json").read_text(encoding="utf-8"))

    assert summary["schema_version"] == "dpl.checkpoint_summary.v3"
    assert isinstance(summary["sample_flow"], list)
    assert summary["confirmation_contract"] == {
        "requires_user_decision": True,
        "confirmation_command_allowed": True,
        "source_of_truth": "canonical_evidence",
        "test_auto_confirmation": True,
    }
    assert summary["test_mode"] is True
    assert summary["test_auto_confirmation"] is True
    assert request["summary_schema"] == summary["schema_version"]
    assert request["stage_summary_sha256"] == summary["stage_summary_sha256"]
    assert agent["stage_summary_sha256"] == summary["stage_summary_sha256"]
    assert agent["review_state"] == summary["review_state"]


def test_v3_contract_rejects_missing_required_field(tmp_path: Path) -> None:
    project = create_project(root=tmp_path / "project", idea="v3 invalid", field="generic scientific workflow").path
    report = write_stage_summary(
        project,
        stage="research_plan",
        command="test-v3-invalid",
        payload={"status": "checkpoint_created"},
        before_artifacts=[],
        checkpoint_id="v3-invalid",
        checkpoint_hash="v3-invalid-hash",
        publish_index=True,
    )
    summary_path = project / report["stage_summary_json"]
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary.pop("sample_flow")
    summary_path.write_text(json.dumps(summary, ensure_ascii=False), encoding="utf-8")

    shown = show_checkpoint_summary(project, report["stage_summary_sha256"])
    assert shown["status"] == "invalid_summary"
    assert any("sample_flow" in reason for reason in shown["reasons"])


def test_v1_v2_summary_is_read_only_legacy(tmp_path: Path) -> None:
    project = create_project(root=tmp_path / "project", idea="legacy summary", field="generic scientific workflow").path
    report = write_stage_summary(
        project,
        stage="methods",
        command="test-legacy-summary",
        payload={"status": "checkpoint_created"},
        before_artifacts=[],
        checkpoint_id="legacy-summary",
        checkpoint_hash="legacy-hash",
        publish_index=True,
    )
    summary_path = project / report["stage_summary_json"]
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["schema_version"] = "dpl.checkpoint_summary.v2"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False), encoding="utf-8")

    shown = show_checkpoint_summary(project, report["stage_summary_sha256"])
    assert shown["status"] == "legacy_summary"
    assert shown["requires_preview"] is True
    validation = validate_checkpoint_summary(
        project,
        {"stage_summary_json": report["stage_summary_json"], "stage_summary_sha256": report["stage_summary_sha256"]},
    )
    assert validation["status"] == "legacy_unqualified"
    assert validation["valid"] is False
