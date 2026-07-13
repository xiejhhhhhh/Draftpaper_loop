# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


MANUSCRIPT_STAGES = [
    "results",
    "introduction",
    "data_writing",
    "methods_writing",
    "discussion",
]

FINAL_STAGES = ["citation_audit", "latex", "quality_checks"]

RESEARCH_DESIGN_STAGES = [
    "research_plan",
    "research_plan_feasibility",
    "data",
    "method_plan",
    "method_feasibility",
    "figure_plan",
    "figure_contracts",
    "code",
    "methods",
    "result_validity",
    "core_evidence",
    *MANUSCRIPT_STAGES,
    *FINAL_STAGES,
]


def artifact_role_for_path(path: str) -> tuple[str, str]:
    """Map a project-relative artifact to its scientific role and owner stage."""
    normalized = str(path or "").replace("\\", "/").lstrip("./")
    lowered = normalized.lower()
    if lowered.startswith("latex/"):
        return "latex_style", "latex"
    if lowered.startswith("citation_audit/"):
        return "citation_report", "citation_audit"
    if lowered.startswith("results/figures/") and lowered.endswith((".png", ".jpg", ".jpeg", ".svg", ".pdf")):
        return "figure", "results"
    if lowered in {
        "results/result_manifest.yaml",
        "results/generated_result_manifest.json",
        "results/figure_metadata.json",
    }:
        return "result_manifest", "results"
    if lowered.startswith("results/tables/"):
        return "result_table", "results"
    if lowered in {"results/results.tex", "introduction/introduction.tex", "discussion/discussion.tex"}:
        return "section_prose", lowered.split("/", 1)[0]
    if lowered == "data/data.tex":
        return "section_prose", "data_writing"
    if lowered == "methods/methods.tex":
        return "section_prose", "methods_writing"
    if lowered.startswith("data/processed/") or lowered.startswith("data/raw/"):
        return "processed_data", "data"
    if lowered in {
        "data/data_code_manifest.json",
        "data/external_data_locators.json",
        "data/source_provenance.json",
    }:
        return "data_schema", "data"
    if lowered.startswith("data/") and lowered.endswith((".py", ".r", ".jl", ".sh")):
        return "data_code", "data"
    if lowered in {
        "methods/method_code_manifest.json",
        "methods/analysis_code_manifest.json",
        "methods/model_provenance.json",
        "code/stage_code_manifest.json",
        "code/code_ownership_manifest.json",
    }:
        return "method_config", "methods"
    if lowered.startswith("methods/") and lowered.endswith(".py"):
        return "method_code", "methods"
    if lowered.startswith("methods/") and "run_manifest" in lowered:
        return "result_metric", "methods"
    if lowered.startswith("research_plan/"):
        if "figure_storyboard" in lowered:
            return "figure_storyboard", "research_plan"
        if "method_plan" in lowered:
            return "method_plan", "research_plan"
        return "research_plan", "research_plan"
    if lowered in {
        "results/figure_quality_report.json",
        "results/figure_semantic_validation_report.json",
        "results/figure_contract_gate_report.json",
    }:
        return "result_manifest", "results"
    if lowered in {"project.json", "project.yaml"}:
        return "idea", "idea"
    if lowered == "references/library.bib":
        return "reference_library", "references"
    if lowered.startswith("references/"):
        return "citation_repair", "references"
    return "unknown", normalized.split("/", 1)[0] or "idea"


@dataclass(frozen=True)
class ChangeClassification:
    change_class: str
    artifact_role: str
    source_stage: str
    scientific_semantics_changed: bool
    presentation_changed: bool
    reason: str
    declaration: dict[str, Any] = field(default_factory=dict)


def _same_evidence_fingerprint(declaration: dict[str, Any]) -> bool:
    before = str(declaration.get("before_evidence_fingerprint") or "")
    after = str(declaration.get("after_evidence_fingerprint") or "")
    return bool(before and before == after)


