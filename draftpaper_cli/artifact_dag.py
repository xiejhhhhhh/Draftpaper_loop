"""Artifact-level semantic dependencies and minimal stale propagation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .project_scaffold import _write_json, utc_now
from .project_state import mark_stage_roots_stale


ARTIFACT_DAG = "writing/artifact_dependency_dag.json"
ARTIFACT_STALE_REPORT = "writing/artifact_stale_report.json"


CHANGE_CLASS_ROOTS = {
    "presentation_only": {"latex_render", "independent_reviews", "quality_release"},
    "citation_local": {"affected_section", "latex_assembly", "citation_audit", "independent_reviews", "quality_release"},
    "prose_semantic_no_evidence_change": {"affected_section", "dependent_discussion_claims", "latex_assembly", "citation_audit", "independent_reviews", "quality_release"},
    "metadata_claim_change": {"manuscript_metadata", "latex_assembly", "citation_audit", "independent_reviews", "quality_release"},
    "cohort_definition_change": {"data_semantics", "analysis_execution", "figures", "core_evidence", "all_sections", "latex_assembly", "citation_audit", "independent_reviews", "quality_release"},
    "analysis_spec_change": {"analysis_execution", "figures", "core_evidence", "results", "methods", "discussion", "latex_assembly", "citation_audit", "independent_reviews", "quality_release"},
    "run_output_change": {"figures", "core_evidence", "results", "methods", "discussion", "latex_assembly", "citation_audit", "independent_reviews", "quality_release"},
    "figure_semantic_change": {"core_evidence", "results", "discussion", "latex_assembly", "citation_audit", "independent_reviews", "quality_release"},
    "claim_contract_change": {"research_plan", "data_semantics", "analysis_execution", "figures", "core_evidence", "all_sections", "latex_assembly", "citation_audit", "independent_reviews", "quality_release"},
}


DEFAULT_DEPENDENCIES = {
    "data_semantics": ["research_plan"],
    "analysis_execution": ["research_plan", "data_semantics"],
    "figures": ["analysis_execution"],
    "core_evidence": ["figures"],
    "results": ["core_evidence"],
    "introduction": ["results"],
    "data_section": ["data_semantics", "results"],
    "methods": ["analysis_execution", "results"],
    "discussion": ["results"],
    "all_sections": ["results", "introduction", "data_section", "methods", "discussion"],
    "affected_section": [],
    "dependent_discussion_claims": ["affected_section"],
    "manuscript_metadata": [],
    "latex_assembly": ["all_sections", "manuscript_metadata"],
    "latex_render": ["latex_assembly"],
    "citation_audit": ["latex_assembly"],
    "independent_reviews": ["latex_render", "citation_audit"],
    "quality_release": ["independent_reviews"],
}


def stage_roots_for_change(change_class: str, *, section: str | None = None) -> list[str]:
    """Translate one semantic change into authoritative project-stage roots."""
    if change_class not in CHANGE_CLASS_ROOTS:
        raise ValueError(f"Unsupported artifact change class: {change_class}")
    normalized = str(section or "").strip().lower()
    if change_class in {"presentation_only", "citation_local", "metadata_claim_change"}:
        return ["latex"]
    if change_class == "prose_semantic_no_evidence_change":
        return ["discussion", "latex"] if normalized in {"data", "methods", "results", "introduction"} else ["latex"]
    return {
        "cohort_definition_change": ["data"],
        "analysis_spec_change": ["method_plan"],
        "run_output_change": ["methods"],
        "figure_semantic_change": ["figure_plan"],
        "claim_contract_change": ["research_plan"],
    }[change_class]


def build_artifact_dag(project: str | Path, *, write: bool = True) -> dict[str, Any]:
    root = Path(project)
    from .project_state import load_project
    from .project_system_of_record import managed_artifact_contracts

    state = load_project(root)
    nodes: list[dict[str, Any]] = []
    for stage, metadata in state.metadata.get("stages", {}).items():
        nodes.append({
            "artifact_id": f"stage:{stage}",
            "node_type": "stage",
            "stage": stage,
            "state_revision": int(state.metadata.get("state_revision") or 0),
            "status": metadata.get("status"),
            "stale": bool(metadata.get("stale")),
            "depends_on": [f"stage:{dependency}" for dependency in metadata.get("depends_on") or []],
        })
    for artifact in managed_artifact_contracts(root):
        owner = str(artifact.get("owner_stage") or "project")
        dependencies = list(artifact.get("input_artifact_ids") or [])
        if owner in state.metadata.get("stages", {}):
            dependencies.append(f"stage:{owner}")
        nodes.append({
            **artifact,
            "node_type": "artifact",
            "depends_on": list(dict.fromkeys(dependencies)),
            "authoritative": artifact.get("category") in {"canonical_decision", "scientific_source", "approved_evidence"},
        })
    edges = [
        {"source": dependency, "target": node["artifact_id"]}
        for node in nodes
        for dependency in node.get("depends_on") or []
    ]
    payload = {
        "schema_version": "dpl.artifact_dependency_dag.v2",
        "generated_at": utc_now(),
        "project_id": state.metadata.get("project_id"),
        "state_revision": int(state.metadata.get("state_revision") or 0),
        "nodes": nodes,
        "edges": edges,
        "change_classes": {key: sorted(value) for key, value in CHANGE_CLASS_ROOTS.items()},
        "policy": "Artifact hashes and producer/consumer edges own stale propagation; stage nodes are compatibility summaries.",
    }
    if write:
        _write_json(root / ARTIFACT_DAG, payload)
    return payload


def downstream_artifact_ids(dag: dict[str, Any], roots: list[str]) -> list[str]:
    """Traverse the executable dependency graph from stage or artifact roots."""
    dependents: dict[str, list[str]] = {}
    for edge in dag.get("edges") or []:
        dependents.setdefault(str(edge.get("source")), []).append(str(edge.get("target")))
    visited = set(roots)
    frontier = list(roots)
    while frontier:
        current = frontier.pop(0)
        for dependent in dependents.get(current, []):
            if dependent in visited:
                continue
            visited.add(dependent)
            frontier.append(dependent)
    node_types = {str(node.get("artifact_id")): node.get("node_type") for node in dag.get("nodes") or []}
    return sorted(node_id for node_id in visited if node_types.get(node_id) == "artifact")


def stale_artifacts_for_change(change_class: str, *, section: str | None = None) -> list[str]:
    if change_class not in CHANGE_CLASS_ROOTS:
        raise ValueError(f"Unsupported artifact change class: {change_class}")
    stale = set(CHANGE_CLASS_ROOTS[change_class])
    if "affected_section" in stale and section:
        stale.remove("affected_section")
        stale.add(section)
    if "all_sections" in stale:
        stale.remove("all_sections")
        stale.update({"results", "introduction", "data_section", "methods", "discussion"})
    return sorted(stale)


def record_artifact_change(
    project: str | Path,
    *,
    change_class: str,
    source_artifact: str,
    source_hash: str,
    section: str | None = None,
) -> dict[str, Any]:
    root = Path(project)
    dag = build_artifact_dag(root)
    stale = stale_artifacts_for_change(change_class, section=section)
    stage_roots = stage_roots_for_change(change_class, section=section)
    stale_artifact_ids = downstream_artifact_ids(dag, [f"stage:{stage}" for stage in stage_roots])
    artifact_paths = {
        str(node.get("artifact_id")): str(node.get("path"))
        for node in dag.get("nodes") or []
        if node.get("node_type") == "artifact" and node.get("path")
    }
    stale_stages = mark_stage_roots_stale(root, stage_roots)
    receipt_seed = f"{change_class}|{source_artifact}|{source_hash}|{section or ''}"
    report = {
        "schema_version": "dpl.artifact_stale_report.v1",
        "generated_at": utc_now(),
        "change_id": "change:" + hashlib.sha256(receipt_seed.encode("utf-8")).hexdigest()[:16],
        "change_class": change_class,
        "source_artifact": source_artifact,
        "source_hash": source_hash,
        "section": section,
        "stale_artifacts": stale,
        "stale_artifact_ids": stale_artifact_ids,
        "stale_artifact_paths": sorted(artifact_paths[item] for item in stale_artifact_ids if item in artifact_paths),
        "stage_roots": stage_roots,
        "stale_stages": stale_stages,
        "preserved_artifacts": sorted(
            artifact_paths[item]
            for item in artifact_paths
            if item not in set(stale_artifact_ids)
        ),
        "dag_schema_version": dag["schema_version"],
    }
    _write_json(root / ARTIFACT_STALE_REPORT, report)
    return report
