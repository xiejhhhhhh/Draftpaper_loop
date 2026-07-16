# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json
import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .project_scaffold import PROJECT_DIRECTORIES, _build_stage_metadata, _write_json, _write_simple_yaml, utc_now
from .scoped_transaction import ScopedProjectTransaction
from .state_kernel import StateKernelError, file_lock, read_json_object


VALID_STAGE_STATUSES = {"pending", "draft", "approved", "stale", "failed", "completed"}


class ProjectStateError(RuntimeError):
    """Raised when a project cannot be loaded or updated safely."""


class UnknownStageError(ProjectStateError):
    """Raised when a requested stage is not declared in project metadata."""


class InvalidStageStatusError(ProjectStateError):
    """Raised when a requested stage status is not supported."""


@dataclass(frozen=True)
class ProjectState:
    path: Path
    metadata: dict[str, Any]

    @property
    def stage_names(self) -> list[str]:
        return list((self.metadata.get("stages") or {}).keys())


def _project_json_path(project: str | Path) -> Path:
    path = Path(project).expanduser().resolve()
    if path.is_file() and path.name == "project.json":
        return path
    return path / "project.json"


def load_project(project: str | Path) -> ProjectState:
    """Load a staged paper project from a project directory or project.json path."""
    json_path = _project_json_path(project)
    if not json_path.exists():
        raise ProjectStateError(f"project.json not found: {json_path}")
    try:
        metadata = read_json_object(json_path, required_keys=("project_id", "stages"))
    except StateKernelError as exc:
        raise ProjectStateError(str(exc)) from exc
    if "stages" not in metadata or not isinstance(metadata["stages"], dict):
        raise ProjectStateError(f"project.json has no stages object: {json_path}")
    return ProjectState(path=json_path.parent, metadata=metadata)


def _stage_dir(project_path: Path, stage: str) -> Path:
    if stage == "quality_checks":
        return project_path / "quality_checks"
    return project_path / stage


def _manifest_path(project_path: Path, stage: str) -> Path:
    return _stage_dir(project_path, stage) / "stage_manifest.json"


def inspect_project_migration(project: str | Path) -> dict[str, Any]:
    """Return a read-only migration plan for an older project."""
    json_path = _project_json_path(project)
    try:
        metadata = read_json_object(json_path, required_keys=("project_id", "stages"))
    except StateKernelError as exc:
        raise ProjectStateError(str(exc)) from exc
    project_path = json_path.parent
    defaults = _build_stage_metadata()
    return {
        "status": "migration_required" if (
            any(not (project_path / relative).is_dir() for relative in PROJECT_DIRECTORIES)
            or any(stage not in metadata["stages"] or metadata["stages"][stage].get("depends_on") != default.get("depends_on") for stage, default in defaults.items())
        ) else "current",
        "project_path": str(project_path),
        "missing_directories": [relative for relative in PROJECT_DIRECTORIES if not (project_path / relative).is_dir()],
        "missing_stages": [stage for stage in defaults if stage not in metadata["stages"]],
        "dependency_updates": [stage for stage, default in defaults.items() if stage in metadata["stages"] and metadata["stages"][stage].get("depends_on") != default.get("depends_on")],
    }


def migrate_project(project: str | Path) -> dict[str, Any]:
    """Explicitly migrate project directories, stage metadata, and manifests."""
    json_path = _project_json_path(project)
    metadata = read_json_object(json_path, required_keys=("project_id", "stages"))
    project_path = json_path.parent
    plan = inspect_project_migration(project_path)
    for relative in PROJECT_DIRECTORIES:
        (project_path / relative).mkdir(parents=True, exist_ok=True)
    defaults = _build_stage_metadata()
    updated = copy.deepcopy(metadata)
    for stage, default_meta in defaults.items():
        if stage not in updated["stages"]:
            updated["stages"][stage] = copy.deepcopy(default_meta)
        else:
            updated["stages"][stage]["depends_on"] = list(default_meta.get("depends_on") or [])
    updated["updated_at"] = utc_now()
    _save_project(ProjectState(path=project_path, metadata=updated), stage_names=list(defaults))
    return {**plan, "status": "migrated", "project_path": str(project_path)}


