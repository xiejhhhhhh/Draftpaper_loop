"""Final PDF, citation-audit, and independent-review confirmation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .evidence_snapshot import EvidenceSnapshotMismatch, validate_citation_audit_snapshot
from .html_utils import write_html_report
from .project_scaffold import _write_json, utc_now
from .project_state import load_project


PACKET_JSON = "review/final_manuscript_confirmation_packet.json"
PACKET_HTML = "review/final_manuscript_confirmation_packet.html"
CONFIRMATION_JSON = "review/final_manuscript_confirmation.json"
ARTIFACTS = [
    "latex/main.pdf",
    "writing/manuscript_completion/active_completion_manifest.json",
    "writing/manuscript_metadata.yaml",
    "introduction/introduction.tex",
    "data/data.tex",
    "methods/methods.tex",
    "results/results.tex",
    "discussion/discussion.tex",
    "references/library.bib",
    "references/reference_registry.json",
    "citation_audit/final_citation_audit_report.json",
    "results/promoted_evidence_snapshot.json",
    "results/result_manifest.yaml",
    "results/figure_metadata.json",
    "core_evidence/core_evidence_report.json",
    "integrity/integrity_report.json",
    "quality_checks/blind_reviews/aggregate.json",
    "quality_checks/blind_reviews/reviewer_01/report.md",
    "quality_checks/blind_reviews/reviewer_02/report.md",
    "quality_checks/quality_report.json",
]


class FinalManuscriptConfirmationError(RuntimeError):
    """Raised when the final release packet is incomplete or stale."""


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _is_passing(payload: dict[str, Any]) -> bool:
    status = str(payload.get("status") or "").lower()
    decision = str(payload.get("decision") or "").lower()
    return status in {"pass", "passed", "approved"} or decision == "pass"


def _validate_release_semantics(project_path: Path) -> dict[str, Any]:
    completion = _read_json(project_path / "writing" / "manuscript_completion" / "active_completion_manifest.json")
    if completion.get("status") != "applied":
        raise FinalManuscriptConfirmationError("Final manuscript completion is missing, rolled back, or not applied.")
    citation = _read_json(project_path / "citation_audit" / "final_citation_audit_report.json")
    if not _is_passing(citation):
        raise FinalManuscriptConfirmationError("Final citation audit is missing or not passing.")
    if (project_path / "citation_audit" / "stale_marker.json").is_file():
        raise FinalManuscriptConfirmationError("Final citation audit is stale after a manuscript change.")
    binding = citation.get("manuscript_snapshot")
    if not isinstance(binding, dict):
        raise FinalManuscriptConfirmationError("Final citation audit has no manuscript snapshot binding.")
    try:
        current_citation_snapshot = validate_citation_audit_snapshot(project_path, binding)
    except EvidenceSnapshotMismatch as exc:
        raise FinalManuscriptConfirmationError("Final citation audit does not cover the current manuscript.") from exc
    applied_at = str(completion.get("applied_at") or "")
    audit_at = str(citation.get("generated_at") or "")
    if applied_at and audit_at and audit_at <= applied_at:
        raise FinalManuscriptConfirmationError("Final citation audit must run after manuscript completion.")
    integrity = _read_json(project_path / "integrity" / "integrity_report.json")
    if not _is_passing(integrity):
        raise FinalManuscriptConfirmationError("Final integrity report is missing or not passing.")
    quality = _read_json(project_path / "quality_checks" / "quality_report.json")
    if not _is_passing(quality):
        raise FinalManuscriptConfirmationError("Final quality report is missing or not passing.")
    reviews = _read_json(project_path / "quality_checks" / "blind_reviews" / "aggregate.json")
    if not _is_passing(reviews) or int(reviews.get("reviewer_count") or 0) < 2:
        raise FinalManuscriptConfirmationError("Independent review aggregate is missing, not passing, or has fewer than two reviewers.")
    evidence = _read_json(project_path / "results" / "promoted_evidence_snapshot.json")
    if not evidence.get("snapshot_id"):
        raise FinalManuscriptConfirmationError("Promoted evidence snapshot is missing an evidence snapshot ID.")
    pdf = project_path / "latex" / "main.pdf"
    if not pdf.is_file() or pdf.stat().st_size == 0:
        raise FinalManuscriptConfirmationError("Final PDF is missing or empty.")
    return {
        "completion_packet_id": completion.get("packet_id"),
        "completion_packet_hash": completion.get("packet_hash"),
        "citation_audit_snapshot_id": current_citation_snapshot.get("snapshot_id"),
        "evidence_snapshot_id": evidence.get("snapshot_id"),
    }


def _records(project_path: Path) -> list[dict[str, Any]]:
    _validate_release_semantics(project_path)
    missing = [relative for relative in ARTIFACTS if not (project_path / relative).is_file()]
    if missing:
        raise FinalManuscriptConfirmationError("Final manuscript packet is incomplete: " + ", ".join(missing))
    return [{"path": relative, "sha256": _hash(project_path / relative), "size_bytes": (project_path / relative).stat().st_size} for relative in ARTIFACTS]


def current_release_hash(project: str | Path) -> str:
    state = load_project(project)
    encoded = json.dumps(_records(state.path), sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def review_final_manuscript(project: str | Path) -> dict[str, Any]:
    state = load_project(project)
    context = _validate_release_semantics(state.path)
    records = _records(state.path)
    release_hash = current_release_hash(state.path)
    packet = {
        "schema_version": "dpl.final_manuscript_confirmation_packet.v1",
        "status": "ready_for_human_review",
        "generated_at": utc_now(),
        "project_id": state.metadata.get("project_id"),
        "release_hash": release_hash,
        "artifacts": records,
        **context,
        "confirmation_semantics": "Confirm the final PDF, final citation audit, both independent blind reviews, unresolved minor findings, and publication boundary as one release.",
    }
    _write_json(state.path / PACKET_JSON, packet)
    lines = [
        "# 最终论文确认",
        "",
        "本页面集中展示最终 PDF、最终引用核查、两位独立盲评和质量报告。确认后，这些内容作为同一发布版本冻结。",
        "",
        f"Release hash: `{release_hash}`",
        "",
        "## 发布产物",
        "",
    ]
    lines.extend(f"- `{item['path']}`" for item in records)
    write_html_report(state.path / PACKET_HTML, "\n".join(lines), title="最终论文确认")
    return {"status": "ready_for_human_review", "project_path": str(state.path), "release_hash": release_hash, "review_packet": PACKET_HTML}


def confirm_final_manuscript(project: str | Path, *, release_hash: str) -> dict[str, Any]:
    state = load_project(project)
    packet_path = state.path / PACKET_JSON
    if not packet_path.exists():
        raise FinalManuscriptConfirmationError("Run review-final-manuscript before confirmation.")
    packet = json.loads(packet_path.read_text(encoding="utf-8-sig"))
    try:
        current = current_release_hash(state.path)
    except FinalManuscriptConfirmationError as exc:
        raise FinalManuscriptConfirmationError(
            "The release hash cannot be confirmed because a bound final artifact changed: " + str(exc)
        ) from exc
    if release_hash != current or packet.get("release_hash") != current:
        raise FinalManuscriptConfirmationError("The supplied release hash does not match the current final manuscript packet.")
    confirmation = {
        "schema_version": "dpl.final_manuscript_confirmation.v1",
        "status": "approved",
        "confirmed_at": utc_now(),
        "project_id": state.metadata.get("project_id"),
        "release_hash": current,
        "artifacts": packet.get("artifacts") or [],
    }
    _write_json(state.path / CONFIRMATION_JSON, confirmation)
    return {"status": "approved", "project_path": str(state.path), "release_hash": current, "confirmation": CONFIRMATION_JSON}


def final_confirmation_state(project: str | Path) -> dict[str, Any]:
    state = load_project(project)
    confirmation_path = state.path / CONFIRMATION_JSON
    if not confirmation_path.exists():
        return {"status": "awaiting_confirmation", "current": False}
    confirmation = json.loads(confirmation_path.read_text(encoding="utf-8-sig"))
    try:
        current = current_release_hash(state.path)
    except FinalManuscriptConfirmationError as exc:
        return {"status": "incomplete", "current": False, "reason": str(exc)}
    matches = confirmation.get("release_hash") == current
    return {"status": "approved" if matches else "release_drift", "current": matches, "release_hash": current}
