# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .metadata import attach_generator_metadata
from .provenance import DPL_SCHEMAS, dpl_block, generated_by_block
from .state_kernel import atomic_write_json, atomic_write_text


class ProjectAlreadyExistsError(FileExistsError):
    """Raised when a paper project already exists and overwrite is not allowed."""


@dataclass(frozen=True)
class ProjectScaffold:
    project_id: str
    project_slug: str
    path: Path
    metadata: dict[str, Any]


PROJECT_DIRECTORIES = [
    "idea",
    "research_plan",
    "research_feasibility",
    "research_plan_feasibility",
    "references",
    "journal_profile",
    "data/acquisition",
    "data/raw",
    "data/processed",
    "data/scripts",
    "observations",
    "method_plan",
    "method_feasibility",
    "figure_plan",
    "figure_contracts",
    "methods",
    "methods/scripts",
    "methods/src",
    "methods/plotting",
    "methods/tests",
    "code",
    "code/shared",
    "code/src",
    "code/scripts",
    "code/tests",
    "result_validity",
    "result_support",
    "core_evidence",
    "results/figures",
    "results/tables",
    "writing",
    "data_writing",
    "methods_writing",
    "introduction",
    "discussion",
    "latex/sections",
    "latex/template",
    "integrity",
    "review",
    "quality_checks",
]

STAGE_ORDER = [
    "idea",
    "references",
    "journal_profile",
    "research_feasibility",
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
    "result_support",
    "core_evidence",
    "results",
    "introduction",
    "data_writing",
    "methods_writing",
    "discussion",
    "latex",
    "quality_checks",
]


def slugify(value: str, max_length: int = 80) -> str:
    """Convert a research idea into a stable, filesystem-friendly slug."""
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower())
    normalized = re.sub(r"-+", "-", normalized).strip("-")
    return (normalized[:max_length].rstrip("-") or "untitled-paper")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _build_stage_metadata() -> dict[str, dict[str, Any]]:
    stages: dict[str, dict[str, Any]] = {}
    for stage in STAGE_ORDER:
        stages[stage] = {
            "status": "draft" if stage == "idea" else "pending",
            "stale": False,
            "depends_on": [],
            "manifest": f"{stage}/stage_manifest.json" if stage != "quality_checks" else "quality_checks/stage_manifest.json",
        }

    stages["references"]["depends_on"] = ["idea"]
    stages["journal_profile"]["depends_on"] = ["idea"]
    stages["research_feasibility"]["depends_on"] = ["references", "journal_profile"]
    stages["research_plan"]["depends_on"] = ["research_feasibility"]
    stages["research_plan_feasibility"]["depends_on"] = ["research_plan"]
    stages["data"]["depends_on"] = ["research_plan_feasibility"]
    stages["method_plan"]["depends_on"] = ["research_plan_feasibility", "references", "data"]
    stages["method_feasibility"]["depends_on"] = ["method_plan", "data"]
    stages["figure_plan"]["depends_on"] = ["method_feasibility", "data", "references", "journal_profile"]
    stages["figure_contracts"]["depends_on"] = ["figure_plan", "method_feasibility", "data"]
    stages["code"]["depends_on"] = ["figure_contracts", "method_plan", "data", "references"]
    stages["methods"]["depends_on"] = ["method_plan", "data", "code"]
    stages["result_validity"]["depends_on"] = ["methods", "method_plan", "data"]
    stages["result_support"]["depends_on"] = ["result_validity", "research_plan", "figure_plan", "methods", "data"]
    stages["core_evidence"]["depends_on"] = ["result_support", "figure_plan", "methods", "data"]
    stages["results"]["depends_on"] = ["core_evidence"]
    stages["introduction"]["depends_on"] = ["research_plan", "references", "journal_profile", "core_evidence"]
    stages["data_writing"]["depends_on"] = ["data", "results", "core_evidence"]
    stages["methods_writing"]["depends_on"] = ["method_plan", "methods", "results", "core_evidence"]
    stages["discussion"]["depends_on"] = ["introduction", "results", "references"]
    stages["latex"]["depends_on"] = ["introduction", "data_writing", "method_plan", "methods_writing", "result_validity", "results", "discussion", "references", "journal_profile"]
    stages["quality_checks"]["depends_on"] = ["latex"]
    return stages


def _write_json(path: Path, payload: Any) -> None:
    if isinstance(payload, dict) and "generated_at" in payload:
        payload = attach_generator_metadata(payload)
    atomic_write_json(path, payload)


