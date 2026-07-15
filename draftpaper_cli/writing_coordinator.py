"""Formal section preparation, Agent composition, editor, acceptance, and release routing."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .artifact_repository import ArtifactRepository
from .project_state import load_project


SECTION_STAGE_MAP = {
    "results": "results", "introduction": "introduction", "data_writing": "data",
    "methods_writing": "methods", "discussion": "discussion",
}
SECTION_PRECONDITIONS = {
    "results": ("results/result_manifest.yaml", "inventory-results"),
    "data": ("data/data_writing_context.json", "build-data-context"),
    "methods": ("methods/method_writing_context.json", "build-method-context"),
}
SECTION_ACTIVE_ARTIFACTS = {
    "results": "results/results.tex",
    "introduction": "introduction/introduction.tex",
    "data": "data/data.tex",
    "methods": "methods/methods.tex",
    "discussion": "discussion/discussion.tex",
}
SECTION_WRITER_COMMANDS = {
    "results": "write-results",
    "introduction": "write-introduction",
    "data": "write-data",
    "methods": "write-methods",
    "discussion": "write-discussion",
}


def _quote(path: Path) -> str:
    return f'"{path}"'


def _cli(project_path: Path, command: str) -> str:
    return f"python -m draftpaper_cli.cli {command} --project {_quote(project_path)}"


def _text_hash(path: Path) -> str:
    return hashlib.sha256(path.read_text(encoding="utf-8-sig").encode("utf-8")).hexdigest() if path.is_file() else ""


def section_lifecycle_action(project_path: Path, section: str) -> dict[str, Any] | None:
    repo = ArtifactRepository(project_path)
    precondition = SECTION_PRECONDITIONS.get(section)
    stage_name = next((stage for stage, mapped in SECTION_STAGE_MAP.items() if mapped == section), section)
    stage_meta = ((load_project(project_path).metadata.get("stages") or {}).get(stage_name) or {})
    stage_precondition_current = stage_meta.get("status") in {"draft", "approved", "completed"} and not stage_meta.get("stale")
    if precondition and (not repo.resolve(precondition[0]).is_file() or not stage_precondition_current):
        return {"stage": next(stage for stage, mapped in SECTION_STAGE_MAP.items() if mapped == section), "command": precondition[1], "cli": _cli(project_path, precondition[1]), "reason": f"Build the scientific {section} context before preparing its free-writing packet.", "section": section, "writing_state": "scientific_context_required"}
    packet_path = repo.resolve(f"writing/section_packets/{section}.json")
    packet = repo.read_mapping(f"writing/section_packets/{section}.json")
    snapshot_id = str(repo.read_mapping("results/promoted_evidence_snapshot.json").get("snapshot_id") or "")
    if not snapshot_id:
        return {"stage": "core_evidence", "command": "checkpoint", "cli": _cli(project_path, "checkpoint") + " --stage core_evidence", "reason": "Formal free-prose writing requires a human-approved core-evidence snapshot.", "section": section, "writing_state": "evidence_confirmation_required"}
    if not packet_path.is_file() or str((packet.get("promoted_evidence_snapshot") or {}).get("snapshot_id") or "") != snapshot_id:
        return {"stage": f"{section}_writing_preparation", "command": "prepare-section-writing", "cli": _cli(project_path, "prepare-section-writing") + f" --section {section}", "reason": f"Prepare the current evidence packet and paragraph-level contract before composing {section}.", "section": section, "writing_state": "preparation_required"}
    draft_path = repo.resolve(f"writing/drafts/{section}.tex")
    candidate_path = repo.resolve(f"writing/candidates/{section}.tex")
    if not candidate_path.is_file() and not draft_path.is_file():
        return {"stage": f"{section}_candidate", "command": "compose-section-with-agent", "cli": None, "reason": f"Codex must compose {section} freely from the prepared packet; deterministic fallback is not formal-release eligible.", "section": section, "writing_state": "agent_composition_required", "input_packet": packet_path.relative_to(project_path).as_posix(), "output_path": draft_path.relative_to(project_path).as_posix(), "agent_instruction": str(packet.get("instruction") or "Compose scientific prose from the section packet and preserve all evidence boundaries.")}
    if draft_path.is_file() and (not candidate_path.is_file() or _text_hash(draft_path) != _text_hash(candidate_path)):
        return {"stage": f"{section}_candidate", "command": "submit-section-draft", "cli": _cli(project_path, "submit-section-draft") + f" --section {section} --input {_quote(draft_path)}", "reason": f"Validate and install the newly composed or locally revised {section} candidate.", "section": section, "writing_state": "candidate_submission_required"}
    candidate_hash = _text_hash(candidate_path)
    validation = repo.read_mapping(f"writing/section_validation/{section}.json")
    claim_bindings = repo.read_mapping(f"writing/claim_bindings/{section}.json")
    validation_current = (
        validation.get("composition_mode") == "codex_free_candidate"
        and str(validation.get("decision") or validation.get("status")) in {"pass", "accepted"}
        and validation.get("quality_parity_eligible") is True
        and validation.get("candidate_hash") == candidate_hash
        and validation.get("evidence_snapshot_id") == snapshot_id
        and claim_bindings.get("status") == "passed"
        and claim_bindings.get("candidate_hash") == candidate_hash
        and claim_bindings.get("evidence_snapshot_id") == snapshot_id
    )
    if not validation_current:
        return {"stage": f"{section}_candidate", "command": "submit-section-draft", "cli": _cli(project_path, "submit-section-draft") + f" --section {section} --input {_quote(candidate_path)}", "reason": f"Revalidate the {section} free-prose candidate against the current evidence snapshot.", "section": section, "writing_state": "candidate_validation_required"}
    editor = repo.read_mapping(f"writing/scientific_editor/{section}.json")
    if editor.get("source_hash") != candidate_hash:
        return {"stage": f"{section}_scientific_editor", "command": "prepare-scientific-editor", "cli": _cli(project_path, "prepare-scientific-editor") + f" --section {section} --input {_quote(candidate_path)}", "reason": f"Run the Scientific Editor on the current {section} candidate before acceptance.", "section": section, "writing_state": "editor_review_required"}
    if editor.get("decision") != "pass":
        return {"stage": f"{section}_scientific_editor", "command": "revise-section-with-agent", "cli": None, "reason": f"Apply only the paragraph-local Scientific Editor tasks for {section}, then resubmit the candidate.", "section": section, "writing_state": "editor_revision_required", "editor_report": f"writing/scientific_editor/{section}.json", "input_path": candidate_path.relative_to(project_path).as_posix(), "output_path": draft_path.relative_to(project_path).as_posix(), "revision_tasks": editor.get("tasks") or []}
    acceptance = repo.read_mapping(f"writing/section_acceptance/{section}.json")
    if not (acceptance.get("status") == "accepted" and acceptance.get("formal_release_eligible") is True and acceptance.get("candidate_hash") == candidate_hash and acceptance.get("evidence_snapshot_id") == snapshot_id):
        return {"stage": f"{section}_acceptance", "command": "accept-section-draft", "cli": _cli(project_path, "accept-section-draft") + f" --section {section}", "reason": f"Record explicit acceptance of the editor-cleared {section} candidate.", "section": section, "writing_state": "acceptance_required"}
    active_artifact = SECTION_ACTIVE_ARTIFACTS[section]
    active_path = repo.resolve(active_artifact)
    if _text_hash(active_path) != candidate_hash:
        writer_command = SECTION_WRITER_COMMANDS[section]
        return {
            "stage": stage_name,
            "command": writer_command,
            "cli": _cli(project_path, writer_command),
            "reason": (
                f"Install the accepted {section} candidate as the active manuscript section "
                "before downstream review or assembly."
            ),
            "section": section,
            "writing_state": "accepted_candidate_installation_required",
            "candidate_path": candidate_path.relative_to(project_path).as_posix(),
            "active_artifact": active_artifact,
            "candidate_hash": candidate_hash,
            "active_hash": _text_hash(active_path),
        }
    return None


def formal_writing_release_action(project_path: Path) -> dict[str, Any] | None:
    repo = ArtifactRepository(project_path)
    for section in ("results", "introduction", "data", "methods", "discussion"):
        action = section_lifecycle_action(project_path, section)
        if action:
            return action
    release = repo.read_mapping("quality/functional_quality_release.json")
    snapshot_id = str(repo.read_mapping("results/promoted_evidence_snapshot.json").get("snapshot_id") or "")
    expected_hashes = {section: _text_hash(repo.resolve(f"writing/candidates/{section}.tex")) for section in ("results", "introduction", "data", "methods", "discussion")}
    if not (release.get("decision") == "pass" and release.get("accepted_candidate_hashes") == expected_hashes and release.get("evidence_snapshot_ids") == [snapshot_id]):
        return {"stage": "functional_quality_release", "command": "assess-functional-quality-release", "cli": _cli(project_path, "assess-functional-quality-release"), "reason": "All five sections must pass free-prose acceptance before LaTeX assembly and final citation audit.", "writing_state": "release_assessment_required"}
    return None
