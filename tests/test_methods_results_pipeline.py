# Copyright (c) 2026 xiejhhhhhh
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json
import tempfile
import unittest

from draftpaper_cli.analysis_code import generate_analysis_code
from draftpaper_cli.figure_plan import plan_figures
from draftpaper_cli.methods import verify_methods
from draftpaper_cli.project_scaffold import create_project
from draftpaper_cli.project_state import load_project
from draftpaper_cli.result_validity import assess_result_validity
from draftpaper_cli.results import inventory_results, write_results

from tests.test_analysis_code_generation import prepare_codegen_project


class MethodsResultsPipelineTests(unittest.TestCase):
    def test_generated_method_artifacts_feed_result_manifest_and_results_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Pipeline coupling", field="astronomy machine learning")
            prepare_codegen_project(project.path)
            figure_plan = plan_figures(project.path)
            codegen = generate_analysis_code(project.path)
            verify_methods(
                project.path,
                command=codegen["verify_command"],
                output_files=codegen["declared_outputs"],
                input_data=[codegen["selected_input_data"]],
            )
            validity = assess_result_validity(project.path, minimum_value=0.4)
            self.assertEqual(validity["decision"], "pass")

            inventory = inventory_results(project.path)
            self.assertEqual(inventory["figure_count"], figure_plan["generated_figure_count"])
            self.assertEqual(inventory["table_count"], 2)
            manifest = json.loads((project.path / "results" / "result_manifest.yaml").read_text(encoding="utf-8"))
            figure_claims = " ".join(entry["result_claim"] for entry in manifest["figures"])
            self.assertIn("observed classes", figure_claims.lower())
            self.assertIn("observ", figure_claims.lower())
            self.assertTrue("r=" in figure_claims or "support ratio" in figure_claims or "metric summary" in figure_claims.lower())

            state_after_inventory = load_project(project.path)
            self.assertEqual(state_after_inventory.metadata["stages"]["results"]["status"], "draft")
            self.assertTrue(state_after_inventory.metadata["stages"]["discussion"]["stale"])

            written = write_results(project.path)
            self.assertEqual(written["artifact_count"], figure_plan["generated_figure_count"] + 2)
            results_tex = (project.path / "results" / "results.tex").read_text(encoding="utf-8")
            self.assertIn("\\includegraphics", results_tex)
            self.assertIn("figure", results_tex.lower())
            self.assertIn("usable observations", results_tex)
            self.assertNotIn("\\cite", results_tex)


if __name__ == "__main__":
    unittest.main()
