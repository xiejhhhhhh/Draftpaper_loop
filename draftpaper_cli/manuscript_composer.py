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
from .paper_narrative import build_section_outline, prepare_section_writing_context
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
    evidence_ids = []
    for record in registry.get("records") or []:
        if not isinstance(record, dict):
            continue
        targets = [str(item).lower() for item in (record.get("target_sections") or [])]
        if targets and section not in targets:
            continue
        if record.get("evidence_id"):
            evidence_ids.append(str(record["evidence_id"]))
    return {
        key: registry.get(key)
        for key in ("status", "schema_version", "project_id", "preferred_run_id", "policy")
        if registry.get(key) not in (None, "", [], {})
    } | {
        "record_count": len(evidence_ids),
        "evidence_ids": evidence_ids,
        "records_omitted_from_packet": True,
        "registry_reference": "writing/scientific_evidence_registry.json",
    }


def _narrative_claims(items: Any) -> list[dict[str, Any]]:
    """Registry records carry numeric facts; allocations carry prose jobs only."""
    return [
        item for item in (items or [])
        if isinstance(item, dict) and str(item.get("claim_role") or "") != "scientific_fact"
    ]


def _compact_result_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    figure_fields = (
        "id", "path", "figure_role", "manuscript_role", "storyboard_id",
        "figure_group", "scientific_question", "caption_draft", "result_claim",
        "claim_boundary", "linked_main_figure",
    )
    table_fields = ("id", "path", "table_role", "caption_draft", "result_claim", "storyboard_id", "figure_group")
    figures = [
        {key: item.get(key) for key in figure_fields if item.get(key) not in (None, "", [], {})}
        for item in manifest.get("figures") or [] if isinstance(item, dict)
    ]
    tables = [
        {key: item.get(key) for key in table_fields if item.get(key) not in (None, "", [], {})}
        for item in manifest.get("tables") or [] if isinstance(item, dict)
    ]
    return {
        "schema_version": manifest.get("schema_version"),
        "figures": figures,
        "tables": tables,
        "supporting_links": manifest.get("supporting_links") or [],
        "inventory_scope": manifest.get("inventory_scope"),
        "full_manifest_reference": "results/result_manifest.yaml",
    }


def _compact_results_contract(contract: dict[str, Any]) -> dict[str, Any]:
    groups = []
    for item in contract.get("figure_groups") or []:
        if not isinstance(item, dict):
            continue
        groups.append({
            key: item.get(key)
            for key in (
                "figure_id", "narrative_role", "scientific_question", "expected_finding",
                "claim_boundary", "required_reasoning",
            )
            if item.get(key) not in (None, "", [], {})
        })
    verified_metrics = [
        {
            key: item.get(key)
            for key in ("metric_name", "value", "run_id", "model_id", "cohort_id", "split")
            if item.get(key) not in (None, "", [], {})
        }
        for item in contract.get("verified_metrics") or [] if isinstance(item, dict)
    ]
    return {
        key: contract.get(key)
        for key in ("status", "schema_version", "project_id", "minimum_quality_score", "policy")
        if contract.get(key) not in (None, "", [], {})
    } | {
        "figure_groups": groups,
        "verified_metrics": verified_metrics,
        "verified_metrics_reference": "writing/scientific_evidence_registry.json",
    }


