# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json

from draftpaper_cli.project_scaffold import create_project


def test_result_review_blocks_when_main_figure_trace_is_not_complete(tmp_path) -> None:
    from draftpaper_cli.result_discipline_review import review_results_with_discipline_rules

    project = create_project(root=tmp_path, idea="Remote sensing prediction with random forest.", field="geography machine learning", target_journal="Test").path
    (project / "results" / "results.tex").write_text("\\section{Results}\n", encoding="utf-8")
    (project / "results" / "figure_plugin_trace_report.json").write_text(json.dumps({"decision": "blocked", "figure_checks": []}), encoding="utf-8")

    result = review_results_with_discipline_rules(project)
    saved = json.loads((project / "review" / "result_discipline_review_report.json").read_text(encoding="utf-8"))

    assert result["decision"] == "revise_required"
    assert saved["trace_decision"] == "blocked"
    assert saved["recommended_next_action"]["command"] == "prepare-plugin-rescue"