def _write_simple_yaml(path: Path, payload: dict[str, Any]) -> None:
    lines: list[str] = []

    def render(key: str, value: Any, indent: int = 0) -> None:
        prefix = " " * indent
        if isinstance(value, dict):
            lines.append(f"{prefix}{key}:")
            for child_key, child_value in value.items():
                render(str(child_key), child_value, indent + 2)
        elif isinstance(value, list):
            lines.append(f"{prefix}{key}:")
            if not value:
                lines.append(f"{prefix}  []")
            for item in value:
                lines.append(f"{prefix}  - {item}")
        elif isinstance(value, bool):
            lines.append(f"{prefix}{key}: {'true' if value else 'false'}")
        elif value is None:
            lines.append(f"{prefix}{key}: null")
        else:
            text = str(value).replace('"', '\\"')
            lines.append(f'{prefix}{key}: "{text}"')

    for root_key, root_value in payload.items():
        render(root_key, root_value)
    atomic_write_text(path, "\n".join(lines) + "\n")


def _write_stage_manifests(project_path: Path, metadata: dict[str, Any]) -> None:
    for stage, stage_meta in metadata["stages"].items():
        stage_dir = project_path / ("quality_checks" if stage == "quality_checks" else stage)
        stage_dir.mkdir(parents=True, exist_ok=True)
        manifest = {
            "project_id": metadata["project_id"],
            "stage": stage,
            "dpl": dpl_block(stage_manifest_schema=DPL_SCHEMAS["stage_manifest"]),
            "generated_by": generated_by_block(schema_version=DPL_SCHEMAS["stage_manifest"]),
            "status": stage_meta["status"],
            "stale": stage_meta["stale"],
            "depends_on": stage_meta["depends_on"],
            "input_files": [],
            "output_files": [],
            "last_updated": metadata["created_at"] if stage == "idea" else None,
        }
        _write_json(stage_dir / "stage_manifest.json", manifest)


def _write_idea_note(project_path: Path, metadata: dict[str, Any]) -> None:
    content = (
        f"# Research Idea\n\n"
        f"**Idea:** {metadata['idea']}\n\n"
        f"**Field:** {metadata['field']}\n\n"
        f"**Target journal:** {metadata['target_journal']}\n\n"
        "## Notes\n\n"
        "Add user constraints, data availability, and writing preferences here before generating the research plan.\n"
    )
    (project_path / "idea" / "idea.md").write_text(content, encoding="utf-8")


def create_project(
    *,
    root: str | Path,
    idea: str,
    field: str,
    target_journal: str | None = None,
    overwrite: bool = False,
) -> ProjectScaffold:
    """Create a single-paper project directory for staged local manuscript work."""
    if not idea.strip():
        raise ValueError("idea is required")
    if not field.strip():
        raise ValueError("field is required")

    root_path = Path(root).expanduser().resolve()
    project_slug = slugify(idea)
    project_path = root_path / project_slug
    if project_path.exists() and not overwrite:
        raise ProjectAlreadyExistsError(f"Project already exists: {project_path}")

    project_path.mkdir(parents=True, exist_ok=True)
    for relative in PROJECT_DIRECTORIES:
        (project_path / relative).mkdir(parents=True, exist_ok=True)

    now = utc_now()
    metadata = {
        "schema_version": 1,
        "dpl": dpl_block(
            project_schema=DPL_SCHEMAS["project"],
            project_passport_schema=DPL_SCHEMAS["project_passport"],
            stage_manifest_schema=DPL_SCHEMAS["stage_manifest"],
            citation_evidence_schema=DPL_SCHEMAS["citation_evidence"],
            run_manifest_schema=DPL_SCHEMAS["run_manifest"],
            result_manifest_schema=DPL_SCHEMAS["result_manifest"],
            artifact_hash_schema=DPL_SCHEMAS["artifact_hash"],
            claim_trace_schema=DPL_SCHEMAS["claim_trace"],
            loop_event_schema=DPL_SCHEMAS["loop_event"],
        ),
        "generated_by": generated_by_block(schema_version=DPL_SCHEMAS["project"]),
        "project_id": project_slug,
        "project_slug": project_slug,
        "title": idea.strip(),
        "idea": idea.strip(),
        "field": field.strip(),
        "target_journal": (target_journal or "General Academic Journal").strip(),
        "created_at": now,
        "updated_at": now,
        "current_stage": "idea",
        "legacy_mvp_reference": "legacy MVP design notes",
        "stages": _build_stage_metadata(),
    }

    _write_json(project_path / "project.json", metadata)
    _write_simple_yaml(project_path / "project.yaml", metadata)
    _write_stage_manifests(project_path, metadata)
    _write_idea_note(project_path, metadata)
    from .passport import initialize_project_passport

    initialize_project_passport(project_path)

    return ProjectScaffold(
        project_id=project_slug,
        project_slug=project_slug,
        path=project_path,
        metadata=metadata,
    )
