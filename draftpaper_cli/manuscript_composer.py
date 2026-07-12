# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json
import hashlib
import re
from pathlib import Path
from typing import Any

from .project_scaffold import _write_json, utc_now
from .project_state import load_project
from .section_contracts import validate_section_writing
from .evidence_snapshot import EvidenceSnapshotMismatch, validate_promoted_snapshot_for_writing
from .evidence_registry import ensure_registry_consistent
from .paper_narrative import prepare_section_writing_context
from .writing_architecture import (
    build_argument_matrices,
    build_panel_writing_contracts,
    build_section_lifecycles,
    resolve_venue_style_adapter,
)


class SectionCompositionError(RuntimeError):
    """Raised when a free-form section candidate violates its writing contract."""


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


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


def _compact_registry(registry: dict[str, Any], section: str) -> dict[str, Any]:
    records = []
    for record in registry.get("records") or []:
        if not isinstance(record, dict):
            continue
        targets = [str(item).lower() for item in (record.get("target_sections") or [])]
        if targets and section not in targets:
            continue
        records.append({
            key: record.get(key)
            for key in (
                "evidence_id", "entity_role", "value", "unit", "metric_dimension",
                "run_id", "cohort_id", "sample_unit", "split", "model_id",
                "source_artifact", "confidence", "target_sections", "claim_boundary",
                "binding_complete", "missing_binding_fields",
            )
            if record.get(key) not in (None, "", [], {})
        })
    return {
        key: registry.get(key)
        for key in ("status", "schema_version", "project_id", "preferred_run_id", "policy")
        if registry.get(key) not in (None, "", [], {})
    } | {"record_count": len(records), "records": records}


def _narrative_claims(items: Any) -> list[dict[str, Any]]:
    """Registry records carry numeric facts; allocations carry prose jobs only."""
    return [
        item for item in (items or [])
        if isinstance(item, dict) and str(item.get("claim_role") or "") != "scientific_fact"
    ]


def _compact_result_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        key: manifest.get(key)
        for key in (
            "schema_version", "figures", "tables", "supporting_links",
            "claim_boundaries", "inventory_scope",
        )
        if manifest.get(key) not in (None, [], {})
    }


def _compact_resolved_evidence(resolved: dict[str, Any]) -> dict[str, Any]:
    return {
        key: resolved.get(key)
        for key in (
            "status", "schema_version", "run_id", "bound_sources",
            "anchor_verified_sources", "primary_metric", "primary_metric_selection",
            "policy", "evidence_fingerprint",
        )
        if resolved.get(key) not in (None, [], {})
    }


def _compact_paper_brief(brief: dict[str, Any]) -> dict[str, Any]:
    return {
        key: brief.get(key)
        for key in (
            "project_id", "title_or_idea", "field", "paper_pitch",
            "central_contribution", "figure_one_hook", "story_progression",
            "claim_boundaries", "reference_count",
        )
        if brief.get(key) not in (None, [], {})
    }


