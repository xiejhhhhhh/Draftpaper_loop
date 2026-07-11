# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json
import hashlib

from draftpaper_cli.project_scaffold import create_project


def _json(path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _png(path, width: int, height: int) -> None:
    from PIL import Image, ImageDraw

    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    margin = max(12, width // 18)
    gap = max(20, width // 10)
    panel_width = (width - 2 * margin - gap) // 2
    for panel in range(2):
        left = margin + panel * (panel_width + gap)
        right = left + panel_width
        top = max(20, height // 10)
        bottom = height - max(25, height // 7)
        draw.line((left, top, left, bottom), fill="black", width=max(2, width // 400))
        draw.line((left, bottom, right, bottom), fill="black", width=max(2, width // 400))
        for index, fraction in enumerate((0.45, 0.7, 0.58)):
            x0 = left + panel_width * (index + 1) // 5
            x1 = x0 + max(8, panel_width // 9)
            y0 = bottom - int((bottom - top) * fraction)
            draw.rectangle((x0, y0, x1, bottom - 1), fill=(40 + panel * 70, 110, 180 - panel * 40), outline="black")
        draw.text((left + 8, bottom + 8), f"Panel {panel + 1} model score", fill="black")
        draw.text((left + 8, top + 4), "Macro F1", fill="black")
    image.save(path)


def test_publication_figure_quality_requires_semantics_plugins_and_legibility(tmp_path) -> None:
    from draftpaper_cli.scientific_figure_quality import assess_scientific_figure_quality

    project = create_project(root=tmp_path, idea="Model study", field="machine learning", target_journal="Test").path
    _png(project / "results" / "figures" / "fig_main.png", 1600, 1000)
    table = project / "results" / "tables" / "fig_main.csv"
    table.parent.mkdir(parents=True, exist_ok=True)
    table.write_text("model,f1\nbaseline,0.86\nproposed,0.81\n", encoding="utf-8")
    table_hash = hashlib.sha256(table.read_bytes()).hexdigest()
    _json(project / "results" / "figure_contracts.json", {"main_contracts": [{
        "figure_id": "fig_main", "scientific_question": "Does the model improve?", "required_variable_roles": ["performance_metric"],
        "required_method_outputs": ["f1"], "required_panels": ["baseline", "proposed"],
    }]})
    _json(project / "results" / "figure_metadata.json", {"figures": [{
        "figure_id": "fig_main", "path": "results/figures/fig_main.png", "has_axes": True,
        "axis_labels": {"x": "model", "y": "macro F1"}, "text_elements": ["Baseline", "Proposed"],
        "statistics": {"baseline_f1": 0.86, "proposed_f1": 0.81}, "interpretation_summary": "The baseline remains stronger.",
        "variable_roles": ["performance_metric"], "method_outputs": ["f1"], "panels": ["baseline", "proposed"],
        "source_tables": ["results/tables/fig_main.csv"],
        "publication_ready": True,
    }]})
    _json(project / "results" / "figure_plugin_trace_report.json", {"decision": "pass", "figure_checks": [{
        "figure_id": "fig_main", "data_plugin_ids": ["table_loader"], "method_plugin_ids": ["baseline_model"], "run_output_event_id": "evt_1",
    }]})
    (project / "methods" / "plugin_execution_ledger.jsonl").write_text(json.dumps({
        "event_id": "evt_1", "status": "project_executed",
        "output_hashes": {"results/tables/fig_main.csv": table_hash},
    }) + "\n", encoding="utf-8")

    report = assess_scientific_figure_quality(project)

    assert report["score"] >= 0.95
    assert report["decision"] == "pass"


def test_publication_figure_quality_rejects_small_untraced_semantic_shell(tmp_path) -> None:
    from draftpaper_cli.scientific_figure_quality import assess_scientific_figure_quality

    project = create_project(root=tmp_path, idea="Model study", field="machine learning", target_journal="Test").path
    _png(project / "results" / "figures" / "fig_main.png", 120, 80)
    _json(project / "results" / "figure_contracts.json", {"main_contracts": [{
        "figure_id": "fig_main", "scientific_question": "Does the model improve?", "required_variable_roles": ["performance_metric"], "required_method_outputs": ["f1"],
    }]})
    _json(project / "results" / "figure_metadata.json", {"figures": [{"figure_id": "fig_main", "path": "results/figures/fig_main.png", "has_axes": True}]})
    _json(project / "results" / "figure_plugin_trace_report.json", {"decision": "ready_for_codegen", "figure_checks": []})

    report = assess_scientific_figure_quality(project)

    assert report["score"] < 0.6
    assert report["decision"] == "repair_required"
    assert {item["kind"] for item in report["issues"]} >= {"insufficient_pixel_dimensions", "missing_plugin_run_trace", "semantic_contract_incomplete"}


def test_publication_figure_quality_rejects_forged_metadata_on_blank_png(tmp_path) -> None:
    from PIL import Image
    from draftpaper_cli.scientific_figure_quality import assess_scientific_figure_quality

    project = create_project(root=tmp_path, idea="Forged figure", field="machine learning", target_journal="Test").path
    path = project / "results" / "figures" / "blank.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (1600, 1000), "white").save(path)
    _json(project / "results" / "figure_contracts.json", {"main_contracts": [{
        "figure_id": "blank", "scientific_question": "Does the model improve?",
        "required_variable_roles": ["performance_metric"], "required_method_outputs": ["f1"],
    }]})
    _json(project / "results" / "figure_metadata.json", {"figures": [{
        "figure_id": "blank", "path": "results/figures/blank.png", "axis_labels": {"x": "model", "y": "F1"},
        "text_elements": ["model", "F1"], "statistics": {"f1": 0.9}, "interpretation_summary": "Strong result",
        "variable_roles": ["performance_metric"], "method_outputs": ["f1"], "publication_ready": True,
    }]})
    _json(project / "results" / "figure_plugin_trace_report.json", {"figure_checks": []})

    report = assess_scientific_figure_quality(project)

    assert report["decision"] == "repair_required"
    assert "invalid_missing_or_blank_png" in {item["kind"] for item in report["issues"]}


def test_generic_plotter_refuses_unknown_main_result_substitution(tmp_path) -> None:
    import pytest

    from draftpaper_cli.plotting.scientific_svg import ScientificPlotError, render_scientific_figure

    with pytest.raises(ScientificPlotError, match="plugin method output"):
        render_scientific_figure(
            tmp_path,
            {
                "id": "fig_main",
                "path": "results/figures/fig_main.png",
                "generation_mode": "generated_code",
                "figure_type": "domain_specific_unknown_plot",
                "figure_role": "main_result",
            },
            [{"feature": "1.0", "label": "A"}],
            {},
            ["feature"],
            "label",
        )
