"""Explicit C3 batch registration for synthetic legacy test fixtures only."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from draftpaper_cli.core_evidence_batch import prepare_core_evidence_batch
from draftpaper_cli.core_evidence_readiness import finalize_core_evidence_batch


def prepare_confirmable_core_batch(project: str | Path) -> dict:
    root = Path(project)
    report_path = root / "core_evidence" / "core_evidence_report.json"
    relative = "core_evidence/core_evidence_report.json"
    task = {
        "task_id": "verify_current_core_report",
        "title_zh": "核验本轮核心证据报告",
        "title_en": "Verify the current core-evidence report",
        "checkpoint_scope": "core_evidence",
        "origin_ref": "synthetic_test_fixture",
        "effect_class": "scientific",
        "required_before_publication": True,
        "depends_on": [],
        "evidence_refs": [relative],
        "expected_artifacts": [relative],
        "completion_checks": ["matching_artifact_hash"],
        "completion_receipts": [{
            "path": relative,
            "sha256": hashlib.sha256(report_path.read_bytes()).hexdigest(),
        }],
        "status": "completed",
    }
    changes_path = root.parent / f"{root.name}-core-batch-test-input.json"
    changes_path.write_text(json.dumps({"tasks": [task]}, ensure_ascii=False), encoding="utf-8")
    prepared = prepare_core_evidence_batch(root, changes_path=changes_path)
    final = finalize_core_evidence_batch(root)
    if final["status"] != "ready":
        raise AssertionError(f"Synthetic core batch is not ready: {final}")
    return {"prepared": prepared, "finalized": final}
