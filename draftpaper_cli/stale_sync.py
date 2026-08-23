# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

from pathlib import Path
from typing import Any
import hashlib
import json
import uuid

from .change_impact import affected_stages, artifact_role_for_path, classify_change
from .passport import (
    PASSPORT_FILES,
    PassportError,
    append_integrity_event,
    collect_artifacts,
    load_project_passport,
    project_root,
    read_jsonl,
    refresh_project_passport,
    utc_now,
)
from .project_scaffold import STAGE_ORDER
from .project_state import ProjectStateError, load_project, mark_stages_stale
from .scientific_baseline import load_active_baseline
from .revision_cycle import load_active_revision_cycle
from .state_kernel import atomic_write_json


class ArtifactDriftError(RuntimeError):
    """Raised when artifact drift cannot be mapped to stage backtracking."""


MANAGED_STATE_ARTIFACTS = {
    "project.json",
    "project.yaml",
    "project_system_of_record.json",
}


def _managed_change_metadata(root: Path) -> dict[str, dict[str, Any]]:
    """Return declared managed-edit ownership without trusting arbitrary paths."""

    rows = read_jsonl(root / ".draftpaper" / "managed_change_ledger.jsonl")
    metadata: dict[str, dict[str, Any]] = {}
    for receipt in rows:
        if not isinstance(receipt, dict) or receipt.get("status") != "committed":
            continue
        raw_packet = str(receipt.get("packet_path") or "")
        if not raw_packet:
            continue
        packet_path = (root / raw_packet).resolve()
        try:
            packet_path.relative_to(root.resolve())
            packet = json.loads(packet_path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            continue
        if not isinstance(packet, dict):
            continue
        for relative in receipt.get("changed_paths") or []:
            path = str(relative).replace("\\", "/")
            if not path:
                continue
            metadata[path] = {
                "writer_identity": "managed_agent_or_cli",
                "managed_change_packet_id": packet.get("packet_id"),
                "managed_change_packet_hash": receipt.get("packet_hash"),
                "declared_change_class": packet.get("change_class"),
                "revision_cycle_id": packet.get("revision_cycle_id"),
            }
    return metadata


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
            role, _owner_stage = artifact_role_for_path(path)
            missing.append({
                "path": path,
                "stage": _known_stage(_stage_for_path(path)),
                "previous_sha256": old.get("byte_sha256") or old.get("sha256"),
                "previous_semantic_sha256": old.get("semantic_sha256"),
                "drift_kind": "unresolved_artifact" if role == "unknown" else "missing_artifact",
            })
            continue
        new = current[path]
        previous_byte = old.get("byte_sha256") or old.get("sha256")
        current_byte = new.get("byte_sha256") or new.get("sha256")
        if previous_byte != current_byte:
            previous_semantic = old.get("semantic_sha256")
            current_semantic = new.get("semantic_sha256")
            semantic_known = bool(previous_semantic and current_semantic)
            semantic_changed = not semantic_known or previous_semantic != current_semantic
            previous_evidence = old.get("evidence_sha256")
            current_evidence = new.get("evidence_sha256")
            evidence_changed = not (previous_evidence and current_evidence) or previous_evidence != current_evidence
            role, _owner_stage = artifact_role_for_path(path)
            changed.append({
                "path": path,
                "stage": _known_stage(_stage_for_path(path)),
                "previous_sha256": previous_byte,
                "current_sha256": current_byte,
                "previous_byte_sha256": previous_byte,
                "current_byte_sha256": current_byte,
                "previous_semantic_sha256": previous_semantic,
                "current_semantic_sha256": current_semantic,
                "previous_evidence_sha256": previous_evidence,
                "current_evidence_sha256": current_evidence,
                "semantic_changed": semantic_changed,
                "evidence_changed": evidence_changed,
                "drift_kind": "unresolved_artifact" if role == "unknown" else "semantic_drift" if semantic_changed else "byte_only_drift",
                "previous_semantic_fingerprint": old.get("semantic_fingerprint"),
                "current_semantic_fingerprint": new.get("semantic_fingerprint"),
            })
    for path, new in sorted(current.items()):
        if path not in baseline:
            role, _owner_stage = artifact_role_for_path(path)
            added.append({
                "path": path,
                "stage": _known_stage(_stage_for_path(path)),
                "current_sha256": new.get("byte_sha256") or new.get("sha256"),
                "current_byte_sha256": new.get("byte_sha256") or new.get("sha256"),
                "current_semantic_sha256": new.get("semantic_sha256"),
                "current_evidence_sha256": new.get("evidence_sha256"),
                "current_semantic_fingerprint": new.get("semantic_fingerprint"),
                "drift_kind": "added_artifact" if role != "unknown" else "unresolved_artifact",
            })

    source_stages = sorted(
        {
            item["stage"]
            for item in [*changed, *missing, *added]
            if item.get("stage") not in {"passport"} and item.get("drift_kind") not in {"byte_only_drift", "unresolved_artifact"}
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
    managed_metadata = _managed_change_metadata(project_path)
    drift_items = [
        *drift.get("changed_artifacts", []),
        *drift.get("missing_artifacts", []),
        *drift.get("added_artifacts", []),
    ]
    for item in drift_items:
        path = str(item.get("path") or "")
        role, owner_stage = artifact_role_for_path(path)
        drift_kind = str(item.get("drift_kind") or "semantic_drift")
        ownership = managed_metadata.get(path, {})
        if drift_kind == "byte_only_drift":
            classified_changes.append({
                "path": path,
                "artifact_role": role,
                "change_class": "byte_only_drift",
                "affected_stages": [],
                "scientific_semantics_changed": False,
                "reason": "File bytes changed while the schema-aware semantic identity remained unchanged.",
                **ownership,
            })
            continue
        if drift_kind == "unresolved_artifact":
            classified_changes.append({
                "path": path,
                "artifact_role": role,
                "change_class": "unregistered_artifact",
                "affected_stages": [],
                "scientific_semantics_changed": None,
                "reason": "The artifact is not registered in the role map; it is isolated for manual classification.",
                **ownership,
            })
            continue
        before_identity = item.get("previous_semantic_sha256") or item.get("previous_sha256")
        after_identity = item.get("current_semantic_sha256") or item.get("current_sha256")
        change = classify_change(
            artifact_role=role,
            before=before_identity,
            after=after_identity,
            source_stage=owner_stage,
            declaration={
                "before_semantic_fingerprint": item.get("previous_semantic_fingerprint"),
                "after_semantic_fingerprint": item.get("current_semantic_fingerprint"),
                "before_evidence_fingerprint": item.get("previous_evidence_sha256"),
                "after_evidence_fingerprint": item.get("current_evidence_sha256"),
            },
        )
        impacted = affected_stages(change)
        classified_changes.append({
            "path": path,
            "artifact_role": role,
            "change_class": change.change_class,
            "affected_stages": impacted,
            "scientific_semantics_changed": change.scientific_semantics_changed,
            "presentation_changed": change.presentation_changed,
            "drift_kind": drift_kind,
            "reason": change.reason,
            **ownership,
        })
        for stage in impacted:
            if stage in (state.metadata.get("stages") or {}) and stage not in stale_stages:
                stale_stages.append(stage)

    stale_stages = mark_stages_stale(project_path, stale_stages)

    baseline = load_active_baseline(project_path)
    cycle = load_active_revision_cycle(project_path)
    reconciliation_id = "reconciliation-" + uuid.uuid4().hex
    reconciliation = {
        "schema_version": "dpl.drift_reconciliation.v2",
        "reconciliation_id": reconciliation_id,
        "project_id": state.metadata.get("project_id"),
        "compared_against_baseline_id": (baseline or {}).get("baseline_id"),
        "compared_against_baseline_sha256": (baseline or {}).get("baseline_sha256"),
        "status": "pending_reconciliation",
        "changes": [
            {
                **item,
                "writer_identity": item.get("writer_identity") or "external_or_unknown",
                "expected_by_revision_cycle": bool(
                    cycle
                    and item.get("declared_change_class")
                    and (
                        not cycle.get("allowed_change_classes")
                        or item.get("declared_change_class") in set(cycle.get("allowed_change_classes") or [])
                    )
                ),
                "requires_agent_review": item.get("change_class") in {"unregistered_artifact", "unclassified"},
                "requires_human_confirmation": item.get("change_class") in {
                    "data_change",
                    "method_change",
                    "cohort_change",
                    "cohort_or_split_change",
                    "metric_or_count_change",
                    "metrics_change",
                    "claim_boundary_change",
                    "run_change",
                },
                "recommended_route": "reopen_scientific_stage" if item.get("scientific_semantics_changed") else "rebuild_derived_artifacts",
            }
            for item in classified_changes
        ],
        "revision_cycle_id": (cycle or {}).get("revision_cycle_id"),
        "affected_stages": sorted(stale_stages, key=_stage_sort_key),
        "created_at": utc_now(),
    }
    reconciliation["reconciliation_sha256"] = hashlib.sha256(json.dumps(reconciliation, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    reconciliation_dir = project_path / "review" / "drift" / reconciliation_id
    reconciliation_path = reconciliation_dir / "drift_reconciliation.json"
    atomic_write_json(reconciliation_path, reconciliation)

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
    append_integrity_event(project_path, event, refresh_passport=False)
    requires_reconciliation = any(
        item.get("change_class") not in {"byte_only_drift"}
        for item in classified_changes
    )
    passport = None
    if not requires_reconciliation:
        passport = refresh_project_passport(project_path, event="artifact_drift_byte_only_synced")
    return {
        "status": "reconciliation_required" if requires_reconciliation else "synced",
        "project_path": str(project_path),
        "stale_stages": sorted(stale_stages, key=_stage_sort_key),
        "drift": drift,
        "classified_changes": classified_changes,
        "reconciliation_id": reconciliation_id,
        "reconciliation_path": str(reconciliation_path.resolve()),
        "compared_against_baseline_id": (baseline or {}).get("baseline_id"),
        "passport": str(project_path / PASSPORT_FILES["passport"]),
        "passport_refreshed": passport is not None,
        "artifact_count": (passport or {}).get("artifact_count", 0),
        "preserve_pending_drift": requires_reconciliation,
    }


def reconcile_project_drift(
    project: str | Path,
    *,
    route: str,
    reconciliation_id: str | None = None,
) -> dict[str, Any]:
    """Record a guarded resolution for one external-edit reconciliation packet."""

    if route not in {"adopt_as_expected_change", "rebuild_derived_artifacts", "reopen_scientific_stage"}:
        raise ArtifactDriftError(f"Unsupported reconciliation route: {route}")
    root = project_root(project)
    candidates = []
    if reconciliation_id:
        candidates = [root / "review" / "drift" / reconciliation_id / "drift_reconciliation.json"]
    else:
        candidates = sorted((root / "review" / "drift").glob("*/drift_reconciliation.json"), key=lambda path: path.stat().st_mtime if path.exists() else 0)
    if not candidates or not candidates[-1].is_file():
        raise ArtifactDriftError("No drift reconciliation packet is available.")
    packet_path = candidates[-1]
    try:
        packet = json.loads(packet_path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise ArtifactDriftError(f"Invalid reconciliation packet: {packet_path}") from exc
    if packet.get("status") != "pending_reconciliation":
        raise ArtifactDriftError("Drift reconciliation packet is no longer pending.")
    existing_resolution = packet_path.parent / "resolution_receipt.json"
    if existing_resolution.is_file():
        raise ArtifactDriftError("Drift reconciliation packet already has a resolution receipt.")
    changes = [item for item in packet.get("changes") or [] if isinstance(item, dict)]
    semantic_changes = [item for item in changes if item.get("scientific_semantics_changed") is True]
    baseline = load_active_baseline(root) or {}
    # v0.41 stores a narrow canonical scientific set separately from the
    # audit snapshot.  Restoration detection is an audit operation, so it may
    # use the latter without turning all project files into scientific facts.
    baseline_hashes = baseline.get("audit_artifact_hashes") or baseline.get("artifact_hashes") or {}
    current_artifacts = {
        str(item.get("path") or ""): item
        for item in collect_artifacts(root)
        if item.get("path")
    }
    baseline_restorations = [
        item
        for item in semantic_changes
        if (
            str(baseline_hashes.get(str(item.get("path") or "")) or "")
            and str(baseline_hashes.get(str(item.get("path") or "")) or "")
            in {
                str(current_artifacts.get(str(item.get("path") or ""), {}).get("evidence_sha256") or ""),
                str(current_artifacts.get(str(item.get("path") or ""), {}).get("semantic_sha256") or ""),
                str(
                    current_artifacts.get(str(item.get("path") or ""), {}).get("byte_sha256")
                    or current_artifacts.get(str(item.get("path") or ""), {}).get("sha256")
                    or ""
                ),
            }
        )
    ]
    unresolved_semantic_changes = [
        item for item in semantic_changes if item not in baseline_restorations
    ]
    if route == "rebuild_derived_artifacts" and unresolved_semantic_changes:
        raise ArtifactDriftError("Derived-artifact rebuild cannot resolve data, method, run, cohort, metric, or claim drift.")
    cycle = load_active_revision_cycle(root)
    if route == "adopt_as_expected_change":
        if not cycle:
            raise ArtifactDriftError("Adopting an external change requires an open revision cycle with a declared scope.")
        allowed = set(cycle.get("allowed_change_classes") or [])
        undeclared = [
            item for item in changes
            if item.get("scientific_semantics_changed") is True
            and (not item.get("change_class") or (allowed and item.get("change_class") not in allowed))
        ]
        if undeclared:
            raise ArtifactDriftError("External scientific changes fall outside the active revision-cycle change-class scope.")
    resolution = {
        "schema_version": "dpl.drift_reconciliation_resolution.v1",
        "reconciliation_id": packet.get("reconciliation_id"),
        "reconciliation_sha256": packet.get("reconciliation_sha256"),
        "route": route,
        "status": "resolved" if route != "reopen_scientific_stage" else "reopen_required",
        "requires_human_confirmation": bool(semantic_changes) or route == "reopen_scientific_stage",
        "revision_cycle_id": (cycle or {}).get("revision_cycle_id"),
        "baseline_restored_paths": [str(item.get("path") or "") for item in baseline_restorations],
        "created_at": utc_now(),
    }
    resolution["resolution_sha256"] = hashlib.sha256(json.dumps(resolution, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    resolution_path = packet_path.parent / "resolution_receipt.json"
    atomic_write_json(resolution_path, resolution)
    passport = refresh_project_passport(root, event=f"drift_reconciled:{route}")
    append_integrity_event(
        root,
        {
            "kind": "artifact_drift_reconciled",
            "recorded_at": utc_now(),
            "reconciliation_id": packet.get("reconciliation_id"),
            "route": route,
            "resolution_receipt": str(resolution_path.relative_to(root).as_posix()),
            "compared_against_baseline_id": packet.get("compared_against_baseline_id"),
        },
    )
    return {
        "status": resolution["status"],
        "project_path": str(root),
        "route": route,
        "reconciliation_id": packet.get("reconciliation_id"),
        "resolution_path": str(resolution_path.resolve()),
        "stale_stages": packet.get("affected_stages") or [],
        "passport": str(root / PASSPORT_FILES["passport"]),
        "artifact_count": passport.get("artifact_count", 0),
    }


def handle_stale_sync_error(exc: Exception) -> dict[str, str]:
    if isinstance(exc, (ArtifactDriftError, PassportError, ProjectStateError)):
        return {"status": "error", "message": str(exc)}
    return {"status": "error", "message": str(exc)}
