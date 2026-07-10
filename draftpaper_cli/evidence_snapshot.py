# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .project_scaffold import _write_json, utc_now
from .project_state import load_project, mark_stages_stale


PROMOTED_EVIDENCE_SNAPSHOT_JSON = "results/promoted_evidence_snapshot.json"
SNAPSHOT_ARTIFACTS = [
    "methods/run_manifest.yaml",
    "results/resolved_result_evidence.json",
    "results/figure_plan.json",
    "results/figure_contracts.json",
    "results/figure_metadata.json",
    "results/figure_semantic_validation_report.json",
    "results/result_validity_report.json",
]
MANUSCRIPT_ARTIFACTS = [
    "introduction/introduction.tex",
    "data/data.tex",
    "methods/methods.tex",
    "results/results.tex",
    "discussion/discussion.tex",
    "latex/library.bib",
    "references/library.bib",
]


class EvidenceSnapshotMismatch(RuntimeError):
    """Raised when scientific evidence changed after human promotion."""


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _artifact_hashes(project_path: Path) -> dict[str, str]:
    paths = [project_path / item for item in SNAPSHOT_ARTIFACTS]
    paths.extend(sorted((project_path / "results" / "figures").glob("*")))
    return {
        path.relative_to(project_path).as_posix(): _hash(path)
        for path in paths
        if path.is_file()
    }


def _snapshot_id(artifacts: dict[str, str]) -> str:
    canonical = json.dumps(artifacts, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:20]


def create_evidence_snapshot(project: str | Path) -> dict[str, Any]:
    """Freeze the scientific evidence version accepted at the human checkpoint."""
    state = load_project(project)
    artifacts = _artifact_hashes(state.path)
    payload = {
        "schema_version": "v0.17.7",
        "snapshot_id": _snapshot_id(artifacts),
        "promoted_at": utc_now(),
        "status": "promoted",
        "artifacts": artifacts,
        "reopen_required_on_change": True,
    }
    _write_json(state.path / PROMOTED_EVIDENCE_SNAPSHOT_JSON, payload)
    return payload


def validate_evidence_snapshot(project: str | Path, expected_snapshot_id: str | None = None) -> dict[str, Any]:
    """Reject consumers when any promoted scientific artifact has changed."""
    state = load_project(project)
    path = state.path / PROMOTED_EVIDENCE_SNAPSHOT_JSON
    if not path.exists():
        raise EvidenceSnapshotMismatch("A promoted evidence snapshot is required.")
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    current = _artifact_hashes(state.path)
    current_id = _snapshot_id(current)
    expected = expected_snapshot_id or str(payload.get("snapshot_id") or "")
    if current != payload.get("artifacts") or current_id != expected:
        changed = sorted(
            key
            for key in set(current) | set(payload.get("artifacts") or {})
            if current.get(key) != (payload.get("artifacts") or {}).get(key)
        )
        raise EvidenceSnapshotMismatch(
            "Scientific evidence changed after promotion; reopen core evidence before writing: "
            + ", ".join(changed)
        )
    return payload


def manuscript_snapshot(project: str | Path) -> dict[str, Any]:
    """Hash the final manuscript inputs covered by a citation audit."""
    state = load_project(project)
    artifacts = {
        relative: _hash(state.path / relative)
        for relative in MANUSCRIPT_ARTIFACTS
        if (state.path / relative).is_file()
    }
    return {
        "snapshot_id": _snapshot_id(artifacts),
        "artifacts": artifacts,
        "captured_at": utc_now(),
    }


def validate_citation_audit_snapshot(project: str | Path, binding: dict[str, Any]) -> dict[str, Any]:
    current = manuscript_snapshot(project)
    if current["artifacts"] != binding.get("artifacts") or current["snapshot_id"] != binding.get("snapshot_id"):
        raise EvidenceSnapshotMismatch(
            "The manuscript or BibTeX library changed after citation audit; rerun the final citation audit."
        )
    return current


def validate_promoted_snapshot_for_writing(project: str | Path) -> dict[str, Any]:
    """Require a current snapshot once core evidence has passed human-review readiness."""
    state = load_project(project)
    snapshot_path = state.path / PROMOTED_EVIDENCE_SNAPSHOT_JSON
    if snapshot_path.exists():
        return validate_evidence_snapshot(state.path)
    core_report = state.path / "core_evidence" / "core_evidence_report.json"
    if core_report.exists():
        payload = json.loads(core_report.read_text(encoding="utf-8-sig"))
        if str(payload.get("decision") or "").lower() == "pass":
            raise EvidenceSnapshotMismatch(
                "Core evidence passed but has not been promoted by the human checkpoint. Resume the core-evidence checkpoint before writing."
            )
    return {}


def reopen_evidence_snapshot(project: str | Path, *, reason: str) -> dict[str, Any]:
    """Archive the promoted snapshot and invalidate its scientific consumers."""
    state = load_project(project)
    snapshot_path = state.path / PROMOTED_EVIDENCE_SNAPSHOT_JSON
    if not snapshot_path.exists():
        raise EvidenceSnapshotMismatch("No promoted evidence snapshot is available to reopen.")
    payload = json.loads(snapshot_path.read_text(encoding="utf-8-sig"))
    snapshot_id = str(payload.get("snapshot_id") or "unknown")
    archive_dir = state.path / "results" / "evidence_snapshots"
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive_path = archive_dir / f"{snapshot_id}.json"
    snapshot_path.replace(archive_path)
    affected = [
        "result_validity",
        "core_evidence",
        "results",
        "introduction",
        "data_writing",
        "methods_writing",
        "discussion",
        "citation_audit",
        "latex",
        "quality_checks",
    ]
    changed = mark_stages_stale(state.path, affected)
    report = {
        "status": "reopened",
        "reopened_at": utc_now(),
        "reason": str(reason or "").strip(),
        "archived_snapshot_id": snapshot_id,
        "archived_snapshot": archive_path.relative_to(state.path).as_posix(),
        "affected_stages": affected,
        "stale_stages": changed,
    }
    _write_json(state.path / "results" / "evidence_snapshot_reopen_report.json", report)
    return report
