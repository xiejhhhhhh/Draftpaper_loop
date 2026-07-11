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
from .paper_narrative import prepare_section_writing_context
from .writing_architecture import (
    build_argument_matrices,
    build_panel_writing_contracts,
    build_section_lifecycles,
    resolve_venue_style_adapter,
)


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


def _functional_job_coverage(section: str, text: str, packet: dict[str, Any]) -> dict[str, Any]:
    """Measure scientific paragraph jobs without prescribing sentence templates."""
    paragraphs = [item.strip() for item in re.split(r"\n\s*\n", text) if item.strip() and not item.lstrip().startswith("\\section")]
    outline_jobs = [item for item in (packet.get("section_outline") or {}).get("paragraphs") or [] if isinstance(item, dict)]
    reasoning = packet.get("section_reasoning_inputs") or []
    expected_jobs = max(len(outline_jobs), len(reasoning), 1)
    paragraph_coverage = min(1.0, len(paragraphs) / expected_jobs)
    plain = re.sub(r"\\[A-Za-z]+\*?(?:\[[^\]]*\])?(?:\{[^{}]*\})?", " ", text)
    plain = re.sub(r"\s+", " ", plain).lower()
    role_patterns = {
        "introduction": [r"\b(?:known|established|reported|observed|evidence)\b", r"\b(?:gap|unknown|unclear|unresolved|remains|however)\b", r"\b(?:we test|we investigate|this study|here we|our aim|research question)\b"],
        "data": [r"\b(?:source|survey|database|registry|cohort|sample|observations?)\b", r"\b(?:processed|filtered|aligned|normalized|quality|excluded|transformed)\b", r"\b(?:coverage|missing|subset|boundary|eligible|held[- ]out|split)\b"],
        "methods": [r"\b(?:constructed|representation|features?|tokens?|estimator|model|fit)\b", r"\b(?:objective|loss|optimized|inference|algorithm|equation|deterministic)\b", r"\b(?:validation|cross[- ]validation|held[- ]out|metrics?|ablation|uncertainty|robustness)\b"],
        "results": [r"\b(?:showed|revealed|observed|increased|decreased|outperformed|difference|association|pattern)\b", r"\b(?:figure|table|panel|supplement|appendix)\b", r"\b(?:however|limited|within|boundary|uncertainty|robust|sensitivity)\b"],
        "discussion": [r"\b(?:finding|result|indicates|suggests|implies|interpret)\b", r"\b(?:consistent|contrast|compared|previous|prior|literature|reported)\b", r"\b(?:because|mechanism|may reflect|could arise|explain)\b", r"\b(?:limitation|boundary|generaliz|uncertainty|future|caution)\b"],
    }
    patterns = role_patterns.get(section, [])
    covered_roles = [pattern for pattern in patterns if re.search(pattern, plain, flags=re.I)]
    role_coverage = len(covered_roles) / max(len(patterns), 1) if patterns else 1.0
    figure_support = 1.0
    if section in {"results", "discussion"}:
        story_groups = (packet.get("paper_narrative") or {}).get("figure_story_arc", {}).get("figure_groups") or []
        supporting = sum(len(item.get("supporting_artifact_ids") or []) for item in story_groups if isinstance(item, dict))
        if story_groups:
            has_figure_language = bool(re.search(r"\\(?:ref|autoref|cref)\{|\b(?:figure|panel|table|appendix|supplement)\b", text, flags=re.I))
            has_support_language = supporting == 0 or bool(re.search(r"\b(?:appendix|supplement|diagnostic|robustness|sensitivity|ablation|uncertainty)\b", plain))
            figure_support = (float(has_figure_language) + float(has_support_language)) / 2.0
    score = 0.45 * paragraph_coverage + 0.4 * role_coverage + 0.15 * figure_support
    return {
        "score": round(score, 4), "paragraph_coverage": round(paragraph_coverage, 4),
        "role_coverage": round(role_coverage, 4), "figure_support_coverage": round(figure_support, 4),
        "expected_paragraph_jobs": expected_jobs, "observed_paragraphs": len(paragraphs),
        "decision": "pass" if score >= 0.8 else "revise",
        "policy": "Functional jobs are checked; sentence wording and paragraph style remain free.",
    }


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
    writing_context = prepare_section_writing_context(state.path, normalized)
    argument_matrices = build_argument_matrices(state.path)
    section_lifecycles = build_section_lifecycles(state.path)
    panel_contracts = build_panel_writing_contracts(state.path) if normalized in {"results", "discussion"} else {}
    venue_style = resolve_venue_style_adapter(state.path)
    packet = {
        "schema_version": "v0.21.3",
        "generated_at": utc_now(),
        "section": normalized,
        "composition_mode": "outline_then_codex_free_writing_with_post_validation",
        "scientific_evidence_registry": registry,
        "resolved_result_evidence": _read_json(state.path / "results" / "resolved_result_evidence.json"),
        "result_manifest": _read_json(state.path / "results" / "result_manifest.yaml"),
        "results_narrative_contract": results_narrative_contract,
        "promoted_evidence_snapshot": promoted_snapshot,
        "paper_narrative": writing_context.get("narrative") or {},
        "section_evidence_pack": writing_context.get("section_evidence_pack") or {},
        "section_outline": writing_context.get("section_outline") or {},
        "results_synthesis_plan": writing_context.get("results_synthesis_plan") or {},
        "argument_matrices": argument_matrices,
        "section_reasoning_inputs": (
            argument_matrices.get("introduction_gap_matrix", []) if normalized == "introduction"
            else argument_matrices.get("discussion_finding_comparison_matrix", []) if normalized == "discussion"
            else (section_lifecycles.get("data_lifecycle", {}).get("stages", []) if normalized == "data"
                  else section_lifecycles.get("method_lifecycle", {}).get("stages", []) if normalized == "methods"
                  else (writing_context.get("results_synthesis_plan") or {}).get("finding_blocks", []))
        ),
        "section_lifecycles": section_lifecycles,
        "panel_figure_contracts": panel_contracts,
        "venue_style_adapter": venue_style,
        "hard_constraints": {
            "results_citations_forbidden": normalized == "results",
            "internal_artifact_language_forbidden": True,
            "unsupported_numeric_claims_forbidden": True,
            "formula_variables_must_be_explained": normalized == "methods",
            "outline_evidence_and_claim_boundaries_must_be_preserved": True,
        },
        "fallback_policy": {
            "allowed_for_legacy_or_offline_diagnostics": True,
            "eligible_for_quality_parity_release": False,
            "reason": "A quality-parity manuscript requires a validated free-prose candidate composed from the section outline.",
        },
        "instruction": (
            "First follow the paragraph-level section outline, then compose fluent scientific prose freely. The outline defines "
            "evidence, claim boundaries, transitions, and forbidden content; it does not prescribe sentence forms. For Results, "
            "turn each finding block into observed evidence, comparison where available, interpretation, and a calibrated limit. "
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
    coverage = _functional_job_coverage(normalized, text, packet)
    report["functional_job_coverage"] = coverage
    if mode == "deterministic_offline_fallback":
        report["quality_parity_eligible"] = False
        report["quality_parity_note"] = "Fallback prose is retained for diagnostics only; submit a free-prose candidate for a quality-parity manuscript."
    else:
        report["quality_parity_eligible"] = coverage.get("decision") == "pass"
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
    report["functional_job_coverage"] = _functional_job_coverage(normalized, text, packet)
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
        "quality_parity_eligible": report.get("functional_job_coverage", {}).get("decision") == "pass",
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