def _save_project(state: ProjectState, *, stage_names: list[str] | None = None) -> ProjectState:
    state.metadata["updated_at"] = utc_now()
    state.metadata["state_revision"] = int(state.metadata.get("state_revision") or 0) + 1
    # Every manifest records the same state revision, so one commit refreshes
    # the complete state view even when only one stage changed.
    selected = state.stage_names
    patterns = [
        "project.json",
        "project.yaml",
        *(_manifest_path(state.path, stage).relative_to(state.path).as_posix() for stage in selected),
    ]
    with file_lock(state.path):
        with ScopedProjectTransaction(state.path, patterns) as transaction:
            _write_json(state.path / "project.json", state.metadata)
            _write_simple_yaml(state.path / "project.yaml", state.metadata)
            for stage in selected:
                _write_stage_manifest(state, stage)
            transaction.commit()
    return load_project(state.path)


def _write_stage_manifest(state: ProjectState, stage: str) -> None:
    stage_meta = state.metadata["stages"][stage]
    manifest_path = _manifest_path(state.path, stage)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    existing: dict[str, Any] = {}
    if manifest_path.exists():
        try:
            existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = {}
    manifest = {
        "project_id": state.metadata.get("project_id"),
        "stage": stage,
        "status": stage_meta.get("status", "pending"),
        "stale": bool(stage_meta.get("stale", False)),
        "depends_on": list(stage_meta.get("depends_on", [])),
        "input_files": existing.get("input_files", []),
        "output_files": existing.get("output_files", []),
        "last_updated": stage_meta.get("last_updated") or existing.get("last_updated"),
        "state_revision": int(state.metadata.get("state_revision") or 0),
    }
    _write_json(manifest_path, manifest)


def _require_stage(state: ProjectState, stage: str) -> None:
    if stage not in state.metadata["stages"]:
        raise UnknownStageError(f"Unknown stage '{stage}'. Known stages: {', '.join(state.stage_names)}")


def _require_status(status: str) -> None:
    if status not in VALID_STAGE_STATUSES:
        raise InvalidStageStatusError(
            f"Invalid stage status '{status}'. Use one of: {', '.join(sorted(VALID_STAGE_STATUSES))}"
        )


def _dependent_stages(state: ProjectState, changed_stage: str) -> list[str]:
    dependents: list[str] = []
    frontier = [changed_stage]
    seen = {changed_stage}
    while frontier:
        current = frontier.pop(0)
        for stage, stage_meta in state.metadata["stages"].items():
            if stage in seen:
                continue
            if current in (stage_meta.get("depends_on") or []):
                dependents.append(stage)
                seen.add(stage)
                frontier.append(stage)
    return dependents


def update_stage_status(project: str | Path, stage: str, status: str) -> ProjectState:
    """Update a stage status and keep project metadata plus stage manifest synchronized."""
    _require_status(status)
    state = load_project(project)
    _require_stage(state, stage)

    now = utc_now()
    state.metadata["current_stage"] = stage
    stage_meta = state.metadata["stages"][stage]
    stage_meta["status"] = status
    stage_meta["stale"] = status == "stale"
    stage_meta["last_updated"] = now
    selected = [stage]
    if status in {"draft", "failed"}:
        for dependent in _dependent_stages(state, stage):
            dependent_meta = state.metadata["stages"][dependent]
            dependent_meta["status"] = "stale"
            dependent_meta["stale"] = True
            dependent_meta["last_updated"] = now
            selected.append(dependent)
    return _save_project(state, stage_names=selected)


def mark_stage_stale(project: str | Path, stage: str, *, include_self: bool = False) -> list[str]:
    """Mark all stages that depend on `stage` as stale, recursively."""
    state = load_project(project)
    _require_stage(state, stage)

    changed = [stage] if include_self else []
    changed.extend(_dependent_stages(state, stage))
    now = utc_now()
    for stale_stage in changed:
        stage_meta = state.metadata["stages"][stale_stage]
        stage_meta["status"] = "stale"
        stage_meta["stale"] = True
        stage_meta["last_updated"] = now
    _save_project(state, stage_names=changed)
    return changed


def mark_stages_stale(project: str | Path, stages: list[str]) -> list[str]:
    """Mark an explicit set of stages stale without recursive dependency expansion."""
    state = load_project(project)
    changed: list[str] = []
    now = utc_now()
    for stage in stages:
        if stage not in state.metadata["stages"] or stage in changed:
            continue
        stage_meta = state.metadata["stages"][stage]
        stage_meta["status"] = "stale"
        stage_meta["stale"] = True
        stage_meta["last_updated"] = now
        changed.append(stage)
    _save_project(state, stage_names=changed)
    return changed


