# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path


class AstronomyRemoteStreamPluginTests(unittest.TestCase):
    def test_astronomy_module_registers_remote_fits_zip_stream_connector(self) -> None:
        from draftpaper_cli.discipline_modules import get_discipline_module

        module = get_discipline_module({"discipline": "astronomy"})
        hints = module.method_blueprint_hints({})
        connector = next(
            item for item in hints["data_acquisition_hints"]
            if item["connector_id"] == "remote_fits_zip_stream"
        )

        self.assertIn("remote_server_ssh", connector["access_modes"])
        self.assertIn("fits_zip_stream", connector["access_modes"])
        self.assertIn("FITS", connector["data_formats"])
        self.assertIn("ZIP", connector["data_formats"])
        self.assertIn("Parquet", connector["data_formats"])
        self.assertIn("astropy", connector["packages"])
        self.assertIn("DRAFTPAPER_REMOTE_HOST", connector["credential_env_vars"])
        self.assertIn("data_connectors/remote_fits_zip_stream/template.py", connector["template_paths"])

    def test_remote_stream_template_builds_generic_manifest_without_private_literals(self) -> None:
        import draftpaper_cli.discipline_modules.astronomy.data_connectors.remote_fits_zip_stream.template as template

        template_path = Path(template.__file__)
        source = template_path.read_text(encoding="utf-8")
        forbidden = [
            "Flares_classificaiton",
            "/home/xiejinhui",
            "home\\xiejinhui",
            "/ep_data",
            "5agn",
            "5xrb",
            "1tde",
            "password",
            "ghp_",
        ]
        for token in forbidden:
            self.assertNotIn(token, source)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_csv = root / "events.csv"
            output_csv = root / "event_manifest.csv"
            input_csv.write_text(
                "object_id,class_label,obs_id,detector,product_level,object_index\n"
                "src-1,class-a,1001,1,2,3\n",
                encoding="utf-8",
            )

            result = template.build_event_product_manifest(
                input_csv=input_csv,
                output_csv=output_csv,
                remote_root="/archive/root",
                column_map={
                    "object_id": "object_id",
                    "class_label": "class_label",
                    "obs_id": "obs_id",
                    "detector": "detector",
                    "product_level": "product_level",
                    "object_index": "object_index",
                },
            )

            rows = list(csv.DictReader(output_csv.open("r", encoding="utf-8", newline="")))
            self.assertEqual(result["row_count"], 1)
            self.assertEqual(rows[0]["event_id"], "obs00000001001det1lv2o3")
            self.assertEqual(rows[0]["remote_product_zip_path"], "/archive/root/lv2/obs00000001001det1lv2.zip")
            self.assertEqual(rows[0]["class_label"], "class-a")

    def test_prepare_data_acquisition_exposes_remote_stream_connector_for_astronomy(self) -> None:
        from draftpaper_cli.data_acquisition import prepare_data_acquisition
        from draftpaper_cli.project_scaffold import create_project

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(
                root=Path(tmp) / "projects",
                idea="High-energy astronomy source classification using FITS ZIP event products on a remote server",
                field="astronomy astrophysics machine learning",
                target_journal="APJS",
            )

            prepare_data_acquisition(project.path)
            plan = json.loads((project.path / "data" / "data_acquisition_plan.json").read_text(encoding="utf-8"))
            connector_ids = {item["connector_id"] for item in plan["discipline_connector_catalog"]}
            remote_connector = next(item for item in plan["discipline_connector_catalog"] if item["connector_id"] == "remote_fits_zip_stream")

            self.assertIn("fits_zip_stream", plan["access_modes"])
            self.assertIn("remote_fits_zip_stream", connector_ids)
            self.assertEqual(remote_connector["fetch_policy"], "plan_first_user_confirmed_fetch")
            self.assertIn("DRAFTPAPER_REMOTE_HOST", remote_connector["missing_env_vars"])

    def test_training_smoke_validation_is_method_template_not_data_connector(self) -> None:
        from draftpaper_cli.discipline_modules import get_discipline_module

        astronomy = get_discipline_module({"discipline": "astronomy"}).method_blueprint_hints({})
        machine_learning = get_discipline_module({"discipline": "machine_learning"}).method_blueprint_hints({})
        astronomy_template_ids = {item["template_id"] for item in astronomy["method_template_hints"]}
        ml_template_ids = {item["template_id"] for item in machine_learning["method_template_hints"]}
        astronomy_connector_ids = {item["connector_id"] for item in astronomy["data_acquisition_hints"]}

        self.assertIn("source_holdout_stream_smoke_test", astronomy_template_ids)
        self.assertIn("group_holdout_training_smoke_test", ml_template_ids)
        self.assertNotIn("source_holdout_stream_smoke_test", astronomy_connector_ids)
        self.assertNotIn("group_holdout_training_smoke_test", astronomy_connector_ids)


if __name__ == "__main__":
    unittest.main()
