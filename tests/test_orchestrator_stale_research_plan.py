from __future__ import annotations

import json

from draftpaper_cli.orchestrator import _gate_failure_action, _next_action
from draftpaper_cli.project_scaffold import create_project
from draftpaper_cli.project_state import load_project, update_stage_status


def test_stale_research_plan_ignores_historical_review_packet(tmp_path) -> None:
    project = create_project(root=tmp_path, idea="A study", field="astronomy").path
    research_plan = project / "research_plan"
    (research_plan / "research_plan.md").write_text("old plan", encoding="utf-8")
    (research_plan / "research_plan_confirmation_required.json").write_text(
        json.dumps({"status": "required"}), encoding="utf-8"
    )
    update_stage_status(project, "research_plan", "stale")

    assert _gate_failure_action(project) is None
    action = _next_action(project, load_project(project).metadata)
    assert action["command"] != "review-research-plan"
    assert action["stage"] in {"references", "journal_profile", "research_feasibility", "research_plan"}
