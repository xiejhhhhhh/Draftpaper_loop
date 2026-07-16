from __future__ import annotations

import json
from pathlib import Path

import pytest

from draftpaper_cli import project_state
from draftpaper_cli.project_scaffold import create_project


def _state_files(project: Path) -> dict[str, bytes]:
    paths = [project / "project.json", project / "project.yaml"]
    paths.extend(project.glob("*/stage_manifest.json"))
    return {path.relative_to(project).as_posix(): path.read_bytes() for path in paths}


def test_state_revision_is_shared_by_project_and_every_stage_manifest(tmp_path: Path) -> None:
    project = create_project(root=tmp_path, idea="State revision", field="engineering").path
    initial = project_state.load_project(project)
    assert initial.metadata["state_revision"] == 1

    updated = project_state.update_stage_status(project, "references", "completed")

    revision = updated.metadata["state_revision"]
    assert revision == 2
    manifests = list(project.glob("*/stage_manifest.json"))
    assert manifests
    assert all(json.loads(path.read_text(encoding="utf-8"))["state_revision"] == revision for path in manifests)
    assert project_state.validate_project(project)["status"] == "passed"


def test_state_commit_rolls_back_every_file_when_manifest_write_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = create_project(root=tmp_path, idea="State rollback", field="engineering").path
    before = _state_files(project)
    real_write = project_state._write_stage_manifest
    calls = 0

    def failing_write(state, stage):
        nonlocal calls
        calls += 1
        real_write(state, stage)
        if calls == 4:
            raise OSError("injected stage manifest failure")

    monkeypatch.setattr(project_state, "_write_stage_manifest", failing_write)
    with pytest.raises(OSError, match="injected stage manifest failure"):
        project_state.update_stage_status(project, "references", "completed")

    assert _state_files(project) == before
    assert project_state.load_project(project).metadata["state_revision"] == 1
