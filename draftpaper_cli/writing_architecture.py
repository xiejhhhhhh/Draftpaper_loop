# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

"""Scientific reasoning artifacts for high-quality, non-templated manuscript writing."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .paper_narrative import build_paper_narrative, build_section_outline
from .project_scaffold import _write_json, utc_now
from .project_state import load_project
from .structured_io import read_mapping


class WritingArchitectureError(RuntimeError):
    """Raised when required scientific writing inputs are unavailable."""


def _read(path: Path) -> dict[str, Any]:
    return read_mapping(path)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        try:
            value = json.loads(line)
        except (ValueError, TypeError):
            continue
        if isinstance(value, dict):
            records.append(value)
    return records


def _text(value: Any, limit: int = 1400) -> str:
    normalized = re.sub(r"\s+", " ", str(value or "")).strip()
    return normalized[:limit].rstrip() + ("..." if len(normalized) > limit else "")


def _items(payload: dict[str, Any], *keys: str) -> list[dict[str, Any]]:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _reference_records(project_path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    root = project_path / "references" / "literature_summaries"
    if not root.exists():
        return records
    for path in sorted(root.rglob("*.json")):
        payload = _read(path)
        candidates = _items(payload, "references", "records", "papers", "summaries") or ([payload] if payload else [])
        for item in candidates:
            row = dict(item)
            row.setdefault("reference_id", row.get("citation_key") or row.get("id") or path.stem)
            row.setdefault("source_artifact", path.relative_to(project_path).as_posix())
            records.append(row)
    unique: dict[str, dict[str, Any]] = {}
    for item in records:
        key = str(item.get("reference_id") or item.get("title") or len(unique))
        unique.setdefault(key, item)
    return list(unique.values())


def build_argument_matrices(project: str | Path) -> dict[str, Any]:
    """Build Introduction gap and Discussion finding-comparison matrices."""
    state = load_project(project)
    narrative = build_paper_narrative(state.path)
    references = _reference_records(state.path)
    claims = narrative.get("section_claim_allocation", {}).get("sections", {})
    introduction_claims = claims.get("introduction") if isinstance(claims.get("introduction"), list) else []
    intro_rows: list[dict[str, Any]] = []
    for index, claim in enumerate(introduction_claims, start=1):
        reference = references[(index - 1) % len(references)] if references else {}
        intro_rows.append({
            "gap_id": f"gap_{index}",
            "paragraph_job": claim.get("rhetorical_job") or claim.get("claim") or "Establish a research gap.",
            "known_evidence": _text(reference.get("finding") or reference.get("summary") or reference.get("abstract")),
            "reference_ids": [reference.get("reference_id")] if reference else [],
            "unresolved_gap": _text(claim.get("gap") or claim.get("claim_boundary") or "State what remains unresolved without inventing a literature consensus."),
            "paper_response": _text(claim.get("claim") or claim.get("response")),
            "citation_role": "Support the specific known fact or unresolved limitation attached to this paragraph job.",
            "forbidden_move": "Do not claim novelty merely because no identical title was found.",
        })
    discussion_rows: list[dict[str, Any]] = []
    for index, story in enumerate(narrative.get("figure_story_arc", {}).get("figure_groups") or [], start=1):
        reference = references[(index - 1) % len(references)] if references else {}
        discussion_rows.append({
            "comparison_id": f"comparison_{index}",
            "finding_id": f"finding:{story.get('story_id')}",
            "current_finding": story.get("claim") or story.get("scientific_question"),
            "evidence_ids": list(story.get("evidence_ids") or []),
            "comparison_reference_ids": [reference.get("reference_id")] if reference else [],
            "comparison_evidence": _text(reference.get("finding") or reference.get("summary") or reference.get("abstract")),
            "comparison_axis": "agreement, disagreement, mechanism, boundary, or methodological difference",
            "interpretation_boundary": story.get("claim_boundary") or "Keep comparison within compatible cohorts, outcomes, and validation settings.",
            "required_reasoning": "Explain why the current result agrees or differs; do not merely list prior work.",
        })
    payload = {
        "schema_version": "v0.21.5",
        "generated_at": utc_now(),
        "introduction_gap_matrix": intro_rows,
        "discussion_finding_comparison_matrix": discussion_rows,
    }
    target = state.path / "writing" / "argument_matrices.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    _write_json(target, payload)
    return payload


def build_section_lifecycles(project: str | Path) -> dict[str, Any]:
    """Reconstruct Data and Methods prose inputs from stage-owned scientific traces."""
    state = load_project(project)
    data_inventory = _read(state.path / "data" / "data_inventory.json")
    data_context = _read(state.path / "data" / "data_writing_context.json")
    method_context = _read(state.path / "methods" / "method_writing_context.json")
    data_manifest = _read(state.path / "data" / "data_code_manifest.json")
    method_manifest = _read(state.path / "methods" / "method_code_manifest.json")
    if not method_manifest:
        method_manifest = _read(state.path / "code" / "stage_code_manifest.json")
    formulas = _read(state.path / "methods" / "method_formula_manifest.json")
    figure_trace = _read(state.path / "results" / "figure_code_trace.json")
    data_plugins = _read_jsonl(state.path / "data" / "plugin_execution_ledger.jsonl")
    method_plugins = _read_jsonl(state.path / "methods" / "plugin_execution_ledger.jsonl")
    formula_rows = [item for item in formulas.get("formulas") or [] if isinstance(item, dict)]
    formula_contracts = [{
        "formula_id": item.get("id") or item.get("formula_id"),
        "latex": item.get("latex"),
        "variables": item.get("variables") or [],
        "source": item.get("source_path") or item.get("source"),
        "required_explanation": ["variable definition", "unit or valid range when applicable", "scientific meaning", "linked method stage", "linked figure or result"],
    } for item in formula_rows]
    data_stages = [
        {"role": "source_and_access_boundary", "evidence": data_context.get("source_summary") or data_inventory.get("sources") or [], "prose_goal": "Describe scientific provenance and access scope, never local paths or credentials."},
        {"role": "raw_to_processed_transformation", "evidence": data_context.get("processing_summary") or data_manifest.get("files") or [], "prose_goal": "Explain transformations in scientific order and justify information retained or removed."},
        {"role": "analysis_cohort_and_subsets", "evidence": data_context.get("data_key_facts") or data_context.get("content_summary") or data_inventory.get("cohorts") or [], "prose_goal": "Separate inventory, usable cohort, train/validation/test units, and stress-test subsets."},
        {"role": "feature_content_groups", "evidence": data_context.get("variable_groups") or [], "prose_goal": "Describe scientifically meaningful variable or measurement groups instead of raw field dumps."},
        {"role": "coverage_missingness_exclusions_and_claim_boundary", "evidence": data_context.get("claim_boundary") or data_context.get("feasibility") or [], "prose_goal": "State missingness, coverage, exclusions, and the population to which conclusions apply."},
    ]
    method_stages = [
        {"role": "sample_construction", "evidence": method_context.get("data_role") or method_context.get("method_blueprint", {}).get("sample_construction") or [], "formula_requirement": "formula_optional"},
        {"role": "feature_or_representation_construction", "evidence": method_context.get("analysis_steps") or method_context.get("method_blueprint", {}).get("feature_construction") or [], "formula_requirement": "formula_or_explicit_deterministic_reason"},
        {"role": "model_estimator_or_physical_fit", "evidence": method_context.get("method_family_summary") or method_manifest.get("files") or [], "formula_requirement": "formula_or_explicit_deterministic_reason"},
        {"role": "objective_and_optimization", "evidence": formula_contracts, "formula_requirement": "formula_or_explicit_deterministic_reason"},
        {"role": "validation_metrics_ablation_uncertainty", "evidence": method_context.get("verification_summary") or figure_trace.get("traces") or [], "formula_requirement": "define_estimand_metric_and_resampling_unit"},
    ]
    deterministic_reason = _text(method_context.get("deterministic_no_formula_reason"))
    formula_status = "covered" if formula_contracts else ("deterministic_no_formula" if deterministic_reason else "missing_formula_or_reason")
    payload = {
        "schema_version": "v0.21.6",
        "generated_at": utc_now(),
        "data_lifecycle": {
            "stages": data_stages,
            "stage_owned_code": data_manifest.get("files") or [],
            "plugin_execution": data_plugins,
            "forbidden_prose": ["local paths", "filenames as scientific variables", "credentials", "script inventory narration"],
        },
        "method_lifecycle": {
            "stages": method_stages,
            "stage_owned_code": method_manifest.get("files") or [],
            "formula_contracts": formula_contracts,
            "formula_coverage_status": formula_status,
            "deterministic_no_formula_reason": deterministic_reason,
            "figure_code_trace": figure_trace.get("traces") or figure_trace.get("figures") or [],
            "plugin_execution": method_plugins,
            "variable_explanation_required": True,
            "forbidden_prose": ["raw variable dumps", "local paths", "script names", "manifest narration"],
        },
    }
    target = state.path / "writing" / "section_lifecycles.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    _write_json(target, payload)
    return payload


def build_panel_writing_contracts(project: str | Path) -> dict[str, Any]:
    """Create panel-aware scientific contracts and isolate repair to affected panels."""
    state = load_project(project)
    plan = _read(state.path / "results" / "figure_plan.json")
    semantic_contracts = _read(state.path / "results" / "figure_contracts.json")
    metadata = _read(state.path / "results" / "figure_metadata.json")
    groups = semantic_contracts.get("contracts") if isinstance(semantic_contracts.get("contracts"), list) else []
    if groups:
        groups = [item for item in groups if isinstance(item, dict) and str(item.get("figure_role") or "main_result") != "supporting"]
    if not groups:
        groups = plan.get("figure_groups") if isinstance(plan.get("figure_groups"), list) else []
    if not groups:
        groups = plan.get("figures") if isinstance(plan.get("figures"), list) else []
    metadata_rows = _items(metadata, "figures", "records")
    by_id: dict[str, dict[str, Any]] = {}
    for item in metadata_rows:
        for key in [item.get("id"), item.get("figure_id"), item.get("storyboard_id"), item.get("panel_id"), item.get("path")]:
            if key:
                by_id[str(key)] = item
    contracts: list[dict[str, Any]] = []
    for group_index, group in enumerate(groups, start=1):
        if not isinstance(group, dict):
            continue
        group_id = str(group.get("storyboard_id") or group.get("figure_id") or group.get("id") or group.get("figure_group_id") or f"figure_group_{group_index}")
        panels = group.get("panels") if isinstance(group.get("panels"), list) else []
        if not panels:
            panels = [group]
        panel_contracts: list[dict[str, Any]] = []
        for panel_index, panel in enumerate(panels, start=1):
            if not isinstance(panel, dict):
                continue
            panel_id = str(panel.get("storyboard_id") or panel.get("figure_id") or panel.get("id") or panel.get("panel_id") or f"{group_id}_panel_{panel_index}")
            observed = by_id.get(panel_id, {})
            contract = {
                "panel_question": panel.get("panel_question") or panel.get("scientific_question") or group.get("scientific_question"),
                "data_subset": panel.get("data_subset") or panel.get("cohort") or group.get("data_subset") or group.get("cohort"),
                "scientific_unit": panel.get("scientific_unit") or panel.get("analysis_unit") or group.get("scientific_unit") or group.get("analysis_unit"),
                "data_roles": panel.get("required_data") or panel.get("data_roles") or panel.get("input_data_roles") or group.get("required_data") or group.get("data_roles") or [],
                "method_output": panel.get("required_method_outputs") or panel.get("method_output") or panel.get("method_outputs") or group.get("required_method_outputs") or group.get("method_output") or group.get("method_outputs") or observed.get("method_outputs") or [],
                "comparison": panel.get("comparison") or panel.get("comparison_entities") or group.get("comparison"),
                "required_statistical_check": panel.get("required_statistical_check") or panel.get("statistical_check") or group.get("required_statistical_check"),
                "chart_grammar": panel.get("plot_grammar") or panel.get("chart_grammar") or panel.get("visual_grammar") or panel.get("plot_type") or group.get("plot_grammar") or group.get("visual_grammar") or observed.get("plot_grammar"),
                "expected_conclusion": panel.get("expected_claim") or panel.get("expected_finding") or panel.get("expected_conclusion") or panel.get("result_claim") or group.get("expected_claim") or group.get("expected_finding") or group.get("expected_conclusion") or group.get("result_claim") or observed.get("interpretation_summary"),
                "claim_boundary": panel.get("claim_boundary") or panel.get("scientific_claim_boundary") or group.get("claim_boundary") or group.get("scientific_claim_boundary") or observed.get("claim_boundary"),
                "parent_figure_group": group_id,
            }
            required_keys = ("panel_question", "method_output", "chart_grammar", "expected_conclusion", "claim_boundary")
            missing = [key for key in required_keys if not contract.get(key)]
            panel_contracts.append({
                "panel_id": panel_id,
                "contract": contract,
                "observed_metadata": observed,
                "status": "repair_required" if missing else "contract_ready",
                "missing_contract_fields": missing,
                "repair_scope": "this_panel_only",
                "no_weaker_substitute": True,
            })
        contracts.append({"figure_group_id": group_id, "panels": panel_contracts, "composite_review_required": True})
    payload = {"schema_version": "v0.21.7", "generated_at": utc_now(), "figure_groups": contracts}
    target = state.path / "results" / "panel_figure_contracts.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    _write_json(target, payload)
    return payload


def prepare_panel_repair(project: str | Path) -> dict[str, Any]:
    """Diagnose panel-local contract failures without inventing substitute evidence."""
    state = load_project(project)
    contracts = build_panel_writing_contracts(state.path)
    tasks: list[dict[str, Any]] = []
    for group in contracts.get("figure_groups") or []:
        for panel in group.get("panels") or []:
            contract = panel.get("contract") or {}
            observed = panel.get("observed_metadata") or {}
            diagnoses: list[str] = []
            if not contract.get("data_subset") or not contract.get("scientific_unit") or not contract.get("data_roles"):
                diagnoses.append("data_contract_mismatch")
            if not contract.get("method_output"):
                diagnoses.append("method_output_mismatch")
            if not observed:
                diagnoses.append("render_or_metadata_missing")
            if contract.get("required_statistical_check") and not (
                observed.get("statistical_checks") or observed.get("statistics") or observed.get("uncertainty")
            ):
                diagnoses.append("statistical_check_missing")
            if not contract.get("expected_conclusion") or not contract.get("claim_boundary"):
                diagnoses.append("claim_contract_mismatch")
            if diagnoses or panel.get("missing_contract_fields"):
                tasks.append({
                    "figure_group_id": group.get("figure_group_id"),
                    "panel_id": panel.get("panel_id"),
                    "diagnoses": sorted(set(diagnoses)),
                    "missing_contract_fields": panel.get("missing_contract_fields") or [],
                    "repair_scope": "affected_panel_chain_only",
                    "repair_order": ["recover_or_bind_data", "recover_or_bind_method", "rerun_panel", "verify_statistics", "reconcile_claim"],
                    "external_rescue_policy": "Search approved discipline plugins and public research code only after local project capabilities are exhausted.",
                    "escalation_policy": "Escalate to the user only after data, method, and public-code rescue attempts fail.",
                    "forbidden_action": "Do not replace the failed panel with weaker or merely similar evidence.",
                })
    payload = {
        "schema_version": "v0.21.7",
        "generated_at": utc_now(),
        "decision": "repair_required" if tasks else "pass",
        "tasks": tasks,
    }
    target = state.path / "results" / "panel_repair_plan.json"
    _write_json(target, payload)
    return payload


def resolve_venue_style_adapter(project: str | Path) -> dict[str, Any]:
    """Translate journal metadata into functional writing signals without copying prose."""
    state = load_project(project)
    profile = _read(state.path / "journal_profile" / "journal_profile.json")
    functional = {
        "section_order": profile.get("section_order") or ["introduction", "data", "methods", "results", "discussion"],
        "section_length_policy": profile.get("section_length_policy") or profile.get("section_word_limits") or {},
        "information_density": profile.get("information_density") or "high scientific information per paragraph without compressed reasoning",
        "caption_density": profile.get("caption_density") or "self-contained captions defining cohort, comparison, encoding, and uncertainty",
        "voice_preference": profile.get("voice_preference") or profile.get("active_passive_preference") or "use active voice for research actions and passive voice only when the actor is irrelevant",
        "numeric_reporting": profile.get("numeric_reporting") or "report value, unit or scale, comparison, uncertainty, and analysis cohort when supported",
        "terminology_definition": profile.get("terminology_definition") or "define specialized terms at first use and preserve canonical terminology",
        "results_interpretation_density": profile.get("results_interpretation_density") or "each finding states observation, comparison, scientific meaning, and boundary",
        "discussion_interpretation_density": profile.get("discussion_interpretation_density") or "compare evidence, explain mechanism, and state limitations without repeating Results",
        "table_and_supplement_usage": profile.get("table_and_supplement_usage") or "move audit detail to tables or supplements while citing it in the main scientific narrative",
        "abstract_word_limit": profile.get("abstract_word_limit"),
        "citation_style": profile.get("bibliography_style") or profile.get("citation_style"),
    }
    contract = {
        "schema_version": "v0.21.8",
        "generated_at": utc_now(),
        "venue": profile.get("target_journal") or profile.get("journal") or "unspecified",
        "functional_preferences": functional,
        "hard_boundary": "Style guidance cannot override evidence, claim, citation, formula, figure, or snapshot contracts.",
    }
    style_profile = {
        "schema_version": "v0.21.8",
        "generated_at": utc_now(),
        "signals": functional,
        "allowed_learning": ["density", "voice preference", "numeric reporting", "definition policy", "interpretation density", "supplement usage"],
        "forbidden_learning": ["copied exemplar sentences", "venue-specific scientific claims", "fixed paragraph wording"],
    }
    writing_dir = state.path / "writing"
    writing_dir.mkdir(parents=True, exist_ok=True)
    _write_json(writing_dir / "venue_writing_contract.json", contract)
    _write_json(writing_dir / "style_function_profile.json", style_profile)
    adapter = dict(contract)
    adapter["forbidden_learning"] = style_profile["forbidden_learning"]
    _write_json(writing_dir / "venue_style_adapter.json", adapter)
    return adapter


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _paragraphs(text: str) -> list[str]:
    prose = re.sub(
        r"\\begin\{(?:figure\*?|table\*?|deluxetable\*?)\}.*?\\end\{(?:figure\*?|table\*?|deluxetable\*?)\}",
        "",
        text,
        flags=re.S,
    )
    return [item.strip() for item in re.split(r"\n\s*\n", prose) if item.strip() and not item.lstrip().startswith("\\section")]


def _normalized_reference(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower()).removeprefix("fig").removeprefix("table")


def _jobs_for_paragraph(paragraph: str, jobs: list[Any]) -> list[dict[str, Any]]:
    paragraph_key = _normalized_reference(paragraph)
    matches: list[dict[str, Any]] = []
    for job in jobs:
        if not isinstance(job, dict):
            continue
        for link in job.get("figure_or_table_links") or []:
            link_key = _normalized_reference(link)
            if link_key and link_key in paragraph_key:
                matches.append(job)
                break
    return matches


def prepare_scientific_editor(project: str | Path, section: str, input_path: str | Path) -> dict[str, Any]:
    """Create auditable paragraph-local revision tasks for at most three rounds."""
    state = load_project(project)
    normalized = str(section).strip().lower()
    source = Path(input_path).expanduser().resolve()
    if not source.is_file():
        raise WritingArchitectureError(f"Section candidate does not exist: {source}")
    text = source.read_text(encoding="utf-8-sig")
    outline = build_section_outline(state.path, normalized)
    paragraphs = _paragraphs(text)
    jobs = outline.get("paragraphs") or []
    tasks: list[dict[str, Any]] = []
    for index, paragraph in enumerate(paragraphs):
        paragraph_jobs = _jobs_for_paragraph(paragraph, jobs)
        job = paragraph_jobs[0] if paragraph_jobs else {}
        issues: list[str] = []
        if len(re.findall(r"[A-Za-z]+", paragraph)) < 35:
            issues.append("underdeveloped_scientific_reasoning")
        if re.search(r"(?:[A-Za-z]:\\|results[/\\]|\.(?:png|csv|json|py)\b)", paragraph, flags=re.I):
            issues.append("internal_artifact_language")
        required_claim = str(job.get("required_claim") or job.get("objective") or "")
        claim_terms = {term.lower() for term in re.findall(r"[A-Za-z]{5,}", required_claim)}
        paragraph_terms = {term.lower() for term in re.findall(r"[A-Za-z]{5,}", paragraph)}
        if claim_terms and len(claim_terms & paragraph_terms) / max(len(claim_terms), 1) < 0.12:
            issues.append("paragraph_job_alignment_weak")
        if issues:
            tasks.append({
                "paragraph_index": index + 1,
                "issues": issues,
                "paragraph_job": job.get("objective") or job.get("paragraph_goal"),
                "required_evidence_ids": [str(item) for item in job.get("required_evidence_ids") or [] if str(item)],
                "before_hash": _hash_text(paragraph),
                "instruction": "Revise only this paragraph. Preserve supported facts, evidence bindings, claim boundaries, citations, and surrounding transitions.",
            })
    matched_job_ids = {
        str(job.get("paragraph_id") or "")
        for paragraph in paragraphs
        for job in _jobs_for_paragraph(paragraph, jobs)
    }
    for index, job in enumerate(jobs):
        if not isinstance(job, dict) or str(job.get("paragraph_id") or "") in matched_job_ids:
            continue
        if job.get("figure_or_table_links"):
            tasks.append({
                "paragraph_index": index + 1,
                "issues": ["paragraph_job_missing"],
                "paragraph_job": job.get("objective"),
                "required_evidence_ids": job.get("required_evidence_ids") or [],
                "before_hash": "",
                "instruction": "Add only the missing paragraph job without rewriting accepted paragraphs.",
            })
    payload = {
        "schema_version": "v0.21.9",
        "generated_at": utc_now(),
        "section": normalized,
        "iteration": 0,
        "max_iterations": 3,
        "revision_scope": "paragraph_local",
        "source_hash": _hash_text(text),
        "tasks": tasks,
        "decision": "pass" if not tasks else "revise",
        "forbidden_actions": ["whole_section_rewrite_for_local_defect", "new_unbound_numeric_claim", "reference_deletion_to_satisfy_citation_audit"],
    }
    target = state.path / "writing" / "scientific_editor" / f"{normalized}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    _write_json(target, payload)
    return payload


def record_scientific_editor_revision(
    project: str | Path,
    section: str,
    before_path: str | Path,
    after_path: str | Path,
    iteration: int,
) -> dict[str, Any]:
    """Record one bounded editor round and reject whole-section churn."""
    if iteration < 1 or iteration > 3:
        raise WritingArchitectureError("Scientific editor iteration must be between 1 and 3.")
    state = load_project(project)
    normalized = str(section).strip().lower()
    before = Path(before_path).expanduser().resolve().read_text(encoding="utf-8-sig")
    after = Path(after_path).expanduser().resolve().read_text(encoding="utf-8-sig")
    before_paragraphs = _paragraphs(before)
    after_paragraphs = _paragraphs(after)
    changes: list[dict[str, Any]] = []
    for index in range(max(len(before_paragraphs), len(after_paragraphs))):
        previous = before_paragraphs[index] if index < len(before_paragraphs) else ""
        current = after_paragraphs[index] if index < len(after_paragraphs) else ""
        if previous != current:
            changes.append({
                "paragraph_index": index + 1,
                "before_hash": _hash_text(previous),
                "after_hash": _hash_text(current),
            })
    if before_paragraphs and len(changes) > max(2, (len(before_paragraphs) + 1) // 2):
        raise WritingArchitectureError("Editor revision changes too many paragraphs for a paragraph-local repair round.")
    payload = {
        "schema_version": "v0.21.9",
        "generated_at": utc_now(),
        "section": normalized,
        "iteration": iteration,
        "before_hash": _hash_text(before),
        "after_hash": _hash_text(after),
        "changed_paragraphs": changes,
        "revision_scope": "paragraph_local",
    }
    target = state.path / "writing" / "scientific_editor" / normalized / f"iteration_{iteration:03d}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    _write_json(target, payload)
    return payload

def assess_functional_quality_release(project: str | Path) -> dict[str, Any]:
    """Assess architecture completeness for a v0.22 quality-parity run."""
    state = load_project(project)
    required = {
        "paper_narrative": state.path / "writing" / "paper_brief.json",
        "argument_matrices": state.path / "writing" / "argument_matrices.json",
        "section_lifecycles": state.path / "writing" / "section_lifecycles.json",
        "panel_contracts": state.path / "results" / "panel_figure_contracts.json",
        "venue_writing_contract": state.path / "writing" / "venue_writing_contract.json",
        "style_function_profile": state.path / "writing" / "style_function_profile.json",
    }
    section_reports = {
        section: _read(state.path / "writing" / "section_validation" / f"{section}.json")
        for section in ("introduction", "data", "methods", "results", "discussion")
    }
    section_acceptances = {
        section: _read(state.path / "writing" / "section_acceptance" / f"{section}.json")
        for section in ("introduction", "data", "methods", "results", "discussion")
    }
    component_scores = {
        name: 1.0 if path.exists() else 0.0 for name, path in required.items()
    }
    for section, report in section_reports.items():
        mode = str(report.get("composition_mode") or "")
        decision = str(report.get("decision") or report.get("status") or "")
        coverage = report.get("functional_job_coverage") or {}
        eligible = report.get("quality_parity_eligible") is True and coverage.get("decision") == "pass"
        acceptance = section_acceptances[section]
        claim_bindings = _read(state.path / "writing" / "claim_bindings" / f"{section}.json")
        accepted = (
            acceptance.get("status") == "accepted"
            and acceptance.get("composition_mode") == "codex_free_candidate"
            and acceptance.get("formal_release_eligible") is True
            and acceptance.get("candidate_hash") == report.get("candidate_hash")
            and acceptance.get("evidence_snapshot_id") == report.get("evidence_snapshot_id")
            and claim_bindings.get("status") == "passed"
            and claim_bindings.get("candidate_hash") == report.get("candidate_hash")
            and claim_bindings.get("evidence_snapshot_id") == report.get("evidence_snapshot_id")
        )
        component_scores[f"section_{section}"] = 1.0 if mode == "codex_free_candidate" and decision in {"pass", "accepted"} and eligible and accepted else 0.0
    score = sum(component_scores.values()) / max(len(component_scores), 1)
    accepted_candidate_hashes = {
        section: str(report.get("candidate_hash") or "")
        for section, report in section_acceptances.items()
    }
    evidence_snapshot_ids = sorted({
        str(report.get("evidence_snapshot_id") or "")
        for report in section_acceptances.values()
        if report.get("evidence_snapshot_id")
    })
    payload = {
        "schema_version": "v0.22.2",
        "generated_at": utc_now(),
        "component_scores": component_scores,
        "functional_quality_score": round(score, 4),
        "hard_correctness_required": True,
        "quality_parity_target": 0.95,
        "decision": "pass" if score >= 0.95 else "blocked",
        "accepted_candidate_hashes": accepted_candidate_hashes,
        "evidence_snapshot_ids": evidence_snapshot_ids,
        "blocking_reason": "All manuscript sections must be editor-cleared, explicitly accepted free-prose candidates; deterministic fallback is not release eligible." if score < 0.95 else "",
    }
    target = state.path / "quality" / "functional_quality_release.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    _write_json(target, payload)
    return payload
