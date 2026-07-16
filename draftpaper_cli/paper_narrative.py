# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

"""Paper-level narrative planning for evidence-grounded free scientific writing.

This module plans arguments and paragraph jobs instead of generating manuscript prose.
It is discipline-neutral: project-specific facts remain in research-plan, figure, run,
citation, and evidence artifacts.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .project_scaffold import _write_json, utc_now
from .project_state import load_project
from .structured_io import read_mapping


PAPER_BRIEF = "writing/paper_brief.json"
FIGURE_STORY_ARC = "writing/figure_story_arc.json"
ARGUMENT_MAP = "writing/manuscript_argument_map.json"
SECTION_ALLOCATION = "writing/section_claim_allocation.json"
SECTION_PACK_DIR = "writing/section_evidence_packs"
SECTION_OUTLINE_DIR = "writing/section_outlines"
RESULTS_SYNTHESIS_PLAN = "writing/results_synthesis_plan.json"
SECTIONS = ("introduction", "data", "methods", "results", "discussion")


class PaperNarrativeError(RuntimeError):
    """Raised when the project lacks enough evidence to plan scientific writing."""


def _read_json(path: Path) -> dict[str, Any]:
    return read_mapping(path)


def _text(value: Any, limit: int = 1100) -> str:
    result = re.sub(r"\s+", " ", str(value or "")).strip()
    return result[:limit].rstrip() + ("..." if len(result) > limit else "")


def _dedupe(values: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = _text(value, 1500)
        key = normalized.lower()
        if normalized and key not in seen:
            output.append(normalized)
            seen.add(key)
    return output


def _records(registry: dict[str, Any]) -> list[dict[str, Any]]:
    values = registry.get("records") or registry.get("evidence_records") or []
    return [item for item in values if isinstance(item, dict)]


def _read_plan_text(project_path: Path) -> str:
    for relative in (
        "research_plan/research_plan.md",
        "research_plan/research_plan.zh-CN.md",
        "research_plan/research_plan.json",
        "research_plan/claim_contract.json",
    ):
        path = project_path / relative
        if not path.exists():
            continue
        if path.suffix == ".json":
            payload = _read_json(path)
            if payload:
                return _text(payload, 12000)
        else:
            return _text(path.read_text(encoding="utf-8-sig", errors="replace"), 12000)
    return ""


def _manifest_entries(project_path: Path) -> list[dict[str, Any]]:
    manifest = _read_json(project_path / "results" / "result_manifest.yaml")
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for key, default_role in (("figures", ""), ("main_figures", "main"), ("appendix_figures", "appendix")):
        for item in manifest.get(key) or []:
            if not isinstance(item, dict):
                continue
            row = dict(item)
            row["artifact_kind"] = "figure"
            if default_role:
                row.setdefault("manuscript_role", default_role)
            identity = str(row.get("id") or row.get("path") or "")
            if identity and identity in seen:
                continue
            if identity:
                seen.add(identity)
            entries.append(row)
    for item in manifest.get("tables") or []:
        if isinstance(item, dict):
            row = dict(item)
            row["artifact_kind"] = "table"
            entries.append(row)
    return entries


def _plan_entries(project_path: Path) -> list[dict[str, Any]]:
    plan = _read_json(project_path / "results" / "figure_plan.json")
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(item: dict[str, Any], *, default_role: str = "", group_id: str = "") -> None:
        row = dict(item)
        if default_role:
            row.setdefault("manuscript_role", default_role)
        if group_id:
            row.setdefault("figure_group_id", group_id)
        identity = str(row.get("id") or row.get("figure_id") or row.get("path") or "")
        if identity and identity in seen:
            return
        if identity:
            seen.add(identity)
        entries.append(row)

    for key, default_role in (("figures", ""), ("main_figures", "main"), ("appendix_figures", "appendix")):
        for item in plan.get(key) or []:
            if isinstance(item, dict):
                add(item, default_role=default_role)
    for group_index, group in enumerate(plan.get("figure_groups") or [], start=1):
        if not isinstance(group, dict):
            continue
        group_id = str(group.get("id") or group.get("figure_group_id") or f"figure_group_{group_index}")
        group_defaults = {key: value for key, value in group.items() if key not in {"figures", "panels", "main_figures", "supporting_figures", "appendix_figures"}}
        child_sets = (("figures", ""), ("panels", "main"), ("main_figures", "main"), ("supporting_figures", "appendix"), ("appendix_figures", "appendix"))
        found_child = False
        for child_key, default_role in child_sets:
            for child in group.get(child_key) or []:
                if isinstance(child, dict):
                    found_child = True
                    add({**group_defaults, **child}, default_role=default_role, group_id=group_id)
        if not found_child:
            add(group_defaults, group_id=group_id)
    return entries


def _story_key(entry: dict[str, Any], index: int) -> str:
    if str(entry.get("manuscript_role") or "main").lower() != "appendix" and entry.get("storyboard_id"):
        return str(entry.get("storyboard_id"))
    return str(
        entry.get("figure_group_id")
        or entry.get("figure_group")
        or entry.get("parent_figure_group")
        or entry.get("storyboard_id")
        or entry.get("linked_main_figure")
        or entry.get("figure_id")
        or entry.get("id")
        or f"figure_group_{index}"
    )


def _string_ids(value: Any) -> set[str]:
    if isinstance(value, (list, tuple, set)):
        return {str(item).strip() for item in value if str(item).strip()}
    text = str(value or "").strip()
    return {text} if text else set()


def _metric_is_bound(metric: dict[str, Any], story: dict[str, Any]) -> bool:
    artifact_ids = _string_ids(story.get("main_artifact_ids")) | _string_ids(story.get("supporting_artifact_ids"))
    evidence_ids = _string_ids(story.get("evidence_ids"))
    run_ids = _string_ids(story.get("run_ids"))
    metric_artifacts = _string_ids(metric.get("figure_links")) | _string_ids(metric.get("artifact_ids")) | _string_ids(metric.get("figure_id")) | _string_ids(metric.get("source_artifact"))
    metric_evidence = _string_ids(metric.get("evidence_id")) | _string_ids(metric.get("evidence_ids"))
    metric_runs = _string_ids(metric.get("run_id")) | _string_ids(metric.get("run_ids"))
    return bool((artifact_ids & metric_artifacts) or (evidence_ids & metric_evidence) or (run_ids & metric_runs))


def _infer_narrative_job(text: str, index: int, plot_grammar: str = "") -> str:
    grammar = _text(plot_grammar).lower().replace("-", "_").replace(" ", "_")
    grammar_roles = {
        "workflow_schematic": "study_boundary",
        "data_overview": "study_boundary",
        "class_distribution": "study_boundary",
        "relationship": "premodel_signal",
        "feature_relationship": "premodel_signal",
        "model_comparison": "model_comparison",
        "ablation": "component_attribution",
        "uncertainty_summary": "error_uncertainty",
        "confusion_matrix": "error_uncertainty",
    }
    if grammar in grammar_roles:
        return grammar_roles[grammar]
    lowered = text.lower()
    keyword_roles = (
        ("ablation", "component_attribution"),
        ("feature importance", "component_attribution"),
        ("uncertainty", "error_uncertainty"),
        ("error", "error_uncertainty"),
        ("confusion", "error_uncertainty"),
        ("baseline", "model_comparison"),
        ("comparison", "model_comparison"),
        ("performance", "model_comparison"),
        ("validation", "validation_evidence"),
        ("coverage", "study_boundary"),
        ("cohort", "study_boundary"),
        ("sample", "study_boundary"),
        ("distribution", "premodel_signal"),
        ("relationship", "premodel_signal"),
        ("trend", "premodel_signal"),
    )
    for keyword, role in keyword_roles:
        if keyword in lowered:
            return role
    return "study_boundary" if index == 1 else "empirical_finding"


def _scientific_question(entry: dict[str, Any]) -> str:
    question = _text(entry.get("scientific_question") or entry.get("question"))
    if question:
        return question
    claim = _text(entry.get("result_claim") or entry.get("expected_finding"))
    return claim or "What empirical relationship or comparison does this evidence resolve?"


def _figure_story_arc(project_path: Path, entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    planned = _plan_entries(project_path)
    by_key: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(planned, start=1):
        by_key.setdefault(_story_key(item, index), item)
    groups: dict[str, list[dict[str, Any]]] = {}
    figure_entries = [item for item in entries if item.get("artifact_kind") == "figure"]
    story_anchors = figure_entries or entries
    for index, entry in enumerate(story_anchors, start=1):
        groups.setdefault(_story_key(entry, index), []).append(entry)
    if figure_entries:
        # Tables support a figure-led finding unless they explicitly declare a matching
        # story group. Unlinked tables remain available in the result manifest and
        # evidence registry, but do not become synthetic manuscript findings.
        for index, entry in enumerate(entries, start=1):
            if entry.get("artifact_kind") != "table":
                continue
            explicit_keys = [
                str(entry.get(key) or "").strip()
                for key in ("storyboard_id", "figure_group_id", "figure_group", "linked_main_figure")
            ]
            target = next((key for key in explicit_keys if key and key in groups), "")
            if target:
                groups[target].append(entry)
    if not groups:
        for index, item in enumerate(planned, start=1):
            groups.setdefault(_story_key(item, index), []).append(item)

    arc: list[dict[str, Any]] = []
    for index, (key, members) in enumerate(groups.items(), start=1):
        primary = next((item for item in members if str(item.get("manuscript_role") or "").lower() != "appendix"), members[0])
        planned_item = by_key.get(key, {})
        source = {**planned_item, **primary}
        claim = _text(source.get("result_claim") or source.get("expected_finding") or source.get("claim"))
        question = _scientific_question(source)
        role = _infer_narrative_job(
            " ".join([key, question, claim, _text(source.get("caption_draft"))]),
            index,
            _text(source.get("plot_grammar") or source.get("visual_grammar") or source.get("suggested_plot_type")),
        )
        if role == "premodel_signal" and any(term in question.lower() for term in ["outperform", "baseline", "improve over"]):
            question = "What class-dependent structure is visible in the measured feature space before model fitting?"
        appendix = [
            str(item.get("id") or item.get("path") or f"appendix_{item_index}")
            for item_index, item in enumerate(members, start=1)
            if str(item.get("manuscript_role") or "").lower() == "appendix"
        ]
        arc.append({
            "story_id": key,
            "order": index,
            "narrative_job": role,
            "scientific_question": question,
            "claim": claim,
            "claim_boundary": _text(source.get("claim_boundary") or source.get("scope_boundary")),
            "main_artifact_ids": [
                str(item.get("id") or item.get("path") or f"artifact_{member_index}")
                for member_index, item in enumerate(members, start=1)
                if str(item.get("manuscript_role") or "").lower() != "appendix"
            ],
            "supporting_artifact_ids": appendix,
            "evidence_ids": sorted(_string_ids(source.get("evidence_ids")) | _string_ids(source.get("evidence_source_ids"))),
            "run_ids": sorted(_string_ids(source.get("run_ids")) | _string_ids(source.get("run_id"))),
            "method_output": _text(source.get("method_output") or source.get("method_outputs")),
            "input_data_role": _text(source.get("input_data_role") or source.get("data_role")),
            "expected_conclusion": claim,
        })
    return arc


def _reference_items(project_path: Path) -> list[dict[str, str]]:
    summaries_dir = project_path / "references" / "literature_summaries"
    rows: list[dict[str, str]] = []
    literature_items_path = project_path / "references" / "literature_items.json"
    if literature_items_path.exists():
        try:
            literature_items = json.loads(literature_items_path.read_text(encoding="utf-8-sig"))
        except (json.JSONDecodeError, OSError):
            literature_items = []
        for item in literature_items if isinstance(literature_items, list) else []:
            if not isinstance(item, dict):
                continue
            deep = item.get("deep_summary") if isinstance(item.get("deep_summary"), dict) else {}
            rows.append({
                "citation_key": _text(item.get("bibtex_key") or item.get("citation_key") or item.get("key"), 160),
                "title": _text(item.get("title"), 360),
                "summary": _text(
                    deep.get("relevance_to_study") or deep.get("research_question")
                    or item.get("evidence_notes") or item.get("abstract"),
                    800,
                ),
                "search_contexts": [str(value) for value in item.get("search_contexts") or [] if str(value)],
            })
    if summaries_dir.exists():
        for path in summaries_dir.glob("*.json"):
            payload = _read_json(path)
            if not payload:
                continue
            rows.append({
                "citation_key": _text(payload.get("citation_key") or payload.get("key") or path.stem, 160),
                "title": _text(payload.get("title"), 360),
                "summary": _text(payload.get("summary") or payload.get("evidence_summary") or payload.get("abstract"), 800),
                "search_contexts": [str(value) for value in payload.get("search_contexts") or [] if str(value)],
            })
    deduped: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = str(row.get("citation_key") or "").strip()
        if key:
            deduped.setdefault(key, row)
    return list(deduped.values())


def _section_claims(arc: list[dict[str, Any]], records: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    allocation: dict[str, list[dict[str, Any]]] = {section: [] for section in SECTIONS}
    for item in arc:
        base = {
            "claim_id": f"claim:{item['story_id']}",
            "claim": item.get("claim") or item.get("scientific_question"),
            "claim_boundary": item.get("claim_boundary") or "Interpret only within the verified data and validation scope.",
            "figure_story_id": item["story_id"],
            "narrative_job": item["narrative_job"],
        }
        allocation["results"].append({**base, "claim_role": "observed_finding"})
        allocation["discussion"].append({**base, "claim_role": "interpretation_and_comparison"})
        allocation["introduction"].append({
            **base,
            "claim": item.get("scientific_question") or "What evidence is required to evaluate this part of the study?",
            "claim_boundary": "Frame this as an unresolved question, hypothesis, or planned comparison; do not reveal observed results.",
            "claim_role": "research_question_or_contribution",
        })
    for record in records:
        targets = {str(item).lower() for item in record.get("target_sections") or []}
        target_sections = targets & set(SECTIONS) if targets else {"data", "methods"}
        for section in target_sections:
            allocation[section].append({
                "claim_id": str(record.get("evidence_id") or record.get("entity_role") or "evidence"),
                "claim": _text(record.get("text") or record.get("claim") or record.get("entity_role")),
                "claim_boundary": _text(record.get("claim_boundary")),
                "evidence_id": str(record.get("evidence_id") or ""),
                "claim_role": "scientific_fact",
            })
    for section in allocation:
        seen: set[str] = set()
        allocation[section] = [item for item in allocation[section] if not (item["claim_id"] in seen or seen.add(item["claim_id"]))]
    return allocation


def build_paper_narrative(project: str | Path) -> dict[str, Any]:
    """Build an argument plan from approved scientific artifacts, without prose."""
    state = load_project(project)
    registry = _read_json(state.path / "writing" / "scientific_evidence_registry.json")
    records = _records(registry)
    entries = _manifest_entries(state.path)
    arc = _figure_story_arc(state.path, entries)
    plan_text = _read_plan_text(state.path)
    title = _text(state.metadata.get("title") or state.metadata.get("idea") or "the study")
    field = _text(state.metadata.get("field") or "the target discipline")
    central_claims = _dedupe([str(item.get("claim") or "") for item in arc])
    brief = {
        "schema_version": "dpl.paper_brief.v2",
        "generated_at": utc_now(),
        "project_id": state.metadata.get("project_id"),
        "title_or_idea": title,
        "field": field,
        "paper_pitch": f"This study tests a bounded, evidence-traceable contribution for {title} in {field}.",
        "central_contribution": central_claims[0] if central_claims else "The contribution is defined by the approved research question and available evidence.",
        "figure_one_hook": arc[0].get("scientific_question") if arc else "The opening result establishes the empirical setting and study boundary.",
        "research_plan_context": plan_text,
        "story_progression": [item.get("narrative_job") for item in arc],
        "claim_boundaries": _dedupe([str(item.get("claim_boundary") or "") for item in arc]),
        "reference_count": len(_reference_items(state.path)),
    }
    allocation = _section_claims(arc, records)
    argument_map = {
        "schema_version": "dpl.manuscript_argument_map.v2",
        "generated_at": utc_now(),
        "paper_pitch": brief["paper_pitch"],
        "research_question": _text(state.metadata.get("idea") or title),
        "central_contribution": brief["central_contribution"],
        "figure_story_arc": [item["story_id"] for item in arc],
        "must_run_or_downgrade": [{"story_id": item["story_id"], "missing_claim": item["claim"]} for item in arc if not item.get("claim")],
    }
    payload = {
        "paper_brief": brief,
        "figure_story_arc": {"schema_version": "dpl.figure_story_arc.v2", "generated_at": utc_now(), "figure_groups": arc},
        "manuscript_argument_map": argument_map,
        "section_claim_allocation": {"schema_version": "dpl.section_claim_allocation.v2", "generated_at": utc_now(), "sections": allocation},
    }
    _write_json(state.path / PAPER_BRIEF, brief)
    _write_json(state.path / FIGURE_STORY_ARC, payload["figure_story_arc"])
    _write_json(state.path / ARGUMENT_MAP, argument_map)
    _write_json(state.path / SECTION_ALLOCATION, payload["section_claim_allocation"])
    return payload


def _pack_item(record: dict[str, Any], section: str) -> dict[str, Any]:
    role = str(record.get("entity_role") or record.get("role") or "scientific_evidence")
    text = _text(record.get("text") or record.get("claim") or record.get("value") or role)
    return {
        "evidence_id": str(record.get("evidence_id") or role),
        "paragraph_role": "scientific_context" if section in {"introduction", "discussion"} else "scientific_method_or_data",
        "claim_role": role,
        "citation_role": "contextual" if section in {"introduction", "discussion"} else "none",
        "comparison_role": "prior_work_comparison" if section == "discussion" else "none",
        "allowed_interpretation": text,
        "forbidden_overclaim": _text(record.get("claim_boundary") or "Do not extend this evidence outside its cohort, model, split, or unit of analysis."),
        "figure_links": list(record.get("figure_ids") or record.get("figure_groups") or []),
        "formula_links": list(record.get("formula_ids") or []),
        "source_artifact": _text(record.get("source_artifact"), 400),
        "value": record.get("value"),
        "unit": _text(record.get("unit"), 80),
        "model_id": _text(record.get("model_id") or record.get("model"), 160),
        "analysis_variant": _text(record.get("analysis_variant"), 160),
        "aggregation": _text(record.get("aggregation"), 160),
    }


def _representative_story_evidence(
    evidence: list[dict[str, Any]],
    story_id: str,
    *,
    limit: int = 28,
) -> list[str]:
    """Select prompt-sized evidence while leaving the full registry authoritative."""
    matched = [
        item for item in evidence
        if item.get("evidence_id") and story_id in {str(value) for value in item.get("figure_links") or []}
    ]
    if len(matched) <= limit:
        return [str(item["evidence_id"]) for item in matched]
    high_value_tokens = {
        "sample": 10,
        "cohort": 10,
        "count": 9,
        "confusion": 10,
        "macro_f1": 10,
        "balanced_accuracy": 8,
        "roc_auc": 8,
        "delta_over_frozen": 10,
        "ci_low": 8,
        "ci_high": 8,
        "adjusted_coefficient": 10,
        "adjusted_p": 9,
        "brier": 8,
        "ece": 8,
        "separation": 9,
        "overlap": 9,
        "shared_tile": 8,
        "external": 8,
        "literature": 8,
    }
    low_value_tokens = {
        "temperature": -5,
        "threshold": -3,
        "trainable": -5,
        "average_precision": -2,
        "standard_error": -1,
    }

    def score(item: dict[str, Any]) -> tuple[int, str]:
        role = str(item.get("claim_role") or "").lower()
        value = sum(weight for token, weight in high_value_tokens.items() if token in role)
        value += sum(weight for token, weight in low_value_tokens.items() if token in role)
        if str(item.get("analysis_variant") or "").lower() in {"primary", "primary_fixed_partition"}:
            value += 3
        return value, str(item.get("evidence_id") or "")

    # First retain the strongest item for each semantic role/model/analysis layer,
    # then fill remaining space with the next most informative bound values.
    ranked = sorted(matched, key=lambda item: (-score(item)[0], score(item)[1]))
    selected: list[dict[str, Any]] = []
    signatures: set[tuple[str, str, str]] = set()
    for item in ranked:
        signature = (
            str(item.get("claim_role") or ""),
            str(item.get("model_id") or ""),
            str(item.get("analysis_variant") or ""),
        )
        if signature in signatures:
            continue
        signatures.add(signature)
        selected.append(item)
        if len(selected) >= limit:
            break
    if len(selected) < limit:
        selected_ids = {str(item.get("evidence_id") or "") for item in selected}
        for item in ranked:
            evidence_id = str(item.get("evidence_id") or "")
            if evidence_id in selected_ids:
                continue
            selected.append(item)
            selected_ids.add(evidence_id)
            if len(selected) >= limit:
                break
    return [str(item["evidence_id"]) for item in selected]


def build_section_evidence_pack(project: str | Path, section: str) -> dict[str, Any]:
    """Build a section-local evidence surface so every writer sees relevant evidence only."""
    state = load_project(project)
    normalized = str(section or "").strip().lower()
    if normalized not in SECTIONS:
        raise PaperNarrativeError(f"Unsupported manuscript section: {section}")
    narrative = build_paper_narrative(state.path)
    registry = _read_json(state.path / "writing" / "scientific_evidence_registry.json")
    records = _records(registry)
    allocation = (narrative["section_claim_allocation"].get("sections") or {}).get(normalized) or []
    selected_records = []
    for record in records:
        targets = {str(item).lower() for item in record.get("target_sections") or []}
        if not targets or normalized in targets:
            selected_records.append(_pack_item(record, normalized))
    story_arc = narrative["figure_story_arc"].get("figure_groups") or []
    relevant_stories = []
    for story in story_arc:
        if normalized in {"results", "discussion", "introduction"}:
            relevant_stories.append(story)
        elif normalized == "methods" and story.get("method_output"):
            relevant_stories.append(story)
        elif normalized == "data" and story.get("input_data_role"):
            relevant_stories.append(story)
    pack = {
        "schema_version": "dpl.section_evidence_pack.v2",
        "generated_at": utc_now(),
        "section": normalized,
        "paper_brief": narrative["paper_brief"],
        "allocated_claims": allocation,
        "evidence_items": selected_records,
        "figure_story_links": relevant_stories,
        "reference_items": _reference_items(state.path) if normalized in {"introduction", "discussion"} else [],
        "section_policy": {
            "results_citations_forbidden": normalized == "results",
            "result_values_forbidden": normalized in {"introduction", "data", "methods"},
            "internal_artifact_language_forbidden": True,
            "citation_role_required": normalized in {"introduction", "discussion"},
        },
    }
    if normalized == "data":
        data_context = _read_json(state.path / "data" / "data_writing_context.json")
        source_provenance = _read_json(state.path / "data" / "source_provenance.json")
        pack["data_writing_contract"] = {
            "source_summary": data_context.get("source_summary"),
            "processing_summary": data_context.get("processing_summary"),
            "variable_groups": data_context.get("variable_groups") or {},
            "data_key_facts": data_context.get("data_key_facts") or {},
            "label_semantics": data_context.get("label_semantics") or {},
            "claim_boundary": data_context.get("claim_boundary"),
            "source_provenance": source_provenance,
            "required_writer_topics": [
                "versioned source products or explicitly unavailable product identity",
                "selection, matching, duplicate-resolution, and join rules",
                "measurement, observation, image, or cutout construction when applicable",
                "quality thresholds, missingness states, and cohort transitions",
                "sample unit, split or grouping unit, and claim boundary",
            ],
            "provenance_policy": "Write all material provenance that is available and state unavailable fields explicitly; never infer missing product, query, transformation, or version metadata.",
            "forbidden_in_manuscript": data_context.get("forbidden_in_manuscript") or [],
        }
    elif normalized == "methods":
        method_context = _read_json(state.path / "methods" / "method_writing_context.json")
        pack["method_writing_contract"] = {
            "analysis_steps": method_context.get("analysis_steps"),
            "data_role": method_context.get("data_role"),
            "verification_summary": method_context.get("verification_summary"),
            "claim_boundary": method_context.get("claim_boundary"),
            "formula_manifest": method_context.get("formula_manifest") or {},
            "reproducibility_contract": method_context.get("reproducibility_contract") or {},
            "forbidden_in_manuscript": method_context.get("forbidden_in_manuscript") or [],
        }
    if normalized in {"results", "discussion"}:
        method_context = _read_json(state.path / "methods" / "method_writing_context.json")
        reproducibility = method_context.get("reproducibility_contract") if isinstance(method_context.get("reproducibility_contract"), dict) else {}
        pack["model_comparison_contract"] = {
            "preprocessing_components": reproducibility.get("preprocessing_components") or [],
            "implemented_components": reproducibility.get("all_implemented_components") or [],
            "comparison_semantics_policy": reproducibility.get("comparison_semantics_policy")
            or "Use incremental or conditional contribution language only for verified nested comparisons; otherwise report an exact pipeline-performance contrast.",
            "policy": "The writer must name material preprocessing differences between compared variants and may not infer nesting from model labels alone.",
        }
    target = state.path / SECTION_PACK_DIR / f"{normalized}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    _write_json(target, pack)
    return pack


def _paragraph_blueprint(section: str, pack: dict[str, Any]) -> list[dict[str, Any]]:
    claims = [item for item in pack.get("allocated_claims") or [] if isinstance(item, dict)]
    stories = [item for item in pack.get("figure_story_links") or [] if isinstance(item, dict)]
    evidence = [item for item in pack.get("evidence_items") or [] if isinstance(item, dict)]
    paragraphs: list[dict[str, Any]] = []
    if section == "results":
        if not stories:
            paragraphs.append({
                "paragraph_id": "results_finding_1",
                "objective": "Interpret the approved empirical evidence as a bounded scientific finding.",
                "required_evidence_ids": [item.get("evidence_id") for item in evidence if item.get("evidence_id")],
                "figure_or_table_links": [],
                "forbidden_content": ["literature citation", "filename or path", "claim beyond the stated boundary"],
            })
        for index, story in enumerate(stories, start=1):
            matched_ids = _representative_story_evidence(evidence, str(story.get("story_id") or ""))
            if not matched_ids and evidence:
                start = (index - 1) * len(evidence) // max(1, len(stories))
                end = index * len(evidence) // max(1, len(stories))
                matched_ids = [item.get("evidence_id") for item in evidence[start:end] if item.get("evidence_id")]
                if not matched_ids:
                    fallback_item = evidence[min(index - 1, len(evidence) - 1)]
                    matched_ids = [fallback_item.get("evidence_id")] if fallback_item.get("evidence_id") else []
            paragraphs.append({
                "paragraph_id": f"results_finding_{index}",
                "objective": f"Resolve the scientific job '{story.get('narrative_job')}' using the approved empirical evidence.",
                "required_evidence_ids": matched_ids,
                "figure_or_table_links": list(story.get("main_artifact_ids") or []) + list(story.get("supporting_artifact_ids") or []),
                "required_claim": story.get("claim") or story.get("scientific_question"),
                "transition_logic": "Explain how this finding changes the scientific interpretation before moving to the next finding.",
                "forbidden_content": ["literature citation", "filename or path", "claim beyond the stated boundary"],
            })
    elif section == "discussion":
        if not stories:
            paragraphs.append({
                "paragraph_id": "discussion_1",
                "objective": "Interpret the approved findings against compatible literature and preserve their claim boundaries.",
                "required_evidence_ids": [item.get("evidence_id") for item in evidence[:8] if item.get("evidence_id")],
                "figure_or_formula_links": [],
                "citation_intent": "Compare like with like; use citations as evidence for the stated comparison rather than as a coverage list.",
                "forbidden_content": ["internal artifact names", "unsupported metric", "conclusion outside the approved evidence boundary"],
            })
        for index, story in enumerate(stories, start=1):
            story_id = str(story.get("story_id") or "")
            matched_ids = _representative_story_evidence(evidence, story_id)
            if not matched_ids and evidence:
                start = (index - 1) * len(evidence) // max(1, len(stories))
                end = index * len(evidence) // max(1, len(stories))
                matched_ids = [item.get("evidence_id") for item in evidence[start:end] if item.get("evidence_id")]
            paragraphs.append({
                "paragraph_id": f"discussion_finding_{index}",
                "objective": "Interpret this finding, compare it with scientifically compatible literature, explain the likely mechanism or methodological contrast, and state the remaining boundary.",
                "required_evidence_ids": matched_ids,
                "allocated_claim_ids": [f"claim:{story_id}"] if story_id else [],
                "figure_or_formula_links": [story_id] if story_id else [],
                "required_claim": story.get("claim") or story.get("scientific_question"),
                "citation_intent": "Support the exact agreement, disagreement, mechanism, or comparability boundary; do not cite by topical similarity alone.",
                "transition_logic": "End with the consequence of this finding for the next part of the paper's argument.",
                "forbidden_content": ["internal artifact names", "unsupported metric", "result repetition without interpretation", "conclusion outside the approved evidence boundary"],
            })
        boundary_terms = {"uncertainty", "limitation", "selection", "coverage", "calibration", "imbalance", "missing"}
        boundary_ids = []
        for item in evidence:
            searchable = " ".join(str(item.get(key) or "") for key in ("claim_role", "allowed_interpretation", "forbidden_overclaim")).lower()
            if any(term in searchable for term in boundary_terms) and item.get("evidence_id"):
                boundary_ids.append(item.get("evidence_id"))
            if len(boundary_ids) >= 8:
                break
        if stories:
            paragraphs.append({
                "paragraph_id": "discussion_synthesis",
                "objective": "Synthesize the innovation, limitations, external-validity boundary, and the next decisive validation without repeating the Results section.",
                "required_evidence_ids": boundary_ids or [item.get("evidence_id") for item in evidence[:8] if item.get("evidence_id")],
                "allocated_claim_ids": [f"claim:{story.get('story_id')}" for story in stories if story.get("story_id")],
                "figure_or_formula_links": [str(story.get("story_id")) for story in stories if story.get("story_id")],
                "citation_intent": "Use references to delimit generalizability and motivate the next validation, not to inflate novelty.",
                "transition_logic": "Close with the maximum supported conclusion and the evidence needed to extend it.",
                "forbidden_content": ["internal artifact names", "unsupported metric", "novelty by absence of an identical title", "conclusion outside the approved evidence boundary"],
            })
    elif section == "methods":
        jobs = [
            (
                "describe sample construction, image representation, and split units",
                {"sample", "cohort", "class", "split", "source", "image", "representation", "embedding", "input"},
            ),
            (
                "explain model architecture, trainable stages, and optimization objective",
                {"model", "architecture", "training", "trainable", "optimizer", "loss", "objective", "parameter", "finetun", "probe"},
            ),
            (
                "define validation, metrics, baselines, ablations, calibration, and uncertainty",
                {"validation", "metric", "macro", "auc", "precision", "recall", "calibration", "baseline", "ablation", "seed", "uncertainty", "threshold"},
            ),
        ]
        for index, (objective, keywords) in enumerate(jobs, start=1):
            scored: list[tuple[int, str, dict[str, Any]]] = []
            for item in evidence:
                searchable = " ".join(
                    str(item.get(key) or "")
                    for key in (
                        "entity_role", "claim_role", "allowed_interpretation", "model_id",
                        "analysis_variant", "metric_dimension", "citation_role", "citation_key",
                    )
                ).lower()
                score = sum(token in searchable for token in keywords)
                if item.get("formula_ids"):
                    score += 4 if index == 2 else 1
                if item.get("citation_key") and index in {1, 2}:
                    score += 2
                if index < 3 and searchable.startswith("result_metric_"):
                    score -= 2
                scored.append((score, str(item.get("evidence_id") or ""), item))
            scored.sort(key=lambda row: (-row[0], row[1]))
            selected: list[dict[str, Any]] = []
            families: set[str] = set()
            for score, _evidence_id, item in scored:
                if score <= 0 and selected:
                    continue
                role = str(item.get("entity_role") or item.get("claim_role") or item.get("citation_key") or item.get("evidence_id") or "")
                family = re.sub(r"_\d+(?=_|$)", "", role.lower())
                if family in families:
                    continue
                selected.append(item)
                families.add(family)
                if len(selected) >= 18:
                    break
            if not selected:
                selected = evidence[:8]
            selected_ids = [str(item.get("evidence_id")) for item in selected if item.get("evidence_id")]
            paragraphs.append({
                "paragraph_id": f"methods_{index}",
                "objective": objective,
                "required_evidence_ids": selected_ids,
                "allocated_claim_ids": selected_ids,
                "figure_or_formula_links": sorted({
                    str(link)
                    for item in selected
                    for link in (item.get("formula_ids") or [])
                    if str(link)
                }),
                "citation_intent": "Cite only the method, model, or data standard directly described in this paragraph.",
                "transition_logic": "Connect the implemented operation to the next reproducibility or validation decision.",
                "forbidden_content": ["internal artifact names", "unsupported metric", "result values presented as method design"],
            })
    else:
        role_goals = {
            "introduction": ["establish the literature-backed problem", "define the unresolved gap", "state the testable question and bounded contribution"],
            "data": ["define scientific data source and access boundary", "explain processing and analytical cohort", "state coverage and claim boundary"],
            "discussion": ["interpret main findings", "compare with relevant literature", "state limitations, innovation, and next validation"],
        }
        goals = role_goals.get(section, [])
        evidence_ids = {str(item.get("evidence_id")) for item in evidence if item.get("evidence_id")}
        for index, objective in enumerate(goals, start=1):
            supporting_claims = claims[max(0, index - 1)::max(1, len(goals))] or claims[:2]
            required_evidence_ids = [
                str(item.get("claim_id"))
                for item in supporting_claims
                if str(item.get("claim_id") or "") in evidence_ids
            ]
            story_start = (index - 1) * len(stories) // max(1, len(goals))
            story_end = index * len(stories) // max(1, len(goals))
            paragraph_stories = stories[story_start:story_end] or stories[:1]
            paragraphs.append({
                "paragraph_id": f"{section}_{index}",
                "objective": objective,
                "required_evidence_ids": required_evidence_ids or [item.get("evidence_id") for item in evidence[:5]],
                "allocated_claim_ids": [item.get("claim_id") for item in supporting_claims],
                "figure_or_formula_links": [item.get("story_id") for item in paragraph_stories],
                "citation_intent": "Use citations to support the paragraph's specific role, not as a coverage list." if section in {"introduction", "discussion"} else "No literature citation required unless it defines a method or data standard.",
                "transition_logic": "End by making the next paragraph's question necessary.",
                "forbidden_content": ["internal artifact names", "unsupported metric", "conclusion outside the approved evidence boundary"],
            })
    return paragraphs


def build_section_outline(project: str | Path, section: str) -> dict[str, Any]:
    """Create a paragraph-level scientific outline before any prose is written."""
    state = load_project(project)
    normalized = str(section or "").strip().lower()
    pack = build_section_evidence_pack(state.path, normalized)
    outline = {
        "schema_version": "dpl.section_outline.v1",
        "generated_at": utc_now(),
        "section": normalized,
        "writing_mode": "outline_then_free_prose",
        "evidence_resolution_mode": "strict",
        "paragraphs": _paragraph_blueprint(normalized, pack),
        "writer_instruction": "Write fluent scientific prose from this outline. Preserve evidence IDs, claim boundaries, and required links, but choose sentence order, terminology, and rhetorical emphasis freely. Do not turn outline labels into manuscript prose.",
    }
    target = state.path / SECTION_OUTLINE_DIR / f"{normalized}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    _write_json(target, outline)
    return outline


def build_results_synthesis_plan(project: str | Path) -> dict[str, Any]:
    """Turn result story groups into finding blocks for a non-templated Results draft."""
    state = load_project(project)
    narrative = build_paper_narrative(state.path)
    resolved = _read_json(state.path / "results" / "resolved_result_evidence.json")
    metrics = [item for item in resolved.get("metrics") or resolved.get("records") or [] if isinstance(item, dict)]
    blocks = []
    for story in narrative["figure_story_arc"].get("figure_groups") or []:
        matched_metrics = [metric for metric in metrics if _metric_is_bound(metric, story)]
        blocks.append({
            "finding_id": f"finding:{story.get('story_id')}",
            "scientific_job": story.get("narrative_job"),
            "scientific_question": story.get("scientific_question"),
            "observed_result": story.get("claim"),
            "figure_evidence": list(story.get("main_artifact_ids") or []),
            "supporting_evidence": list(story.get("supporting_artifact_ids") or []),
            "metric_evidence": matched_metrics[:6],
            "evidence_ids": list(story.get("evidence_ids") or []),
            "run_ids": list(story.get("run_ids") or []),
            "comparison_requirement": "State direction and comparison only when evidence identifies both entities.",
            "interpretation_requirement": "Explain what the empirical pattern means for the stated question without invoking literature citations.",
            "claim_boundary": story.get("claim_boundary") or "Limit interpretation to the represented cohort, method, and validation setting.",
        })
    plan = {"schema_version": "dpl.results_synthesis_plan.v1", "generated_at": utc_now(), "finding_blocks": blocks}
    _write_json(state.path / RESULTS_SYNTHESIS_PLAN, plan)
    return plan


def prepare_section_writing_context(project: str | Path, section: str) -> dict[str, Any]:
    """Public helper used by CLI and section writers to prepare v0.21 writing inputs."""
    state = load_project(project)
    narrative = build_paper_narrative(state.path)
    pack = build_section_evidence_pack(state.path, section)
    outline = build_section_outline(state.path, section)
    synthesis = build_results_synthesis_plan(state.path) if str(section).lower() == "results" else {}
    return {"narrative": narrative, "section_evidence_pack": pack, "section_outline": outline, "results_synthesis_plan": synthesis}
