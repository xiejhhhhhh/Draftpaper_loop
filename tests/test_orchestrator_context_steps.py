# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json
import tempfile
import unittest

from draftpaper_cli.data_feasibility import assess_data_feasibility, assess_data_quality, build_data_writing_context, inventory_data, write_data
from draftpaper_cli.method_plan import collect_method_plan
from draftpaper_cli.methods import build_method_writing_context
from draftpaper_cli.orchestrator import run_pipeline
from draftpaper_cli.passport import refresh_project_passport
from draftpaper_cli.project_scaffold import create_project
from draftpaper_cli.project_state import update_stage_status


class OrchestratorContextStepTests(unittest.TestCase):
    def test_data_stage_recommends_context_and_writer_outputs_before_completion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Exploratory data context", field="workflow engineering")
            for stage in ["references", "journal_profile", "research_plan", "introduction"]:
                update_stage_status(project.path, stage, "draft")
            (project.path / "research_plan" / "research_plan.md").write_text("# Plan\n\nExploratory pilot analysis.\n", encoding="utf-8")
            (project.path / "data" / "raw" / "sample.csv").write_text("id,target\n1,0\n2,1\n3,0\n", encoding="utf-8")
            inventory_data(project.path)
            assess_data_quality(project.path)
            assess_data_feasibility(project.path, min_rows=3)
            refresh_project_passport(project.path, event="test")

            self.assertEqual(run_pipeline(project.path)["next_action"]["command"], "build-data-context")
            build_data_writing_context(project.path)
            refresh_project_passport(project.path, event="test")
            self.assertEqual(run_pipeline(project.path)["next_action"]["command"], "write-data")
            write_data(project.path)
            refresh_project_passport(project.path, event="test")
            self.assertNotEqual(run_pipeline(project.path)["next_action"]["stage"], "data")

    def test_methods_stage_recommends_context_and_writer_after_successful_verification(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Exploratory methods context", field="workflow engineering")
            for stage in ["references", "journal_profile", "research_plan", "introduction"]:
                update_stage_status(project.path, stage, "draft")
            (project.path / "research_plan" / "research_plan.md").write_text("# Plan\n\nExploratory analysis.\n", encoding="utf-8")
            (project.path / "data" / "raw" / "sample.csv").write_text("id,target,value\n1,0,0.1\n2,1,0.2\n3,0,0.3\n", encoding="utf-8")
            inventory_data(project.path)
            assess_data_quality(project.path)
            assess_data_feasibility(project.path, min_rows=3)
            write_data(project.path)
            collect_method_plan(project.path, user_method="Use correlation analysis.", primary_metric="r2", minimum_primary_metric=0.05)
            update_stage_status(project.path, "figure_plan", "draft")
            update_stage_status(project.path, "code", "draft")
            (project.path / "results" / "tables" / "metrics.csv").write_text("metric,value\nr2,0.1\n", encoding="utf-8")
            (project.path / "methods" / "run_manifest.yaml").write_text(
                json.dumps({"status": "success", "metrics": {"r2": "0.1"}, "output_files": ["results/tables/metrics.csv"]}),
                encoding="utf-8",
            )
            update_stage_status(project.path, "methods", "approved")
            refresh_project_passport(project.path, event="test")

            self.assertEqual(run_pipeline(project.path)["next_action"]["command"], "build-method-context")
            build_method_writing_context(project.path)
            refresh_project_passport(project.path, event="test")
            self.assertEqual(run_pipeline(project.path)["next_action"]["command"], "write-methods")


if __name__ == "__main__":
    unittest.main()
