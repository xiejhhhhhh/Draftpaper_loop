"""Core-evidence batch scope persists across CLI invocations."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from draftpaper_cli.project_scaffold import create_project
from draftpaper_cli.revision_cycle import begin_revision_cycle, load_active_revision_cycle


def _task(task_id: str, *, depends_on: tuple[str, ...] = ()) -> dict:
    return {
        "task_id": task_id,
        "title_zh": f"任务 {task_id}",
        "title_en": f"Task {task_id}",
        "checkpoint_scope": "core_evidence",
        "origin_ref": "user_request",
        "effect_class": "scientific",
        "required_before_publication": True,
        "depends_on": list(depends_on),
        "evidence_refs": ["results/result_validity_report.json"],
        "expected_artifacts": ["results/result_validity_report.json"],
        "completion_checks": ["matching_artifact_hash"],
        "completion_receipts": [],
        "status": "pending",
    }


def _changes_file(project: Path, tasks: list[dict]) -> Path:
    path = project / "revision_changes.json"
    path.write_text(json.dumps({"tasks": tasks}, ensure_ascii=False), encoding="utf-8")
    return path


def test_core_evidence_batch_review_names_work_and_bounds_summary_size(monkeypatch, tmp_path: Path) -> None:
    from draftpaper_cli import core_evidence_batch

    tasks = [
        {
            "task_id": f"task_{index}",
            "title_zh": f"核验事项 {index}",
            "title_en": f"Validate item {index}",
            "checkpoint_scope": "core_evidence",
            "required_before_publication": True,
            "effect_class": "scientific",
            "evidence_refs": [f"results/evidence_{index}.json"],
            "expected_artifacts": [f"results/output_{index}.json"],
        }
        for index in range(1, 6)
    ]
    monkeypatch.setattr(core_evidence_batch, "load_active_revision_cycle", lambda _project: {"pending_tasks": tasks})
    monkeypatch.setattr(core_evidence_batch, "load_core_evidence_batch", lambda _project: {"batch_id": "batch-1"})

    review = core_evidence_batch.core_evidence_batch_review(
        tmp_path,
        {
            "publishable": True,
            "batch_id": "batch-1",
            "scope_sha256": "scope-hash",
            "input_manifest_sha256": "manifest-hash",
        },
    )

    assert review["completed_task_count"] == 5
    assert "核验事项 1" in review["summary_zh"]
    assert "另 1 项" in review["summary_zh"]
    assert "Validate item 1" in review["summary_en"]
    assert "and 1 more" in review["summary_en"]
    assert len(review["summary_zh"]) < 500 and len(review["summary_en"]) < 700
    assert len(review["tasks"]) == 5


def test_prepare_batch_upgrades_cycle_and_reuses_same_scope(tmp_path: Path) -> None:
    from draftpaper_cli.core_evidence_batch import load_core_evidence_batch, prepare_core_evidence_batch

    project = create_project(root=tmp_path, idea="Batch persistence", field="generic").path
    path = _changes_file(project, [_task("result"), _task("figure", depends_on=("result",))])

    first = prepare_core_evidence_batch(project, changes_path=path)
    second = prepare_core_evidence_batch(project, changes_path=path)
    cycle = load_active_revision_cycle(project)

    assert cycle["schema_version"] == "dpl.revision_cycle.v3"
    assert cycle["revision_cycle_sha256"] == first["revision_cycle"]["revision_cycle_sha256"]
    assert second["revision_cycle"]["revision_cycle_sha256"] == cycle["revision_cycle_sha256"]
    assert cycle["evidence_batch"]["phase"] == "collecting"
    assert cycle["evidence_batch"]["scope_sha256"] == first["batch"]["scope_sha256"]
    assert {task["task_id"] for task in cycle["pending_tasks"]} == {"result", "figure"}
    assert load_core_evidence_batch(project)["batch_id"] == first["batch"]["batch_id"]


def test_prepare_batch_rejects_dependency_cycle(tmp_path: Path) -> None:
    from draftpaper_cli.core_evidence_batch import CoreEvidenceBatchError, prepare_core_evidence_batch

    project = create_project(root=tmp_path, idea="Cyclic batch", field="generic").path
    path = _changes_file(project, [_task("a", depends_on=("b",)), _task("b", depends_on=("a",))])

    with pytest.raises(CoreEvidenceBatchError, match="cycle"):
        prepare_core_evidence_batch(project, changes_path=path)
    assert load_active_revision_cycle(project) is None


def test_prepare_batch_rejects_conflicting_duplicate_task_identity(tmp_path: Path) -> None:
    from draftpaper_cli.core_evidence_batch import CoreEvidenceBatchError, prepare_core_evidence_batch

    project = create_project(root=tmp_path, idea="Conflicting task identity", field="generic").path
    required_science = _task("shared_task_id")
    optional_presentation = {
        **required_science,
        "title_zh": "仅调整呈现",
        "title_en": "Presentation only",
        "effect_class": "presentation",
        "required_before_publication": False,
        "evidence_refs": [],
        "expected_artifacts": [],
    }
    path = _changes_file(project, [required_science, optional_presentation])

    with pytest.raises(CoreEvidenceBatchError, match="duplicate|conflict"):
        prepare_core_evidence_batch(project, changes_path=path)

    assert load_active_revision_cycle(project) is None


def test_prepare_batch_rejects_unknown_checkpoint_scope_instead_of_excluding_it(tmp_path: Path) -> None:
    from draftpaper_cli.core_evidence_batch import CoreEvidenceBatchError, prepare_core_evidence_batch

    project = create_project(root=tmp_path, idea="Unknown checkpoint scope", field="generic").path
    misscoped_science = {**_task("misscoped_science"), "checkpoint_scope": "core_evidnce"}
    path = _changes_file(project, [_task("known_core_task"), misscoped_science])

    with pytest.raises(CoreEvidenceBatchError, match="(?i)unknown.*checkpoint scope|checkpoint scope.*unknown"):
        prepare_core_evidence_batch(project, changes_path=path)

    assert load_active_revision_cycle(project) is None


def test_prepare_batch_can_explicitly_reclassify_an_existing_unknown_scope(tmp_path: Path) -> None:
    from draftpaper_cli.core_evidence_batch import prepare_core_evidence_batch

    project = create_project(root=tmp_path, idea="Reclassify checkpoint scope", field="generic").path
    begin_revision_cycle(
        project,
        pending_tasks=[{**_task("recovered_task"), "checkpoint_scope": "core_evidnce"}],
    )

    result = prepare_core_evidence_batch(
        project, changes_path=_changes_file(project, [_task("recovered_task")]),
    )

    tasks = result["revision_cycle"]["pending_tasks"]
    assert len(tasks) == 1
    assert tasks[0]["task_id"] == "recovered_task"
    assert tasks[0]["checkpoint_scope"] == "core_evidence"


def test_prepare_batch_rejects_reclassifying_core_task_out_of_c3_scope(tmp_path: Path) -> None:
    from draftpaper_cli.core_evidence_batch import CoreEvidenceBatchError, prepare_core_evidence_batch

    project = create_project(root=tmp_path, idea="Preserve core task scope", field="generic").path
    begin_revision_cycle(project, pending_tasks=[_task("anchor"), _task("core_science")])
    changes = _changes_file(project, [
        _task("anchor"),
        {**_task("core_science"), "checkpoint_scope": "post_acceptance"},
    ])

    with pytest.raises(CoreEvidenceBatchError, match="cannot be reclassified to a non-core scope"):
        prepare_core_evidence_batch(project, changes_path=changes)


def test_unscoped_legacy_task_requires_explicit_classification(tmp_path: Path) -> None:
    from draftpaper_cli.core_evidence_batch import CoreEvidenceBatchError, prepare_core_evidence_batch

    project = create_project(root=tmp_path, idea="Legacy scope", field="generic").path
    begin_revision_cycle(project, pending_tasks=("unclassified existing task",))

    with pytest.raises(CoreEvidenceBatchError, match="scope|classif"):
        prepare_core_evidence_batch(project)
    assert load_active_revision_cycle(project)["schema_version"] == "dpl.revision_cycle.v2"


def test_one_required_task_is_a_valid_batch(tmp_path: Path) -> None:
    from draftpaper_cli.core_evidence_batch import prepare_core_evidence_batch

    project = create_project(root=tmp_path, idea="Single task batch", field="generic").path
    result = prepare_core_evidence_batch(project, changes_path=_changes_file(project, [_task("one")]))
    assert result["batch"]["phase"] == "collecting"
    assert len(result["revision_cycle"]["pending_tasks"]) == 1


def test_prepare_batch_preserves_tasks_for_other_gates(tmp_path: Path) -> None:
    from draftpaper_cli.core_evidence_batch import prepare_core_evidence_batch

    project = create_project(root=tmp_path, idea="Scoped task preservation", field="generic").path
    existing_release_task = {
        "task_id": "release_doi",
        "checkpoint_scope": "post_acceptance",
        "status": "pending",
        "title_en": "Add the final publication DOI",
    }
    imported_literature_task = {
        "task_id": "literature_gate",
        "checkpoint_scope": "literature_review",
        "status": "pending",
        "title_en": "Complete literature review confirmation",
    }
    begin_revision_cycle(project, pending_tasks=[existing_release_task])
    path = _changes_file(project, [_task("core_result"), imported_literature_task])

    result = prepare_core_evidence_batch(project, changes_path=path)

    rows = result["revision_cycle"]["pending_tasks"]
    assert {row["task_id"] for row in rows} == {"release_doi", "literature_gate", "core_result"}
    assert all(row["checkpoint_scope"] == "core_evidence" for row in rows if row["task_id"] == "core_result")


def test_scientific_task_cannot_opt_out_of_confirmation_readiness(tmp_path: Path) -> None:
    from draftpaper_cli.core_evidence_batch import CoreEvidenceBatchError, prepare_core_evidence_batch

    project = create_project(root=tmp_path, idea="Required scientific work", field="generic").path
    task = _task("scientific_change")
    task["required_before_publication"] = False
    path = _changes_file(project, [task])

    with pytest.raises(CoreEvidenceBatchError, match="required_before_publication"):
        prepare_core_evidence_batch(project, changes_path=path)


def test_legacy_v1_requires_shadow_and_exact_source_hash_to_migrate(tmp_path: Path) -> None:
    from draftpaper_cli.core_evidence_batch import (
        CoreEvidenceBatchError,
        migrate_legacy_core_evidence_batch,
        shadow_core_evidence_batch_migration,
    )
    from tests.test_revision_cycle_schema_migration import _make_legacy_v1_cycle

    project = create_project(root=tmp_path, idea="Legacy batch migration", field="generic").path
    _, source, _ = _make_legacy_v1_cycle(project)
    report = shadow_core_evidence_batch_migration(project)
    assert report["can_migrate"] is True
    assert report["source_cycle_sha256"] == source["revision_cycle_sha256"]
    task = {
        "task_id": "legacy_migrated_evidence_review",
        "title_zh": "核验迁移后的核心证据",
        "title_en": "Review migrated core evidence",
        "checkpoint_scope": "core_evidence",
        "origin_ref": "explicit_legacy_migration",
        "effect_class": "scientific",
        "required_before_publication": True,
        "status": "pending",
        "depends_on": [],
        "evidence_refs": ["core_evidence/core_evidence_report.json"],
        "expected_artifacts": ["core_evidence/core_evidence_report.json"],
        "completion_checks": ["matching_artifact_hash"],
        "completion_receipts": [],
    }
    changes = project / "legacy_batch.json"
    changes.write_text(json.dumps({"tasks": [task]}, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(CoreEvidenceBatchError, match="source SHA-256"):
        migrate_legacy_core_evidence_batch(
            project, changes_path=changes, expected_legacy_source_sha256="0" * 64,
        )

    migrated = migrate_legacy_core_evidence_batch(
        project, changes_path=changes, expected_legacy_source_sha256=report["source_cycle_sha256"],
    )
    assert migrated["revision_cycle"]["migration_status"] == "explicitly_scoped"
    assert migrated["revision_cycle"]["migration_source_sha256"] == report["source_cycle_sha256"]
    assert migrated["batch"]["phase"] == "collecting"


def test_shadow_missing_legacy_scope_fields_is_unknown_not_empty() -> None:
    from draftpaper_cli.core_evidence_batch import _shadow_task_scope

    missing = _shadow_task_scope({}, legacy=True, source={})
    partial = _shadow_task_scope(
        {"pending_tasks": [{"task_id": "old-task", "status": "pending"}]},
        legacy=False,
        source={},
    )

    assert missing["status"] == "unknown"
    assert missing["task_count"] is None
    assert missing["missing_fields"] == ["pending_tasks"]
    assert partial["status"] == "incomplete"
    assert partial["task_count"] == 1
    assert {"checkpoint_scope", "effect_class", "evidence_refs"}.issubset(partial["missing_fields"])
