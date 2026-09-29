"""Notification delivery is separate from author approval."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from draftpaper_cli.checkpoint_summary import show_checkpoint_summary
from draftpaper_cli.orchestrator import checkpoint_project
from tests.test_core_evidence_batch_flow import _ready_project


def _tree(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*") if path.is_file()
    }


def test_notification_replay_and_ack_do_not_approve_science(tmp_path: Path) -> None:
    from draftpaper_cli.checkpoint_delivery import (
        acknowledge_checkpoint_notification,
        pending_checkpoint_notification,
    )

    project = _ready_project(tmp_path)
    checkpoint = checkpoint_project(project, stage="core_evidence")
    request_id = checkpoint["checkpoint_hash"]
    before = _tree(project)
    first = pending_checkpoint_notification(project, request_id=request_id, consumer_id="codex-agent")
    second = pending_checkpoint_notification(project, request_id=request_id, consumer_id="codex-agent")
    assert first == second
    assert first["status"] == "pending_delivery"
    assert _tree(project) == before

    receipt = acknowledge_checkpoint_notification(
        project, notification_id=first["notification_id"], consumer_id="codex-agent"
    )
    assert receipt["status"] == "acknowledged"
    repeated = pending_checkpoint_notification(project, request_id=request_id, consumer_id="codex-agent")
    assert repeated["status"] == "already_delivered"
    assert repeated["notification_id"] == first["notification_id"]
    assert acknowledge_checkpoint_notification(
        project, notification_id=first["notification_id"], consumer_id="codex-agent"
    ) == receipt
    assert show_checkpoint_summary(project, request_id)["review_state"] == "confirmable"
    assert not (project / "results" / "promoted_evidence_snapshot.json").exists()


def test_notification_ack_rejects_another_consumer(tmp_path: Path) -> None:
    from draftpaper_cli.checkpoint_delivery import (
        CheckpointDeliveryError,
        acknowledge_checkpoint_notification,
        pending_checkpoint_notification,
    )

    project = _ready_project(tmp_path)
    checkpoint = checkpoint_project(project, stage="core_evidence")
    notice = pending_checkpoint_notification(
        project, request_id=checkpoint["checkpoint_hash"], consumer_id="codex-agent"
    )
    with pytest.raises(CheckpointDeliveryError):
        acknowledge_checkpoint_notification(
            project, notification_id=notice["notification_id"], consumer_id="other-agent"
        )
