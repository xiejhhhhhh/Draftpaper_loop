"""Preview/apply transactions for multi-source literature synchronization."""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .literature_repository import write_literature_registry
from .literature_sources import collect_registered_sources
from .project_scaffold import _write_json
from .project_state import load_project
from .references import _load_existing_literature_items, _reference_identity, normalize_reference_items, refresh_reference_outputs, write_reference_outputs


PREVIEW_RELATIVE_PATH = "references/literature_merge_preview.json"
RECEIPT_RELATIVE_PATH = "references/literature_merge_receipt.json"


def _packet_hash(payload: dict[str, Any]) -> str:
    body = {key: value for key, value in payload.items() if key not in {"packet_hash", "created_at"}}
    return "sha256:" + hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return default


def _field_changes(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    changes: list[str] = []
    for key in sorted(set(before) | set(after)):
        if before.get(key) != after.get(key):
            changes.append(key)
    return changes


def build_literature_merge_preview(
    project: str | Path,
    *,
    incoming: list[dict[str, Any]] | None = None,
    mode: str = "augment",
    source_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    state = load_project(project)
    baseline = _load_existing_literature_items(state.path / "references") if mode != "replace" else []
    incoming_items = [item for item in incoming or [] if isinstance(item, dict) and str(item.get("title") or "").strip()]
    merged = normalize_reference_items([*baseline, *incoming_items])
    baseline_map = {_reference_identity(item): item for item in baseline if _reference_identity(item)}
    merged_map = {_reference_identity(item): item for item in merged if _reference_identity(item)}
    additions = sorted(set(merged_map) - set(baseline_map))
    changes = [
        {
            "work_id": work_id,
            "title": str(merged_map[work_id].get("title") or ""),
            "changed_fields": _field_changes(baseline_map[work_id], merged_map[work_id]),
        }
        for work_id in sorted(set(baseline_map) & set(merged_map))
        if _field_changes(baseline_map[work_id], merged_map[work_id])
    ]
    payload: dict[str, Any] = {
        "schema_version": "dpl.literature_merge_packet.v1",
        "project_path": str(state.path),
        "mode": mode,
        "baseline_count": len(baseline),
        "incoming_count": len(incoming_items),
        "proposed_count": len(merged),
        "added_work_ids": additions,
        "changed_records": changes,
        "preserved_work_ids": sorted(set(baseline_map) & set(merged_map)),
        "incoming": deepcopy(incoming_items),
        "source_report": source_report or {},
    }
    payload["packet_hash"] = _packet_hash(payload)
    payload["created_at"] = datetime.now(timezone.utc).isoformat()
    _write_json(state.path / PREVIEW_RELATIVE_PATH, payload)
    return {
        "status": "preview",
        "packet_hash": payload["packet_hash"],
        "preview": PREVIEW_RELATIVE_PATH,
        "baseline_count": len(baseline),
        "incoming_count": len(incoming_items),
        "proposed_count": len(merged),
        "added_count": len(additions),
        "changed_count": len(changes),
    }


def apply_literature_merge(project: str | Path, *, packet_hash: str) -> dict[str, Any]:
    state = load_project(project)
    preview_path = state.path / PREVIEW_RELATIVE_PATH
    payload = _read_json(preview_path, {})
    if not isinstance(payload, dict) or str(payload.get("packet_hash") or "") != str(packet_hash):
        raise ValueError("Literature merge packet hash does not match the current preview.")
    if _packet_hash(payload) != str(packet_hash):
        raise ValueError("Literature merge preview contents changed after hashing.")
    references_dir = state.path / "references"
    backup_root = Path(tempfile.mkdtemp(prefix="literature-merge-backup-"))
    backup_references = backup_root / "references"
    shutil.copytree(references_dir, backup_references, dirs_exist_ok=True)
    try:
        result = write_reference_outputs(
            state.path,
            payload.get("incoming") or [],
            query=str(state.metadata.get("idea") or ""),
            search_queries={"mode": "apply_literature_merge", "merge_mode": str(payload.get("mode") or "augment"), "packet_hash": packet_hash},
        )
        registry = write_literature_registry(state.path, _load_existing_literature_items(state.path / "references"))
    except Exception:
        if references_dir.exists():
            shutil.rmtree(references_dir)
        shutil.copytree(backup_references, references_dir, dirs_exist_ok=True)
        _write_json(state.path / RECEIPT_RELATIVE_PATH, {
            "schema_version": "dpl.literature_merge_receipt.v1",
            "status": "rolled_back",
            "packet_hash": packet_hash,
            "rollback_reason": "apply_failed",
            "applied_at": datetime.now(timezone.utc).isoformat(),
        })
        raise
    finally:
        shutil.rmtree(backup_root, ignore_errors=True)
    receipt = {
        "schema_version": "dpl.literature_merge_receipt.v1",
        "status": "applied",
        "packet_hash": packet_hash,
        "snapshot_hash": _read_json(state.path / "references" / "literature_snapshot.json", {}).get("snapshot_hash"),
        "registry_hash": registry.get("registry_hash"),
        "result": {"item_count": result.get("item_count"), "outputs": result.get("outputs")},
        "applied_at": datetime.now(timezone.utc).isoformat(),
    }
    _write_json(state.path / RECEIPT_RELATIVE_PATH, receipt)
    return {"status": "applied", "packet_hash": packet_hash, "receipt": RECEIPT_RELATIVE_PATH, "registry": registry, "item_count": result.get("item_count")}


def sync_literature_sources(project: str | Path, *, apply: bool = False, packet_hash: str | None = None) -> dict[str, Any]:
    state = load_project(project)
    items, report = collect_registered_sources(state.path)
    preview = build_literature_merge_preview(state.path, incoming=items, mode="augment", source_report=report)
    if not apply:
        return {**preview, "source_collection": report}
    return apply_literature_merge(state.path, packet_hash=packet_hash or str(preview["packet_hash"]))


def repair_literature_identities(project: str | Path, *, apply: bool = False) -> dict[str, Any]:
    state = load_project(project)
    items = _load_existing_literature_items(state.path / "references")
    normalized = normalize_reference_items(items)
    changes = [
        {"title": item.get("title"), "before": original.get("work_id"), "after": item.get("work_id")}
        for original, item in zip(items, normalized)
        if str(original.get("work_id") or "") != str(item.get("work_id") or "")
    ]
    preview = {"schema_version": "dpl.literature_identity_repair.v1", "status": "preview", "change_count": len(changes), "changes": changes}
    _write_json(state.path / "references" / "literature_identity_repair_preview.json", preview)
    if not apply:
        return {"status": "preview", "preview": "references/literature_identity_repair_preview.json", "change_count": len(changes)}
    result = write_reference_outputs(state.path, normalized, query=str(state.metadata.get("idea") or ""), search_queries={"merge_mode": "replace", "mode": "repair_literature_identities"}, limit=max(30, len(normalized)))
    registry = write_literature_registry(state.path, _load_existing_literature_items(state.path / "references"))
    return {"status": "applied", "change_count": len(changes), "item_count": result.get("item_count"), "registry": registry}


def rebuild_literature_index(project: str | Path) -> dict[str, Any]:
    result = refresh_reference_outputs(project)
    return {
        "status": "rebuilt",
        "outputs": result.get("outputs") or [],
        "item_count": result.get("item_count", 0),
        "snapshot_hash": result.get("snapshot_hash"),
        "manifest": result.get("manifest"),
    }
