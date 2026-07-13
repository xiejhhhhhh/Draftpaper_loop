"""Project-root policy, Windows path budgets, and project-layout diagnostics."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from pathlib import Path
from typing import Any

from .project_scaffold import utc_now


PROJECT_SLUG_MAX = 48
PROJECT_NAME_MAX = 64
PROJECT_ROOT_BUDGET = 100
GENERAL_PATH_BUDGET = 200
TOOL_PATH_BUDGET = 180
CONFIG_ENV = "DRAFTPAPER_PROJECTS_ROOT"
WORKSPACE_CONTRACT = "project_workspace.json"


class WorkspacePolicyError(RuntimeError):
    """Raised when a project path violates the configured workspace policy."""


class ArtifactOwnershipGuard:
    """Resolve every managed output under one paper-project ownership root."""

    def __init__(self, project_path: str | Path) -> None:
        self.project_path = Path(project_path).expanduser().resolve(strict=True)

    def output(self, candidate: str | Path, *, explicit_export: bool = False) -> Path:
        return validate_output_path(self.project_path, candidate, explicit_export=explicit_export)


def _config_projects_root() -> Path | None:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return None
    config_path = Path(appdata) / "DraftpaperLoop" / "config.toml"
    if not config_path.exists():
        return None
    text = config_path.read_text(encoding="utf-8-sig", errors="replace")
    match = re.search(r'^\s*projects_root\s*=\s*["\'](.+?)["\']\s*$', text, flags=re.MULTILINE)
    return Path(match.group(1)).expanduser() if match else None


def _repository_projects_root() -> Path:
    package_root = Path(__file__).resolve().parent.parent
    if (package_root / "pyproject.toml").exists():
        return package_root / "projects"
    return Path.cwd() / "projects"


def resolve_projects_root(explicit: str | Path | None = None) -> Path:
    """Resolve the central paper-project root without hard-coding one machine."""
    candidate = (
        Path(explicit).expanduser()
        if explicit
        else Path(os.environ[CONFIG_ENV]).expanduser()
        if os.environ.get(CONFIG_ENV)
        else _config_projects_root()
        or _repository_projects_root()
    )
    return candidate.resolve()


def project_identifier(idea: str, field: str) -> str:
    payload = f"{idea.strip()}\n{field.strip()}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:8]


def short_project_slug(idea: str, field: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", idea.strip().lower())
    normalized = re.sub(r"-+", "-", normalized).strip("-") or "paper"
    identifier = project_identifier(idea, field)
    base_budget = PROJECT_SLUG_MAX - len(identifier) - 1
    base = normalized[:base_budget].rstrip("-") or "paper"
    return f"{base}_{identifier}"


def _path_length(path: Path) -> int:
    return len(str(path.resolve()))


def assess_path_budget(project_path: str | Path, *, include_tree: bool = True) -> dict[str, Any]:
    root = Path(project_path).expanduser().resolve()
    checks: list[dict[str, Any]] = []

    def add(path: Path, category: str, budget: int) -> None:
        length = _path_length(path)
        checks.append({
            "path": str(path),
            "category": category,
            "length": length,
            "budget": budget,
            "within_budget": length <= budget,
        })

    add(root, "project_root", PROJECT_ROOT_BUDGET)
    if include_tree and root.exists():
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(root).as_posix().lower()
            tool_sensitive = relative.startswith(("latex/", "references/")) or path.suffix.lower() in {".tex", ".bib", ".bst", ".cls"}
            add(path, "latex_or_bibliography" if tool_sensitive else "artifact", TOOL_PATH_BUDGET if tool_sensitive else GENERAL_PATH_BUDGET)
    violations = [item for item in checks if not item["within_budget"]]
    return {
        "schema_version": "dpl.path_budget_report.v1",
        "status": "passed" if not violations else "failed",
        "generated_at": utc_now(),
        "project_path": str(root),
        "budgets": {
            "project_slug_max": PROJECT_SLUG_MAX,
            "project_name_max": PROJECT_NAME_MAX,
            "project_root": PROJECT_ROOT_BUDGET,
            "general_path": GENERAL_PATH_BUDGET,
            "latex_or_bibliography": TOOL_PATH_BUDGET,
        },
        "checks": checks,
        "violations": violations,
    }


def require_path_budget(project_path: str | Path, *, include_tree: bool = True) -> dict[str, Any]:
    """Reject tool-sensitive execution when the project exceeds safe path budgets."""
    report = assess_path_budget(project_path, include_tree=include_tree)
    if report["status"] != "passed":
        first = report["violations"][0]
        raise WorkspacePolicyError(
            "Project path budget failed before tool-sensitive execution: "
            f"{first['category']} path length {first['length']} exceeds {first['budget']}. "
            "Run path-budget-check and create a short versioned project before continuing."
        )
    return report


def write_workspace_contract(project_path: str | Path, projects_root: str | Path) -> dict[str, Any]:
    root = Path(project_path).resolve()
    payload = {
        "schema_version": "dpl.project_workspace.v1",
        "status": "active",
        "generated_at": utc_now(),
        "project_root": str(root),
        "projects_root": str(Path(projects_root).resolve()),
        "artifact_policy": "all_managed_outputs_remain_inside_project_except_explicit_export",
        "temporary_root": ".draftpaper/tmp",
        "log_root": ".draftpaper/logs",
        "external_data_policy": "manifest_only_read_only_by_default",
        "path_budgets": assess_path_budget(root, include_tree=False)["budgets"],
    }
    (root / WORKSPACE_CONTRACT).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def validate_output_path(project_path: str | Path, output: str | Path, *, explicit_export: bool = False) -> Path:
    root = Path(project_path).expanduser().resolve(strict=True)
    raw = Path(output).expanduser()
    target = (raw if raw.is_absolute() else root / raw).resolve()
    if explicit_export:
        return target
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise WorkspacePolicyError(f"Managed output escapes the paper project: {target}") from exc
    return target


_ORPHAN_TARGETS = {
    "citation_audit_latest.json": "citation_audit/imported_citation_audit_latest.json",
    "discussion_prepare_output.json": "discussion/imported_discussion_prepare_output.json",
    "quality_latest.json": "quality_checks/imported_quality_latest.json",
    "reviewer_01_current.json": "review/imported_reviewer_01_current.json",
    "reviewer_02_current.json": "review/imported_reviewer_02_current.json",
}


def doctor_project_layout(project: str | Path) -> dict[str, Any]:
    root = Path(project).expanduser().resolve()
    metadata = json.loads((root / "project.json").read_text(encoding="utf-8-sig"))
    candidates: list[dict[str, Any]] = []
    for name, target in _ORPHAN_TARGETS.items():
        source = root.parent / name
        if not source.is_file():
            continue
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        ownership = "unverified"
        try:
            payload = json.loads(source.read_text(encoding="utf-8-sig"))
            serialized = json.dumps(payload, ensure_ascii=False)
            if str(metadata.get("project_id")) in serialized or str(metadata.get("project_slug")) in serialized:
                ownership = "project_id_or_slug_match"
        except (OSError, json.JSONDecodeError):
            pass
        candidates.append({"source": str(source), "target": target, "sha256": digest, "ownership": ownership})
    tmp = root.parent / "tmp"
    if tmp.is_dir():
        candidates.append({"source": str(tmp), "target": ".draftpaper/imported_tmp", "sha256": None, "ownership": "unverified_directory"})
    budget = assess_path_budget(root)
    return {
        "schema_version": "dpl.project_layout_diagnosis.v1",
        "status": "passed" if not candidates and budget["status"] == "passed" else "review_required",
        "generated_at": utc_now(),
        "project_path": str(root),
        "orphan_candidates": candidates,
        "path_budget": budget,
        "policy": "Candidates are never adopted without an explicit write request and verified project ownership.",
    }


def adopt_orphan_artifacts(project: str | Path, *, write: bool = False) -> dict[str, Any]:
    diagnosis = doctor_project_layout(project)
    root = Path(project).expanduser().resolve()
    actions: list[dict[str, Any]] = []
    for item in diagnosis["orphan_candidates"]:
        eligible = item.get("ownership") == "project_id_or_slug_match" and Path(str(item["source"])).is_file()
        action = {**item, "eligible": eligible, "action": "planned" if eligible else "skipped_unverified"}
        if write and eligible:
            destination = validate_output_path(root, str(item["target"]))
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                action["action"] = "skipped_target_exists"
            else:
                shutil.copy2(Path(str(item["source"])), destination)
                action["action"] = "copied_into_project"
        actions.append(action)
    return {
        "schema_version": "dpl.orphan_adoption_plan.v1",
        "status": "written" if write else "dry_run",
        "generated_at": utc_now(),
        "project_path": str(root),
        "actions": actions,
        "copied_count": sum(item["action"] == "copied_into_project" for item in actions),
        "policy": "Source artifacts are not deleted; adoption is copy-only and hash-auditable.",
    }


def apply_orphan_adoption(project: str | Path) -> dict[str, Any]:
    """Apply only the hash- and identity-verified subset of an adoption plan."""
    return adopt_orphan_artifacts(project, write=True)
