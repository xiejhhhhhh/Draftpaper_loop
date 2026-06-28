# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from draftpaper_cli.data_feasibility import assess_data_feasibility, assess_data_quality, inventory_data
from draftpaper_cli.method_plan import collect_method_plan
from draftpaper_cli.project_scaffold import create_project


def prepare_geography_project(project_path: Path) -> None:
    (project_path / "research_plan" / "research_plan.md").write_text(
        "# Plan\n\nUse NDVI and spatial validation for wheat yield response.",
        encoding="utf-8",
    )
    rows = "\n".join(f"{i},region_{i%4},{0.2+i/1000:.3f},{3000+i}" for i in range(1, 50))
    (project_path / "data" / "processed" / "wheat.csv").write_text(
        "sample_id,region,ndvi,yield\n" + rows + "\n",
        encoding="utf-8",
    )
    inventory_data(project_path)
    assess_data_quality(project_path, required_columns=["ndvi", "yield"])
    assess_data_feasibility(project_path, min_rows=30)
    collect_method_plan(
        project_path,
        user_method="Use remote sensing feature reconstruction and spatial block validation.",
        primary_metric="r2",
        minimum_primary_metric=0.05,
    )
    (project_path / "methods" / "src").mkdir(parents=True, exist_ok=True)
    (project_path / "methods" / "src" / "generated_pipeline.py").write_text(
        "def run_pipeline():\n    return {'status': 'ok'}\n",
        encoding="utf-8",
    )


class PluginCandidateTests(unittest.TestCase):
    def test_candidate_lifecycle_writes_reports_and_package(self) -> None:
        from draftpaper_cli.plugin_candidates import (
            generalize_plugin_candidate,
            package_plugin_contribution,
            summarize_plugin_candidates,
            validate_plugin_candidate,
            write_github_contribution_guide,
        )

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="NDVI wheat plugin candidate", field="geography remote sensing")
            prepare_geography_project(project.path)

            summary = summarize_plugin_candidates(project.path, method="spatial_block_validation")
            candidate = Path(summary["candidates"][0]["path"])
            self.assertTrue((candidate / "candidate_manifest.json").exists())

            generalize = generalize_plugin_candidate(candidate)
            self.assertTrue(Path(generalize["template_path"]).exists())

            validation = validate_plugin_candidate(candidate)
            self.assertEqual(validation["status"], "passed")
            self.assertEqual(validation["overlap_report"]["decision"], "merge_with_existing")

            packaged = package_plugin_contribution(candidate)
            self.assertTrue((Path(packaged["package_dir"]) / "merge_plan.json").exists())

            guide = write_github_contribution_guide(project.path)
            self.assertTrue(Path(guide["guide"]).exists())

    def test_candidate_manifest_has_merge_target(self) -> None:
        from draftpaper_cli.plugin_candidates import summarize_plugin_candidates

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Geography method candidate", field="geography remote sensing")
            prepare_geography_project(project.path)

            summary = summarize_plugin_candidates(project.path, method="remote_sensing")
            manifest = json.loads(Path(summary["candidates"][0]["manifest"]).read_text(encoding="utf-8"))

            self.assertIn("draftpaper_cli/discipline_modules/geography/method_templates", manifest["intended_merge_target"])
            self.assertEqual(manifest["plugin_type"], "method_template")


if __name__ == "__main__":
    unittest.main()
