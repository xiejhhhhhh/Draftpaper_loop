# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from draftpaper_cli.figure_contract_gate import assess_figure_contracts
from draftpaper_cli.figure_repair import repair_figure_data
from draftpaper_cli.project_scaffold import create_project


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


class FigureContractGateTests(unittest.TestCase):
    def test_figure_contract_gate_routes_missing_data_to_repair(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Transformer classification", field="astronomy machine learning")
            _write_json(project.path / "results" / "figure_contracts.json", {"contracts": [{"storyboard_id": "fig_main", "required_data": ["flux", "class_label"], "required_method": ["time_aware_transformer"], "expected_finding": "classification performance"}]})
            _write_json(project.path / "results" / "figure_plan.json", {"figures": []})
            _write_json(project.path / "results" / "storyboard_alignment_report.json", {"decision": "pass", "all_storyboard_figures_planned": True})
            _write_json(project.path / "methods" / "method_feasibility_report.json", {"decision": "pass"})
            _write_json(project.path / "data" / "data_role_coverage_report.json", {"available_roles": ["spectral_or_remote_sensing_features"]})

            result = assess_figure_contracts(project.path)
            report = json.loads((project.path / "results" / "figure_contract_gate_report.json").read_text(encoding="utf-8"))

            self.assertEqual(result["decision"], "blocked")
            self.assertEqual(report["recommended_next_action"]["command"], "repair-figure-data")
            self.assertEqual(report["contract_checks"][0]["figure_id"], "fig_main")

    def test_generated_figure_count_can_exceed_main_group_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Six main figure groups with appendix diagnostics", field="astronomy machine learning")
            contracts = [
                {"storyboard_id": f"fig_main_{index}", "figure_id": f"fig_main_{index}", "required_data": [], "required_method": [], "expected_finding": "main empirical finding"}
                for index in range(1, 6)
            ]
            _write_json(project.path / "results" / "figure_contracts.json", {"contracts": contracts, "main_figure_group_count": 5})
            _write_json(project.path / "results" / "figure_plan.json", {
                "figure_policy": {"minimum_main_figures": 5, "target_main_figures": 6},
                "main_figure_group_count": 5,
                "generated_figure_count": 9,
                "supporting_figure_count": 4,
                "appendix_figure_count": 4,
                "figures": [],
            })
            _write_json(project.path / "results" / "storyboard_alignment_report.json", {"decision": "pass", "all_storyboard_figures_planned": True})
            _write_json(project.path / "methods" / "method_feasibility_report.json", {"decision": "pass"})
            _write_json(project.path / "data" / "data_role_coverage_report.json", {"available_roles": ["local_data"]})

            result = assess_figure_contracts(project.path)
            report = json.loads((project.path / "results" / "figure_contract_gate_report.json").read_text(encoding="utf-8"))

            self.assertEqual(result["decision"], "pass")
            self.assertEqual(report["main_figure_group_count"], 5)
            self.assertEqual(report["generated_figure_count"], 9)

    def test_repair_figure_data_consumes_contract_gate_failures(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Missing light curve contract", field="astronomy")
            _write_json(project.path / "results" / "figure_contracts.json", {"contracts": [{"storyboard_id": "fig_lc", "figure_id": "fig_lc", "title": "Light-curve evidence", "required_data": ["light_curve"], "expected_finding": "light-curve separation"}]})
            _write_json(project.path / "results" / "figure_plan.json", {"figures": []})
            _write_json(project.path / "results" / "storyboard_alignment_report.json", {"decision": "pass", "all_storyboard_figures_planned": True})
            _write_json(project.path / "methods" / "method_feasibility_report.json", {"decision": "pass"})
            _write_json(project.path / "data" / "data_role_coverage_report.json", {"available_roles": ["source_catalog"]})
            assess_figure_contracts(project.path)

            plan = repair_figure_data(project.path)

            self.assertTrue(plan["tasks"])
            self.assertEqual(plan["tasks"][0]["storyboard_id"], "fig_lc")
            self.assertIn("light_curve", plan["tasks"][0]["missing"])


if __name__ == "__main__":
    unittest.main()
