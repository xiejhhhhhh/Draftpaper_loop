"""One auditable transaction for bounded manuscript section revisions."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .artifact_dag import record_artifact_change
from .manuscript_composer import SectionCompositionError, accept_section_draft, submit_section_draft
from .project_scaffold import _write_json, utc_now
from .project_state import load_project
from .writing_architecture import prepare_scientific_editor


class SectionRevisionTransactionError(RuntimeError):
    """Raised when a section revision cannot commit as one bounded transaction."""


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else ""


def _classify(before: str, after: str, explicit: str | None) -> str:
    if explicit:
        return explicit
    compact_before = " ".join(before.split())
    compact_after = " ".join(after.split())
    if compact_before == compact_after:
        return "presentation_only"
    before_cites = sorted(part for part in before.split("\\cite") if part)
    after_cites = sorted(part for part in after.split("\\cite") if part)
    if before_cites != after_cites:
        return "citation_local"
    return "prose_semantic_no_evidence_change"


def apply_section_revision(
    project: str | Path,
    section: str,
    input_path: str | Path,
    change_class: str | None = None,
) -> dict[str, Any]:
    state = load_project(project)
    normalized = str(section or "").strip().lower()
    source = Path(input_path).expanduser().resolve()
    if not source.is_file():
        raise SectionRevisionTransactionError(f"Revised section does not exist: {source}")
    active = state.path / "latex" / "sections" / f"{normalized}.tex"
    before = active.read_text(encoding="utf-8-sig", errors="replace") if active.exists() else ""
    after = source.read_text(encoding="utf-8-sig", errors="replace")
    classified = _classify(before, after, change_class)
    try:
        validation = submit_section_draft(state.path, normalized, source)
        editor = prepare_scientific_editor(state.path, normalized, state.path / "writing" / "candidates" / f"{normalized}.tex")
    except SectionCompositionError as exc:
        raise SectionRevisionTransactionError(str(exc)) from exc
    committed = False
    acceptance: dict[str, Any] = {}
    if editor.get("decision") == "pass":
        acceptance = accept_section_draft(state.path, normalized)
        active.parent.mkdir(parents=True, exist_ok=True)
        active.write_text(after, encoding="utf-8")
        committed = True
    source_hash = hashlib.sha256(after.encode("utf-8")).hexdigest()
    stale = record_artifact_change(
        state.path,
        change_class=classified,
        source_artifact=f"latex/sections/{normalized}.tex",
        source_hash=source_hash,
        section=normalized,
    )
    receipt = {
        "schema_version": "dpl.section_revision_transaction.v1",
        "generated_at": utc_now(),
        "section": normalized,
        "change_class": classified,
        "before_hash": _sha(active) if not committed else hashlib.sha256(before.encode("utf-8")).hexdigest(),
        "after_hash": source_hash,
        "decision": "committed" if committed else "editor_repair_required",
        "validation": validation,
        "scientific_editor": editor,
        "acceptance": acceptance,
        "artifact_stale_report": stale,
    }
    target = state.path / "writing" / "revision_transactions" / f"{normalized}_{source_hash[:12]}.json"
    _write_json(target, receipt)
    receipt["receipt"] = target.relative_to(state.path).as_posix()
    return receipt
