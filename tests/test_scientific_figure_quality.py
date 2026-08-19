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


def test_publication_figure_quality_requires_semantics_plugins_and_legibility(tmp_path, monkeypatch) -> None:
    from draftpaper_cli import scientific_figure_quality as figure_quality

    monkeypatch.setattr(
        figure_quality,
        "_ocr_png",
        lambda _path: ("Baseline Proposed Macro F1", "rapidocr_onnxruntime", 0.97),
    )

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
        "minimum_font_points": 8,
        "panel_overlap_detected": False,
        "content_cropped": False,
        "colorblind_safe": True,
        "caption_self_contained": True,
        "panel_finite_check": True,
        "panel_finite_value_count": 6,
        "panel_nonfinite_value_count": 0,
        "global_title": False,
        "display_labels_checked": True,
        "display_label_map": {"baseline": "Baseline", "proposed": "Proposed"},
        "publication_ready": True,
    }]})
    _json(project / "results" / "figure_plugin_trace_report.json", {"decision": "pass", "figure_checks": [{
        "figure_id": "fig_main", "data_plugin_ids": ["table_loader"], "method_plugin_ids": ["baseline_model"], "run_output_event_id": "evt_1",
    }]})
    (project / "methods" / "plugin_execution_ledger.jsonl").write_text(json.dumps({
        "event_id": "evt_1", "status": "project_executed",
        "output_hashes": {"results/tables/fig_main.csv": table_hash},
    }) + "\n", encoding="utf-8")

    report = figure_quality.assess_scientific_figure_quality(project)

    assert report["score"] >= 0.95
    assert report["decision"] == "pass"
    assert report["figure_checks"][0]["pixel_evidence"]["inferred_plot_body_content_groups"] >= 2


def test_workflow_diagram_does_not_require_axis_region_pixels(tmp_path, monkeypatch) -> None:
    from draftpaper_cli import scientific_figure_quality as figure_quality

    monkeypatch.setattr(
        figure_quality,
        "_ocr_png",
        lambda _path: ("Data Method Validation Reporting", "rapidocr_onnxruntime", 0.98),
    )
    monkeypatch.setattr(
        figure_quality,
        "_pixel_evidence",
        lambda _path: {
            "decoded": True,
            "nonblank": True,
            "axis_region_evidence": False,
            "text_edge_evidence": True,
            "inferred_horizontal_content_groups": 4,
            "inferred_plot_body_content_groups": 4,
        },
    )

    project = create_project(root=tmp_path, idea="Workflow study", field="astronomy", target_journal="Test").path
    _png(project / "results" / "figures" / "workflow.png", 1600, 1000)
    table = project / "results" / "tables" / "workflow.csv"
    table.parent.mkdir(parents=True, exist_ok=True)
    table.write_text("stage,count\ndata,1\n", encoding="utf-8")
    table_hash = hashlib.sha256(table.read_bytes()).hexdigest()
    _json(project / "results" / "figure_contracts.json", {"main_contracts": [{
        "figure_id": "workflow", "scientific_question": "How does evidence reach a decision?",
        "required_variable_roles": ["data_flow"], "required_method_outputs": ["pipeline_completeness"],
        "plot_grammar": "workflow_diagram",
    }]})
    _json(project / "results" / "figure_metadata.json", {"figures": [{
        "figure_id": "workflow", "path": "results/figures/workflow.png", "has_axes": False,
        "axis_labels": {}, "text_elements": ["Data", "Method", "Validation", "Reporting"],
        "statistics": {"pipeline_completeness": 1.0},
        "interpretation_summary": "The diagram traces the evidence workflow.",
        "variable_roles": ["data_flow"], "method_outputs": ["pipeline_completeness"],
        "plot_grammar": "workflow_diagram", "source_tables": ["results/tables/workflow.csv"],
        "minimum_font_points": 8, "panel_overlap_detected": False, "content_cropped": False,
        "colorblind_safe": True, "caption_self_contained": True, "panel_finite_check": True,
        "panel_finite_value_count": 1, "panel_nonfinite_value_count": 0, "global_title": False,
        "display_labels_checked": True, "display_label_map": {}, "publication_ready": True,
    }]})
    _json(project / "results" / "figure_plugin_trace_report.json", {"decision": "pass", "figure_checks": [{
        "figure_id": "workflow", "data_plugin_ids": ["table_loader"],
        "method_plugin_ids": ["workflow_renderer"], "run_output_event_id": "evt_workflow",
    }]})
    (project / "methods" / "plugin_execution_ledger.jsonl").write_text(json.dumps({
        "event_id": "evt_workflow", "status": "project_executed",
        "output_hashes": {"results/tables/workflow.csv": table_hash},
    }) + "\n", encoding="utf-8")

    report = figure_quality.assess_scientific_figure_quality(project)

    assert report["decision"] == "pass"
    assert "rendered_axis_or_text_evidence_missing" not in {item["kind"] for item in report["issues"]}


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


