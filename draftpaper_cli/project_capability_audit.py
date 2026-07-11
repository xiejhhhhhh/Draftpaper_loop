# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

"""Audit apparent plugin gaps against stage-owned project-local capabilities."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .html_utils import write_html_report
from .project_scaffold import utc_now
from .project_state import load_project


SUFFICIENCY_REPORT = "research_plan/plugin_sufficiency_report.json"
BINDING_PLAN = "research_plan/plugin_binding_plan.json"
AUDIT_JSON = "research_plan/project_capability_audit.json"
AUDIT_HTML = "research_plan/project_capability_audit.html"

ROLE_TERMS = {
    "label": {"label", "class", "category", "target", "source_class"},
    "spectral_features": {"spectral", "hardness", "pha", "arf", "rmf", "spectrum"},
    "multiwavelength_features": {"multiwavelength", "multi_wavelength", "multiband", "counterpart", "crossmatch", "catalog_match"},
    "multimodal_learning": {"multimodal", "fusion", "transformer", "token", "timeaware", "time_aware"},
    "modality_availability": {"dataset_quality", "completeness", "inventory", "availability", "token", "spectrum"},
}


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _role_for(requirement: dict[str, Any]) -> str:
    return str(requirement.get("role") or requirement.get("method_family") or "").strip().lower()


def _candidate_files(project_path: Path, kind: str) -> list[Path]:
    roots = [project_path / "data" / "raw", project_path / "data" / "processed"] if kind == "data" else [project_path / "methods" / "scripts", project_path / "methods" / "src", project_path / "code" / "src"]
    suffixes = {".csv", ".tsv", ".json"} if kind == "data" else {".py"}
    files = []
    for root in roots:
        if root.exists():
            files.extend(
                path for path in root.rglob("*")
                if path.is_file()
                and path.suffix.lower() in suffixes
                and "__pycache__" not in path.parts
                and path.name not in {"generated_pipeline.py", "scientific_plotting.py", "install_plotting_requirements.py"}
            )
    return files


def _text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig", errors="replace")[:16000].lower()
    except OSError:
        return ""


def _matches(requirement: dict[str, Any], path: Path) -> tuple[int, list[str]]:
    role = _role_for(requirement)
    terms = ROLE_TERMS.get(role, {part for part in role.replace("_", " ").split() if part})
    text = f"{path.name.lower()} {_text(path)}"
    matched = sorted(term for term in terms if term in text)
    if requirement.get("kind") == "method" and role == "multimodal_learning":
        valid = ("fusion" in matched and "transformer" in matched) or "multimodal" in matched
        return (len(matched) if valid else 0), matched
    score = len(matched)
    if requirement.get("kind") == "method" and path.name.lower().startswith(("train_", "fit_", "run_")):
        score += 2
    return score, matched


def _binding(requirement: dict[str, Any], evidence: Path, matched_terms: list[str], score: int, project_path: Path) -> dict[str, Any]:
    role = _role_for(requirement)
    return {
        "requirement_id": requirement.get("requirement_id"),
        "figure_id": requirement.get("figure_id"),
        "kind": requirement.get("kind"),
        "plugin_id": f"project_local:{role}",
        "binding_scope": "project_local",
        "state": "covered_project_local",
        "coverage_basis": "stage_owned_project_asset",
        "runtime_class": "project_local_verified_asset",
        "validation_level": "project_asset_audited",
        "evidence": {
            "path": str(evidence.relative_to(project_path)).replace("\\", "/"),
            "sha256": _sha256(evidence),
            "matched_terms": matched_terms,
            "match_score": score,
        },
        "promotion_policy": "project_local_only; run candidate generalization and explicit promotion separately before any discipline-module write",
    }


def _render(report: dict[str, Any]) -> str:
    lines = ["# Project Capability Audit", "", f"Decision: `{report.get('decision')}`", ""]
    for item in report.get("assessments") or []:
        evidence = (item.get("binding") or {}).get("evidence") or {}
        lines.append(f"- `{item.get('requirement_id')}`: **{item.get('state')}**; evidence: `{evidence.get('path') or 'none'}`")
    return "\n".join(lines)


def audit_project_capabilities(project: str | Path) -> dict[str, Any]:
    """Resolve missing capability requirements from local stage-owned evidence only."""
    state = load_project(project)
    sufficiency = _read_json(state.path / SUFFICIENCY_REPORT)
    assessments = list(sufficiency.get("requirement_assessments") or [])
    bindings_payload = _read_json(state.path / BINDING_PLAN)
    bindings = [item for item in bindings_payload.get("bindings") or [] if isinstance(item, dict)]
    audit_items = []
    for requirement in assessments:
        if not isinstance(requirement, dict) or requirement.get("kind") not in {"data", "method"} or requirement.get("state") not in {"missing", "partially_covered", "audit_required", "covered_project_local", "true_missing"}:
            continue
        candidates = []
        for path in _candidate_files(state.path, str(requirement["kind"])):
            score, terms = _matches(requirement, path)
            if score:
                candidates.append((score, path, terms))
        candidates.sort(key=lambda item: (-item[0], str(item[1])))
        if candidates:
            score, evidence, terms = candidates[0]
            binding = _binding(requirement, evidence, terms, score, state.path)
            requirement.update({
                "state": "covered_project_local",
                "matched_plugin_id": binding["plugin_id"],
                "binding_scope": "project_local",
                "coverage_basis": binding["coverage_basis"],
                "project_local_evidence": binding["evidence"],
            })
            bindings = [item for item in bindings if item.get("requirement_id") != binding["requirement_id"]]
            bindings.append(binding)
            audit_items.append({"requirement_id": requirement.get("requirement_id"), "state": "covered_project_local", "binding": binding})
        else:
            requirement["state"] = "true_missing"
            audit_items.append({"requirement_id": requirement.get("requirement_id"), "state": "true_missing", "binding": None})
    core_unresolved = [
        item for item in assessments
        if isinstance(item, dict) and item.get("core") and item.get("kind") in {"data", "method"} and item.get("state") not in {"covered", "covered_project_local"}
    ]
    sufficiency["requirement_assessments"] = assessments
    sufficiency["decision"] = "blocked" if core_unresolved else "pass"
    sufficiency["core_figure_decision"] = sufficiency["decision"]
    sufficiency["rescue_tasks"] = [item for item in sufficiency.get("rescue_tasks") or [] if item.get("requirement_id") in {row.get("requirement_id") for row in core_unresolved}]
    bindings_payload.update({"status": "written", "generated_at": utc_now(), "bindings": bindings})
    report = {
        "status": "written",
        "generated_at": utc_now(),
        "project_id": state.metadata.get("project_id"),
        "decision": sufficiency["decision"],
        "assessments": audit_items,
        "unresolved_requirement_ids": [item.get("requirement_id") for item in core_unresolved],
        "policy": "Project-local bindings are auditable only within this project. They do not create a discipline plugin, alter a global manifest, or bypass candidate validation and explicit promotion.",
    }
    _write_json(state.path / SUFFICIENCY_REPORT, sufficiency)
    _write_json(state.path / BINDING_PLAN, bindings_payload)
    _write_json(state.path / AUDIT_JSON, report)
    write_html_report(state.path / AUDIT_HTML, _render(report), title="Project Capability Audit")
    return {"status": "written", "project_path": str(state.path), "decision": report["decision"], "covered_project_local": sum(item.get("state") == "covered_project_local" for item in audit_items), "unresolved_count": len(core_unresolved), "report": AUDIT_JSON}
