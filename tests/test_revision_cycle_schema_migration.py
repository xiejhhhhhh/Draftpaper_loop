from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator
import pytest

from draftpaper_cli.revision_cycle import (
    ACTIVE_POINTER,
    REVISION_DIR,
    RevisionCycleError,
    begin_revision_cycle,
    load_active_revision_cycle,
    set_revision_mode,
    _hash,
)
from draftpaper_cli.orchestrator import checkpoint_project, status_project
from draftpaper_cli.project_scaffold import create_project


def _new_project(tmp_path: Path) -> Path:
    return create_project(root=tmp_path, idea="Revision schema", field="astronomy").path


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _make_legacy_v1_cycle(project: Path) -> tuple[Path, dict, dict]:
    started = begin_revision_cycle(project, reason="legacy fixture", mode="author_edit")
    path = Path(started["revision_cycle_path"])
    payload = _read_json(path)
    payload["schema_version"] = "dpl.revision_cycle.v1"
    for field in (
        "revision_generation",
        "mode",
        "automatic_upstream",
        "reconciliation_status",
        "draft_generation",
        "candidate_generation",
    ):
        payload.pop(field, None)
    payload["legacy_extension"] = {"retained": True}
    payload["revision_cycle_sha256"] = _hash(
        {key: value for key, value in payload.items() if key != "revision_cycle_sha256"}
    )
    _write_json(path, payload)

    pointer_path = project / ACTIVE_POINTER
    pointer = _read_json(pointer_path)
    pointer["revision_cycle_sha256"] = payload["revision_cycle_sha256"]
    _write_json(pointer_path, pointer)
    return path, payload, pointer


def _schema_v2() -> dict:
    schema_path = Path(__file__).parents[1] / "draftpaper_cli" / "resources" / "schemas" / "revision_cycle_v2.json"
    return json.loads(schema_path.read_text(encoding="utf-8"))


def test_new_revision_cycles_use_complete_strict_v2_schema(tmp_path: Path) -> None:
    project = _new_project(tmp_path)
    cycle = begin_revision_cycle(project, reason="new cycle")['revision_cycle']
    assert cycle["schema_version"] == "dpl.revision_cycle.v2"

    schema = _schema_v2()
    validator = Draft202012Validator(schema)

    assert not list(validator.iter_errors(cycle))
    assert list(validator.iter_errors({**cycle, "unregistered_state": True}))
    assert list(validator.iter_errors({key: value for key, value in cycle.items() if key != "mode"}))


def test_v1_cycle_is_conservatively_projected_without_mutating_legacy_files(tmp_path: Path) -> None:
    project = _new_project(tmp_path)
    path, source, pointer = _make_legacy_v1_cycle(project)
    source_bytes = path.read_bytes()
    pointer_path = project / ACTIVE_POINTER
    pointer_bytes = pointer_path.read_bytes()

    loaded = load_active_revision_cycle(project)

    assert loaded is not None
    assert loaded["schema_version"] == "dpl.revision_cycle.v2"
    assert loaded["mode"] == "author_edit"
    assert loaded["automatic_upstream"] is False
    assert loaded["reconciliation_status"] == "pending"
    assert loaded["revision_generation"] == 1
    assert loaded["draft_generation"] == 1
    assert loaded["candidate_generation"] == 1
    assert loaded["migration_status"] == "legacy_unverified"
    assert loaded["migration_source_schema_version"] == "dpl.revision_cycle.v1"
    assert loaded["migration_source_sha256"] == source["revision_cycle_sha256"]
    assert loaded["migration_missing_fields"]
    assert loaded["legacy_source_record"] == source
    assert loaded["legacy_source_record"]["legacy_extension"] == {"retained": True}
    assert path.read_bytes() == source_bytes
    assert pointer_path.read_bytes() == pointer_bytes
    assert pointer["revision_cycle_sha256"] == source["revision_cycle_sha256"]
    assert not list(Draft202012Validator(_schema_v2()).iter_errors(loaded))


def test_legacy_author_edit_status_does_not_hide_pending_human_checkpoint(tmp_path: Path) -> None:
    project = _new_project(tmp_path)
    cycle_path, _, _ = _make_legacy_v1_cycle(project)
    cycle_bytes = cycle_path.read_bytes()
    checkpoint = checkpoint_project(project, stage="idea", note="Review the current idea.")

    status = status_project(project)

    assert status["pipeline_state"] == "author_edit_paused"
    assert status["revision_mode"] == "author_edit"
    assert status["awaiting_checkpoint"]["hash"] == checkpoint["checkpoint_hash"]
    assert status["workflow_gate"] == "awaiting_confirmation"
    summary_path = status["pending_checkpoint_paths"]["stage_summary_zh_html"]["absolute_path"]
    assert Path(summary_path).is_file()
    assert status["release_eligible"] is False
    assert status["next_action"]["command"] == "prepare-revision-reconciliation"
    assert cycle_path.read_bytes() == cycle_bytes


def test_explicit_transition_persists_v2_migration_and_keeps_reconciliation_pending(tmp_path: Path) -> None:
    project = _new_project(tmp_path)
    _, source, _ = _make_legacy_v1_cycle(project)

    changed = set_revision_mode(project, mode="live")["revision_cycle"]

    assert changed["schema_version"] == "dpl.revision_cycle.v2"
    assert changed["mode"] == "live"
    assert changed["automatic_upstream"] is True
    assert changed["reconciliation_status"] == "pending"
    assert changed["migration_status"] == "legacy_unverified"
    assert changed["migration_source_sha256"] == source["revision_cycle_sha256"]
    assert changed["legacy_source_record"] == source
    assert not list(Draft202012Validator(_schema_v2()).iter_errors(changed))

    pointer = _read_json(project / ACTIVE_POINTER)
    persisted_path = project / pointer["path"]
    persisted = _read_json(persisted_path)
    assert persisted["schema_version"] == "dpl.revision_cycle.v2"
    assert persisted["revision_cycle_sha256"] == pointer["revision_cycle_sha256"]
    assert load_active_revision_cycle(project) == persisted
    assert persisted_path.parent == project / REVISION_DIR


@pytest.mark.parametrize("corruption", ["digest", "unknown_schema", "unknown_field"])
def test_invalid_active_revision_cycle_fails_closed(tmp_path: Path, corruption: str) -> None:
    project = _new_project(tmp_path)
    started = begin_revision_cycle(project, reason="corruption fixture")
    path = Path(started["revision_cycle_path"])
    payload = _read_json(path)

    if corruption == "digest":
        payload["reason"] = "tampered without updating digest"
        _write_json(path, payload)
    else:
        if corruption == "unknown_schema":
            payload["schema_version"] = "dpl.revision_cycle.v99"
        else:
            payload["unexpected"] = "must not be silently accepted"
            payload["revision_cycle_sha256"] = _hash(
                {key: value for key, value in payload.items() if key != "revision_cycle_sha256"}
            )
        _write_json(path, payload)
        pointer_path = project / ACTIVE_POINTER
        pointer = _read_json(pointer_path)
        pointer["revision_cycle_sha256"] = payload["revision_cycle_sha256"]
        _write_json(pointer_path, pointer)

    with pytest.raises(RevisionCycleError, match="Active revision cycle"):
        load_active_revision_cycle(project)
