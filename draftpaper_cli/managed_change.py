"""Scoped managed edits for Agent and external-edit reconciliation."""

from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path
from typing import Any, Iterable

from .artifact_identity import canonical_json, compute_artifact_identity
from .passport import project_root, utc_now
from .revision_cycle import load_active_revision_cycle
from .scientific_baseline import load_active_baseline
from .state_kernel import append_jsonl_locked, atomic_write_json, atomic_write_text


MANAGED_CHANGE_SCHEMA = "dpl.managed_change_packet.v1"
MANAGED_CHANGE_DIR = ".draftpaper/managed_changes"
MANAGED_CHANGE_LEDGER = ".draftpaper/managed_change_ledger.jsonl"


class ManagedChangeError(RuntimeError):
    """Raised when a scoped edit packet is stale or unsafe."""


def _hash(payload: Any) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _safe_relative(root: Path, raw: str) -> str:
    candidate = (root / raw).resolve()
    try:
        relative = candidate.relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise ManagedChangeError(f"Managed change path escapes project: {raw}") from exc
    if not relative or relative.startswith(".git/") or relative in {"project.json", "project.yaml"}:
        raise ManagedChangeError(f"Managed change path is protected: {raw}")
    return relative


def _identity(path: Path, relative: str) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    return compute_artifact_identity(path, relative)


def begin_managed_change(
    project: str | Path,
    *,
    intent: str,
    change_class: str,
    paths: Iterable[str] = (),
    content_file: str | None = None,
) -> dict[str, Any]:
    root = project_root(project)
    cycle = load_active_revision_cycle(root)
    if cycle and cycle.get("status") != "open":
        raise ManagedChangeError("A managed change cannot be created from a closed revision cycle.")
    baseline = load_active_baseline(root)
    if cycle and cycle.get("allowed_change_classes") and change_class not in set(cycle.get("allowed_change_classes") or []):
        raise ManagedChangeError("Managed change class is outside the active revision-cycle scope.")
    packet_id = "change-" + uuid.uuid4().hex
    normalized_paths = [_safe_relative(root, str(item)) for item in paths if str(item).strip()]
    changes: list[dict[str, Any]] = []
    for relative in normalized_paths:
        path = root / relative
        current = _identity(path, relative)
        changes.append({"path": relative, "before": current, "content": None})
    if content_file:
        source = Path(content_file).expanduser().resolve()
        if not source.is_file():
            raise ManagedChangeError(f"Managed change content file not found: {source}")
        content = source.read_text(encoding="utf-8-sig")
        if len(changes) != 1:
            raise ManagedChangeError("--content-file requires exactly one --path.")
        changes[0]["content"] = content
    packet = {
        "schema_version": MANAGED_CHANGE_SCHEMA,
        "packet_id": packet_id,
        "project_id": _project_id(root),
        "revision_cycle_id": (cycle or {}).get("revision_cycle_id"),
        "baseline_id": (baseline or {}).get("baseline_id"),
        "intent": intent,
        "change_class": change_class,
        "changes": changes,
        "status": "preview",
        "created_at": utc_now(),
    }
    packet["packet_sha256"] = _hash(packet)
    path = root / MANAGED_CHANGE_DIR / packet_id / "packet.json"
    atomic_write_json(path, packet)
    return {"status": "preview_ready", "project_path": str(root), "packet": packet, "packet_path": str(path.resolve()), "packet_hash": packet["packet_sha256"]}


