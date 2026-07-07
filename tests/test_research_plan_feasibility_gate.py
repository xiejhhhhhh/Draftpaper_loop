# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from draftpaper_cli.project_scaffold import create_project
from draftpaper_cli.research_feasibility import assess_research_plan_feasibility


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


class ResearchPlanFeasibilityGateTests(unittest.TestCase):
    def test_plan_feasibility_records_missing_data_without_silent_replacement(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Time-aware X-ray source classification", field="astronomy machine learning")
            _write_json(
                project.path / "research_plan" / "figure_storyboard.json",
                {"figures": [{"figure_id": "fig_main", "required_data": ["flux", "class_label"], "required_method": ["time_aware_transformer"], "expected_finding": "model separates source classes"}]},
            )
            _write_json(project.path / "research_plan" / "method_plan.json", {"method_tasks": [{"method_family": "time_aware_transformer"}]})
            _write_json(project.path / "data" / "data_inventory.json", {"files": [{"path": "data/processed/input.csv", "kind": "processed", "suffix": ".csv", "columns": ["flux"], "row_count": 20}]})

            result = assess_research_plan_feasibility(project.path)
            report = json.loads((project.path / "research_plan" / "research_plan_feasibility_report.json").read_text(encoding="utf-8"))

            self.assertEqual(result["decision"], "conditional")
            self.assertEqual(report["figure_assessments"][0]["repair_route"], "prepare-data-acquisition")
            self.assertIn("label_or_response", report["figure_assessments"][0]["missing_data_roles"])


if __name__ == "__main__":
    unittest.main()
