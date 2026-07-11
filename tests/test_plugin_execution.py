# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json

from draftpaper_cli.project_scaffold import create_project


def test_plugin_execution_writes_stage_owned_binding_and_hash_ledger(tmp_path) -> None:
    from draftpaper_cli.plugin_execution import execute_method_plugins

    project = create_project(root=tmp_path, idea="Aeon time series classification.", field="machine learning", target_journal="Test").path
    plan = {
        "bindings": [{
            "requirement_id": "method:fig_main:aeon_time_series_classification",
            "figure_id": "fig_main",
            "kind": "method",
            "plugin_id": "aeon_time_series_classification",
            "state": "covered",
            "runtime_class": "local_optional_dependency",
            "validation_level": "fixture_runnable",
        }],
    }
    (project / "research_plan" / "plugin_binding_plan.json").write_text(json.dumps(plan), encoding="utf-8")

    result = execute_method_plugins(project)
    ledger = (project / "methods" / "plugin_execution_ledger.jsonl").read_text(encoding="utf-8").splitlines()
    event = json.loads(ledger[-1])

    assert result["binding_count"] == 1
    assert event["plugin_id"] == "aeon_time_series_classification"
    assert event["stage"] == "methods"
    assert event["manifest_sha256"]
    assert event["template_path"].endswith("template.py")
    assert (project / "methods" / "plugin_runs" / "aeon_time_series_classification" / "plugin_fixture_result.json").exists()
