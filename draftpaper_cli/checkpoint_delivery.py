"""Idempotent presentation receipts that never approve a checkpoint."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .checkpoint_summary import show_checkpoint_summary
from .core_evidence_readiness import assess_core_evidence_readiness
from .passport import load_project_passport, project_root, utc_now
from .state_kernel import atomic_write_json, file_lock


class CheckpointDeliveryError(RuntimeError):
    """A notice cannot be associated with the current frozen request."""


_CONSUMER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


def _notification_id(request_id: str, consumer_id: str) -> str:
    return hashlib.sha256(f"{request_id}:{consumer_id}".encode("utf-8")).hexdigest()[:24]


def _receipt_path(root: Path, notification_id: str) -> Path:
    return root / "review" / "checkpoint_notifications" / f"{notification_id}.json"


def _consumer_id(value: str) -> str:
    if not _CONSUMER.fullmatch(value):
        raise CheckpointDeliveryError("consumer_id must be a stable, safe receiver identifier.")
    return value


def _current_request(root: Path, request_id: str) -> dict[str, Any]:
    awaiting = load_project_passport(root).get("awaiting_checkpoint") or {}
    if awaiting.get("stage") != "core_evidence" or awaiting.get("hash") != request_id:
        raise CheckpointDeliveryError("This is not the current core-evidence confirmation request.")
    readiness = assess_core_evidence_readiness(root)
    if (
        readiness.get("status") not in {"ready", "awaiting_confirmation"}
        or awaiting.get("batch_id") != readiness.get("batch_id")
        or awaiting.get("scope_sha256") != readiness.get("scope_sha256")
        or awaiting.get("input_manifest_sha256") != readiness.get("input_manifest_sha256")
    ):
        raise CheckpointDeliveryError("The frozen batch changed; the old request cannot be delivered.")
    shown = show_checkpoint_summary(root, request_id)
    if shown.get("status") != "ready_for_human_review" or shown.get("review_state") != "confirmable":
        raise CheckpointDeliveryError("The current checkpoint packet is not confirmable.")
    return shown


def pending_checkpoint_notification(
    project: str | Path, *, request_id: str, consumer_id: str,
) -> dict[str, Any]:
    """Return a stable notice without counting a read as a delivery."""
    root = project_root(project)
    consumer = _consumer_id(consumer_id)
    notification_id = _notification_id(request_id, consumer)
    receipt_path = _receipt_path(root, notification_id)
    if receipt_path.is_file():
        receipt = json.loads(receipt_path.read_text(encoding="utf-8-sig"))
        if receipt.get("request_id") != request_id or receipt.get("consumer_id") != consumer:
            raise CheckpointDeliveryError("A notification receipt has a mismatched identity.")
        return {**receipt, "status": "already_delivered"}
    shown = _current_request(root, request_id)
    return {
        "status": "pending_delivery",
        "notification_id": notification_id,
        "request_id": request_id,
        "consumer_id": consumer,
        "stage_summary_zh_html": shown["stage_summary_zh_html"],
        "stage_summary_en_html": shown.get("stage_summary_en_html"),
    }


def acknowledge_checkpoint_notification(
    project: str | Path, *, notification_id: str, consumer_id: str,
) -> dict[str, Any]:
    """Record display only; scientific approval remains the existing C3 decision."""
    root = project_root(project)
    consumer = _consumer_id(consumer_id)
    if not re.fullmatch(r"[0-9a-f]{24}", notification_id):
        raise CheckpointDeliveryError("Invalid notification ID.")
    path = _receipt_path(root, notification_id)
    with file_lock(root / ".draftpaper" / "checkpoint_delivery_gate"):
        if path.is_file():
            receipt = json.loads(path.read_text(encoding="utf-8-sig"))
            if receipt.get("consumer_id") != consumer:
                raise CheckpointDeliveryError("This notice belongs to a different consumer.")
            return receipt
        awaiting = load_project_passport(root).get("awaiting_checkpoint") or {}
        request_id = str(awaiting.get("hash") or "")
        if not request_id or _notification_id(request_id, consumer) != notification_id:
            raise CheckpointDeliveryError("The notification does not match the current request and consumer.")
        _current_request(root, request_id)
        receipt = {
            "schema_version": "dpl.checkpoint_delivery_receipt.v1",
            "status": "acknowledged",
            "notification_id": notification_id,
            "request_id": request_id,
            "consumer_id": consumer,
            "recorded_at": utc_now(),
            "decision_status": "pending",
        }
        atomic_write_json(path, receipt)
        return receipt


__all__ = [
    "CheckpointDeliveryError", "pending_checkpoint_notification", "acknowledge_checkpoint_notification",
]