def _compact_panel_contracts(payload: dict[str, Any]) -> dict[str, Any]:
    groups = []
    for group in payload.get("figure_groups") or []:
        if not isinstance(group, dict):
            continue
        panels = []
        for panel in group.get("panels") or []:
            if not isinstance(panel, dict):
                continue
            panels.append({
                "panel_id": panel.get("panel_id"),
                "contract": panel.get("contract") or {},
                "status": panel.get("status"),
                "missing_contract_fields": panel.get("missing_contract_fields") or [],
                "no_weaker_substitute": bool(panel.get("no_weaker_substitute", True)),
            })
        groups.append({"figure_group_id": group.get("figure_group_id"), "panels": panels})
    return {
        "schema_version": payload.get("schema_version"),
        "figure_groups": groups,
        "observed_metadata_reference": "results/figure_metadata.json",
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
        "allocated_claims": _narrative_claims(pack.get("allocated_claims")),
        "reference_items": pack.get("reference_items") or [],
        "section_policy": pack.get("section_policy") or {},
        "evidence_registry_reference": "writing/scientific_evidence_registry.json",
        "full_pack_reference": f"writing/section_evidence_packs/{section}.json",
    }
    if section not in {"results", "discussion"}:
        compact_pack["paper_brief"] = _compact_paper_brief(pack.get("paper_brief") or {})
    if section != "results":
        compact_pack["figure_story_links"] = pack.get("figure_story_links") or []
    if section == "data":
        compact_pack["data_writing_contract"] = pack.get("data_writing_contract") or {}
    elif section == "methods":
        compact_pack["method_writing_contract"] = pack.get("method_writing_contract") or {}
    if section in {"results", "discussion"}:
        compact_pack["model_comparison_contract"] = pack.get("model_comparison_contract") or {}
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
    # The outline has already consolidated claims into paragraph-sized jobs.
    # Counting the underlying reasoning rows again penalizes deliberate synthesis
    # and pushes free prose back toward one-claim-per-paragraph templates.
    expected_jobs = len(outline_jobs) if outline_jobs else max(len(reasoning), 1)
    paragraph_coverage = min(1.0, len(paragraphs) / expected_jobs)
    plain = re.sub(r"\\[A-Za-z]+\*?(?:\[[^\]]*\])?(?:\{[^{}]*\})?", " ", text)
    plain = re.sub(r"\s+", " ", plain).lower()
    role_patterns = {
        "introduction": [
            r"\b(?:known|established|reported|observed|shown|demonstrated|evidence)\b",
            r"\b(?:gap|unknown|unclear|unresolved|remains|however|yet|insufficient|not by itself)\b",
            r"\b(?:we test|we investigate|we (?:therefore )?ask|this study|here we|our aim|research question)\b",
        ],
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
    from .evidence_resolver import EvidenceResolutionError, estimate_tokens, resolve_figure_evidence, resolve_paragraph_evidence

    try:
        paragraph_context = resolve_paragraph_evidence(
            state.path,
            normalized,
            outline=writing_context.get("section_outline") or {},
        )
    except EvidenceResolutionError as exc:
        if not str(exc).startswith("outline_evidence_gap:"):
            raise
        # An outline can predate the latest evidence registry. Rebuild it once
        # from current IDs; never fill the gap with arbitrary first-N records.
        refreshed_outline = build_section_outline(state.path, normalized)
        paragraph_context = resolve_paragraph_evidence(state.path, normalized, outline=refreshed_outline)
    figure_evidence = {}
    if normalized in {"results", "discussion"} and resolved_evidence:
        figure_evidence = resolve_figure_evidence(state.path)
    packet = {
        "schema_version": "v0.23.1",
        "generated_at": utc_now(),
        "section": normalized,
        "composition_mode": "outline_then_codex_free_writing_with_post_validation",
        "scientific_evidence_registry": _compact_registry(registry, normalized),
        "resolved_result_evidence": _compact_resolved_evidence(resolved_evidence),
        "result_manifest": _compact_result_manifest(result_manifest),
        "results_narrative_contract": _compact_results_contract(results_narrative_contract) if results_narrative_contract else {},
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
                  else {
                      "job_count": len((writing_context.get("results_synthesis_plan") or {}).get("finding_blocks", [])),
                      "artifact": "writing/results_synthesis_plan.json",
                  })
        ),
        "section_lifecycles": compact_lifecycles,
        "panel_figure_contracts": _compact_panel_contracts(panel_contracts) if panel_contracts else {},
        "venue_style_adapter": venue_style,
        "section_context_index": paragraph_context,
        "figure_evidence_resolution": {
            "status": figure_evidence.get("status"),
            "run_id": figure_evidence.get("run_id"),
            "story_role_counts": figure_evidence.get("story_role_counts") or {},
            "artifact": "results/figure_evidence_resolution.json" if figure_evidence else None,
        },
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
            "available_data_or_model_provenance_must_be_reported_or_explicitly_bounded": normalized in {"data", "methods"},
            "incremental_or_conditional_model_claim_requires_verified_nested_preprocessing": normalized in {"results", "discussion"},
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
            "For Data and Methods, treat the provenance and reproducibility contracts as manuscript evidence: report material "
            "source products, selection and transformation rules, quality thresholds, model identifiers, execution semantics, "
            "and explicitly unavailable reproducibility fields without inventing them. For Results and Discussion, inspect the "
            "model-comparison contract before naming a difference: use incremental or conditional contribution language only "
            "for verified nested variants, and otherwise describe the exact pipeline-performance contrast. The completed draft is accepted only "
            "after deterministic evidence and quality validation."
        ),
        "agent_draft_path": f"writing/drafts/{normalized}.tex",
        "candidate_path": f"writing/candidates/{normalized}.tex",
    }
    packet["estimated_input_tokens"] = estimate_tokens(packet)
    packet["hard_token_budget"] = paragraph_context.get("budget")
    packet["within_token_budget"] = packet["estimated_input_tokens"] <= int(packet["hard_token_budget"] or 0)
    if not packet["within_token_budget"]:
        raise SectionCompositionError(
            f"{normalized.capitalize()} evidence packet requires {packet['estimated_input_tokens']} estimated tokens, "
            f"above the hard budget {packet['hard_token_budget']}. Split or compact paragraph jobs before writing."
        )
    output = state.path / "writing" / "section_packets" / f"{normalized}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    _write_json(output, packet)
    from .stage_receipts import record_stage_receipt

    record_stage_receipt(
        state.path,
        stage=normalized,
        task_id=f"prepare-section-writing:{normalized}",
        input_artifacts=[
            "writing/scientific_evidence_registry.json",
            "results/resolved_result_evidence.json",
            "results/result_manifest.yaml",
        ],
        estimated_input_tokens=packet["estimated_input_tokens"],
        status="packet_prepared",
    )
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
        _read_json(state.path / "writing" / "scientific_evidence_registry.json"),
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
        _read_json(state.path / "writing" / "scientific_evidence_registry.json"),
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
