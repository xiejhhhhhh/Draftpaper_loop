"""Persist the complete scope of one core-evidence confirmation round."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from pathlib import Path
from typing import Any

from .artifact_identity import canonical_json
from .confirmation_continuity import latest_valid_user_receipt
from .passport import (
    append_checkpoint_event,
    append_checkpoint_batch_association,
    checkpoint_batch_association,
    load_project_passport,
    overlay_checkpoint_batch_association,
    project_root,
    read_jsonl,
    refresh_project_passport,
    utc_now,
)
from .revision_cycle import (
    ACTIVE_POINTER,
    BATCH_REVISION_SCHEMA,
    REVISION_DIR,
    _seal_revision_cycle_record,
    begin_revision_cycle,
    load_active_revision_cycle,
)
from .state_kernel import atomic_write_json, file_lock


class CoreEvidenceBatchError(RuntimeError):
    """The requested confirmation scope cannot be safely recorded."""


CORE_EVIDENCE_OPERATION_LOCK = ".draftpaper/core_evidence_batch_operation"
_EFFECT_CLASSES = {"scientific", "binding", "presentation", "unknown"}
_TASK_STATUSES = {"pending", "running", "completed", "blocked", "deferred", "cancelled"}
_TASK_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
_LIST_FIELDS = ("depends_on", "evidence_refs", "expected_artifacts", "completion_checks")
_SCOPE_FIELDS = (
    "task_id", "title_zh", "title_en", "checkpoint_scope", "origin_ref",
    "effect_class", "required_before_publication", "depends_on", "evidence_refs",
    "expected_artifacts", "completion_checks",
)


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _project_relative(value: str) -> str:
    relative = value.replace("\\", "/").strip()
    if not relative or relative.startswith("/") or ":" in relative or any(part in {".", "..", ""} for part in relative.split("/")):
        raise CoreEvidenceBatchError(f"Invalid project-relative artifact path: {value!r}.")
    return relative


def _normalized_task(value: dict[str, Any]) -> dict[str, Any]:
    task = dict(value)
    identifier = task.get("task_id")
    if not isinstance(identifier, str) or not _TASK_ID.fullmatch(identifier):
        raise CoreEvidenceBatchError("Each core-evidence task needs a stable task_id.")
    if task.get("checkpoint_scope") != "core_evidence":
        raise CoreEvidenceBatchError(f"Task {identifier} has an unclassified checkpoint scope.")
    for field in ("title_zh", "title_en", "origin_ref"):
        if not isinstance(task.get(field), str) or not task[field].strip():
            raise CoreEvidenceBatchError(f"Task {identifier} is missing {field}.")
    if task.get("effect_class") not in _EFFECT_CLASSES:
        raise CoreEvidenceBatchError(f"Task {identifier} has an unknown effect class.")
    if not isinstance(task.get("required_before_publication"), bool):
        raise CoreEvidenceBatchError(f"Task {identifier} must declare required_before_publication.")
    if task["effect_class"] in {"scientific", "binding", "unknown"} and not task["required_before_publication"]:
        raise CoreEvidenceBatchError(f"Task {identifier} must set required_before_publication for evidence-affecting work.")
    if task.get("status") not in _TASK_STATUSES:
        raise CoreEvidenceBatchError(f"Task {identifier} has an invalid status.")
    for field in _LIST_FIELDS:
        items = task.get(field)
        if not isinstance(items, list) or not all(isinstance(item, str) and item.strip() for item in items):
            raise CoreEvidenceBatchError(f"Task {identifier} needs a string list for {field}.")
        task[field] = sorted(set(items)) if field != "depends_on" else sorted(set(items))
    task["expected_artifacts"] = [_project_relative(path) for path in task["expected_artifacts"]]
    task["evidence_refs"] = [_project_relative(path) for path in task["evidence_refs"]]
    if task["required_before_publication"] and not (task["expected_artifacts"] or task["evidence_refs"]):
        raise CoreEvidenceBatchError(f"Required task {identifier} has no evidence or artifact binding.")
    receipts = task.get("completion_receipts")
    if not isinstance(receipts, list) or not all(isinstance(item, dict) for item in receipts):
        raise CoreEvidenceBatchError(f"Task {identifier} needs completion_receipts as a list.")
    return task


def _validate_dependencies(tasks: list[dict[str, Any]]) -> None:
    all_ids = {task["task_id"] for task in tasks}
    dependencies = {task["task_id"]: task["depends_on"] for task in tasks}
    if len(all_ids) != len(tasks):
        raise CoreEvidenceBatchError("Duplicate core-evidence task IDs are not allowed.")
    for identifier, requirements in dependencies.items():
        if set(requirements) - all_ids:
            raise CoreEvidenceBatchError(f"Task {identifier} depends on an unrecorded task.")
    visited: set[str] = set()
    active: set[str] = set()

    def visit(identifier: str) -> None:
        if identifier in active:
            raise CoreEvidenceBatchError("Core-evidence task dependency cycle detected.")
        if identifier in visited:
            return
        active.add(identifier)
        for predecessor in dependencies[identifier]:
            visit(predecessor)
        active.remove(identifier)
        visited.add(identifier)

    for identifier in dependencies:
        visit(identifier)


def _incoming_tasks(changes_path: str | Path | None) -> list[dict[str, Any]]:
    if changes_path is None:
        return []
    try:
        payload = json.loads(Path(changes_path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise CoreEvidenceBatchError("The core-evidence changes file cannot be read as JSON.") from exc
    rows = payload.get("tasks") if isinstance(payload, dict) else None
    if not isinstance(rows, list) or not all(isinstance(item, dict) for item in rows):
        raise CoreEvidenceBatchError("The changes file must contain an array of task objects.")
    return rows


def _write_revision(root: Path, revision: dict[str, Any]) -> Path:
    filename = (
        f"{revision['revision_cycle_id']}-batch-{revision['revision_generation']:04d}"
        f"-{revision['revision_cycle_sha256'][:12]}.json"
    )
    path = root / REVISION_DIR / filename
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8-sig"))
        if existing != revision:
            raise CoreEvidenceBatchError("An immutable revision-cycle record would be overwritten.")
    else:
        atomic_write_json(path, revision)
    atomic_write_json(
        root / ACTIVE_POINTER,
        {
            "schema_version": "dpl.active_revision_cycle.v1",
            "revision_cycle_id": revision["revision_cycle_id"],
            "revision_cycle_sha256": revision["revision_cycle_sha256"],
            "path": path.relative_to(root).as_posix(),
            "updated_at": utc_now(),
        },
    )
    return path


def load_core_evidence_batch(project: str | Path) -> dict[str, Any] | None:
    cycle = load_active_revision_cycle(project)
    if not cycle or cycle.get("schema_version") != BATCH_REVISION_SCHEMA or cycle.get("status") != "open":
        return None
    batch = cycle.get("evidence_batch")
    return dict(batch) if isinstance(batch, dict) else None


def core_evidence_batch_review(project: str | Path, readiness: dict[str, Any]) -> dict[str, Any]:
    """A compact human-facing projection of the same frozen batch, not another task ledger."""
    cycle = load_active_revision_cycle(project) or {}
    batch = load_core_evidence_batch(project) or {}
    if not readiness.get("publishable") or batch.get("batch_id") != readiness.get("batch_id"):
        raise CoreEvidenceBatchError("Only a current frozen core-evidence batch can be presented for confirmation.")
    tasks = [
        {
            "task_id": task["task_id"],
            "title_zh": task["title_zh"],
            "title_en": task["title_en"],
            "effect_class": task["effect_class"],
            "evidence_refs": task["evidence_refs"],
            "expected_artifacts": task["expected_artifacts"],
        }
        for task in cycle.get("pending_tasks") or []
        if isinstance(task, dict) and task.get("checkpoint_scope") == "core_evidence"
        and task.get("required_before_publication")
    ]
    count = len(tasks)
    return {
        "batch_id": batch["batch_id"],
        "base_decision_receipt_id": batch.get("base_decision_receipt_id"),
        "scope_sha256": readiness["scope_sha256"],
        "input_manifest_sha256": readiness["input_manifest_sha256"],
        "completed_task_count": count,
        "summary_zh": f"本轮已完成并核验 {count} 项核心证据相关修订；下面列出全部已登记工作及其证据来源。请结合科学事实、图表和论断边界确认整轮结果。",
        "summary_en": f"This round completed and checked {count} core-evidence tasks. All registered work and its evidence sources are listed below; review the scientific facts, figures, and claim boundaries together.",
        "tasks": tasks,
    }


def _supersede_old_request(
    root: Path,
    batch: dict[str, Any],
    *,
    source_cycle_sha256: str | None = None,
) -> None:
    awaiting = load_project_passport(root).get("awaiting_checkpoint") or {}
    if awaiting.get("stage") != "core_evidence":
        return
    unscoped_legacy_request = not awaiting.get("batch_id") and not awaiting.get("scope_sha256")
    if awaiting.get("batch_id") != batch.get("batch_id") and not unscoped_legacy_request:
        return
    if awaiting.get("scope_sha256") == batch.get("scope_sha256") and batch.get("frozen_candidate_ref"):
        return
    old_hash = str(awaiting.get("hash") or "")
    if not old_hash:
        return
    events = read_jsonl(root / "checkpoint_ledger.jsonl")
    if any(row.get("kind") == "checkpoint_superseded" and row.get("supersedes_hash") == old_hash for row in events):
        refresh_project_passport(root, event="checkpoint_superseded_recovery")
        return
    reason = (
        "legacy_unscoped_checkpoint_superseded_after_explicit_scope_registration"
        if unscoped_legacy_request
        else "new_work_discovered_before_core_evidence_confirmation"
    )
    append_checkpoint_event(root, {
        "kind": "checkpoint_superseded",
        "supersedes_hash": old_hash,
        "batch_id": batch["batch_id"],
        "new_scope_sha256": batch["scope_sha256"],
        "reason": reason,
        "superseded_scope_status": "unscoped" if unscoped_legacy_request else "batch_scoped",
        "old_request_reusable": False,
        "source_cycle_sha256": source_cycle_sha256,
        "created_at": utc_now(),
    })


def mark_core_evidence_batch_awaiting(project: str | Path, *, checkpoint_hash: str) -> dict[str, Any]:
    root = project_root(project)
    cycle = load_active_revision_cycle(root) or {}
    batch = load_core_evidence_batch(root) or {}
    awaiting = load_project_passport(root).get("awaiting_checkpoint") or {}
    if awaiting.get("hash") != checkpoint_hash or awaiting.get("batch_id") != batch.get("batch_id"):
        raise CoreEvidenceBatchError("The published checkpoint is not the active frozen batch request.")
    if batch.get("phase") == "awaiting_decision" and batch.get("request_id") == checkpoint_hash:
        return batch
    if batch.get("phase") != "ready_for_review" or batch.get("request_id"):
        raise CoreEvidenceBatchError("Core-evidence batch is not ready to enter awaiting_decision.")
    updated = dict(cycle)
    updated["evidence_batch"] = {**batch, "phase": "awaiting_decision", "request_id": checkpoint_hash}
    updated["review_status"] = "awaiting_decision"
    updated["revision_generation"] = int(cycle["revision_generation"]) + 1
    updated["updated_at"] = utc_now()
    updated = _seal_revision_cycle_record(updated)
    _write_revision(root, updated)
    return updated["evidence_batch"]


def resolve_core_evidence_batch(
    project: str | Path, *, checkpoint_hash: str, receipt_ref: str, receipt_id: str,
) -> dict[str, Any]:
    root = project_root(project)
    cycle = load_active_revision_cycle(root) or {}
    batch = load_core_evidence_batch(root) or {}
    if batch.get("phase") == "closed" and batch.get("request_id") == checkpoint_hash:
        return batch
    if batch.get("phase") != "awaiting_decision" or batch.get("request_id") != checkpoint_hash:
        raise CoreEvidenceBatchError("The resolved decision does not belong to the awaiting batch.")
    relative = _project_relative(receipt_ref)
    receipt_path = (root / relative).resolve()
    try:
        receipt_path.relative_to(root.resolve())
        receipt = json.loads(receipt_path.read_text(encoding="utf-8-sig"))
    except (ValueError, OSError) as exc:
        raise CoreEvidenceBatchError("The batch resolution receipt is unavailable or outside the project.") from exc
    if receipt.get("receipt_id") != receipt_id or (
        receipt.get("checkpoint_hash") not in {None, checkpoint_hash}
    ):
        raise CoreEvidenceBatchError("The batch resolution receipt does not bind this decision.")
    events = read_jsonl(root / "checkpoint_ledger.jsonl")
    if not any(row.get("kind") == "resume" and row.get("consumes_hash") == checkpoint_hash for row in events):
        raise CoreEvidenceBatchError("The checkpoint has not been consumed.")
    updated = dict(cycle)
    updated["evidence_batch"] = {
        **batch, "phase": "closed", "resolution_receipt_ref": relative,
    }
    updated["review_status"] = "drafting"
    updated["revision_generation"] = int(cycle["revision_generation"]) + 1
    updated["updated_at"] = utc_now()
    updated = _seal_revision_cycle_record(updated)
    _write_revision(root, updated)
    return updated["evidence_batch"]


def prepare_core_evidence_batch(
    project: str | Path, *, changes_path: str | Path | None = None,
) -> dict[str, Any]:
    root = project_root(project)
    with file_lock(root / CORE_EVIDENCE_OPERATION_LOCK):
        return _prepare_core_evidence_batch(root, changes_path=changes_path)


def _prepare_core_evidence_batch(
    project: str | Path, *, changes_path: str | Path | None = None,
    expected_legacy_source_sha256: str | None = None,
) -> dict[str, Any]:
    root = project_root(project)
    incoming = _incoming_tasks(changes_path)
    incoming_core: dict[str, dict[str, Any]] = {}
    incoming_other: dict[tuple[str, str], dict[str, Any]] = {}
    for row in incoming:
        scope = row.get("checkpoint_scope")
        if not isinstance(scope, str):
            raise CoreEvidenceBatchError("Every imported revision task needs an explicit checkpoint scope.")
        if scope == "core_evidence":
            normalized = _normalized_task(row)
            identifier = normalized["task_id"]
            if identifier in incoming_core and incoming_core[identifier] != normalized:
                raise CoreEvidenceBatchError(f"Conflicting duplicate core-evidence task ID: {identifier}.")
            incoming_core[identifier] = normalized
        else:
            task_id = row.get("task_id")
            identity = str(task_id) if isinstance(task_id, str) and task_id.strip() else _digest(row)
            key = (scope, identity)
            if key in incoming_other and incoming_other[key] != row:
                raise CoreEvidenceBatchError(f"Conflicting duplicate task identity in scope {scope}: {identity}.")
            incoming_other[key] = row
    active = load_active_revision_cycle(root)
    if active and active.get("status") != "open":
        active = None
    source_cycle_sha256 = str((active or {}).get("revision_cycle_sha256") or "") or None
    migrating_legacy = bool(active and active.get("migration_status") == "legacy_unverified")
    if migrating_legacy:
        if expected_legacy_source_sha256 != active.get("migration_source_sha256"):
            raise CoreEvidenceBatchError("Legacy scope migration requires the exact source-cycle SHA-256 from the shadow report.")
        source = active.get("legacy_source_record") or {}
        if "pending_tasks" not in source or "requested_changes" not in source:
            raise CoreEvidenceBatchError("Legacy scope is incomplete; shadow migration must stop for manual scope recovery.")
        if source.get("pending_tasks") or source.get("requested_changes"):
            raise CoreEvidenceBatchError("Legacy revision work is still recorded; explicitly reconcile or close that scope before C3 batch migration.")
        if not incoming:
            raise CoreEvidenceBatchError("Legacy migration needs an explicit new core-evidence task manifest.")
    previous_batch = (active or {}).get("evidence_batch") or {}
    previous_batch_closed = previous_batch.get("phase") in {"closed", "abandoned"}
    old_tasks = []
    if active and not migrating_legacy:
        old_tasks = [
            row for row in active.get("pending_tasks") or []
            if not (
                previous_batch_closed
                and isinstance(row, dict)
                and row.get("checkpoint_scope") == "core_evidence"
            )
        ]
    merged: dict[str, dict[str, Any]] = {}
    other_scoped: dict[tuple[str, str], dict[str, Any]] = {}
    for row in [*old_tasks, *incoming]:
        if not isinstance(row, dict) or not isinstance(row.get("checkpoint_scope"), str):
            raise CoreEvidenceBatchError("An existing revision task has an unclassified checkpoint scope.")
        if row["checkpoint_scope"] != "core_evidence":
            identifier = row.get("task_id")
            identity = str(identifier) if isinstance(identifier, str) and identifier.strip() else _digest(row)
            other_scoped[(row["checkpoint_scope"], identity)] = row
            continue
        if not isinstance(row.get("task_id"), str):
            raise CoreEvidenceBatchError("An existing core-evidence task has no task ID.")
        merged[row["task_id"]] = row
    tasks = [_normalized_task(merged[key]) for key in sorted(merged)]
    if not tasks:
        raise CoreEvidenceBatchError("The core-evidence batch needs at least one scoped task.")
    cycle_tasks = [other_scoped[key] for key in sorted(other_scoped)] + tasks
    _validate_dependencies(tasks)
    scope_hash = _digest([{field: task[field] for field in _SCOPE_FIELDS} for task in tasks])
    if active and previous_batch.get("phase") not in {"closed", "abandoned"}:
        active_core_tasks = [
            task for task in active.get("pending_tasks") or []
            if isinstance(task, dict) and task.get("checkpoint_scope") == "core_evidence"
        ]
        if tasks == active_core_tasks and scope_hash == previous_batch.get("scope_sha256"):
            association = _pending_legacy_association(root, active)
            if _association_matches_batch(association, previous_batch):
                _record_legacy_batch_association(root, association)
                if cycle_tasks != active.get("pending_tasks"):
                    updated = dict(active)
                    updated["pending_tasks"] = cycle_tasks
                    updated["revision_generation"] = int(active.get("revision_generation") or 1) + 1
                    updated["updated_at"] = utc_now()
                    updated = _seal_revision_cycle_record(updated)
                    path = _write_revision(root, updated)
                    return {
                        "status": "associated_existing_request",
                        "project_path": str(root),
                        "revision_cycle": updated,
                        "revision_cycle_path": str(path.resolve()),
                        "batch": previous_batch,
                        "other_scope_tasks_updated": True,
                    }
                return {
                    "status": "associated_existing_request",
                    "project_path": str(root),
                    "revision_cycle": active,
                    "batch": previous_batch,
                }
            if cycle_tasks != active.get("pending_tasks"):
                updated = dict(active)
                updated["pending_tasks"] = cycle_tasks
                updated["revision_generation"] = int(active.get("revision_generation") or 1) + 1
                updated["updated_at"] = utc_now()
                updated = _seal_revision_cycle_record(updated)
                path = _write_revision(root, updated)
                return {
                    "status": "existing",
                    "project_path": str(root),
                    "revision_cycle": updated,
                    "revision_cycle_path": str(path.resolve()),
                    "batch": previous_batch,
                    "other_scope_tasks_updated": True,
                }
            _supersede_old_request(root, previous_batch, source_cycle_sha256=source_cycle_sha256)
            return {"status": "existing", "project_path": str(root), "revision_cycle": active, "batch": previous_batch}
    association: dict[str, Any] | None = None
    if active and not migrating_legacy and not previous_batch:
        association = _pending_legacy_association(root, active)
        if not _association_matches_scope(association, scope_hash):
            association = None
    if active is None:
        active = begin_revision_cycle(
            root, reason="core_evidence_batch", scope="core_evidence", pending_tasks=cycle_tasks,
            expected_artifacts=sorted({path for task in tasks for path in task["expected_artifacts"]}),
            started_by="user" if incoming else "system",
        )["revision_cycle"]
    if association:
        batch = {
            "batch_id": association["batch_id"],
            "base_decision_receipt_id": association.get("base_decision_receipt_id"),
            "base_snapshot_id": association.get("base_snapshot_id"),
            "scope_sha256": association["scope_sha256"],
            "phase": "awaiting_decision",
            "finalization_requested": True,
            "frozen_candidate_ref": association["frozen_candidate_ref"],
            "request_id": association["request_id"],
            "resolution_receipt_ref": None,
        }
    elif previous_batch and previous_batch.get("phase") not in {"closed", "abandoned"}:
        batch = {
            **previous_batch,
            "scope_sha256": scope_hash,
            "phase": "collecting",
            "finalization_requested": False,
            "frozen_candidate_ref": None,
            "request_id": None,
        }
    else:
        previous = latest_valid_user_receipt(root, checkpoint_type="core_evidence")
        promoted_path = root / "results" / "promoted_evidence_snapshot.json"
        promoted = json.loads(promoted_path.read_text(encoding="utf-8-sig")) if promoted_path.is_file() else {}
        batch = {
            "batch_id": f"core-batch-{uuid.uuid4().hex}",
            "base_decision_receipt_id": (previous or {}).get("receipt_id"),
            "base_snapshot_id": promoted.get("snapshot_id"),
            "scope_sha256": scope_hash,
            "phase": "collecting",
            "finalization_requested": False,
            "frozen_candidate_ref": None,
            "request_id": None,
            "resolution_receipt_ref": None,
        }
    revision = dict(active)
    revision["schema_version"] = BATCH_REVISION_SCHEMA
    if migrating_legacy:
        revision["migration_status"] = "explicitly_scoped"
    revision["pending_tasks"] = cycle_tasks
    revision["evidence_batch"] = batch
    revision["review_status"] = "awaiting_decision" if association else "drafting"
    if previous_batch.get("phase") in {"ready_for_review", "awaiting_decision", "closed", "abandoned"}:
        revision["candidate_generation"] = int(active.get("candidate_generation") or 1) + 1
    revision["revision_generation"] = int(active.get("revision_generation") or 1) + 1
    revision["updated_at"] = utc_now()
    revision = _seal_revision_cycle_record(revision)
    if association:
        _record_legacy_batch_association(root, association)
    path = _write_revision(root, revision)
    if not association:
        _supersede_old_request(root, batch, source_cycle_sha256=source_cycle_sha256)
    return {
        "status": "associated_existing_request" if association else "prepared",
        "project_path": str(root),
        "revision_cycle": revision,
        "revision_cycle_path": str(path.resolve()),
        "batch": batch,
    }


def _legacy_runtime_identity_shadow(root: Path) -> dict[str, Any]:
    from .runtime_handshake import IDENTITY_FIELDS, RUNTIME_LOCK, SCHEMA_VERSION

    path = root / RUNTIME_LOCK
    next_command = f'draftpaper session-preflight --project "{root}"'
    if not path.is_file():
        return {
            "status": "unknown",
            "reason": "runtime_lock_missing",
            "path": str(path),
            "next_command": next_command,
        }
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        payload = None
    if not isinstance(payload, dict) or payload.get("schema_version") != SCHEMA_VERSION:
        return {
            "status": "unknown",
            "reason": "runtime_lock_invalid_or_unsupported",
            "path": str(path),
            "next_command": next_command,
        }
    missing = sorted(
        field for field in IDENTITY_FIELDS
        if not isinstance(payload.get(field), str) or not payload[field].strip()
    )
    if missing:
        return {
            "status": "unknown",
            "reason": "runtime_identity_fields_missing",
            "missing_fields": missing,
            "path": str(path),
            "next_command": next_command,
        }
    return {
        "status": "recorded_unverified",
        "reason": "runtime_lock_present_but_not_compared_to_current_runtime",
        "path": str(path),
        "next_command": next_command,
    }


def _shadow_task_scope(cycle: dict[str, Any], *, legacy: bool, source: dict[str, Any]) -> dict[str, Any]:
    owner = source if legacy else cycle
    owner_name = "legacy_source_record" if legacy else "revision_cycle"
    if "pending_tasks" not in owner:
        return {
            "status": "unknown",
            "source": f"{owner_name}.pending_tasks",
            "task_count": None,
            "tasks": [],
            "missing_fields": ["pending_tasks"],
        }
    raw_tasks = owner.get("pending_tasks")
    if not isinstance(raw_tasks, list):
        return {
            "status": "invalid",
            "source": f"{owner_name}.pending_tasks",
            "task_count": None,
            "tasks": [],
            "missing_fields": [],
            "reason": "pending_tasks_is_not_a_list",
        }
    required = (
        "task_id", "checkpoint_scope", "effect_class", "required_before_publication",
        "status", "evidence_refs", "expected_artifacts", "completion_receipts",
    )
    tasks: list[dict[str, Any]] = []
    missing_union: set[str] = set()
    for index, item in enumerate(raw_tasks):
        if not isinstance(item, dict):
            tasks.append({"index": index, "task_id": None, "status": "unknown", "missing_fields": list(required)})
            missing_union.update(required)
            continue
        missing = sorted(field for field in required if field not in item)
        missing_union.update(missing)
        tasks.append({
            "index": index,
            "task_id": item.get("task_id") if isinstance(item.get("task_id"), str) else None,
            "checkpoint_scope": item.get("checkpoint_scope") if isinstance(item.get("checkpoint_scope"), str) else None,
            "effect_class": item.get("effect_class") if isinstance(item.get("effect_class"), str) else None,
            "status": item.get("status") if isinstance(item.get("status"), str) else "unknown",
            "missing_fields": missing,
        })
    return {
        "status": "known" if not missing_union else "incomplete",
        "source": f"{owner_name}.pending_tasks",
        "task_count": len(raw_tasks),
        "tasks": tasks,
        "missing_fields": sorted(missing_union),
    }


def _shadow_candidate(root: Path, cycle: dict[str, Any]) -> dict[str, Any]:
    batch = cycle.get("evidence_batch") if isinstance(cycle.get("evidence_batch"), dict) else {}
    reference = batch.get("frozen_candidate_ref")
    base = {
        "batch_id": batch.get("batch_id"),
        "phase": batch.get("phase"),
        "candidate_generation": cycle.get("candidate_generation"),
        "reuse_eligible": False,
    }
    if not isinstance(reference, str) or not reference.strip():
        return {**base, "status": "not_registered", "path": None}
    try:
        relative = _project_relative(reference)
        path = (root / relative).resolve()
        path.relative_to(root.resolve())
    except (CoreEvidenceBatchError, OSError, ValueError):
        return {**base, "status": "invalid_path", "path": None}
    if not path.is_file():
        return {**base, "status": "missing", "path": relative}
    try:
        if path.stat().st_size > 1024 * 1024:
            return {**base, "status": "oversized", "path": relative}
        raw = path.read_bytes()
        payload = json.loads(raw.decode("utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {**base, "status": "invalid", "path": relative}
    if not isinstance(payload, dict):
        return {**base, "status": "invalid", "path": relative}
    expected = {
        "batch_id": batch.get("batch_id"),
        "scope_sha256": batch.get("scope_sha256"),
        "candidate_generation": cycle.get("candidate_generation"),
    }
    missing = sorted(key for key, value in expected.items() if value is None)
    mismatched = sorted(key for key, value in expected.items() if value is not None and payload.get(key) != value)
    status = "identity_incomplete" if missing else ("identity_mismatch" if mismatched else "identity_match")
    reusable = status == "identity_match" and batch.get("phase") in {"ready_for_review", "awaiting_decision"}
    return {
        **base,
        "status": status,
        "path": relative,
        "file_sha256": hashlib.sha256(raw).hexdigest(),
        "input_manifest_sha256": payload.get("input_manifest_sha256"),
        "missing_identity_fields": missing,
        "mismatched_identity_fields": mismatched,
        "reuse_eligible": reusable,
    }


def _legacy_request_association(
    root: Path,
    cycle: dict[str, Any],
    *,
    checkpoint_hash: str,
    checkpoint_record: dict[str, Any] | None,
    summary: dict[str, Any],
    request: dict[str, Any],
    package_valid: bool,
) -> dict[str, Any]:
    """Prove whether a complete old package can retain its exact pending request."""
    blockers: list[str] = []
    if not package_valid:
        blockers.append("checkpoint_package_not_valid")
    if not checkpoint_record or checkpoint_record.get("stage") != "core_evidence":
        blockers.append("checkpoint_record_not_core_evidence")
    if summary.get("review_state") != "confirmable" or not request.get("confirmation_command"):
        blockers.append("package_has_no_authorized_pending_decision")
    batch_review = summary.get("core_evidence_batch")
    batch_review = batch_review if isinstance(batch_review, dict) else {}
    batch_id = batch_review.get("batch_id")
    scope_sha256 = batch_review.get("scope_sha256")
    input_manifest_sha256 = batch_review.get("input_manifest_sha256")
    if not all(isinstance(value, str) and value for value in (batch_id, scope_sha256, input_manifest_sha256)):
        blockers.append("package_batch_identity_incomplete")
    if request.get("batch_id") != batch_id or request.get("scope_sha256") != scope_sha256 or request.get("input_manifest_sha256") != input_manifest_sha256:
        blockers.append("confirmation_request_batch_identity_mismatch")

    raw_tasks = cycle.get("pending_tasks")
    normalized_tasks: list[dict[str, Any]] = []
    if not isinstance(raw_tasks, list):
        blockers.append("revision_task_scope_unknown")
    else:
        try:
            normalized_tasks = [
                _normalized_task(item)
                for item in raw_tasks
                if isinstance(item, dict) and item.get("checkpoint_scope") == "core_evidence"
            ]
            if any(not isinstance(item, dict) for item in raw_tasks):
                blockers.append("revision_task_scope_contains_unclassified_rows")
            _validate_dependencies(normalized_tasks)
        except CoreEvidenceBatchError:
            blockers.append("revision_task_scope_incomplete")
    computed_scope = _digest([
        {field: task[field] for field in _SCOPE_FIELDS}
        for task in sorted(normalized_tasks, key=lambda item: item["task_id"])
    ]) if normalized_tasks else None
    if computed_scope != scope_sha256:
        blockers.append("package_scope_does_not_match_revision_tasks")
    expected_display_tasks = [
        {
            "task_id": task["task_id"],
            "title_zh": task["title_zh"],
            "title_en": task["title_en"],
            "effect_class": task["effect_class"],
            "evidence_refs": task["evidence_refs"],
            "expected_artifacts": task["expected_artifacts"],
        }
        for task in sorted(normalized_tasks, key=lambda item: item["task_id"])
        if task["required_before_publication"]
    ]
    if batch_review.get("tasks") != expected_display_tasks or batch_review.get("completed_task_count") != len(expected_display_tasks):
        blockers.append("confirmation_package_task_inventory_mismatch")

    generation = cycle.get("candidate_generation")
    batch = cycle.get("evidence_batch") if isinstance(cycle.get("evidence_batch"), dict) else {}
    reference = batch.get("frozen_candidate_ref")
    if not reference and isinstance(generation, int) and generation > 0 and cycle.get("revision_cycle_id"):
        reference = (
            Path("review") / "revision_reconciliation" / str(cycle["revision_cycle_id"])
            / f"generation-{generation:04d}" / "core_evidence_readiness.json"
        ).as_posix()
    candidate_payload: dict[str, Any] = {}
    candidate_path: Path | None = None
    candidate_file_sha256: str | None = None
    try:
        if not isinstance(reference, str) or not reference:
            raise ValueError("candidate_reference_missing")
        candidate_path = (root / _project_relative(reference)).resolve()
        candidate_path.relative_to(root.resolve())
        if not candidate_path.is_file() or candidate_path.stat().st_size > 1024 * 1024:
            raise ValueError("candidate_file_missing_or_oversized")
        candidate_bytes = candidate_path.read_bytes()
        candidate_file_sha256 = hashlib.sha256(candidate_bytes).hexdigest()
        value = json.loads(candidate_bytes.decode("utf-8-sig"))
        candidate_payload = value if isinstance(value, dict) else {}
    except (CoreEvidenceBatchError, OSError, UnicodeError, ValueError, TypeError):
        blockers.append("frozen_candidate_unavailable")
    expected_candidate = {
        "batch_id": batch_id,
        "scope_sha256": scope_sha256,
        "input_manifest_sha256": input_manifest_sha256,
        "candidate_generation": generation,
    }
    if any(candidate_payload.get(key) != value for key, value in expected_candidate.items()):
        blockers.append("frozen_candidate_identity_mismatch")
    if candidate_payload.get("status") != "ready" or candidate_payload.get("publishable") is not True:
        blockers.append("frozen_candidate_not_ready")
    if candidate_file_sha256 is None:
        blockers.append("frozen_candidate_hash_unavailable")

    return {
        "eligible": not blockers,
        "blockers": sorted(set(blockers)),
        "checkpoint_hash": checkpoint_hash,
        "checkpoint_package_sha256": summary.get("stage_summary_sha256"),
        "source_cycle_sha256": cycle.get("revision_cycle_sha256"),
        "batch_id": batch_id,
        "base_decision_receipt_id": batch_review.get("base_decision_receipt_id"),
        "base_snapshot_id": batch.get("base_snapshot_id") or cycle.get("parent_baseline_id"),
        "scope_sha256": scope_sha256,
        "input_manifest_sha256": input_manifest_sha256,
        "candidate_generation": generation,
        "frozen_candidate_ref": reference,
        "request_id": checkpoint_hash,
        "candidate_file_sha256": candidate_file_sha256,
        "package_relative_path": str(checkpoint_record.get("stage_summary_json") or "") if checkpoint_record else None,
        "package_valid": package_valid,
        "revision_task_scope_sha256": computed_scope,
    }


def _pending_legacy_association(root: Path, cycle: dict[str, Any]) -> dict[str, Any]:
    candidate = _shadow_candidate(root, cycle)
    pending = _shadow_pending_checkpoint(root, cycle, candidate)
    association = pending.get("association") if isinstance(pending.get("association"), dict) else {}
    if pending.get("status") != "unscoped_pending" or association.get("eligible") is not True:
        return {}
    return association


def _association_matches_scope(association: dict[str, Any], scope_sha256: str) -> bool:
    return bool(association.get("eligible") and association.get("scope_sha256") == scope_sha256)


def _association_matches_batch(association: dict[str, Any], batch: dict[str, Any]) -> bool:
    return bool(
        association.get("eligible")
        and association.get("batch_id") == batch.get("batch_id")
        and association.get("scope_sha256") == batch.get("scope_sha256")
        and association.get("frozen_candidate_ref") == batch.get("frozen_candidate_ref")
        and association.get("request_id") == batch.get("request_id")
    )


def _record_legacy_batch_association(root: Path, association: dict[str, Any]) -> dict[str, Any]:
    fields = {
        "checkpoint_hash": association["checkpoint_hash"],
        "checkpoint_package_sha256": association["checkpoint_package_sha256"],
        "source_cycle_sha256": association["source_cycle_sha256"],
        "batch_id": association["batch_id"],
        "base_decision_receipt_id": association.get("base_decision_receipt_id"),
        "scope_sha256": association["scope_sha256"],
        "input_manifest_sha256": association["input_manifest_sha256"],
        "candidate_file_sha256": association["candidate_file_sha256"],
        "candidate_generation": association["candidate_generation"],
        "frozen_candidate_ref": association["frozen_candidate_ref"],
    }
    existing = checkpoint_batch_association(root, str(fields["checkpoint_hash"]))
    if existing:
        if any(existing.get(key) != value for key, value in fields.items() if key != "source_cycle_sha256"):
            raise CoreEvidenceBatchError("A conflicting checkpoint-to-batch association already exists.")
        return existing
    try:
        return append_checkpoint_batch_association(root, fields)
    except ValueError as exc:
        raise CoreEvidenceBatchError(str(exc)) from exc


def _shadow_pending_checkpoint(
    root: Path,
    cycle: dict[str, Any],
    candidate: dict[str, Any],
) -> dict[str, Any]:
    awaiting = load_project_passport(root).get("awaiting_checkpoint")
    if not isinstance(awaiting, dict):
        return {"status": "none", "reuse_eligible": False}
    if awaiting.get("stage") != "core_evidence":
        return {"status": "other_stage_pending", "stage": awaiting.get("stage"), "reuse_eligible": False}
    checkpoint_hash = str(awaiting.get("hash") or "")
    if not checkpoint_hash:
        return {"status": "invalid_pending_pointer", "reuse_eligible": False}

    from .checkpoint_summary import _select_checkpoint_record, validate_checkpoint_summary
    from .review_policy import decision_receipt_for_checkpoint

    record = _select_checkpoint_record(root, checkpoint_hash)
    event = next((
        row for row in reversed(read_jsonl(root / "checkpoint_ledger.jsonl"))
        if row.get("kind") == "checkpoint" and row.get("hash") == checkpoint_hash
    ), None)
    package_validation: dict[str, Any]
    summary_payload: dict[str, Any] = {}
    request_payload: dict[str, Any] = {}
    summary_path: Path | None = None
    summary_relative = str((record or {}).get("stage_summary_json") or "")
    try:
        if not summary_relative:
            raise ValueError("checkpoint_summary_path_missing")
        summary_path = (root / summary_relative).resolve()
        summary_path.relative_to(root.resolve())
        package_validation = validate_checkpoint_summary(root, record) if record else {
            "status": "missing_record", "valid": False, "reasons": ["checkpoint_record_missing"],
        }
        if summary_path.is_file():
            payload = json.loads(summary_path.read_text(encoding="utf-8-sig"))
            if isinstance(payload, dict):
                summary_payload = payload
                request_path = summary_path.parent / "confirmation_request.json"
                request_value = json.loads(request_path.read_text(encoding="utf-8-sig"))
                if isinstance(request_value, dict):
                    request_payload = request_value
    except (OSError, UnicodeError, ValueError, TypeError):
        package_validation = {"status": "invalid_path_or_package", "valid": False, "reasons": ["checkpoint_package_unavailable_or_outside_project"]}

    batch = cycle.get("evidence_batch") if isinstance(cycle.get("evidence_batch"), dict) else {}
    package_batch = summary_payload.get("core_evidence_batch")
    package_batch = package_batch if isinstance(package_batch, dict) else {}
    checkpoint_identity = overlay_checkpoint_batch_association(root, event) if isinstance(event, dict) else {}
    identity_sources = [
        ("awaiting_pointer", awaiting),
        ("checkpoint_ledger_or_sealed_association", checkpoint_identity),
        ("checkpoint_summary", package_batch),
    ]
    expected_identity = {
        "batch_id": batch.get("batch_id"),
        "scope_sha256": batch.get("scope_sha256"),
        "input_manifest_sha256": candidate.get("input_manifest_sha256"),
    }
    missing_sources = [
        source_name for source_name, values in identity_sources
        if any(not values.get(key) for key in expected_identity)
    ]
    mismatched_sources = [
        source_name for source_name, values in identity_sources
        if all(expected_identity.values()) and any(values.get(key) != value for key, value in expected_identity.items())
    ]
    if mismatched_sources:
        scope_binding = "mismatch"
    elif missing_sources or not all(expected_identity.values()):
        scope_binding = "unscoped"
    else:
        scope_binding = "matched"

    receipt = decision_receipt_for_checkpoint(root, checkpoint_hash)
    receipt_status = "none"
    receipt_brief: dict[str, Any] = {"status": receipt_status}
    if receipt:
        receipt_status = "valid"
        receipt_brief = {
            "status": receipt_status,
            "receipt_id": receipt.get("receipt_id"),
            "decision": receipt.get("decision"),
            "decision_status": receipt.get("decision_status"),
            "actor_type": receipt.get("actor_type"),
        }
    receipt_reusable = receipt is None or (
        receipt.get("decision") == "approve"
        and receipt.get("decision_status") == "user_confirmed"
        and receipt.get("actor_type") == "user"
    )
    package_valid = package_validation.get("status") == "valid" and package_validation.get("valid") is True
    reusable = (
        package_valid
        and scope_binding == "matched"
        and candidate.get("reuse_eligible") is True
        and receipt_reusable
    )
    association = _legacy_request_association(
        root,
        cycle,
        checkpoint_hash=checkpoint_hash,
        checkpoint_record=record,
        summary=summary_payload,
        request=request_payload,
        package_valid=package_valid,
    )
    if scope_binding == "mismatch":
        association["eligible"] = False
        association["blockers"] = sorted(set([*association.get("blockers", []), "checkpoint_scope_identity_conflict"]))
    if not receipt_reusable:
        association["eligible"] = False
        association["blockers"] = sorted(set([*association.get("blockers", []), "checkpoint_has_non_user_confirmation_receipt"]))
    pending_status = {
        "matched": "scoped_pending",
        "mismatch": "scope_mismatch_pending",
        "unscoped": "unscoped_pending",
    }[scope_binding]
    return {
        "status": pending_status,
        "checkpoint_hash": checkpoint_hash,
        "stage": "core_evidence",
        "checkpoint_found": bool(record and event),
        "scope_binding_status": scope_binding,
        "missing_scope_sources": missing_sources,
        "mismatched_scope_sources": mismatched_sources,
        "batch_id": batch.get("batch_id"),
        "scope_sha256": batch.get("scope_sha256"),
        "package_validation": {
            "status": package_validation.get("status", "unknown"),
            "valid": bool(package_validation.get("valid")),
            "reasons": list(package_validation.get("reasons") or []),
        },
        "decision_receipt": receipt_brief,
        "reuse_eligible": reusable,
        "association": association,
    }


def _shadow_latest_user_confirmation(root: Path, cycle: dict[str, Any]) -> dict[str, Any]:
    receipt = latest_valid_user_receipt(root, checkpoint_type="core_evidence")
    if not receipt:
        return {"status": "none", "authorizes_current_candidate": False}
    batch = cycle.get("evidence_batch") if isinstance(cycle.get("evidence_batch"), dict) else {}
    return {
        "status": "found",
        "receipt_id": receipt.get("receipt_id"),
        "checkpoint_hash": receipt.get("checkpoint_hash"),
        "revision_cycle_id": receipt.get("revision_cycle_id"),
        "scientific_decision_sha256": receipt.get("scientific_decision_sha256"),
        "created_at": receipt.get("created_at"),
        "is_batch_base_receipt": receipt.get("receipt_id") == batch.get("base_decision_receipt_id"),
        "authorizes_current_candidate": False,
    }


def shadow_core_evidence_batch_migration(project: str | Path) -> dict[str, Any]:
    """Report whether an old revision cycle can be explicitly scoped without mutation."""
    root = project_root(project)
    runtime_identity = _legacy_runtime_identity_shadow(root)
    cycle = load_active_revision_cycle(root)
    if not cycle:
        empty_cycle: dict[str, Any] = {}
        candidate = _shadow_candidate(root, empty_cycle)
        pending = _shadow_pending_checkpoint(root, empty_cycle, candidate)
        return {
            "status": "no_active_cycle", "project_path": str(root), "migration_required": False,
            "runtime_identity": runtime_identity,
            "task_scope": _shadow_task_scope(empty_cycle, legacy=False, source={}),
            "candidate": candidate,
            "pending_checkpoint": pending,
            "latest_valid_user_confirmation": _shadow_latest_user_confirmation(root, empty_cycle),
            "recovery": {
                "action": "register_new_explicit_core_evidence_batch" if pending.get("status") in {"unscoped_pending", "scope_mismatch_pending"} else "none",
                "old_request_disposition": "preserve_as_audit_only" if pending.get("status") in {"unscoped_pending", "scope_mismatch_pending"} else "none",
                "approval_transfer_allowed": False,
            },
        }
    legacy = cycle.get("migration_status") == "legacy_unverified"
    source = cycle.get("legacy_source_record") if legacy else {}
    source = source if isinstance(source, dict) else {}
    task_scope = _shadow_task_scope(cycle, legacy=legacy, source=source)
    raw_requested_changes = source.get("requested_changes") if legacy and "requested_changes" in source else None
    requested_changes_status = (
        "not_applicable"
        if not legacy
        else "unknown"
        if "requested_changes" not in source
        else "known"
        if isinstance(raw_requested_changes, list)
        else "invalid"
    )
    candidate = _shadow_candidate(root, cycle)
    pending = _shadow_pending_checkpoint(root, cycle, candidate)
    latest_confirmation = _shadow_latest_user_confirmation(root, cycle)
    blockers: list[str] = []
    if not legacy and cycle.get("schema_version") != BATCH_REVISION_SCHEMA:
        blockers.append("scope_requires_explicit_batch_registration")
    if legacy and ("pending_tasks" not in source or "requested_changes" not in source):
        blockers.append("legacy_scope_fields_missing")
    if legacy and (source.get("pending_tasks") or source.get("requested_changes")):
        blockers.append("legacy_revision_work_requires_manual_reconciliation")
    if legacy and not cycle.get("migration_source_sha256"):
        blockers.append("legacy_source_hash_missing")
    if task_scope.get("status") in {"unknown", "invalid", "incomplete"}:
        blockers.append("legacy_task_scope_unknown_or_incomplete")
    if pending.get("status") in {"unscoped_pending", "scope_mismatch_pending"}:
        blockers.append("pending_checkpoint_not_bound_to_a_complete_batch")
    if pending.get("status") == "scoped_pending" and not pending.get("reuse_eligible"):
        blockers.append("pending_checkpoint_package_or_candidate_not_reusable")
    if candidate.get("status") in {"invalid_path", "missing", "invalid", "oversized", "identity_incomplete", "identity_mismatch"}:
        blockers.append("frozen_candidate_missing_or_unverified")
    if pending.get("status") == "unscoped_pending" and pending.get("association", {}).get("eligible"):
        recovery_action = "associate_complete_legacy_request"
        old_request_disposition = "preserve_as_current_request"
    elif pending.get("status") == "unscoped_pending":
        recovery_action = "register_new_explicit_core_evidence_batch"
        old_request_disposition = "preserve_as_audit_only"
    elif pending.get("status") == "scope_mismatch_pending":
        recovery_action = "recover_scope_from_authoritative_sources"
        old_request_disposition = "preserve_without_reuse"
    elif task_scope.get("status") in {"unknown", "invalid", "incomplete"}:
        recovery_action = "recover_task_scope_from_authoritative_sources"
        old_request_disposition = "preserve_without_reuse"
    elif pending.get("status") == "scoped_pending" and pending.get("reuse_eligible"):
        recovery_action = "reuse_exact_existing_request"
        old_request_disposition = "preserve_as_current_request"
    elif legacy and not blockers:
        recovery_action = "migrate_core_evidence_batch"
        old_request_disposition = "none"
    elif blockers:
        recovery_action = "resolve_shadow_blockers"
        old_request_disposition = "preserve_without_reuse" if pending.get("status") != "none" else "none"
    else:
        recovery_action = "none"
        old_request_disposition = "none"
    return {
        "status": "migration_required" if legacy else ("scope_registration_required" if blockers else "current"),
        "project_path": str(root),
        "migration_required": legacy,
        "revision_cycle_id": cycle.get("revision_cycle_id"),
        "source_schema_version": cycle.get("migration_source_schema_version") if legacy else cycle.get("schema_version"),
        "source_cycle_sha256": cycle.get("migration_source_sha256") if legacy else cycle.get("revision_cycle_sha256"),
        "legacy_pending_tasks": source.get("pending_tasks") if legacy and "pending_tasks" in source else None,
        "legacy_requested_changes": raw_requested_changes,
        "legacy_requested_changes_status": requested_changes_status,
        "legacy_requested_changes_count": len(raw_requested_changes) if isinstance(raw_requested_changes, list) else None,
        "missing_fields": cycle.get("migration_missing_fields", []),
        "blockers": blockers,
        "can_migrate": legacy and not blockers,
        "runtime_identity": runtime_identity,
        "task_scope": task_scope,
        "candidate": candidate,
        "pending_checkpoint": pending,
        "latest_valid_user_confirmation": latest_confirmation,
        "recovery": {
            "action": recovery_action,
            "old_request_disposition": old_request_disposition,
            "approval_transfer_allowed": False,
            "requires_authoritative_scope_manifest": recovery_action == "register_new_explicit_core_evidence_batch",
        },
        "next_action": "migrate-core-evidence-batch" if legacy and not blockers else (
            "prepare-core-evidence-batch" if not legacy and blockers else "none"
        ),
    }


def migrate_legacy_core_evidence_batch(
    project: str | Path, *, changes_path: str | Path,
    expected_legacy_source_sha256: str,
) -> dict[str, Any]:
    """Upgrade only an unchanged, empty-scope legacy cycle with an explicit task manifest."""
    root = project_root(project)
    with file_lock(root / CORE_EVIDENCE_OPERATION_LOCK):
        shadow = shadow_core_evidence_batch_migration(root)
        if not shadow.get("can_migrate"):
            raise CoreEvidenceBatchError("Legacy scope cannot be safely migrated: " + ", ".join(shadow.get("blockers") or []))
        if expected_legacy_source_sha256 != shadow.get("source_cycle_sha256"):
            raise CoreEvidenceBatchError("Legacy source SHA-256 changed; regenerate the shadow report before migration.")
        return _prepare_core_evidence_batch(
            root,
            changes_path=changes_path,
            expected_legacy_source_sha256=expected_legacy_source_sha256,
        )


__all__ = [
    "CORE_EVIDENCE_OPERATION_LOCK", "CoreEvidenceBatchError", "core_evidence_batch_review",
    "load_core_evidence_batch", "mark_core_evidence_batch_awaiting", "migrate_legacy_core_evidence_batch",
    "prepare_core_evidence_batch", "resolve_core_evidence_batch", "shadow_core_evidence_batch_migration",
]