def apply_managed_change(project: str | Path, *, packet_id: str, packet_hash: str) -> dict[str, Any]:
    root = project_root(project)
    path = root / MANAGED_CHANGE_DIR / packet_id / "packet.json"
    try:
        packet = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise ManagedChangeError(f"Managed packet not found or invalid: {packet_id}") from exc
    if packet.get("packet_sha256") != packet_hash or _hash({key: value for key, value in packet.items() if key != "packet_sha256"}) != packet_hash:
        raise ManagedChangeError("Managed packet hash does not match its immutable preview.")
    previous_receipt = _find_committed_receipt(root, packet_id=packet_id, packet_hash=packet_hash)
    if previous_receipt is not None:
        raise ManagedChangeError(f"Managed change packet has already been committed: {packet_id}")
    cycle = load_active_revision_cycle(root)
    if packet.get("revision_cycle_id") and (
        not cycle
        or cycle.get("revision_cycle_id") != packet.get("revision_cycle_id")
        or cycle.get("status") != "open"
    ):
        raise ManagedChangeError("Managed change packet belongs to a different or closed revision cycle.")
    if cycle and cycle.get("allowed_change_classes") and packet.get("change_class") not in set(cycle.get("allowed_change_classes") or []):
        raise ManagedChangeError("Managed change class is outside the active revision-cycle scope.")
    baseline = load_active_baseline(root)
    if packet.get("baseline_id") and (not baseline or baseline.get("baseline_id") != packet.get("baseline_id")):
        raise ManagedChangeError("Managed change packet became stale because its scientific baseline changed.")

    prepared: list[tuple[str, Path, str]] = []
    for change in packet.get("changes") or []:
        relative = _safe_relative(root, str(change.get("path") or ""))
        target = root / relative
        expected = change.get("before") or {}
        current = _identity(target, relative)
        expected_hash = expected.get("semantic_sha256") or expected.get("byte_sha256") or expected.get("sha256")
        current_hash = (current or {}).get("semantic_sha256") or (current or {}).get("byte_sha256") or (current or {}).get("sha256")
        if expected_hash != current_hash:
            raise ManagedChangeError(f"Managed change target became stale: {relative}")
        content = change.get("content")
        if content is None:
            continue
        prepared.append((relative, target, str(content)))

    changed = [relative for relative, _, _ in prepared]
    for _, target, content in prepared:
        atomic_write_text(target, content)

    after_identities = {
        relative: _identity(target, relative)
        for relative, target, _ in prepared
    }
    receipt = {
        "schema_version": "dpl.managed_change_receipt.v1",
        "receipt_id": uuid.uuid4().hex,
        "packet_id": packet_id,
        "packet_hash": packet_hash,
        "packet_path": str(path.relative_to(root).as_posix()),
        "change_class": packet.get("change_class"),
        "revision_cycle_id": packet.get("revision_cycle_id"),
        "baseline_id": packet.get("baseline_id"),
        "changed_paths": changed,
        "before_identities": {str(change.get("path")): change.get("before") for change in packet.get("changes") or []},
        "after_identities": after_identities,
        "status": "committed",
        "created_at": utc_now(),
    }
    receipt_path = root / MANAGED_CHANGE_DIR / packet_id / "receipts" / f"{receipt['receipt_id']}.json"
    atomic_write_json(receipt_path, receipt)
    append_jsonl_locked(root / MANAGED_CHANGE_LEDGER, receipt)
    return {
        "status": "committed",
        "project_path": str(root),
        "packet_id": packet_id,
        "changed_paths": changed,
        "receipt": receipt,
        "receipt_path": str(receipt_path.resolve()),
        "ledger_path": str((root / MANAGED_CHANGE_LEDGER).resolve()),
    }


def _find_committed_receipt(root: Path, *, packet_id: str, packet_hash: str) -> dict[str, Any] | None:
    ledger = root / MANAGED_CHANGE_LEDGER
    if not ledger.is_file():
        return None
    for line in ledger.read_text(encoding="utf-8-sig").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except ValueError:
            continue
        if (
            isinstance(payload, dict)
            and payload.get("packet_id") == packet_id
            and payload.get("packet_hash") == packet_hash
            and payload.get("status") == "committed"
        ):
            return payload
    return None


def _project_id(root: Path) -> str | None:
    try:
        payload = json.loads((root / "project.json").read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    return str(payload.get("project_id") or "") or None


__all__ = ["MANAGED_CHANGE_SCHEMA", "ManagedChangeError", "apply_managed_change", "begin_managed_change"]
