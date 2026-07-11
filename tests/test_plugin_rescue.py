# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json
from pathlib import Path

from draftpaper_cli.project_scaffold import create_project


def test_plugin_rescue_scopes_academicforge_and_github_work_to_each_gap(tmp_path: Path) -> None:
    from draftpaper_cli.plugin_rescue import prepare_plugin_rescue

    project = create_project(
        root=tmp_path,
        idea="A remote sensing study needs a bespoke segmentation method.",
        field="geography machine learning",
        target_journal="Test Journal",
    ).path
    report = {
        "decision": "blocked",
        "rescue_tasks": [{
            "requirement_id": "method:fig_01:bespoke_segmentation",
            "kind": "method",
            "figure_id": "fig_01",
            "state": "missing",
            "search_scope": {"discipline": "machine_learning", "role": "bespoke_segmentation"},
        }],
    }
    path = project / "research_plan" / "plugin_sufficiency_report.json"
    path.write_text(json.dumps(report), encoding="utf-8")

    result = prepare_plugin_rescue(project, academicforge_root="D:/AcademicForge", github_metadata="D:/repos.json")
    saved = json.loads((project / "review" / "plugin_rescue_plan.json").read_text(encoding="utf-8"))

    assert result["decision"] == "rescue_prepared"
    task = saved["tasks"][0]
    assert task["requirement_id"] == "method:fig_01:bespoke_segmentation"
    assert task["search_scope"]["role"] == "bespoke_segmentation"
    assert any(item["route"] == "academicforge" for item in task["routes"])
    assert any(item["route"] == "github_research_code" for item in task["routes"])
    assert saved["promotion_policy"]["requires_explicit_human_confirmation"] is True
    assert any("promote-plugin-candidate" in command and "--write" in command for command in saved["recommended_next_commands"])
