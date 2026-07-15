# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

from pathlib import Path
from typing import Any

from .change_impact import affected_stages, artifact_role_for_path, classify_change
from .passport import (
    PASSPORT_FILES,
    PassportError,
    append_integrity_event,
    collect_artifacts,
    load_project_passport,
    project_root,
    refresh_project_passport,
    utc_now,
)
from .project_scaffold import STAGE_ORDER
from .project_state import ProjectStateError, load_project, mark_stages_stale


class ArtifactDriftError(RuntimeError):
    """Raised when artifact drift cannot be mapped to stage backtracking."""


MANAGED_STATE_ARTIFACTS = {
    "project.json",
    "project.yaml",
    "project_system_of_record.json",
}


def _is_managed_state_artifact(path: str) -> bool:
    normalized = str(path or "").replace("\\", "/")
    return (
        normalized in MANAGED_STATE_ARTIFACTS
        or normalized.endswith("/stage_manifest.json")
        or normalized.startswith("stage_manifests/")
    )


def _stage_for_path(path: str) -> str:
    normalized = path.replace("\\", "/")
    if normalized in {"project.json", "project.yaml"}:
        return "idea"
    first = normalized.split("/", 1)[0]
    if first in {"artifact_ledger.jsonl", "checkpoint_ledger.jsonl", "integrity_ledger.jsonl", "project_passport.yaml"}:
        return "passport"
    return first


def _known_stage(stage: str) -> str:
    if stage == "quality_checks":
        return stage
    if stage in STAGE_ORDER:
        return stage
    if stage == "code":
        return "code"
    return "idea"


def _stage_sort_key(stage: str) -> int:
    try:
        return STAGE_ORDER.index(stage)
    except ValueError:
        return len(STAGE_ORDER)


def _artifact_maps(project: str | Path) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    project_path = project_root(project)
    passport = load_project_passport(project_path)
    baseline = {
        str(item.get("path")): item
        for item in (passport.get("artifacts") or [])
        if (
            isinstance(item, dict)
            and item.get("path")
            and not _is_managed_state_artifact(str(item.get("path")))
        )
    }
    current = {
        str(item.get("path")): item
        for item in collect_artifacts(project_path)
        if (
            isinstance(item, dict)
            and item.get("path")
            and not _is_managed_state_artifact(str(item.get("path")))
        )
    }
    return baseline, current


def detect_artifact_drift(project: str | Path) -> dict[str, Any]:
    """Compare current artifact hashes against project_passport.yaml without mutating state."""
    project_path = project_root(project)
    baseline, current = _artifact_maps(project_path)
    changed = []
    missing = []
    added = []
    for path, old in sorted(baseline.items()):
        if path not in current:
            missing.append({"path": path, "stage": _known_stage(_stage_for_path(path)), "previous_sha256": old.get("sha256")})
            continue
        new = current[path]
        if old.get("sha256") != new.get("sha256"):
            changed.append({
                "path": path,
                "stage": _known_stage(_stage_for_path(path)),
                "previous_sha256": old.get("sha256"),
                "current_sha256": new.get("sha256"),
                "previous_semantic_fingerprint": old.get("semantic_fingerprint"),
                "current_semantic_fingerprint": new.get("semantic_fingerprint"),
            })
    for path, new in sorted(current.items()):
        if path not in baseline:
            added.append({"path": path, "stage": _known_stage(_stage_for_path(path)), "current_sha256": new.get("sha256")})

    source_stages = sorted(
        {
            item["stage"]
            for item in [*changed, *missing, *added]
            if item.get("stage") not in {"passport"}
        },
        key=_stage_sort_key,
    )
    drift_count = len(changed) + len(missing) + len(added)
    return {
        "status": "drift_detected" if drift_count else "clean",
        "project_path": str(project_path),
        "drift_count": drift_count,
        "changed_artifacts": changed,
        "missing_artifacts": missing,
        "added_artifacts": added,
        "source_stages": source_stages,
        "recommended_command": (
            f"python -m draftpaper_cli.cli sync-artifact-stale --project \"{project_path}\""
            if drift_count else None
        ),
    }


def sync_artifact_stale(project: str | Path) -> dict[str, Any]:
    """Mark dependent stages stale from artifact hash drift and refresh passport baseline."""
    project_path = project_root(project)
    state = load_project(project_path)
    drift = detect_artifact_drift(project_path)
    if drift["status"] == "clean":
        passport = refresh_project_passport(project_path, event="artifact_drift_clean")
        return {
            "status": "clean",
            "project_path": str(project_path),
            "stale_stages": [],
            "drift": drift,
            "passport": str(project_path / PASSPORT_FILES["passport"]),
            "artifact_count": passport.get("artifact_count", 0),
        }

    stale_stages: list[str] = []
    classified_changes: list[dict[str, Any]] = []
    drift_items = [
        *drift.get("changed_artifacts", []),
        *drift.get("missing_artifacts", []),
        *drift.get("added_artifacts", []),
    ]
    for item in drift_items:
        path = str(item.get("path") or "")
        role, owner_stage = artifact_role_for_path(path)
        change = classify_change(
            artifact_role=role,
            before=item.get("previous_sha256"),
            after=item.get("current_sha256"),
            source_stage=owner_stage,
            declaration={
                "before_semantic_fingerprint": item.get("previous_semantic_fingerprint"),
                "after_semantic_fingerprint": item.get("current_semantic_fingerprint"),
            },
        )
        impacted = affected_stages(change)
        classified_changes.append({
            "path": path,
            "artifact_role": role,
            "change_class": change.change_class,
            "affected_stages": impacted,
            "reason": change.reason,
        })
        for stage in impacted:
            if stage in (state.metadata.get("stages") or {}) and stage not in stale_stages:
                stale_stages.append(stage)

    stale_stages = mark_stages_stale(project_path, stale_stages)

    event = {
        "kind": "artifact_drift",
        "recorded_at": utc_now(),
        "source_stages": drift.get("source_stages") or [],
        "stale_stages": stale_stages,
        "changed_artifacts": drift.get("changed_artifacts") or [],
        "missing_artifacts": drift.get("missing_artifacts") or [],
        "added_artifacts": drift.get("added_artifacts") or [],
        "classified_changes": classified_changes,
    }
    append_integrity_event(project_path, event)
    passport = refresh_project_passport(project_path, event="artifact_drift_synced")
    return {
        "status": "synced",
        "project_path": str(project_path),
        "stale_stages": sorted(stale_stages, key=_stage_sort_key),
        "drift": drift,
        "classified_changes": classified_changes,
        "passport": str(project_path / PASSPORT_FILES["passport"]),
        "artifact_count": passport.get("artifact_count", 0),
    }


def handle_stale_sync_error(exc: Exception) -> dict[str, str]:
    if isinstance(exc, (ArtifactDriftError, PassportError, ProjectStateError)):
        return {"status": "error", "message": str(exc)}
    return {"status": "error", "message": str(exc)}
