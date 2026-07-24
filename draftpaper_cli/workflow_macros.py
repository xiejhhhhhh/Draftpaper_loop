"""Small user-facing workflow macros built on the native Draftpaper orchestrator."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .doctor import doctor_project, verify_next_action
from .orchestrator import run_pipeline, status_project
from .passport import refresh_project_passport
from .project_scaffold import create_project
from .project_state import load_project


def start_workflow(idea: str, field: str, target_journal: str = "General Academic Journal", root: str | Path | None = None) -> dict[str, Any]:
    created = create_project(root=root, idea=idea, field=field, target_journal=target_journal)
    return {"status": "started", "project_path": str(created.path), "project_id": created.project_id, "next_action": status_project(created.path)["next_action"]}


def continue_workflow(project: str | Path) -> dict[str, Any]:
    from .extensions.status_projection import extension_status

    return {
        "status": "reported",
        "pipeline": run_pipeline(project),
        "verification": verify_next_action(project),
        "extensions": extension_status(project),
    }


def review_workflow(project: str | Path) -> dict[str, Any]:
    status = status_project(project)
    root = load_project(project).path
    aggregate = root / "quality_checks" / "blind_reviews" / "aggregate.json"
    next_command = "assess-manuscript-quality-release" if aggregate.is_file() else "prepare-independent-manuscript-review"
    return {"status": "reported", "pipeline_state": status.get("pipeline_state"), "next_command": next_command, "cli": f'python -m draftpaper_cli.cli {next_command} --project "{root}"'}


def recover_workflow(project: str | Path) -> dict[str, Any]:
    report = doctor_project(project)
    commands = []
    for finding in report.get("findings") or []:
        command = finding.get("next_command")
        if command and command not in commands:
            commands.append(command)
    return {"status": "recovery_plan", "doctor_status": report.get("status"), "commands": commands, "protected_actions_require_confirmation": True, "doctor": report}


def rebase_project_passport(project: str | Path, origin: str | Path, confirm: bool = False) -> dict[str, Any]:
    if not confirm:
        raise ValueError("rebase-project-passport is protected and requires --confirm.")
    state = load_project(project)
    parent = load_project(origin)
    if state.metadata.get("project_id") != parent.metadata.get("project_id"):
        raise ValueError("Passport rebase is only for a structural copy of the same project. Use create-project-version for a new scientific version.")
    origin_hash = hashlib.sha256((parent.path / "project_passport.yaml").read_bytes()).hexdigest()
    receipt = {
        "schema_version": "dpl.passport_rebase.v1",
        "origin_project": str(parent.path),
        "origin_passport_sha256": origin_hash,
        "policy": "Scientific changes require create-project-version; this recovery only adopts the current copy as a new managed artifact baseline.",
    }
    target = state.path / "passport_rebase_receipt.json"
    target.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    refresh_project_passport(state.path, event="rebase_project_passport")
    return {"status": "rebased", "project_path": str(state.path), "receipt": "passport_rebase_receipt.json"}
