# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from draftpaper_cli.core_evidence import assess_core_evidence
from draftpaper_cli.figure_plan import plan_figures
from draftpaper_cli.orchestrator import run_pipeline
from draftpaper_cli.passport import refresh_project_passport
from draftpaper_cli.project_scaffold import create_project
from draftpaper_cli.project_state import update_stage_status


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _prepare_planning_inputs(project_path: Path) -> None:
    _write_json(
        project_path / "data" / "data_inventory.json",
        {
            "files": [
                {
                    "path": "data/processed/model_inputs.csv",
                    "kind": "processed",
                    "suffix": ".csv",
                    "readable": True,
                    "row_count": 120,
                    "column_count": 5,
                    "columns": ["source_id", "class_label", "flux", "hardness", "time_bin"],
                }
            ]
        },
    )
    (project_path / "research_plan" / "research_plan.md").write_text("Research plan", encoding="utf-8")
    _write_json(project_path / "references" / "literature_items.json", [])
    _write_json(project_path / "journal_profile" / "journal_profile.json", {"profile": {"journal": "APJS"}})
    (project_path / "methods" / "method_plan.md").write_text("Use a token-level Transformer and ablation study.", encoding="utf-8")
    _write_json(
        project_path / "methods" / "method_requirements.json",
        {
            "method_data_fit": "proceed",
            "user_method": "Use a token-level Transformer and ablation study.",
            "method_families": ["time_aware_transformer", "ablation_study"],
            "required_data_features": ["flux", "hardness", "class_label"],
        },
    )
    update_stage_status(project_path, "method_plan", "draft")


class FigureContractTests(unittest.TestCase):
    def test_storyboard_main_figures_are_not_replaced_by_discipline_fallbacks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(
                root=tmp,
                idea="Time-aware Transformer classification of WXT flaring sources",
                field="high-energy astronomy machine learning",
                target_journal="APJS",
            )
            _prepare_planning_inputs(project.path)
            _write_json(
                project.path / "research_plan" / "figure_storyboard.json",
                {
                    "status": "written",
                    "figures": [
                        {
                            "figure_id": "fig_1_workflow",
                            "proposed_title": "End-to-end time-aware classification workflow",
                            "research_question": "How is the data-to-model workflow constructed?",
                            "expected_finding": "The workflow should expose the complete data and method route.",
                            "required_data": ["source_catalog", "light_curve", "class_label"],
                            "required_method": ["data_alignment"],
                            "suggested_plot_type": "data_overview",
                            "validation_metric": "pipeline_completeness",
                            "supporting_literature_keys": ["Ref2024"],
                        },
                        {
                            "figure_id": "fig_2_transformer_performance",
                            "proposed_title": "Token-level Transformer source-held-out performance",
                            "research_question": "Does the token-level Transformer improve source-held-out classification?",
                            "expected_finding": "The planned Transformer result should be compared against baselines.",
                            "required_data": ["current_observation_tokens", "history_lc_tokens", "class_label"],
                            "required_method": ["time_aware_transformer", "source_held_out_validation"],
                            "suggested_plot_type": "metric_summary",
                            "validation_metric": "f1_macro",
                            "supporting_literature_keys": ["Ref2024"],
                        },
                    ],
                },
            )

            plan_figures(project.path)

            plan = json.loads((project.path / "results" / "figure_plan.json").read_text(encoding="utf-8"))
            contracts = json.loads((project.path / "results" / "figure_contracts.json").read_text(encoding="utf-8"))
            alignment = json.loads((project.path / "results" / "storyboard_alignment_report.json").read_text(encoding="utf-8"))
            main_figures = [item for item in plan["figures"] if item.get("figure_role") == "main_result"]
            supporting_figures = [item for item in plan["figures"] if item.get("figure_role") != "main_result"]

            self.assertEqual([item["storyboard_id"] for item in main_figures], ["fig_1_workflow", "fig_2_transformer_performance"])
            self.assertEqual(plan["main_figure_count"], 2)
            self.assertGreaterEqual(len(supporting_figures), 1)
            self.assertTrue(all(item.get("contract_locked") for item in main_figures))
            self.assertTrue(all(not item.get("counts_toward_main_figures", True) for item in supporting_figures))
            self.assertEqual([item["storyboard_id"] for item in contracts["contracts"]], ["fig_1_workflow", "fig_2_transformer_performance"])
            self.assertEqual(alignment["decision"], "pass")

    def test_core_evidence_blocks_missing_main_contract_and_recommends_repair(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Transformer classification", field="astronomy machine learning")
            results = project.path / "results"
            methods = project.path / "methods"
            data = project.path / "data"
            (results / "figures").mkdir(parents=True, exist_ok=True)
            (results / "figures" / "supporting_metric.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 256)
            _write_json(
                results / "figure_contracts.json",
                {
                    "contracts": [
                        {
                            "storyboard_id": "fig_transformer",
                            "title": "Token-level Transformer source-held-out performance",
                            "path": "results/figures/fig_transformer.png",
                            "required_data": ["current_observation_tokens", "history_lc_tokens", "class_label"],
                            "required_method": ["time_aware_transformer", "source_held_out_validation"],
                            "allowed_substitute": False,
                        }
                    ]
                },
            )
            _write_json(
                results / "figure_plan.json",
                {
                    "figures": [
                        {
                            "id": "supporting_metric",
                            "path": "results/figures/supporting_metric.png",
                            "title": "Supporting baseline metric",
                            "figure_role": "supporting",
                            "counts_toward_main_figures": False,
                        }
                    ]
                },
            )
            _write_json(
                results / "figure_metadata.json",
                {
                    "figures": [
                        {
                            "figure_id": "supporting_metric",
                            "path": "results/figures/supporting_metric.png",
                            "title": "Supporting baseline metric",
                            "caption": "Supporting baseline metric.",
                            "has_axes": True,
                            "axis_labels": {"x": "metric", "y": "value"},
                            "interpretation_summary": "A supporting baseline is visible.",
                            "publication_ready": True,
                        }
                    ]
                },
            )
            _write_json(
                results / "figure_execution_diagnosis.json",
                {
                    "figures": [
                        {
                            "storyboard_id": "fig_transformer",
                            "status": "missing_method_repairing",
                            "required_method": ["time_aware_transformer"],
                        }
                    ]
                },
            )
            _write_json(methods / "run_manifest.yaml", {"status": "success", "figures_generated": ["results/figures/supporting_metric.png"]})
            _write_json(results / "result_validity_report.json", {"decision": "pass"})
            _write_json(data / "data_acquisition_plan.json", {"tasks": [{"status": "ready"}]})
            _write_json(data / "data_inventory.json", {"files": [{"path": "data/processed/model_inputs.csv"}]})
            _write_json(data / "data_quality_report.json", {"decision": "pass"})
            _write_json(data / "data_feasibility_report.json", {"decision": "pass"})

            report = assess_core_evidence(project.path)

            self.assertEqual(report["decision"], "revise_required")
            self.assertIn("figure_contract_coverage", report)
            self.assertFalse(report["figure_contract_coverage"]["all_main_contracts_satisfied"])
            self.assertEqual(report["recommended_next_action"]["command"], "repair-figure-method")
            refresh_project_passport(project.path, event="test_core_evidence_repair_route")
            plan = run_pipeline(project.path)
            self.assertEqual(plan["next_action"]["stage"], "core_evidence")
            self.assertEqual(plan["next_action"]["command"], "repair-figure-method")


if __name__ == "__main__":
    unittest.main()
