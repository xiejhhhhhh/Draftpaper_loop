# Copyright (c) 2026 Jinray Xie
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

from tests.test_analysis_code_generation import prepare_codegen_project, write_passing_figure_contract_gate


class MethodsResultsPipelineTests(unittest.TestCase):
    def test_generic_generated_artifacts_do_not_bypass_semantic_result_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Pipeline coupling", field="astronomy machine learning")
            prepare_codegen_project(project.path)
            figure_plan = plan_figures(project.path)
            write_passing_figure_contract_gate(project.path)
            codegen = generate_analysis_code(project.path)
            verify_methods(
                project.path,
                command=codegen["verify_command"],
                output_files=codegen["declared_outputs"],
                input_data=[codegen["selected_input_data"]],
            )
            validity = assess_result_validity(project.path, minimum_value=0.4)
            self.assertEqual(validity["decision"], "revise_required")
            semantic = json.loads(
                (project.path / "results" / "figure_semantic_validation_report.json").read_text(encoding="utf-8")
            )
            self.assertEqual(semantic["decision"], "blocked")
            issue_kinds = {
                issue["kind"]
                for check in semantic["figure_checks"]
                for issue in check.get("issues") or []
            }
            self.assertTrue(issue_kinds & {"mixed_unit_families", "missing_required_variable_role", "plot_grammar_mismatch"})


if __name__ == "__main__":
    unittest.main()
