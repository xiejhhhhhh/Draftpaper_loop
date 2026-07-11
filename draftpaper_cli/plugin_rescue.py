# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

"""Prepare scoped capability-rescue work without silently importing source code."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .html_utils import write_html_report
from .project_scaffold import utc_now
from .project_state import load_project


RESCUE_PLAN = "review/plugin_rescue_plan.json"
RESCUE_HTML = "review/plugin_rescue_plan.html"
SUFFICIENCY_REPORT = "research_plan/plugin_sufficiency_report.json"


class PluginRescueError(RuntimeError):
    """Raised when a plugin rescue plan cannot be constructed."""


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


def _command(project: Path, name: str, extra: str = "") -> str:
    return f'python -m draftpaper_cli.cli {name} --project "{project}"{extra}'


def _routes(project: Path, scope: dict[str, Any], academicforge_root: str | None, github_metadata: str | None) -> list[dict[str, Any]]:
    discipline = str(scope.get("discipline") or "default")
    role = str(scope.get("role") or "missing_capability")
    routes = [{
        "route": "existing_registry",
        "action": "Re-run structured plugin sufficiency after confirming aliases, variants, and manifest overlays.",
        "command": _command(project, "assess-plugin-sufficiency"),
    }]
    if academicforge_root:
        routes.append({
            "route": "academicforge",
            "action": "Inspect and classify only the skill scope needed by this missing capability; do not copy third-party source into a discipline module.",
            "command": f'python -m draftpaper_cli.cli compile-skill-source --source-root "{academicforge_root}" --adapter academicforge --discipline {discipline} --output-root "{project / "plugin_candidates"}"',
        })
    if github_metadata:
        routes.append({
            "route": "github_research_code",
            "action": "Discover and inspect license-aware research-code candidates for this single capability, then create a reviewable candidate instead of importing code directly.",
            "command": f'python -m draftpaper_cli.cli discover-research-repos --output-root "{project / "plugin_candidates"}" --discipline {discipline} --query "{role}" --from-json "{github_metadata}"',
        })
    routes.extend([
        {
            "route": "candidate_generalization",
            "action": "Generalize only the reusable contract, template, fixtures, and provenance after privacy/license review.",
            "command": _command(project, "generalize-plugin-candidate"),
        },
        {
            "route": "candidate_validation",
            "action": "Run genericity, privacy, fixture, duplicate, and runtime validation before promotion.",
            "command": _command(project, "validate-plugin-candidate"),
        },
        {
            "route": "explicit_promotion",
            "action": "Promotion writes a manifest/template only after human review; project-specific or license-uncertain code stays local.",
            "command": "python -m draftpaper_cli.cli promote-plugin-candidate --candidate <validated_candidate> --require-human-confirmation --write",
        },
    ])
    return routes


def _render(payload: dict[str, Any]) -> str:
    lines = ["# Plugin Rescue Plan", "", "## Missing Capabilities", ""]
    for task in payload.get("tasks") or []:
        lines.append(f"- `{task.get('requirement_id')}` ({task.get('state')}): {task.get('search_scope', {}).get('role')}")
        for route in task.get("routes") or []:
            lines.append(f"  - `{route.get('route')}`: `{route.get('command')}`")
    return "\n".join(lines)


def prepare_plugin_rescue(
    project: str | Path,
    *,
    academicforge_root: str | None = None,
    github_metadata: str | None = None,
) -> dict[str, Any]:
    """Write ordered, scoped rescue tasks for insufficiency gaps.

    The function produces commands and review requirements only. It does not
    clone repositories, use credentials, promote candidates, or execute unknown
    third-party code.
    """
    state = load_project(project)
    sufficiency = _read_json(state.path / SUFFICIENCY_REPORT)
    gaps = sufficiency.get("rescue_tasks") or []
    if not isinstance(gaps, list):
        raise PluginRescueError(f"Invalid rescue tasks in {SUFFICIENCY_REPORT}")
    tasks = []
    for item in gaps:
        if not isinstance(item, dict):
            continue
        scope = dict(item.get("search_scope") or {})
        tasks.append({
            "requirement_id": str(item.get("requirement_id") or "missing_requirement"),
            "figure_id": item.get("figure_id"),
            "kind": str(item.get("kind") or "method"),
            "state": str(item.get("state") or "missing"),
            "search_scope": scope,
            "routes": _routes(state.path, scope, academicforge_root, github_metadata),
            "stop_condition": "Return to assess-plugin-sufficiency only after a validated, explicitly promoted reusable plugin or a project-local method/data implementation is available.",
        })
    commands = []
    for task in tasks:
        for route in task["routes"]:
            command = str(route.get("command") or "")
            if command and command not in commands:
                commands.append(command)
    payload = {
        "status": "written",
        "generated_at": utc_now(),
        "project_id": state.metadata.get("project_id"),
        "decision": "rescue_prepared" if tasks else "not_required",
        "source_sufficiency_report": SUFFICIENCY_REPORT,
        "tasks": tasks,
        "recommended_next_commands": commands,
        "promotion_policy": {
            "requires_explicit_human_confirmation": True,
            "project_specific_code_policy": "keep_project_local",
            "license_uncertain_code_policy": "do_not_promote",
            "deduplicate_before_write": True,
        },
    }
    _write_json(state.path / RESCUE_PLAN, payload)
    write_html_report(state.path / RESCUE_HTML, _render(payload), title="Plugin Rescue Plan")
    return {"status": "written", "project_path": str(state.path), "decision": payload["decision"], "task_count": len(tasks), "plugin_rescue_plan": RESCUE_PLAN}
