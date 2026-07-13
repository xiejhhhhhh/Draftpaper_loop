"""Task-scoped figure and paragraph evidence resolution with hard token budgets."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .figure_semantics import build_semantic_figure_contract, validate_figure_semantics
from .project_scaffold import utc_now
from .project_state import load_project


FIGURE_EVIDENCE_PATH = "results/figure_evidence_resolution.json"
SECTION_CONTEXT_INDEX = "writing/section_context_index.json"
PARAGRAPH_SLICE_ROOT = "writing/paragraph_evidence_slices"

SECTION_TOKEN_BUDGETS = {
    "results": 16000,
    "introduction": 13000,
    "data": 10000,
    "methods": 18000,
    "discussion": 15000,
}


class EvidenceResolutionError(RuntimeError):
    """Raised when active evidence cannot be resolved safely."""


def _read(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def estimate_tokens(payload: Any) -> int:
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True) if not isinstance(payload, str) else payload
    return len(re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]|[^\s]", text))


def _story_role(contract: dict[str, Any], *, manuscript_role: str) -> str:
    explicit = str(contract.get("story_role") or contract.get("narrative_role") or "").strip().lower()
    if explicit:
        return explicit
    text = " ".join(
        str(contract.get(key) or "")
        for key in ("scientific_question", "research_question", "title", "expected_claim", "plot_grammar")
    ).lower()
    if manuscript_role in {"appendix", "supporting", "supplement"}:
        return "supporting_diagnostic"
    if any(token in text for token in ("sample", "cohort", "coverage", "missingness")):
        return "study_cohort_boundary"
    if any(token in text for token in ("ablation", "without", "component", "feature importance")):
        return "ablation_component_attribution"
    if any(token in text for token in ("uncertainty", "error", "confidence", "failure", "boundary")):
        return "uncertainty_error_boundary"
    if any(token in text for token in ("baseline", "compare", "versus", "performance")):
        return "primary_comparison"
    if any(token in text for token in ("embedding", "distribution", "structure", "correlation")):
        return "pre_model_structure"
    return "direct_scientific_signal"


def _contract_rows(root: Path) -> list[dict[str, Any]]:
    payload = _read(root / "results" / "figure_contracts.json")
    rows = payload.get("main_contracts") or payload.get("contracts") or payload.get("figures") or []
    if not rows:
        storyboard = _read(root / "research_plan" / "figure_storyboard.json") or _read(root / "results" / "figure_storyboard.json")
        rows = storyboard.get("figures") or storyboard.get("storyboard") or []
    return [dict(item) for item in rows if isinstance(item, dict)]


def _metadata_index(root: Path) -> dict[str, dict[str, Any]]:
    payload = _read(root / "results" / "figure_metadata.json")
    rows = payload.get("figures") or payload.get("entries") or []
    result: dict[str, dict[str, Any]] = {}
    for item in rows:
        if not isinstance(item, dict):
            continue
        for value in (item.get("figure_id"), item.get("storyboard_id"), item.get("id")):
            if value:
                result[str(value)] = item
    return result


def resolve_figure_evidence(project: str | Path) -> dict[str, Any]:
    state = load_project(project)
    resolved = _read(state.path / "results" / "resolved_result_evidence.json")
    if not resolved:
        raise EvidenceResolutionError("Resolve run-aware result evidence before figure evidence.")
    run_id = str(resolved.get("run_id") or "")
    metadata = _metadata_index(state.path)
    metric_records = [item for item in resolved.get("evidence_records") or [] if isinstance(item, dict)]
    panels = []
    blocking = []
    for index, raw in enumerate(_contract_rows(state.path), start=1):
        figure_id = str(raw.get("figure_id") or raw.get("storyboard_id") or raw.get("id") or f"figure_{index:02d}")
        contract = {"figure_id": figure_id, **build_semantic_figure_contract(raw), **raw}
        produced = metadata.get(figure_id) or {}
        semantic = produced.get("semantic_metadata") if isinstance(produced.get("semantic_metadata"), dict) else produced
        validation = validate_figure_semantics(contract, semantic) if semantic else {
            "decision": "metadata_pending",
            "issues": [{"severity": "blocking", "kind": "missing_rendered_semantic_metadata", "detail": figure_id}],
        }
        required_outputs = {str(item).lower() for item in contract.get("required_method_outputs") or []}
        matched_metrics = [
            item
            for item in metric_records
            if str(item.get("run_id") or "") == run_id
            and (
                not required_outputs
                or str(item.get("entity_role") or "").lower().removeprefix("result_metric_") in required_outputs
                or str(item.get("metric_name") or "").lower() in required_outputs
            )
        ]
        manuscript_role = str(raw.get("manuscript_role") or produced.get("manuscript_role") or "main").lower()
        row = {
            "figure_id": figure_id,
            "story_role": _story_role(contract, manuscript_role=manuscript_role),
            "manuscript_role": manuscript_role,
            "scientific_question": contract.get("scientific_question") or raw.get("research_question"),
            "scientific_unit": raw.get("scientific_unit") or produced.get("scientific_unit"),
            "required_data_roles": list(raw.get("required_data_roles") or raw.get("required_data") or []),
            "required_method_outputs": list(contract.get("required_method_outputs") or []),
            "run_id": run_id,
            "model_ids": sorted({str(item.get("model_id")) for item in matched_metrics if item.get("model_id")}),
            "cohort_ids": sorted({str(item.get("cohort_id")) for item in matched_metrics if item.get("cohort_id")}),
            "evidence_ids": [item.get("evidence_id") for item in matched_metrics if item.get("evidence_id")],
            "source_artifacts": sorted({str(item.get("source_artifact")) for item in matched_metrics if item.get("source_artifact")}),
            "semantic_validation": validation,
            "claim_boundary": raw.get("claim_boundary") or contract.get("expected_claim"),
            "substitution_policy": "A supporting diagnostic may accompany but never replace a required direct scientific signal.",
        }
        if validation.get("decision") == "blocked":
            blocking.append({"figure_id": figure_id, "issues": validation.get("issues") or []})
        panels.append(row)
    payload = {
        "schema_version": "dpl.figure_evidence_resolution.v1",
        "status": "blocked" if blocking else "resolved",
        "generated_at": utc_now(),
        "project_id": state.metadata.get("project_id"),
        "run_id": run_id,
        "panels": panels,
        "blocking": blocking,
        "story_role_counts": {
            role: sum(item["story_role"] == role for item in panels)
            for role in sorted({item["story_role"] for item in panels})
        },
        "policy": "Figure evidence is selected by semantic contract, run, model, cohort and output role; file order and generic metric filenames have no priority.",
    }
    _write(state.path / FIGURE_EVIDENCE_PATH, payload)
    return payload


def _record_excerpt(record: dict[str, Any]) -> dict[str, Any]:
    return {
        key: record.get(key)
        for key in (
            "evidence_id",
            "entity_role",
            "value",
            "unit",
            "metric_dimension",
            "run_id",
            "cohort_id",
            "sample_unit",
            "split",
            "model_id",
            "aggregation",
            "analysis_variant",
            "claim_boundary",
            "allowed_interpretation",
        )
        if record.get(key) not in (None, "", [], {})
    }


def resolve_paragraph_evidence(
    project: str | Path,
    section: str,
    *,
    outline: dict[str, Any] | None = None,
) -> dict[str, Any]:
    state = load_project(project)
    normalized = str(section).strip().lower()
    if normalized not in SECTION_TOKEN_BUDGETS:
        raise EvidenceResolutionError(f"Unsupported manuscript section: {section}")
    registry = _read(state.path / "writing" / "scientific_evidence_registry.json")
    records = [item for item in registry.get("records") or [] if isinstance(item, dict)]
    section_records = [
        item
        for item in records
        if not item.get("target_sections") or normalized in {str(value).lower() for value in item.get("target_sections") or []}
    ]
    outline_payload = outline or _read(state.path / "writing" / "section_outlines" / f"{normalized}.json")
    paragraphs = [item for item in outline_payload.get("paragraphs") or [] if isinstance(item, dict)]
    if not paragraphs:
        paragraphs = [{"paragraph_id": f"{normalized}_1", "objective": f"Compose the {normalized} section."}]
    record_index = {str(item.get("evidence_id")): item for item in section_records if item.get("evidence_id")}
    section_budget = SECTION_TOKEN_BUDGETS[normalized]
    base_slice_budget = max(1000, section_budget // len(paragraphs))
    slices = []
    for paragraph in paragraphs:
        requested = [str(item) for item in paragraph.get("required_evidence_ids") or [] if str(item)]
        selected = [record_index[item] for item in requested if item in record_index]
        if not selected:
            selected = section_records[: min(8, len(section_records))]
        compact = [_record_excerpt(item) for item in selected]
        slice_payload = {
            "schema_version": "dpl.paragraph_evidence_slice.v1",
            "section": normalized,
            "paragraph_id": paragraph.get("paragraph_id"),
            "objective": paragraph.get("objective"),
            "selected_evidence": compact,
            "bound_numbers": [
                {key: item.get(key) for key in ("evidence_id", "value", "unit")}
                for item in compact
                if item.get("value") is not None
            ],
            "figure_table_formula_links": {
                "outline": paragraph.get("figure_or_table_links") or paragraph.get("figure_or_formula_links") or [],
                "figures": sorted({str(value) for item in selected for value in item.get("figure_ids") or []}),
                "formulas": sorted({str(value) for item in selected for value in item.get("formula_ids") or []}),
            },
            "citation_roles": [
                {"citation_key": item.get("citation_key"), "role": item.get("citation_role")}
                for item in selected
                if item.get("citation_key")
            ],
            "allowed_interpretations": [item.get("allowed_interpretation") for item in compact if item.get("allowed_interpretation")],
            "forbidden_moves": list(paragraph.get("forbidden_content") or [])
            + ["invent an unbound number", "change cohort, model, split, unit or run silently"],
            "omitted_candidates": [
                {"evidence_id": item.get("evidence_id"), "reason": "not selected for this paragraph job"}
                for item in section_records
                if item not in selected
            ][:20],
            "source_hashes": {
                str(item.get("source_artifact")): item.get("source_hash")
                for item in selected
                if item.get("source_artifact") and item.get("source_hash")
            },
            "token_budget": base_slice_budget,
        }
        slice_payload["estimated_tokens"] = estimate_tokens(slice_payload)
        if slice_payload["estimated_tokens"] > base_slice_budget:
            slice_payload["omitted_candidates"] = []
            slice_payload["estimated_tokens"] = estimate_tokens(slice_payload)
        if slice_payload["estimated_tokens"] > section_budget:
            raise EvidenceResolutionError(
                f"Required evidence for {slice_payload['paragraph_id']} exceeds the entire {normalized} section budget. "
                "Split the scientific finding into narrower claim-bound paragraph jobs instead of dropping bound evidence."
            )
        slice_payload["token_budget"] = max(base_slice_budget, slice_payload["estimated_tokens"])
        relative = f"{PARAGRAPH_SLICE_ROOT}/{normalized}/{slice_payload['paragraph_id']}.json"
        _write(state.path / relative, slice_payload)
        slices.append({"paragraph_id": slice_payload["paragraph_id"], "path": relative, "estimated_tokens": slice_payload["estimated_tokens"], "evidence_ids": [item.get("evidence_id") for item in compact]})
    total = sum(int(item["estimated_tokens"]) for item in slices)
    if total > section_budget:
        raise EvidenceResolutionError(
            f"Required evidence for {normalized} needs {total} estimated tokens, above the hard section budget "
            f"of {section_budget}. Narrow or merge the outline by scientific claim without dropping bound evidence."
        )
    index_path = state.path / SECTION_CONTEXT_INDEX
    index = _read(index_path)
    sections = dict(index.get("sections") or {})
    sections[normalized] = {
        "budget": section_budget,
        "estimated_tokens": total,
        "within_budget": total <= section_budget,
        "allowed_evidence_ids": sorted(record_index),
        "slices": slices,
        "source_registry_hash": hashlib.sha256((state.path / "writing" / "scientific_evidence_registry.json").read_bytes()).hexdigest() if (state.path / "writing" / "scientific_evidence_registry.json").is_file() else None,
    }
    index = {
        "schema_version": "dpl.section_context_index.v1",
        "generated_at": utc_now(),
        "project_id": state.metadata.get("project_id"),
        "total_hard_budget": sum(SECTION_TOKEN_BUDGETS.values()),
        "sections": sections,
    }
    _write(index_path, index)
    return {"status": "resolved", "section": normalized, **sections[normalized], "index": SECTION_CONTEXT_INDEX}
