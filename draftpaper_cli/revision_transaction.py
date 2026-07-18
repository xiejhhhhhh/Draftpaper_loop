"""One auditable transaction for bounded manuscript section revisions."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from .artifact_dag import record_artifact_change
from .change_impact import normalize_change_class
from .manuscript_artifacts import SECTION_CANONICAL_ARTIFACTS, SECTION_DERIVED_ARTIFACTS
from .manuscript_composer import SectionCompositionError, accept_section_draft, submit_section_draft
from .project_scaffold import _write_json, utc_now
from .project_state import load_project
from .scoped_transaction import ScopedProjectTransaction
from .state_kernel import atomic_write_text
from .writing_architecture import WritingArchitectureError, prepare_scientific_editor


class SectionRevisionTransactionError(RuntimeError):
    """Raised when a section revision cannot commit as one bounded transaction."""


def _classify(before: str, after: str, explicit: str | None) -> str:
    if explicit:
        return normalize_change_class(explicit)
    compact_before = " ".join(before.split())
    compact_after = " ".join(after.split())
    if compact_before == compact_after:
        return "presentation_only"
    citation_pattern = re.compile(r"\\cite[a-zA-Z*]*\s*(?:\[[^\]]*\]\s*)*\{([^}]*)\}")
    before_cites = sorted(key.strip() for group in citation_pattern.findall(before) for key in group.split(","))
    after_cites = sorted(key.strip() for group in citation_pattern.findall(after) for key in group.split(","))
    if before_cites != after_cites:
        return "citation_change"
    return "prose_only"


def apply_section_revision(
    project: str | Path,
    section: str,
    input_path: str | Path,
    change_class: str | None = None,
) -> dict[str, Any]:
    state = load_project(project)
    normalized = str(section or "").strip().lower()
    if normalized not in SECTION_CANONICAL_ARTIFACTS:
        raise SectionRevisionTransactionError(f"Unsupported manuscript section: {normalized}")
    source = Path(input_path).expanduser().resolve()
    if not source.is_file():
        raise SectionRevisionTransactionError(f"Revised section does not exist: {source}")
    canonical_relative = SECTION_CANONICAL_ARTIFACTS[normalized]
    derived_relative = SECTION_DERIVED_ARTIFACTS[normalized]
    active = state.path / canonical_relative
    before = active.read_text(encoding="utf-8-sig", errors="replace") if active.exists() else ""
    after = source.read_text(encoding="utf-8-sig", errors="replace")
    classified = _classify(before, after, change_class)
    source_hash = hashlib.sha256(after.encode("utf-8")).hexdigest()
    patterns = (
        "writing/**",
        canonical_relative,
        derived_relative,
        "project.json",
        "project.yaml",
        "*/stage_manifest.json",
        "quality_checks/stage_manifest.json",
        "token_ledger.jsonl",
    )
    try:
        with ScopedProjectTransaction(state.path, patterns) as transaction:
            validation = submit_section_draft(state.path, normalized, source)
            candidate = state.path / "writing" / "candidates" / f"{normalized}.tex"
            editor = prepare_scientific_editor(state.path, normalized, candidate)
            acceptance: dict[str, Any] = {}
            stale: dict[str, Any] = {}
            committed = editor.get("decision") == "pass"
            if committed:
                acceptance = accept_section_draft(state.path, normalized)
                atomic_write_text(active, after)
                stale = record_artifact_change(
                    state.path,
                    change_class=classified,
                    source_artifact=canonical_relative,
                    source_hash=source_hash,
                    section=normalized,
                )
            receipt = {
                "schema_version": "dpl.section_revision_transaction.v2",
                "generated_at": utc_now(),
                "section": normalized,
                "canonical_artifact": canonical_relative,
                "derived_artifact": derived_relative,
                "change_class": classified,
                "before_hash": hashlib.sha256(before.encode("utf-8")).hexdigest(),
                "after_hash": source_hash,
                "decision": "committed" if committed else "editor_repair_required",
                "validation": validation,
                "scientific_editor": editor,
                "acceptance": acceptance,
                "artifact_stale_report": stale,
                "rollback_policy": "restore_all_scoped_artifacts_on_failure",
            }
            target = state.path / "writing" / "revision_transactions" / f"{normalized}_{source_hash[:12]}.json"
            _write_json(target, receipt)
            transaction.commit()
    except (SectionCompositionError, WritingArchitectureError) as exc:
        raise SectionRevisionTransactionError(str(exc)) from exc
    receipt["receipt"] = target.relative_to(state.path).as_posix()
    return receipt
