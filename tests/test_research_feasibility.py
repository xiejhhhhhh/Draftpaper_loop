# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from draftpaper_cli.project_scaffold import create_project
from draftpaper_cli.research_feasibility import assess_research_plan_feasibility, preflight_research_feasibility


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


class ResearchFeasibilityTests(unittest.TestCase):
    def test_preflight_blocks_without_literature_and_writes_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Crop yield mapping from NDVI", field="geography remote sensing")
            _write_json(project.path / "references" / "literature_items.json", [])
            result = preflight_research_feasibility(project.path)
            report = json.loads((project.path / "research_plan" / "research_preflight_feasibility.json").read_text(encoding="utf-8"))

            self.assertEqual(result["decision"], "blocked")
            self.assertEqual(report["recommended_next_action"], "search-literature")
            self.assertIn("spatial_or_sky_coordinates", report["expected_data_roles"])

    def test_image_astronomy_preflight_does_not_require_time_series(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Survey galaxy image morphology", field="astronomy machine learning")
            _write_json(project.path / "references" / "literature_items.json", [{"title": "Image study"}])
            preflight_research_feasibility(project.path)
            report = json.loads((project.path / "research_plan" / "research_preflight_feasibility.json").read_text(encoding="utf-8"))
            self.assertIn("image_or_raster_data", report["expected_data_roles"])
            self.assertNotIn("time_series", report["expected_data_roles"])

    def test_plan_feasibility_routes_to_inventory_before_declaring_data_absent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Image representation", field="astronomy machine learning")
            _write_json(project.path / "research_plan" / "figure_storyboard.json", {"figures": [{
                "figure_id": "fig_image",
                "research_question": "Does the representation generalize?",
                "required_data": ["image_embedding", "independent_target"],
                "required_method": ["group_aware_validation"],
            }]})
            _write_json(project.path / "research_plan" / "method_plan.json", {"method_tasks": [{"method_family": "group_aware_validation"}]})
            _write_json(project.path / "data" / "data_acquisition_plan.json", {"status": "planned"})
            result = assess_research_plan_feasibility(project.path)
            self.assertEqual(result["decision"], "conditional")
            self.assertEqual(result["recommended_next_action"], "inventory-data")


if __name__ == "__main__":
    unittest.main()