def mark_stage_roots_stale(project: str | Path, stages: list[str]) -> list[str]:
    """Mark stage roots and every transitive dependent stale in one state update."""
    state = load_project(project)
    requested = list(dict.fromkeys(stages))
    for stage in requested:
        _require_stage(state, stage)
    selected = set(requested)
    for stage in requested:
        selected.update(_dependent_stages(state, stage))
    changed = [stage for stage in state.stage_names if stage in selected]
    now = utc_now()
    for stage in changed:
        stage_meta = state.metadata["stages"][stage]
        stage_meta["status"] = "stale"
        stage_meta["stale"] = True
        stage_meta["last_updated"] = now
    _save_project(state, stage_names=changed)
    return changed


def update_project_state(
    project: str | Path,
    *,
    metadata_updates: dict[str, Any] | None = None,
    stage_updates: dict[str, str] | None = None,
) -> ProjectState:
    """Commit metadata and stage changes under one state revision."""
    state = load_project(project)
    for key, value in (metadata_updates or {}).items():
        if key in {"project_id", "stages", "state_revision"}:
            raise ProjectStateError(f"Protected project metadata cannot be replaced: {key}")
        state.metadata[key] = value
    now = utc_now()
    selected: list[str] = []
    for stage, status in (stage_updates or {}).items():
        _require_stage(state, stage)
        _require_status(status)
        stage_meta = state.metadata["stages"][stage]
        stage_meta["status"] = status
        stage_meta["stale"] = status == "stale"
        stage_meta["last_updated"] = now
        state.metadata["current_stage"] = stage
        selected.append(stage)
    return _save_project(state, stage_names=selected)


def validate_project(project: str | Path) -> dict[str, Any]:
    """Validate project metadata, required directories, and stage manifests."""
    issues: list[dict[str, str]] = []
    try:
        state = load_project(project)
    except ProjectStateError as exc:
        return {
            "status": "failed",
            "project_path": str(Path(project).expanduser().resolve()),
            "issues": [{"severity": "error", "code": "project_load_failed", "message": str(exc)}],
        }

    for relative in PROJECT_DIRECTORIES:
        if not (state.path / relative).is_dir():
            issues.append({
                "severity": "error",
                "code": "missing_project_directory",
                "message": f"Missing project directory: {relative}",
            })

    for stage, stage_meta in state.metadata["stages"].items():
        status = stage_meta.get("status")
        if status not in VALID_STAGE_STATUSES:
            issues.append({
                "severity": "error",
                "code": "invalid_stage_status",
                "message": f"Stage {stage} has invalid status: {status}",
            })
        manifest_path = _manifest_path(state.path, stage)
        if not manifest_path.exists():
            issues.append({
                "severity": "error",
                "code": "missing_stage_manifest",
                "message": f"Stage {stage} is missing stage_manifest.json",
            })
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            issues.append({
                "severity": "error",
                "code": "invalid_stage_manifest_json",
                "message": f"Stage {stage} manifest is invalid JSON",
            })
            continue
        if manifest.get("stage") != stage:
            issues.append({
                "severity": "error",
                "code": "stage_manifest_mismatch",
                "message": f"Stage {stage} manifest declares stage {manifest.get('stage')}",
            })
        if manifest.get("status") != stage_meta.get("status"):
            issues.append({
                "severity": "warning",
                "code": "stage_manifest_status_drift",
                "message": f"Stage {stage} manifest status differs from project.json",
            })
        if bool(manifest.get("stale", False)) != bool(stage_meta.get("stale", False)):
            issues.append({
                "severity": "warning",
                "code": "stage_manifest_stale_drift",
                "message": f"Stage {stage} manifest stale flag differs from project.json",
            })
        state_revision = int(state.metadata.get("state_revision") or 0)
        if state_revision and int(manifest.get("state_revision") or 0) != state_revision:
            issues.append({
                "severity": "error",
                "code": "stage_manifest_revision_drift",
                "message": f"Stage {stage} manifest belongs to state revision {manifest.get('state_revision')}, expected {state_revision}",
            })

    error_count = sum(1 for issue in issues if issue["severity"] == "error")
    warning_count = sum(1 for issue in issues if issue["severity"] == "warning")
    return {
        "status": "passed" if error_count == 0 else "failed",
        "project_path": str(state.path),
        "project_id": state.metadata.get("project_id"),
        "error_count": error_count,
        "warning_count": warning_count,
        "issues": issues,
    }
