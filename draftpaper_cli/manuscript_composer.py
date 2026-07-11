# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .project_scaffold import _write_json, utc_now
from .project_state import load_project
from .section_contracts import validate_section_writing
from .evidence_snapshot import EvidenceSnapshotMismatch, validate_promoted_snapshot_for_writing


class SectionCompositionError(RuntimeError):
    """Raised when a free-form section candidate violates its writing contract."""


def _dedupe_fallback_sentences(text: str) -> str:
    """Remove exact fallback repetition without rewriting freely composed prose."""
    pieces = re.split(r"(?<=[.!?])([ \t]+|\n+)", text)
    seen: set[str] = set()
    output: list[str] = []
    for index in range(0, len(pieces), 2):
        sentence = pieces[index]
        separator = pieces[index + 1] if index + 1 < len(pieces) else ""
        normalized = re.sub(r"\\[A-Za-z]+(?:\{[^}]*\})?", " ", sentence)
        normalized = re.sub(r"\s+", " ", normalized).strip().lower()
        if len(re.findall(r"[A-Za-z]+", normalized)) >= 8 and normalized in seen:
            continue
        if normalized:
            seen.add(normalized)
        output.extend([sentence, separator])
    return "".join(output).strip() + ("\n" if text.endswith("\n") else "")


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def build_section_evidence_packet(project: str | Path, section: str) -> dict[str, Any]:
    """Expose structured evidence and constraints without prescribing paragraph wording."""
    state = load_project(project)
    normalized = str(section or "").strip().lower()
    try:
        promoted_snapshot = validate_promoted_snapshot_for_writing(state.path)
    except EvidenceSnapshotMismatch as exc:
        raise SectionCompositionError(str(exc)) from exc
    registry = _read_json(state.path / "writing" / "scientific_evidence_registry.json")
    results_narrative_contract: dict[str, Any] = {}
    if normalized == "results":
        from .manuscript_quality import build_results_narrative_contract

        results_narrative_contract = build_results_narrative_contract(state.path)
    packet = {
        "schema_version": "v0.17.6",
        "generated_at": utc_now(),
        "section": normalized,
        "composition_mode": "codex_free_writing_with_post_validation",
        "scientific_evidence_registry": registry,
        "resolved_result_evidence": _read_json(state.path / "results" / "resolved_result_evidence.json"),
        "result_manifest": _read_json(state.path / "results" / "result_manifest.yaml"),
        "results_narrative_contract": results_narrative_contract,
        "promoted_evidence_snapshot": promoted_snapshot,
        "hard_constraints": {
            "results_citations_forbidden": normalized == "results",
            "internal_artifact_language_forbidden": True,
            "unsupported_numeric_claims_forbidden": True,
            "formula_variables_must_be_explained": normalized == "methods",
        },
        "instruction": (
            "Compose the section freely from the supplied scientific evidence. Paragraph order and sentence form are not "
            "templated. For Results, treat each narrative-contract role as a distinct scientific job: establish the study "
            "boundary, diagnose pre-model signal, compare models, interpret ablations, and delimit uncertainty where present. "
            "The completed draft is accepted only after deterministic evidence and quality validation."
        ),
    }
    output = state.path / "writing" / "section_packets" / f"{normalized}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    _write_json(output, packet)
    return packet


def select_validated_section_draft(project: str | Path, section: str, fallback_text: str) -> dict[str, Any]:
    """Prefer a Codex-composed candidate; never silently replace a rejected candidate."""
    state = load_project(project)
    normalized = str(section or "").strip().lower()
    packet = build_section_evidence_packet(state.path, normalized)
    candidate_path = state.path / "writing" / "candidates" / f"{normalized}.tex"
    if candidate_path.exists():
        text = candidate_path.read_text(encoding="utf-8-sig")
        mode = "codex_free_candidate"
    else:
        text = _dedupe_fallback_sentences(fallback_text)
        mode = "deterministic_offline_fallback"
    report = validate_section_writing(
        normalized,
        text,
        packet.get("scientific_evidence_registry") or {},
    )
    report["composition_mode"] = mode
    report["evidence_snapshot_id"] = str(
        (packet.get("promoted_evidence_snapshot") or {}).get("snapshot_id") or "legacy_unpromoted"
    )
    report["candidate_path"] = candidate_path.relative_to(state.path).as_posix() if candidate_path.exists() else ""
    quality_report: dict[str, Any] = {}
    if normalized == "results" and len((packet.get("results_narrative_contract") or {}).get("figure_groups") or []) >= 3:
        from .manuscript_quality import assess_results_manuscript_quality

        quality_report = assess_results_manuscript_quality(
            state.path,
            text=text,
            contract=packet.get("results_narrative_contract") or {},
        )
        report["manuscript_quality"] = quality_report
        if mode == "codex_free_candidate" and quality_report.get("decision") != "pass":
            report["decision"] = "blocked"
            report.setdefault("issues", []).append({
                "severity": "blocking",
                "kind": "results_quality_below_target",
                "detail": f"Results quality score {quality_report.get('score')} is below 0.95.",
            })
    report_path = state.path / "writing" / "section_validation" / f"{normalized}.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    _write_json(report_path, report)
    if report.get("decision") == "blocked":
        details = "; ".join(str(item.get("detail") or item.get("kind")) for item in report.get("issues") or [])
        raise SectionCompositionError(f"{normalized.capitalize()} writing contract failed: {details}")
    return {"text": text, "composition_mode": mode, "validation_report": report, "manuscript_quality": quality_report}


def submit_section_draft(project: str | Path, section: str, input_path: str | Path) -> dict[str, Any]:
    """Validate a Codex-composed section before installing it as the active candidate."""
    state = load_project(project)
    normalized = str(section or "").strip().lower()
    if normalized not in {"introduction", "data", "methods", "results", "discussion"}:
        raise SectionCompositionError(f"Unsupported manuscript section: {normalized}")
    source = Path(input_path).expanduser().resolve()
    if not source.is_file():
        raise SectionCompositionError(f"Section draft does not exist: {source}")
    text = source.read_text(encoding="utf-8-sig")
    packet = build_section_evidence_packet(state.path, normalized)
    report = validate_section_writing(
        normalized,
        text,
        packet.get("scientific_evidence_registry") or {},
    )
    if normalized == "results" and len((packet.get("results_narrative_contract") or {}).get("figure_groups") or []) >= 3:
        from .manuscript_quality import assess_results_manuscript_quality

        quality_report = assess_results_manuscript_quality(
            state.path,
            text=text,
            contract=packet.get("results_narrative_contract") or {},
        )
        report["manuscript_quality"] = quality_report
        if quality_report.get("decision") != "pass":
            raise SectionCompositionError(
                f"Results quality contract failed: score {quality_report.get('score')} is below 0.95; "
                "revise the evidence narrative before submission."
            )
    if report.get("decision") == "blocked":
        details = "; ".join(str(item.get("detail") or item.get("kind")) for item in report.get("issues") or [])
        raise SectionCompositionError(f"{normalized.capitalize()} writing contract failed: {details}")
    target = state.path / "writing" / "candidates" / f"{normalized}.tex"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    report.update({
        "status": "accepted",
        "composition_mode": "codex_free_candidate",
        "candidate_path": target.relative_to(state.path).as_posix(),
        "evidence_snapshot_id": str(
            (packet.get("promoted_evidence_snapshot") or {}).get("snapshot_id") or "legacy_unpromoted"
        ),
    })
    validation_dir = state.path / "writing" / "section_validation"
    validation_dir.mkdir(parents=True, exist_ok=True)
    _write_json(validation_dir / f"{normalized}.json", report)
    return report
