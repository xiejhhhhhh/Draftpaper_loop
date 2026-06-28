# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from draftpaper_cli.data_feasibility import assess_data_feasibility, assess_data_quality, inventory_data
from draftpaper_cli.method_plan import collect_method_plan
from draftpaper_cli.project_scaffold import create_project


def prepare_blueprint_project(project_path: Path) -> None:
    (project_path / "research_plan" / "research_plan.md").write_text(
        "# Research Plan\n\nAssess NDVI-yield relationships with spatial validation.\n",
        encoding="utf-8",
    )
    rows = "\n".join(f"{i},{2020 + i % 3},region_{i % 4},{0.2 + i / 1000:.3f},{3000 + i}" for i in range(1, 50))
    (project_path / "data" / "processed" / "wheat_ndvi.csv").write_text(
        "sample_id,year,region,ndvi,yield\n" + rows + "\n",
        encoding="utf-8",
    )
    inventory_data(project_path)
    assess_data_quality(project_path, required_columns=["ndvi", "yield"])
    assess_data_feasibility(project_path, min_rows=30)
    collect_method_plan(
        project_path,
        user_method="Use remote sensing feature reconstruction and spatial block validation for wheat yield response.",
        primary_metric="r2",
        minimum_primary_metric=0.05,
    )


class MethodBlueprintTests(unittest.TestCase):
    def test_prepare_method_blueprint_writes_discipline_contract(self) -> None:
        from draftpaper_cli.method_blueprint import prepare_method_blueprint

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="NDVI wheat spatial yield analysis", field="geography remote sensing")
            prepare_blueprint_project(project.path)

            result = prepare_method_blueprint(project.path)

            self.assertEqual(result["status"], "written")
            self.assertEqual(result["discipline"], "geography")
            self.assertTrue((project.path / "methods" / "method_blueprint.json").exists())
            self.assertTrue((project.path / "methods" / "method_blueprint.html").exists())
            self.assertTrue((project.path / "methods" / "method_data_contract.json").exists())
            self.assertTrue((project.path / "methods" / "method_code_plan.json").exists())
            self.assertTrue((project.path / "methods" / "method_formula_plan.json").exists())
            blueprint = json.loads((project.path / "methods" / "method_blueprint.json").read_text(encoding="utf-8"))
            self.assertIn("spatial_block_validation", blueprint["method_code_plan"]["method_families"])
            self.assertIn("spatial_group_or_coordinates", blueprint["method_data_contract"]["available_roles"])
            self.assertIn("methods/scripts", blueprint["method_code_plan"]["stage_owned_code_locations"])

    def test_cli_prepare_method_blueprint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="NDVI wheat CLI blueprint", field="geography remote sensing")
            prepare_blueprint_project(project.path)

            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "draftpaper_cli.cli",
                    "prepare-method-blueprint",
                    "--project",
                    str(project.path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            payload = json.loads(completed.stdout)
            self.assertEqual(payload["status"], "written")
            self.assertTrue(Path(payload["method_blueprint"]).exists())


if __name__ == "__main__":
    unittest.main()