def test_publication_figure_quality_rejects_gallery_with_only_panel_frames(tmp_path) -> None:
    from PIL import Image, ImageDraw
    from draftpaper_cli.scientific_figure_quality import assess_scientific_figure_quality

    project = create_project(root=tmp_path, idea="Image gallery", field="astronomy", target_journal="Test").path
    path = project / "results" / "figures" / "gallery.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (1600, 1000), "white")
    draw = ImageDraw.Draw(image)
    for row in range(2):
        for column in range(4):
            left = 20 + column * 395
            top = 70 + row * 460
            draw.rectangle((left, top, left + 360, top + 380), outline="black", width=3)
            draw.text((left + 10, top - 25), f"Candidate {row * 4 + column + 1}", fill="black")
    image.save(path)
    table = project / "results" / "tables" / "candidates.csv"
    table.parent.mkdir(parents=True, exist_ok=True)
    table.write_text("candidate,score\n1,0.9\n", encoding="utf-8")
    table_hash = hashlib.sha256(table.read_bytes()).hexdigest()
    _json(project / "results" / "figure_contracts.json", {"main_contracts": [{
        "figure_id": "gallery", "scientific_question": "Which candidates require review?",
        "required_variable_roles": ["features"], "required_method_outputs": ["candidate_stability"],
        "plot_grammar": "image_gallery",
    }]})
    _json(project / "results" / "figure_metadata.json", {"figures": [{
        "figure_id": "gallery", "path": "results/figures/gallery.png",
        "statistics": {"candidate_stability": 0.9}, "interpretation_summary": "Candidates require review.",
        "variable_roles": ["features"], "method_outputs": ["candidate_stability"],
        "plot_grammar": "image_gallery", "source_tables": ["results/tables/candidates.csv"],
    }]})
    _json(project / "results" / "figure_plugin_trace_report.json", {"figure_checks": [{
        "figure_id": "gallery", "data_plugin_ids": ["image_loader"], "method_plugin_ids": ["anomaly_model"],
        "run_output_event_id": "evt_gallery",
    }]})
    (project / "methods" / "plugin_execution_ledger.jsonl").write_text(json.dumps({
        "event_id": "evt_gallery", "status": "project_executed",
        "output_hashes": {"results/tables/candidates.csv": table_hash},
    }) + "\n", encoding="utf-8")

    report = assess_scientific_figure_quality(project)

    assert report["decision"] == "repair_required"
    assert "empty_image_gallery_panels" in {item["kind"] for item in report["issues"]}


def test_figure_source_rejects_global_titles_and_internal_label_fallbacks(tmp_path) -> None:
    from draftpaper_cli.scientific_figure_quality import _figure_code_quality

    source = tmp_path / "methods" / "scripts" / "plot.py"
    source.parent.mkdir(parents=True)
    source.write_text(
        "fig.suptitle('internal title')\n"
        "labels = frame.model_name.map(MODEL_LABELS).fillna(frame.model_name)\n",
        encoding="utf-8",
    )
    kinds = {item["kind"] for item in _figure_code_quality(tmp_path)}
    assert "figure_level_title_forbidden" in kinds
    assert "unmapped_internal_label_fallback" in kinds


def test_figure_source_rejects_subplot_titles(tmp_path) -> None:
    from draftpaper_cli.scientific_figure_quality import _figure_code_quality

    source = tmp_path / "methods" / "src" / "plot.py"
    source.parent.mkdir(parents=True)
    source.write_text("axes[0].set_title('panel title')\n", encoding="utf-8")
    kinds = {item["kind"] for item in _figure_code_quality(tmp_path)}
    assert "figure_level_title_forbidden" in kinds


def test_dynamic_model_dictionary_rejects_unmapped_and_code_style_labels() -> None:
    from draftpaper_cli.scientific_figure_quality import _display_label_issues

    item = {
        "display_labels_checked": True,
        "display_label_map": {
            "current_spectrum": "Current and spectrum",
            "new_history_branch": "new_history_branch",
        },
    }
    kinds = {
        issue["kind"]
        for issue in _display_label_issues(
            item,
            {"current_spectrum", "new_history_branch", "unmapped_model_branch"},
        )
    }
    assert "display_label_dictionary_incomplete" in kinds
    assert "display_label_dictionary_invalid" in kinds


def test_rendered_png_ocr_reports_visible_text_and_confidence(tmp_path, monkeypatch) -> None:
    from PIL import Image
    from draftpaper_cli import scientific_figure_quality as figure_quality

    image_path = tmp_path / "figure.png"
    Image.new("RGB", (24, 24), "white").save(image_path)

    class FakeOCR:
        def __call__(self, _image):
            return ([[[0, 0], "current_only", 0.95]], None)

    monkeypatch.setattr(figure_quality, "RapidOCR", lambda: FakeOCR())
    text, backend, confidence = figure_quality._ocr_png(image_path)
    assert text == "current_only"
    assert backend == "rapidocr_onnxruntime"
    assert confidence == 0.95


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
