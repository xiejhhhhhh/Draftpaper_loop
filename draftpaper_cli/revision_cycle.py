"""First-class revision cycles bound to immutable scientific baselines."""

from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path
from typing import Any, Iterable

from .artifact_identity import canonical_json
from .passport import project_root, utc_now
from .scientific_baseline import create_scientific_baseline, load_active_baseline
from .state_kernel import atomic_write_json


REVISION_SCHEMA = "dpl.revision_cycle.v1"
REVISION_DIR = "lineage/revision_cycles"
ACTIVE_POINTER = ".draftpaper/active_revision_cycle.json"


class RevisionCycleError(RuntimeError):
    """Raised when a revision cycle cannot be opened safely."""


def _hash(payload: Any) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def begin_revision_cycle(
    project: str | Path,
    *,
    reason: str = "author_update",
    requested_changes: Iterable[str] = (),
    allowed_change_classes: Iterable[str] = (),
    protected_facts: Iterable[str] = (),
    expected_artifacts: Iterable[str] = (),
    started_by: str = "user",
    baseline_id: str | None = None,
) -> dict[str, Any]:
    root = project_root(project)
    active_cycle = load_active_revision_cycle(root)
    if active_cycle and active_cycle.get("status") == "open":
        raise RevisionCycleError("An active revision cycle is already open; close or reject it before opening another.")
    baseline = load_active_baseline(root)
    if baseline_id and (not baseline or baseline.get("baseline_id") != baseline_id):
        raise RevisionCycleError("Requested baseline is not the active immutable baseline.")
    if baseline is None:
        baseline = create_scientific_baseline(root, reason="revision_cycle_seed")["baseline"]
    payload = {
        "schema_version": REVISION_SCHEMA,
        "revision_cycle_id": "revision-" + uuid.uuid4().hex,
        "project_id": _project_id(root),
        "parent_baseline_id": baseline.get("baseline_id"),
        "reason": reason,
        "requested_changes": sorted({str(item) for item in requested_changes if str(item).strip()}),
        "allowed_change_classes": sorted({str(item) for item in allowed_change_classes if str(item).strip()}),
        "protected_facts": sorted({str(item) for item in protected_facts if str(item).strip()}),
        "expected_artifacts": sorted({str(item) for item in expected_artifacts if str(item).strip()}),
        "started_by": started_by,
        "started_at": utc_now(),
        "status": "open",
        "candidate_baseline_id": None,
        "closed_by_decision_receipt": None,
    }
    payload["revision_cycle_sha256"] = _hash(payload)
    path = root / REVISION_DIR / f"{payload['revision_cycle_id']}.json"
    atomic_write_json(path, payload)
    pointer = {
        "schema_version": "dpl.active_revision_cycle.v1",
        "revision_cycle_id": payload["revision_cycle_id"],
        "revision_cycle_sha256": payload["revision_cycle_sha256"],
        "path": str(path.relative_to(root).as_posix()),
        "updated_at": utc_now(),
    }
    atomic_write_json(root / ACTIVE_POINTER, pointer)
    return {"status": "started", "project_path": str(root), "revision_cycle": payload, "revision_cycle_path": str(path.resolve()), "active_pointer": str((root / ACTIVE_POINTER).resolve()), "parent_baseline_id": payload["parent_baseline_id"]}


def load_active_revision_cycle(project: str | Path) -> dict[str, Any] | None:
    root = project_root(project)
    try:
        pointer = json.loads((root / ACTIVE_POINTER).read_text(encoding="utf-8-sig"))
        path = (root / str(pointer.get("path") or "")).resolve()
        path.relative_to(root.resolve())
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict) or payload.get("schema_version") != REVISION_SCHEMA:
        return None
    if payload.get("revision_cycle_sha256") != _hash({key: value for key, value in payload.items() if key != "revision_cycle_sha256"}):
        return None
    if pointer.get("revision_cycle_id") != payload.get("revision_cycle_id") or pointer.get("revision_cycle_sha256") != payload.get("revision_cycle_sha256"):
        return None
    return payload


def close_revision_cycle(
    project: str | Path,
    *,
    decision_receipt_id: str,
    candidate_baseline_id: str | None = None,
    status: str = "closed",
) -> dict[str, Any]:
    if status not in {"closed", "superseded", "rejected"}:
        raise RevisionCycleError("Invalid revision cycle close status.")
    root = project_root(project)
    active = load_active_revision_cycle(root)
    if not active:
        raise RevisionCycleError("No active revision cycle.")
    active["status"] = status
    active["candidate_baseline_id"] = candidate_baseline_id
    active["closed_by_decision_receipt"] = decision_receipt_id
    active["closed_at"] = utc_now()
    active["revision_cycle_sha256"] = _hash({key: value for key, value in active.items() if key != "revision_cycle_sha256"})
    # The immutable input is kept intact; a superseding cycle record is used
    # for closure metadata so history cannot be silently rewritten.
    closed_path = root / REVISION_DIR / f"{active['revision_cycle_id']}-closed.json"
    atomic_write_json(closed_path, active)
    pointer = {
        "schema_version": "dpl.active_revision_cycle.v1",
        "revision_cycle_id": active["revision_cycle_id"],
        "revision_cycle_sha256": active["revision_cycle_sha256"],
        "path": str(closed_path.relative_to(root).as_posix()),
        "updated_at": utc_now(),
    }
    atomic_write_json(root / ACTIVE_POINTER, pointer)
    return {"status": status, "project_path": str(root), "revision_cycle": active, "closed_record": str(closed_path.resolve()), "active_pointer": str((root / ACTIVE_POINTER).resolve())}


def _project_id(root: Path) -> str | None:
    try:
        payload = json.loads((root / "project.json").read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    return str(payload.get("project_id") or "") or None


__all__ = ["ACTIVE_POINTER", "REVISION_SCHEMA", "RevisionCycleError", "begin_revision_cycle", "close_revision_cycle", "load_active_revision_cycle"]