def classify_change(
    *,
    artifact_role: str,
    before: str | bytes | None,
    after: str | bytes | None,
    source_stage: str,
    declaration: dict[str, Any] | None = None,
) -> ChangeClassification:
    """Classify a change by scientific impact rather than file location alone."""
    declaration = dict(declaration or {})
    role = str(artifact_role or "unknown").strip().lower()
    changed = before != after
    if not changed:
        return ChangeClassification(
            "no_change",
            role,
            source_stage,
            False,
            False,
            "Artifact content is unchanged.",
            declaration,
        )
    if role == "citation_repair" and declaration.get("claim_semantics_changed") is False:
        return ChangeClassification(
            "citation_local",
            role,
            source_stage,
            False,
            True,
            "Citation placement or wording changed without changing the scientific claim.",
            declaration,
        )
    if role == "reference_library":
        before_fingerprint = declaration.get("before_semantic_fingerprint") or {}
        after_fingerprint = declaration.get("after_semantic_fingerprint") or {}
        same_reference_set = bool(before_fingerprint and after_fingerprint) and all(
            before_fingerprint.get(field) == after_fingerprint.get(field)
            for field in ("citation_key_count", "work_count", "citation_keys_sha256", "work_ids_sha256")
        )
        if same_reference_set:
            return ChangeClassification(
                "reference_metadata_only",
                role,
                source_stage,
                False,
                True,
                "Reference keys and canonical works are unchanged; only publication metadata changed.",
                declaration,
            )
        return ChangeClassification(
            "research_design",
            role,
            source_stage,
            True,
            True,
            "The retained reference set changed or could not be proven identical.",
            declaration,
        )
    if role == "citation_report":
        return ChangeClassification(
            "presentation_only",
            role,
            source_stage,
            False,
            True,
            "Citation audit report changed without changing empirical evidence.",
            declaration,
        )
    if role == "figure":
        if declaration.get("cosmetic_only") is True and _same_evidence_fingerprint(declaration):
            return ChangeClassification(
                "presentation_only",
                role,
                source_stage,
                False,
                True,
                "Figure pixels changed while the evidence fingerprint remained identical.",
                declaration,
            )
        return ChangeClassification(
            "scientific_result",
            role,
            source_stage,
            True,
            True,
            "A figure changed without a verified cosmetic-only declaration.",
            declaration,
        )
    if role in {"result_metric", "result_table", "result_manifest"}:
        return ChangeClassification(
            "scientific_result",
            role,
            source_stage,
            True,
            True,
            "Quantitative result evidence changed.",
            declaration,
        )
    if role in {"method_code", "method_config", "validation_split"}:
        return ChangeClassification(
            "method_semantic",
            role,
            source_stage,
            True,
            False,
            "Method implementation or validation semantics changed.",
            declaration,
        )
    if role in {"processed_data", "data_schema", "data_code", "labels"}:
        return ChangeClassification(
            "data_semantic",
            role,
            source_stage,
            True,
            False,
            "Scientific data values, schema, or labels changed.",
            declaration,
        )
    if role in {"research_plan", "idea", "figure_storyboard", "method_plan"}:
        return ChangeClassification(
            "research_design",
            role,
            source_stage,
            True,
            False,
            "The research question or executable research design changed.",
            declaration,
        )
    if role in {"latex_style", "journal_template", "figure_style"}:
        return ChangeClassification(
            "presentation_only",
            role,
            source_stage,
            False,
            True,
            "Only presentation metadata changed.",
            declaration,
        )
    if role in {"section_prose", "abstract"}:
        semantics_changed = declaration.get("claim_semantics_changed") is not False
        return ChangeClassification(
            "prose_semantic" if semantics_changed else "presentation_only",
            role,
            source_stage,
            semantics_changed,
            True,
            "Manuscript prose changed.",
            declaration,
        )
    return ChangeClassification(
        "research_design",
        role,
        source_stage,
        True,
        True,
        "Unknown changes are treated conservatively as research-design changes.",
        declaration,
    )


def affected_stages(change: ChangeClassification) -> list[str]:
    """Return the exact stages invalidated by a classified change."""
    if change.change_class == "no_change":
        return []
    if change.change_class == "citation_local":
        return list(dict.fromkeys([change.source_stage, *FINAL_STAGES]))
    if change.change_class == "reference_metadata_only":
        return list(dict.fromkeys(["references", "citation_audit", "latex", "quality_checks"]))
    if change.change_class == "presentation_only":
        if change.artifact_role == "figure":
            return ["results", "latex", "quality_checks"]
        if change.artifact_role == "citation_report":
            return ["citation_audit", "quality_checks"]
        if change.source_stage == "latex":
            return ["latex", "quality_checks"]
        return list(dict.fromkeys([change.source_stage, "citation_audit", "latex", "quality_checks"]))
    if change.change_class == "scientific_result":
        return [
            "result_validity",
            "core_evidence",
            *MANUSCRIPT_STAGES,
            *FINAL_STAGES,
        ]
    if change.change_class == "method_semantic":
        return [
            "methods",
            "result_validity",
            "core_evidence",
            *MANUSCRIPT_STAGES,
            *FINAL_STAGES,
        ]
    if change.change_class == "data_semantic":
        return [
            "data",
            "method_plan",
            "method_feasibility",
            "figure_plan",
            "figure_contracts",
            "code",
            "methods",
            "result_validity",
            "core_evidence",
            *MANUSCRIPT_STAGES,
            *FINAL_STAGES,
        ]
    if change.change_class == "prose_semantic":
        downstream = [change.source_stage]
        if change.source_stage == "results":
            downstream.extend(["discussion"])
        downstream.extend(FINAL_STAGES)
        return list(dict.fromkeys(downstream))
    upstream = ["references", "journal_profile"] if change.source_stage == "idea" else []
    return list(dict.fromkeys([change.source_stage, *upstream, *RESEARCH_DESIGN_STAGES]))
