# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from draftpaper_cli.project_scaffold import create_project
from draftpaper_cli.research_feasibility import preflight_research_feasibility


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


if __name__ == "__main__":
    unittest.main()
