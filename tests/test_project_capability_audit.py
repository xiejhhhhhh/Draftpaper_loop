# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json

from draftpaper_cli.project_scaffold import create_project


def test_audit_converts_traceable_local_data_and_transformer_code_to_project_local_bindings(tmp_path) -> None:
    from draftpaper_cli.project_capability_audit import audit_project_capabilities

    project = create_project(root=tmp_path, idea="Astronomy transformer test", field="astronomy machine learning", target_journal="Test").path
    (project / "data" / "processed" / "events.csv").write_text(
        "label,spectral_hardness,multiwavelength_counterpart\n0,0.2,1\n", encoding="utf-8"
    )
    (project / "methods" / "scripts" / "fusion_transformer.py").write_text(
        "class TimeAwareFusionTransformer:\n    pass\n", encoding="utf-8"
    )
    report = {
        "decision": "blocked",
        "core_figure_decision": "blocked",
        "requirement_assessments": [
            {"requirement_id": "data:fig_main:label", "kind": "data", "figure_id": "fig_main", "role": "label", "core": True, "state": "missing"},
            {"requirement_id": "data:fig_main:spectral_features", "kind": "data", "figure_id": "fig_main", "role": "spectral_features", "core": True, "state": "missing"},
            {"requirement_id": "data:fig_main:multiwavelength_features", "kind": "data", "figure_id": "fig_main", "role": "multiwavelength_features", "core": True, "state": "missing"},
            {"requirement_id": "method:fig_main:multimodal_learning", "kind": "method", "figure_id": "fig_main", "method_family": "multimodal_learning", "core": True, "state": "missing"},
        ],
        "rescue_tasks": [],
    }
    (project / "research_plan" / "plugin_sufficiency_report.json").write_text(json.dumps(report), encoding="utf-8")
    (project / "research_plan" / "plugin_binding_plan.json").write_text(json.dumps({"bindings": []}), encoding="utf-8")

    result = audit_project_capabilities(project)
    updated = json.loads((project / "research_plan" / "plugin_sufficiency_report.json").read_text(encoding="utf-8"))
    bindings = json.loads((project / "research_plan" / "plugin_binding_plan.json").read_text(encoding="utf-8"))

    assert result["decision"] == "pass"
    assert updated["decision"] == "pass"
    assert {item["state"] for item in updated["requirement_assessments"]} == {"covered_project_local"}
    assert all(item["binding_scope"] == "project_local" for item in bindings["bindings"])


def test_audit_recognizes_common_project_local_analysis_roles(tmp_path) -> None:
    from draftpaper_cli.project_capability_audit import audit_project_capabilities

    project_path = create_project(
        root=tmp_path,
        idea="Astronomy baseline feature diagnostics",
        field="astronomy machine learning",
        target_journal="Test",
    ).path
    processed = project_path / "data" / "processed"
    scripts = project_path / "methods" / "scripts"
    processed.mkdir(parents=True, exist_ok=True)
    scripts.mkdir(parents=True, exist_ok=True)
    (processed / "history_lc_tokens.csv").write_text(
        "source_id,mjd,rate,class_label\n1,1.0,0.4,AGN\n",
        encoding="utf-8",
    )
    (scripts / "train_baselines.py").write_text(
        "# class_count and value_counts diagnostics\n"
        "# baseline random_forest feature importance and spectral feature_space\n",
        encoding="utf-8",
    )
    requirements = [
        ("data:fig_1:light_curve", "data", "light_curve"),
        ("method:fig_2:class_balance_check", "method", "class_balance_check"),
        ("method:fig_3:feature_space_diagnostic", "method", "feature_space_diagnostic"),
        ("method:fig_4:baseline_model", "method", "baseline_model"),
    ]
    report_path = project_path / "research_plan" / "plugin_sufficiency_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps({
            "requirement_assessments": [
                {
                    "requirement_id": requirement_id,
                    "figure_id": requirement_id.split(":")[1],
                    "kind": kind,
                    "role": role,
                    "state": "execution_required",
                    "core": True,
                }
                for requirement_id, kind, role in requirements
            ],
            "rescue_tasks": [],
        }),
        encoding="utf-8",
    )
    (project_path / "research_plan" / "plugin_binding_plan.json").write_text(
        json.dumps({"bindings": []}), encoding="utf-8"
    )

    result = audit_project_capabilities(project_path)

    assert result["decision"] == "pass"
    assert result["covered_project_local"] == 4
