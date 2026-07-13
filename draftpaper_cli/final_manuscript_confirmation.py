"""Final PDF, citation-audit, and independent-review confirmation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .html_utils import write_html_report
from .project_scaffold import _write_json, utc_now
from .project_state import load_project


PACKET_JSON = "review/final_manuscript_confirmation_packet.json"
PACKET_HTML = "review/final_manuscript_confirmation_packet.html"
CONFIRMATION_JSON = "review/final_manuscript_confirmation.json"
ARTIFACTS = [
    "latex/main.pdf",
    "citation_audit/final_citation_audit_report.json",
    "quality_checks/blind_reviews/aggregate.json",
    "quality_checks/blind_reviews/reviewer_01/report.md",
    "quality_checks/blind_reviews/reviewer_02/report.md",
    "quality_checks/quality_report.json",
]


class FinalManuscriptConfirmationError(RuntimeError):
    """Raised when the final release packet is incomplete or stale."""


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _records(project_path: Path) -> list[dict[str, Any]]:
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
    records = _records(state.path)
    release_hash = current_release_hash(state.path)
    packet = {
        "schema_version": "dpl.final_manuscript_confirmation_packet.v1",
        "status": "ready_for_human_review",
        "generated_at": utc_now(),
        "project_id": state.metadata.get("project_id"),
        "release_hash": release_hash,
        "artifacts": records,
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
    current = current_release_hash(state.path)
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