def _compact_writing_context(
    section: str,
    writing_context: dict[str, Any],
    argument_matrices: dict[str, Any],
    section_lifecycles: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    narrative = writing_context.get("narrative") or {}
    allocation = (narrative.get("section_claim_allocation") or {}).get("sections") or {}
    compact_narrative = {
        "paper_brief": _compact_paper_brief(narrative.get("paper_brief") or {}),
        "figure_story_arc": narrative.get("figure_story_arc") or {},
        "manuscript_argument_map": narrative.get("manuscript_argument_map") or {},
        "section_claim_allocation": {section: _narrative_claims(allocation.get(section))},
    }
    pack = writing_context.get("section_evidence_pack") or {}
    compact_pack = {
        "section": section,
        "paper_brief": _compact_paper_brief(pack.get("paper_brief") or {}),
        "allocated_claims": _narrative_claims(pack.get("allocated_claims")),
        "figure_story_links": pack.get("figure_story_links") or [],
        "reference_items": pack.get("reference_items") or [],
        "section_policy": pack.get("section_policy") or {},
        "evidence_registry_reference": "writing/scientific_evidence_registry.json",
    }
    compact_matrices: dict[str, Any] = {}
    if section == "introduction":
        compact_matrices["introduction_gap_matrix"] = argument_matrices.get("introduction_gap_matrix") or []
    elif section == "discussion":
        compact_matrices["discussion_finding_comparison_matrix"] = argument_matrices.get("discussion_finding_comparison_matrix") or []
    compact_lifecycles: dict[str, Any] = {}
    if section == "data":
        lifecycle = section_lifecycles.get("data_lifecycle") or {}
        compact_lifecycles["data_lifecycle"] = {
            key: lifecycle.get(key)
            for key in ("stages", "stage_owned_code", "forbidden_prose")
            if lifecycle.get(key) not in (None, [], {})
        }
    elif section == "methods":
        lifecycle = section_lifecycles.get("method_lifecycle") or {}
        plugin_events = [item for item in lifecycle.get("plugin_execution") or [] if isinstance(item, dict)]
        compact_lifecycles["method_lifecycle"] = {
            key: lifecycle.get(key)
            for key in (
                "stages", "stage_owned_code", "formula_contracts", "formula_coverage_status",
                "deterministic_no_formula_reason", "figure_code_trace",
                "variable_explanation_required", "forbidden_prose",
            )
            if lifecycle.get(key) not in (None, [], {})
        }
        compact_lifecycles["method_lifecycle"]["plugin_execution_summary"] = {
            "event_count": len(plugin_events),
            "plugin_ids": sorted({str(item.get("plugin_id")) for item in plugin_events if item.get("plugin_id")}),
            "statuses": sorted({str(item.get("status")) for item in plugin_events if item.get("status")}),
            "audit_source": "methods/plugin_execution_ledger.jsonl",
        }
    return compact_narrative, compact_pack, compact_matrices, compact_lifecycles


def _write_quantitative_claim_bindings(
    project_path: Path,
    section: str,
    text: str,
    validation: dict[str, Any],
    evidence_snapshot_id: str,
) -> dict[str, Any]:
    bindings = list(validation.get("numeric_claim_bindings") or [])
    report = {
        "schema_version": "v0.22.3",
        "generated_at": utc_now(),
        "section": section,
        "candidate_hash": _hash_text(text),
        "evidence_snapshot_id": evidence_snapshot_id,
        "required_binding_fields": list(validation.get("required_binding_fields") or []),
        "quantitative_claim_count": len(bindings),
        "bound_claim_count": sum(1 for item in bindings if item.get("status") == "bound"),
        "status": "passed" if all(item.get("status") == "bound" for item in bindings) else "blocked",
        "bindings": bindings,
        "policy": "Every quantitative manuscript claim must resolve to one complete evidence/run/cohort/unit/split/model/dimension binding.",
    }
    target = project_path / "writing" / "claim_bindings" / f"{section}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    _write_json(target, report)
    return report


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
    existing_registry = _read_json(state.path / "writing" / "scientific_evidence_registry.json")
    registry = (
        ensure_registry_consistent(state.path)
        if promoted_snapshot.get("snapshot_id") or not existing_registry.get("records")
        else existing_registry
    )
    results_narrative_contract: dict[str, Any] = {}
    if normalized == "results":
        from .manuscript_quality import build_results_narrative_contract

        results_narrative_contract = build_results_narrative_contract(state.path)
    writing_context = prepare_section_writing_context(state.path, normalized)
    argument_matrices = build_argument_matrices(state.path)
    section_lifecycles = build_section_lifecycles(state.path)
    panel_contracts = build_panel_writing_contracts(state.path) if normalized in {"results", "discussion"} else {}
    venue_style = resolve_venue_style_adapter(state.path)
    compact_narrative, compact_pack, compact_matrices, compact_lifecycles = _compact_writing_context(
        normalized, writing_context, argument_matrices, section_lifecycles,
    )
    resolved_evidence = _read_json(state.path / "results" / "resolved_result_evidence.json")
    result_manifest = _read_json(state.path / "results" / "result_manifest.yaml")
    packet = {
        "schema_version": "v0.23.1",
        "generated_at": utc_now(),
        "section": normalized,
        "composition_mode": "outline_then_codex_free_writing_with_post_validation",
        "scientific_evidence_registry": _compact_registry(registry, normalized),
        "resolved_result_evidence": _compact_resolved_evidence(resolved_evidence),
        "result_manifest": _compact_result_manifest(result_manifest),
        "results_narrative_contract": results_narrative_contract,
        "promoted_evidence_snapshot": promoted_snapshot,
        "paper_narrative": compact_narrative,
        "section_evidence_pack": compact_pack,
        "section_outline": writing_context.get("section_outline") or {},
        "results_synthesis_plan": writing_context.get("results_synthesis_plan") or {},
        "argument_matrices": compact_matrices,
        "section_reasoning_inputs": (
            argument_matrices.get("introduction_gap_matrix", []) if normalized == "introduction"
            else argument_matrices.get("discussion_finding_comparison_matrix", []) if normalized == "discussion"
            else (section_lifecycles.get("data_lifecycle", {}).get("stages", []) if normalized == "data"
                  else section_lifecycles.get("method_lifecycle", {}).get("stages", []) if normalized == "methods"
                  else (writing_context.get("results_synthesis_plan") or {}).get("finding_blocks", []))
        ),
        "section_lifecycles": compact_lifecycles,
        "panel_figure_contracts": panel_contracts,
        "venue_style_adapter": venue_style,
        "audit_sources": {
            "scientific_evidence_registry": "writing/scientific_evidence_registry.json",
            "resolved_result_evidence": "results/resolved_result_evidence.json",
            "result_manifest": "results/result_manifest.yaml",
            "section_lifecycles": "writing/section_lifecycles.json",
            "note": "Full audit ledgers remain on disk; this packet contains the active section slice.",
        },
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
        "agent_draft_path": f"writing/drafts/{normalized}.tex",
        "candidate_path": f"writing/candidates/{normalized}.tex",
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
    if mode == "deterministic_offline_fallback":
        binding_issue_kinds = {
            "unsupported_numeric_claim",
            "numeric_claim_scope_mismatch",
            "incomplete_evidence_binding",
            "ambiguous_numeric_claim_binding",
        }
        for issue in report.get("issues") or []:
            if issue.get("kind") in binding_issue_kinds:
                issue["severity"] = "diagnostic_warning"
        report["decision"] = (
            "blocked" if any(issue.get("severity") == "blocking" for issue in report.get("issues") or []) else "pass"
        )
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
    report["candidate_hash"] = _hash_text(text) if candidate_path.exists() else ""
    claim_bindings = _write_quantitative_claim_bindings(
        state.path, normalized, text, report, report["evidence_snapshot_id"]
    )
    report["claim_binding_report"] = f"writing/claim_bindings/{normalized}.json"
    report["claim_binding_status"] = claim_bindings["status"]
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
    evidence_snapshot_id = str(
        (packet.get("promoted_evidence_snapshot") or {}).get("snapshot_id") or "legacy_unpromoted"
    )
    claim_bindings = _write_quantitative_claim_bindings(
        state.path, normalized, text, report, evidence_snapshot_id
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
        "quality_parity_eligible": report.get("functional_job_coverage", {}).get("decision") == "pass",
        "status": "accepted",
        "composition_mode": "codex_free_candidate",
        "candidate_path": target.relative_to(state.path).as_posix(),
        "candidate_hash": _hash_text(text),
        "evidence_snapshot_id": str(
            (packet.get("promoted_evidence_snapshot") or {}).get("snapshot_id") or "legacy_unpromoted"
        ),
        "claim_binding_report": f"writing/claim_bindings/{normalized}.json",
        "claim_binding_status": claim_bindings["status"],
    })
    validation_dir = state.path / "writing" / "section_validation"
    validation_dir.mkdir(parents=True, exist_ok=True)
    _write_json(validation_dir / f"{normalized}.json", report)
    return report


def accept_section_draft(project: str | Path, section: str) -> dict[str, Any]:
    """Accept an editor-cleared free-prose candidate for formal manuscript writing."""
    state = load_project(project)
    normalized = str(section or "").strip().lower()
    if normalized not in {"introduction", "data", "methods", "results", "discussion"}:
        raise SectionCompositionError(f"Unsupported manuscript section: {normalized}")
    candidate_path = state.path / "writing" / "candidates" / f"{normalized}.tex"
    if not candidate_path.is_file():
        raise SectionCompositionError(f"No submitted free-prose candidate exists for {normalized}.")
    text = candidate_path.read_text(encoding="utf-8-sig")
    candidate_hash = _hash_text(text)
    validation = _read_json(state.path / "writing" / "section_validation" / f"{normalized}.json")
    editor = _read_json(state.path / "writing" / "scientific_editor" / f"{normalized}.json")
    claim_bindings = _read_json(state.path / "writing" / "claim_bindings" / f"{normalized}.json")
    packet = build_section_evidence_packet(state.path, normalized)
    snapshot_id = str((packet.get("promoted_evidence_snapshot") or {}).get("snapshot_id") or "legacy_unpromoted")
    if (
        validation.get("composition_mode") != "codex_free_candidate"
        or str(validation.get("decision") or validation.get("status")) not in {"pass", "accepted"}
        or validation.get("quality_parity_eligible") is not True
        or validation.get("candidate_hash") != candidate_hash
        or validation.get("evidence_snapshot_id") != snapshot_id
    ):
        raise SectionCompositionError(f"The {normalized} candidate has not passed its current evidence and writing contract.")
    if editor.get("source_hash") != candidate_hash or editor.get("decision") != "pass":
        raise SectionCompositionError(f"The {normalized} candidate still requires Scientific Editor review or local repair.")
    if (
        claim_bindings.get("status") != "passed"
        or claim_bindings.get("candidate_hash") != candidate_hash
        or claim_bindings.get("evidence_snapshot_id") != snapshot_id
    ):
        raise SectionCompositionError(f"The {normalized} candidate has incomplete or stale quantitative evidence bindings.")
    report = {
        "schema_version": "v0.22.2",
        "generated_at": utc_now(),
        "section": normalized,
        "status": "accepted",
        "decision": "accepted",
        "composition_mode": "codex_free_candidate",
        "candidate_path": candidate_path.relative_to(state.path).as_posix(),
        "candidate_hash": candidate_hash,
        "evidence_snapshot_id": snapshot_id,
        "editor_report": f"writing/scientific_editor/{normalized}.json",
        "claim_binding_report": f"writing/claim_bindings/{normalized}.json",
        "formal_release_eligible": True,
    }
    target = state.path / "writing" / "section_acceptance" / f"{normalized}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    _write_json(target, report)
    return report
