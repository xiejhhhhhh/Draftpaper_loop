# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json
import tempfile
import unittest

from draftpaper_cli.core_evidence import assess_core_evidence
from draftpaper_cli.orchestrator import run_pipeline
from draftpaper_cli.passport import refresh_project_passport
from draftpaper_cli.project_scaffold import create_project
from draftpaper_cli.project_state import update_stage_status


class EvidenceFirstPipelineTests(unittest.TestCase):
    def test_scaffold_places_writing_after_core_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Evidence-first paper", field="workflow engineering")
            stages = list(project.metadata["stages"].keys())

            self.assertLess(stages.index("result_validity"), stages.index("result_support"))
            self.assertLess(stages.index("result_support"), stages.index("core_evidence"))
            self.assertLess(stages.index("core_evidence"), stages.index("results"))
            self.assertLess(stages.index("results"), stages.index("introduction"))
            self.assertLess(stages.index("introduction"), stages.index("data_writing"))
            self.assertLess(stages.index("data_writing"), stages.index("methods_writing"))
            self.assertIn("core_evidence", project.metadata["stages"]["introduction"]["depends_on"])
            self.assertIn("results", project.metadata["stages"]["data_writing"]["depends_on"])
            self.assertIn("results", project.metadata["stages"]["methods_writing"]["depends_on"])

    def test_orchestrator_recommends_result_support_after_result_validity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Core evidence gate", field="workflow engineering")
            for stage in [
                "references",
                "journal_profile",
                "research_plan",
                "data",
                "method_plan",
                "figure_plan",
                "code",
                "methods",
                "result_validity",
            ]:
                update_stage_status(project.path, stage, "draft")
            (project.path / "data" / "data_acquisition_plan.json").write_text(json.dumps({"tasks": [{"status": "ready"}]}), encoding="utf-8")
            (project.path / "data" / "data_inventory.json").write_text(json.dumps({"files": []}), encoding="utf-8")
            (project.path / "data" / "data_quality_report.json").write_text(json.dumps({"decision": "pass"}), encoding="utf-8")
            (project.path / "data" / "data_feasibility_report.json").write_text(json.dumps({"decision": "pass"}), encoding="utf-8")
            (project.path / "methods" / "run_manifest.yaml").write_text(json.dumps({"status": "success", "output_files": []}), encoding="utf-8")
            refresh_project_passport(project.path, event="test")

            next_action = run_pipeline(project.path)["next_action"]

            self.assertEqual(next_action["stage"], "result_support")
            self.assertEqual(next_action["command"], "assess-result-support")

    def test_core_evidence_gate_requires_reviewable_figures_and_workflow_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Core evidence figures", field="workflow engineering")
            results = project.path / "results"
            methods = project.path / "methods"
            data = project.path / "data"
            (results / "figures").mkdir(parents=True, exist_ok=True)
            for index in range(1, 6):
                (results / "figures" / f"figure_{index}.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 256)
            (results / "figure_plan.json").write_text(
                json.dumps(
                    {
                        "figures": [
                            {
                                "figure_id": f"fig_{index}",
                                "title": f"Figure {index}",
                                "path": f"results/figures/figure_{index}.png",
                                "generation_mode": "generated_code",
                                "scientific_question": "What empirical pattern is visible?",
                            }
                            for index in range(1, 6)
                        ]
                    }
                ),
                encoding="utf-8",
            )
            (results / "figure_metadata.json").write_text(
                json.dumps(
                    {
                        "figures": [
                            {
                                "figure_id": f"fig_{index}",
                                "path": f"results/figures/figure_{index}.png",
                                "title": f"Figure {index}",
                                "caption": "Scientific caption",
                                "has_axes": True,
                                "axis_labels": {"x": "X", "y": "Y"},
                                "interpretation_summary": "A reviewable empirical result is visible.",
                                "publication_ready": True,
                            }
                            for index in range(1, 6)
                        ]
                    }
                ),
                encoding="utf-8",
            )
            (methods / "run_manifest.yaml").write_text(
                json.dumps(
                    {
                        "status": "success",
                        "output_files": [f"results/figures/figure_{index}.png" for index in range(1, 6)],
                        "figures_generated": [f"results/figures/figure_{index}.png" for index in range(1, 6)],
                        "metrics": {"r2": "0.42"},
                    }
                ),
                encoding="utf-8",
            )
            (results / "result_validity_report.json").write_text(json.dumps({"decision": "pass"}), encoding="utf-8")
            (results / "result_support_checkpoint.json").write_text(
                json.dumps({"decision": "pass", "support_level": "pass", "requires_user_decision": False}),
                encoding="utf-8",
            )
            (data / "data_acquisition_plan.json").write_text(json.dumps({"tasks": [{"status": "ready"}]}), encoding="utf-8")
            (data / "data_inventory.json").write_text(json.dumps({"files": [{"path": "data/raw/sample.csv"}]}), encoding="utf-8")
            (data / "data_quality_report.json").write_text(json.dumps({"decision": "pass"}), encoding="utf-8")
            (data / "data_feasibility_report.json").write_text(json.dumps({"decision": "pass"}), encoding="utf-8")

            report = assess_core_evidence(project.path)

            self.assertEqual(report["decision"], "pass")
            self.assertTrue(report["requires_user_confirmation"])
            self.assertEqual(report["figure_count"], 5)
            self.assertTrue(report["workflow_coverage"]["data_supplementation"])
            self.assertTrue(report["workflow_coverage"]["data_integration"])
            self.assertTrue(report["workflow_coverage"]["method_analysis"])
            self.assertTrue(report["workflow_coverage"]["figure_production"])
            self.assertTrue(report["workflow_coverage"]["result_validity"])
            self.assertTrue((project.path / "core_evidence" / "core_evidence_report.html").exists())


if __name__ == "__main__":
    unittest.main()
