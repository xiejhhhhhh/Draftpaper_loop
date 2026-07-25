"""Prepare auditable Agent tasks for methods absent from the reusable plugin registry."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .project_scaffold import utc_now
from .project_state import load_project


SUFFICIENCY_REPORT = "research_plan/plugin_sufficiency_report.json"
IMPLEMENTATION_TASKS = "methods/project_method_implementation_tasks.json"


class ProjectMethodImplementationError(RuntimeError):
    """Raised when project-local method implementation tasks cannot be prepared."""


def _read(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def current_project_method_implementation_scope(project: str | Path) -> dict[str, Any]:
    """Return the current scoped Agent implementation contract, if any.

    The scope authorizes code scaffolding only. It does not count as a
    validated method binding until project capability audit and verify-methods
    record the implemented code and real outputs.
    """
    root = Path(project)
    sufficiency_path = root / SUFFICIENCY_REPORT
    tasks_payload = _read(root / IMPLEMENTATION_TASKS)
    current_hash = (
        hashlib.sha256(sufficiency_path.read_bytes()).hexdigest()
        if sufficiency_path.is_file()
        else ""
    )
    declared_hash = str(tasks_payload.get("source_sufficiency_sha256") or "")
    tasks = [
        item
        for item in tasks_payload.get("tasks") or []
        if isinstance(item, dict)
        and item.get("status") in {
            "agent_implementation_required",
            "implementation_in_progress",
        }
    ]
    valid = bool(
        tasks_payload.get("status") == "agent_action_required"
        and current_hash
        and declared_hash == current_hash
        and tasks
    )
    requirement_ids = {
        str(item.get("requirement_id") or "")
        for item in tasks
        if str(item.get("requirement_id") or "")
    }
    by_figure: dict[str, set[str]] = {}
    for item in tasks:
        figure_id = str(item.get("figure_id") or "")
        method_family = str(item.get("method_family") or "")
        if figure_id and method_family:
            by_figure.setdefault(figure_id, set()).add(method_family)
    return {
        "valid": valid,
        "source_sufficiency_sha256": declared_hash,
        "requirement_ids": requirement_ids,
        "methods_by_figure": by_figure,
        "task_count": len(tasks),
    }


def project_method_implementation_covers(
    project: str | Path,
    *,
    figure_id: str,
    method_families: list[str] | tuple[str, ...],
) -> bool:
    scope = current_project_method_implementation_scope(project)
    if not scope["valid"]:
        return False
    covered = scope["methods_by_figure"].get(str(figure_id), set())
    required = {str(item) for item in method_families if str(item).strip()}
    return bool(required) and required.issubset(covered)


def prepare_project_method_implementation(project: str | Path) -> dict[str, Any]:
    state = load_project(project)
    sufficiency = _read(state.path / SUFFICIENCY_REPORT)
    requirements = [
        item
        for item in sufficiency.get("requirement_assessments") or []
        if isinstance(item, dict)
        and item.get("core")
        and item.get("kind") == "method"
        and item.get("state") in {"project_method_implementation_required", "true_missing", "missing"}
    ]
    if not requirements:
        raise ProjectMethodImplementationError("No project-local method implementation requirement is pending.")
    tasks = []
    for item in requirements:
        requirement_id = str(item.get("requirement_id") or "method_requirement")
        method_family = str(item.get("method_family") or requirement_id.rsplit(":", 1)[-1])
        safe_name = "".join(char if char.isalnum() or char == "_" else "_" for char in method_family.lower()).strip("_")
        tasks.append(
            {
                "task_id": f"implement:{requirement_id}",
                "requirement_id": requirement_id,
                "figure_id": item.get("figure_id"),
                "claim_ids": list(item.get("claim_ids") or []),
                "method_family": method_family,
                "capability_pack_id": item.get("capability_pack_id"),
                "required_inputs": list(item.get("input_roles") or item.get("required_inputs") or []),
                "required_outputs": list(item.get("required_outputs") or []),
                "target_code_path": f"methods/src/{safe_name or 'project_method'}.py",
                "target_test_path": f"methods/tests/test_{safe_name or 'project_method'}.py",
                "status": "agent_implementation_required",
                "implementation_contract": {
                    "must_read": [
                        "research_plan/research_capability_contract.json",
                        "research_plan/figure_storyboard.json",
                        "method_plan/method_plan.json",
                        "data/data_inventory.json",
                    ],
                    "must_not": [
                        "substitute a different method merely to produce a similar figure",
                        "promote project-specific code into a discipline module automatically",
                        "claim runtime validation before verify-methods records outputs",
                    ],
                    "search_order": [
                        "project_local_stage_code",
                        "existing_capability_pack_and_registry",
                        "AcademicForge_contracts",
                        "license_compatible_GitHub_research_code",
                        "new_project_local_implementation",
                    ],
                    "acceptance": [
                        "method matches the planned scientific role",
                        "sample unit and split unit are explicit",
                        "outputs satisfy the bound figure contract",
                        "tests or smoke verification are present",
                        "code provenance is recorded",
                    ],
                },
            }
        )
    payload = {
        "schema_version": "dpl.project_method_implementation_tasks.v1",
        "status": "agent_action_required",
        "generated_at": utc_now(),
        "project_id": state.metadata.get("project_id"),
        "source_sufficiency_sha256": hashlib.sha256((state.path / SUFFICIENCY_REPORT).read_bytes()).hexdigest(),
        "tasks": tasks,
        "next_stage": "generate-analysis-code",
        "reaudit_command": f'python -m draftpaper_cli.cli audit-project-capabilities --project "{state.path}"',
        "promotion_policy": "Project-local implementation is sufficient for this paper after run validation; reusable promotion is a separate candidate workflow.",
    }
    output = state.path / IMPLEMENTATION_TASKS
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        "status": "written",
        "decision": "agent_action_required",
        "project_path": str(state.path),
        "task_count": len(tasks),
        "tasks": IMPLEMENTATION_TASKS,
        "next_command": "generate-analysis-code",
    }
