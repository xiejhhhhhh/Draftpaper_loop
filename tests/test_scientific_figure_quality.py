# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json
import struct
import zlib

from draftpaper_cli.project_scaffold import create_project


def _json(path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _png(path, width: int, height: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = b"".join(b"\x00" + b"\xff\xff\xff" * width for _ in range(height))
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def test_publication_figure_quality_requires_semantics_plugins_and_legibility(tmp_path) -> None:
    from draftpaper_cli.scientific_figure_quality import assess_scientific_figure_quality

    project = create_project(root=tmp_path, idea="Model study", field="machine learning", target_journal="Test").path
    _png(project / "results" / "figures" / "fig_main.png", 1600, 1000)
    _json(project / "results" / "figure_contracts.json", {"main_contracts": [{
        "figure_id": "fig_main", "scientific_question": "Does the model improve?", "required_variable_roles": ["performance_metric"],
        "required_method_outputs": ["f1"], "required_panels": ["baseline", "proposed"],
    }]})
    _json(project / "results" / "figure_metadata.json", {"figures": [{
        "figure_id": "fig_main", "path": "results/figures/fig_main.png", "has_axes": True,
        "axis_labels": {"x": "model", "y": "macro F1"}, "text_elements": ["Baseline", "Proposed"],
        "statistics": {"baseline_f1": 0.86, "proposed_f1": 0.81}, "interpretation_summary": "The baseline remains stronger.",
        "variable_roles": ["performance_metric"], "method_outputs": ["f1"], "panels": ["baseline", "proposed"],
        "publication_ready": True,
    }]})
    _json(project / "results" / "figure_plugin_trace_report.json", {"decision": "pass", "figure_checks": [{
        "figure_id": "fig_main", "data_plugin_ids": ["table_loader"], "method_plugin_ids": ["baseline_model"], "run_output_event_id": "evt_1",
    }]})

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
