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

from draftpaper_cli.project_scaffold import create_project


class DataAcquisitionTests(unittest.TestCase):
    def test_prepare_data_acquisition_detects_generic_connector_modes(self) -> None:
        from draftpaper_cli.data_acquisition import prepare_data_acquisition

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "external_source"
            source.mkdir()
            (source / "fetch_api.py").write_text(
                "import requests\nTOKEN = '<redacted>'\nrequests.get('https://example.org/api/lightcurve')\n",
                encoding="utf-8",
            )
            (source / "server_manifest.md").write_text(
                "Use ssh server with read-only /ep_data and symlink processed outputs under /home/user/results.",
                encoding="utf-8",
            )
            (source / "sample.csv").write_text("id,value\n1,0.2\n", encoding="utf-8")
            project = create_project(
                root=root / "projects",
                idea="X-ray flare source classification using light curve data",
                field="astronomy machine learning",
                target_journal="APJS",
            )

            result = prepare_data_acquisition(project.path, source_root=source)

            self.assertEqual(result["status"], "written")
            self.assertEqual(result["discipline"], "astronomy")
            self.assertIn("local_files", result["access_modes"])
            self.assertIn("api_access", result["access_modes"])
            self.assertIn("remote_server", result["access_modes"])
            self.assertTrue((project.path / "data" / "data_acquisition_plan.html").exists())
            self.assertTrue((project.path / "data" / "data_source_manifest.csv").exists())

    def test_data_acquisition_and_review_share_discipline_profile(self) -> None:
        from draftpaper_cli.data_acquisition import classify_data_access
        from draftpaper_cli.review_engines import infer_review_discipline

        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "geo_source"
            source.mkdir()
            (source / "gee_plan.md").write_text(
                "Use Google Earth Engine API, NDVI raster composites, GeoTIFF exports, and spatial validation.",
                encoding="utf-8",
            )
            project = create_project(
                root=Path(tmp) / "projects",
                idea="NDVI crop yield zoning with remote sensing",
                field="geography remote sensing",
                target_journal="Remote Sensing",
            )
            (project.path / "research_plan" / "research_plan.md").write_text(
                "Use NDVI, spatial zoning, raster predictors, and crop yield response.",
                encoding="utf-8",
            )

            access_profile = classify_data_access(project.path, source_root=source)
            review_profile = infer_review_discipline(project.path)

            self.assertEqual(access_profile["discipline_profile"]["discipline"], "geography")
            self.assertEqual(review_profile["discipline"], "geography")

    def test_prepare_data_acquisition_writes_discipline_connector_catalog(self) -> None:
        from draftpaper_cli.data_acquisition import prepare_data_acquisition

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(
                root=Path(tmp) / "projects",
                idea="Wheat NDVI geography analysis with Google Earth Engine",
                field="geography agriculture remote sensing",
                target_journal="Remote Sensing",
            )

            prepare_data_acquisition(project.path)
            plan = json.loads((project.path / "data" / "data_acquisition_plan.json").read_text(encoding="utf-8"))
            catalog = plan["discipline_connector_catalog"]
            connector_ids = {item["connector_id"] for item in catalog}

            self.assertIn("google_earth_engine", connector_ids)
            self.assertIn("local_raster_vector", connector_ids)
            gee = next(item for item in catalog if item["connector_id"] == "google_earth_engine")
            self.assertIn("earthengine-api", gee["packages"])
            self.assertIn("GeoTIFF", gee["data_formats"])
            self.assertIn(gee["feasibility_status"], {"requires_credentials", "requires_package_install", "locally_feasible"})
            local = next(item for item in catalog if item["connector_id"] == "local_raster_vector")
            self.assertIn("rasterio", local["packages"])
            self.assertIn("Shapefile", local["data_formats"])

    def test_cli_prepare_data_acquisition_writes_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source"
            source.mkdir()
            (source / "fetch.py").write_text("import requests\nrequests.get('https://example.org/api')\n", encoding="utf-8")
            project = create_project(
                root=Path(tmp) / "projects",
                idea="API based environmental analysis",
                field="environmental data workflow",
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "draftpaper_cli.cli",
                    "prepare-data-acquisition",
                    "--project",
                    str(project.path),
                    "--source-root",
                    str(source),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            payload = json.loads(completed.stdout)

            self.assertEqual(payload["status"], "written")
            self.assertIn("api_access", payload["access_modes"])
            self.assertTrue((project.path / "data" / "data_acquisition_plan.json").exists())

    def test_source_root_noise_does_not_override_project_discipline(self) -> None:
        from draftpaper_cli.data_acquisition import classify_data_access

        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "mixed_source"
            source.mkdir()
            (source / "generic_notes.md").write_text(
                "The script mentions spatial indexing and GIS-like manifest layouts, but the paper itself is not geography.",
                encoding="utf-8",
            )
            project = create_project(
                root=Path(tmp) / "projects",
                idea="X-ray flare transient source classification using light curve and spectral features",
                field="astronomy astrophysics machine learning",
                target_journal="APJS",
            )

            profile = classify_data_access(project.path, source_root=source)

            self.assertEqual(profile["discipline_profile"]["discipline"], "astronomy")

    def test_prepare_data_acquisition_turns_review_missing_data_into_connector_tasks(self) -> None:
        from draftpaper_cli.data_acquisition import prepare_data_acquisition

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(
                root=Path(tmp) / "projects",
                idea="NDVI crop yield zoning with remote sensing",
                field="geography remote sensing agriculture",
                target_journal="Remote Sensing",
            )
            review_dir = project.path / "review"
            review_dir.mkdir(parents=True, exist_ok=True)
            (review_dir / "actionable_analysis_tasks.json").write_text(
                json.dumps({
                    "status": "analysis_revision_prepared",
                    "tasks": [
                        {
                            "task_id": "T-spatial_block_validation",
                            "operation_family": "spatial_block_validation",
                            "discipline": "geography",
                            "source_codes": ["spatial_ecological_validation"],
                            "target_stage": "methods",
                            "fallback_if_missing": "Spatial blocking requires coordinates or a scientifically meaningful region, field, grid, or plot identifier.",
                            "feasibility": {
                                "status": "blocked_missing_data",
                                "missing_required_roles": ["spatial_group_or_coordinates"],
                                "missing_optional_roles": ["time"],
                            },
                        }
                    ],
                }, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            (review_dir / "review_engineering_plan.json").write_text(
                json.dumps({
                    "status": "review_engineering_plan_written",
                    "issues": [
                        {
                            "issue_id": "E-spatial",
                            "source": "review_engineering",
                            "code": "geography_spatial_autocorrelation",
                            "target_stage": "data",
                            "title": "Assess spatial autocorrelation and spatial validation risk",
                            "reason": "Coordinates, administrative regions, plots, or spatial blocks are needed.",
                            "required_user_input": "Are coordinates, administrative regions, plots, or spatial blocks available?",
                        }
                    ],
                }, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            result = prepare_data_acquisition(project.path)
            tasks = json.loads((project.path / "data" / "data_acquisition_tasks.json").read_text(encoding="utf-8"))

            self.assertEqual(result["data_acquisition_task_count"], 2)
            self.assertTrue((project.path / "data" / "data_acquisition_tasks.html").exists())
            blocked_task = next(task for task in tasks["tasks"] if task["source"] == "analysis_revision")
            self.assertEqual(blocked_task["needed_data"], ["spatial_group_or_coordinates"])
            self.assertIn("local_files", blocked_task["suggested_connectors"])
            self.assertIn("api_access", blocked_task["suggested_connectors"])
            self.assertTrue(blocked_task["requires_user_confirmation"])
            review_task = next(task for task in tasks["tasks"] if task["source"] == "review_engineering")
            self.assertIn("spatial", review_task["needed_data"][0])
            self.assertTrue(review_task["requires_user_confirmation"])


if __name__ == "__main__":
    unittest.main()
