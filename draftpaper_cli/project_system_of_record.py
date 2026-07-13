"""Authoritative artifact categories for Draftpaper-loop projects."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .artifact_repository import ArtifactRepository
from .passport import collect_artifacts
from .project_scaffold import utc_now
from .structured_io import read_mapping


SYSTEM_OF_RECORD_PATH = "project_system_of_record.json"


STAGE_WRITERS = {
    "references": "search-literature",
    "journal_profile": "resolve-journal-template",
    "research_plan": "generate-plan",
    "data": "inventory-data",
    "method_plan": "collect-method-plan",
    "figure_plan": "plan-figures",
    "figure_contracts": "assess-figure-contracts",
    "code": "generate-analysis-code",
    "methods": "verify-methods",
    "result_validity": "assess-result-validity",
    "result_support": "assess-result-support",
    "core_evidence": "assess-core-evidence",
    "results": "inventory-results",
    "introduction": "write-introduction",
    "data_writing": "write-data",
    "methods_writing": "write-methods",
    "discussion": "write-discussion",
    "latex": "assemble-latex",
    "quality_checks": "quality-check",
}


ARTIFACT_CATEGORIES: dict[str, dict[str, Any]] = {
    "canonical_decision": {
        "description": "User-approved scientific or manuscript decisions.",
        "mutation_policy": "protected_command_or_explicit_user_confirmation",
        "rebuildable": False,
        "examples": [
            "idea/idea.md",
            "research_plan/research_plan.md",
            "writing/section_acceptance/*.json",
            "writing/revisions/*.json",
        ],
    },
    "scientific_source": {
        "description": "Data, code, references, plugin manifests, and run outputs that can produce evidence.",
        "mutation_policy": "stage_owned_command",
        "rebuildable": False,
        "examples": [
            "data/raw/**",
            "data/processed/**",
            "data/scripts/**",
            "methods/src/**",
            "references/reference_registry.json",
        ],
    },
    "approved_evidence": {
        "description": "Human-confirmed evidence snapshots and their bound figures, metrics, and claims.",
        "mutation_policy": "explicit_reopen_then_stage_owned_command",
        "rebuildable": False,
        "examples": [
            "results/promoted_evidence_snapshot.json",
            "core_evidence/core_evidence_report.json",
        ],
    },
    "derived_rebuildable": {
        "description": "Reports, indices, packets, and rendered projections derived from declared inputs.",
        "mutation_policy": "declared_writer_only",
        "rebuildable": True,
        "examples": [
            "results/result_manifest.yaml",
            "writing/section_packets/*.json",
            "citation_audit/*.html",
            "quality_checks/*.json",
        ],
    },
    "runtime_private": {
        "description": "Caches, locks, credentials, private captures, and temporary artifacts.",
        "mutation_policy": "runtime_only",
        "rebuildable": True,
        "public_repository_allowed": False,
        "examples": [
            ".env",
            "tmp/**",
            "references/fulltext/**",
            "quality_checks/local_eval_captures/**",
        ],
    },
    "lineage_baseline": {
        "description": "Read-only artifacts retained from a parent project for comparison or audit.",
        "mutation_policy": "version_import_only",
        "rebuildable": False,
        "active_evidence_allowed": False,
        "examples": [
            "lineage/baseline_assets/**",
            "lineage/legacy_reports/**",
        ],
    },
}


def build_system_of_record_payload(project_id: str) -> dict[str, Any]:
    return {
        "schema_version": "dpl.system_of_record.v1",
        "project_id": project_id,
        "generated_at": utc_now(),
        "categories": ARTIFACT_CATEGORIES,
        "artifact_contract_schema": {
            "required_fields": [
                "artifact_id",
                "path",
                "category",
                "owner_stage",
                "writer_command",
                "input_artifact_ids",
                "input_sha256",
                "schema_version",
                "generator_version",
                "evidence_snapshot_id",
                "run_id",
                "privacy_class",
                "rebuild_command",
            ],
            "dynamic_view": "inspect-system-of-record",
        },
        "stage_rebuild_contracts": STAGE_WRITERS,
        "invariants": [
            "Derived artifacts cannot overwrite canonical decisions or scientific sources.",
            "An artifact is current only when its owner stage and declared input hashes are current.",
            "Approved evidence requires explicit reopen before scientific regeneration.",
            "Lineage baseline artifacts cannot enter the active evidence graph.",
            "Runtime-private artifacts are excluded from public fixtures and package data.",
        ],
    }


def _artifact_category(relative: str) -> str:
    normalized = relative.replace("\\", "/")
    if normalized.startswith("lineage/") or normalized == "project_lineage.json":
        return "lineage_baseline"
    if normalized.startswith(("tmp/", "references/fulltext/")) or normalized.startswith(".env"):
        return "runtime_private"
    if normalized in {"idea/idea.md", "research_plan/research_plan.md"} or normalized.startswith(
        ("writing/section_acceptance/", "writing/revisions/")
    ):
        return "canonical_decision"
    if normalized.startswith(("data/", "methods/", "code/", "references/")) and not normalized.endswith(
        ("stage_manifest.json", ".html")
    ):
        return "scientific_source"
    if normalized in {
        "results/promoted_evidence_snapshot.json",
        "core_evidence/core_evidence_report.json",
    }:
        return "approved_evidence"
    return "derived_rebuildable"


def _manifest_bindings(root: Path) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    output_bindings: dict[str, dict[str, Any]] = {}
    input_hashes: dict[str, str] = {}
    for manifest_path in root.rglob("stage_manifest.json"):
        manifest = read_mapping(manifest_path)
        stage = str(manifest.get("stage") or manifest_path.parent.name)
        inputs = [str(item).replace("\\", "/") for item in (manifest.get("input_files") or [])]
        for relative in inputs:
            path = (root / relative).resolve()
            if path.is_file():
                input_hashes[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
        for relative in manifest.get("output_files") or []:
            output_bindings[str(relative).replace("\\", "/")] = {
                "stage": stage,
                "inputs": inputs,
                "schema_version": manifest.get("schema_version") or (manifest.get("dpl") or {}).get("stage_manifest_schema"),
                "generator_version": (manifest.get("generated_by") or {}).get("version"),
                "run_id": manifest.get("run_id"),
                "evidence_snapshot_id": manifest.get("evidence_snapshot_id"),
            }
    return output_bindings, input_hashes


def managed_artifact_contracts(project: str | Path) -> list[dict[str, Any]]:
    root = Path(project).expanduser().resolve()
    if root.is_file():
        root = root.parent
    bindings, input_hashes = _manifest_bindings(root)
    collected = collect_artifacts(root)
    artifact_ids = {str(item["path"]): str(item["artifact_id"]) for item in collected}
    records: list[dict[str, Any]] = []
    for artifact in collected:
        relative = str(artifact["path"])
        binding = bindings.get(relative) or {}
        owner_stage = str(binding.get("stage") or artifact.get("stage") or "project")
        inputs = list(binding.get("inputs") or [])
        category = _artifact_category(relative)
        writer = STAGE_WRITERS.get(owner_stage)
        records.append(
            {
                "artifact_id": artifact.get("artifact_id"),
                "path": relative,
                "sha256": artifact.get("sha256"),
                "category": category,
                "owner_stage": owner_stage,
                "writer_command": writer,
                "input_artifact_ids": [artifact_ids.get(item, item) for item in inputs],
                "input_sha256": {item: input_hashes.get(item) for item in inputs},
                "schema_version": binding.get("schema_version"),
                "generator_version": binding.get("generator_version"),
                "evidence_snapshot_id": binding.get("evidence_snapshot_id"),
                "run_id": binding.get("run_id"),
                "privacy_class": "private" if category == "runtime_private" else "project_local",
                "rebuild_command": writer if category == "derived_rebuildable" else None,
                "active_evidence_allowed": category != "lineage_baseline",
            }
        )
    return records


def initialize_project_system_of_record(project: str | Path, project_id: str) -> dict[str, Any]:
    payload = build_system_of_record_payload(project_id)
    ArtifactRepository(project).write_json(SYSTEM_OF_RECORD_PATH, payload)
    return payload


def inspect_project_system_of_record(project: str | Path) -> dict[str, Any]:
    root = Path(project).expanduser().resolve()
    if root.is_file():
        root = root.parent
    payload = read_mapping(root / SYSTEM_OF_RECORD_PATH)
    if not payload:
        return {
            "status": "missing",
            "project_path": str(root),
            "system_of_record": SYSTEM_OF_RECORD_PATH,
            "recommended_command": "migrate-project",
        }
    categories = payload.get("categories") if isinstance(payload.get("categories"), dict) else {}
    artifacts = managed_artifact_contracts(root)
    violations = [
        {
            "code": "lineage_artifact_marked_active",
            "path": item["path"],
        }
        for item in artifacts
        if item["category"] == "lineage_baseline" and item.get("active_evidence_allowed")
    ]
    return {
        "status": "current" if categories else "invalid",
        "project_path": str(root),
        "schema_version": payload.get("schema_version"),
        "category_count": len(categories),
        "categories": sorted(categories),
        "invariants": list(payload.get("invariants") or []),
        "system_of_record": SYSTEM_OF_RECORD_PATH,
        "artifact_count": len(artifacts),
        "artifacts": artifacts,
        "violation_count": len(violations),
        "violations": violations,
    }
