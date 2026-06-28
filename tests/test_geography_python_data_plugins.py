# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GEO = ROOT / "draftpaper_cli" / "discipline_modules" / "geography"


def load_template(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem + "_geography_test_module", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot import template: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class GeographyPythonDataPluginTests(unittest.TestCase):
    def test_geography_module_exposes_python_data_plugins(self) -> None:
        from draftpaper_cli.discipline_modules import get_discipline_module

        hints = get_discipline_module({"discipline": "geography"}).method_blueprint_hints({})
        connector_ids = {item["connector_id"] for item in hints["data_acquisition_hints"]}
        template_ids = {item["template_id"] for item in hints["method_template_hints"]}
        self.assertIn("google_earth_engine_precip_export", connector_ids)
        self.assertIn("netcdf_to_geotiff_converter", connector_ids)
        self.assertIn("gridded_text_to_geotiff_converter", connector_ids)
        self.assertIn("arcgis_zonal_statistics_adapter", connector_ids)
        self.assertIn("monthly_remote_sensing_index_summary", template_ids)
        self.assertIn("phenology_curve_smoothing", template_ids)
        self.assertIn("ndvi_temporal_kmeans_zoning", template_ids)
        self.assertIn("ndvi_cluster_statistical_diagnostics", template_ids)

    def test_google_earth_engine_precip_export_builds_confirmable_plan(self) -> None:
        module = load_template(GEO / "data_connectors" / "google_earth_engine_precip_export" / "template.py")
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "gee_plan.json"
            plan = module.build_precip_export_plan(
                collection_id="UCSB-CHG/CHIRPS/DAILY",
                region_asset="users/example/study_area",
                start_date="2020-01-01",
                end_date="2020-12-31",
                reducer="monthly_sum",
                output_json=output,
            )
            text = output.read_text(encoding="utf-8")
        self.assertEqual(plan["status"], "requires_user_confirmed_cloud_export")
        self.assertIn("monthly_sum", text)
        self.assertNotIn("private", text.lower())

    def test_netcdf_converter_writes_geotiff_export_plan(self) -> None:
        module = load_template(GEO / "data_connectors" / "netcdf_to_geotiff_converter" / "template.py")
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "netcdf_plan.json"
            result = module.write_netcdf_geotiff_plan(
                variable_name="precipitation",
                lon_values=[350.0, 351.0, 10.0],
                lat_values=[30.0, 31.0],
                output_json=output,
            )
            text = output.read_text(encoding="utf-8")
        self.assertEqual(result["normalized_lon_min"], -10.0)
        self.assertIn("precipitation", text)

    def test_gridded_text_converter_validates_grid_shape(self) -> None:
        module = load_template(GEO / "data_connectors" / "gridded_text_to_geotiff_converter" / "template.py")
        grid = module.reshape_grid_values([1, 2, 3, 4, 5, 6], rows=2, cols=3)
        self.assertEqual(grid, [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])
        with self.assertRaises(ValueError):
            module.reshape_grid_values([1, 2, 3], rows=2, cols=3)

    def test_arcgis_zonal_statistics_adapter_writes_safe_plan(self) -> None:
        module = load_template(GEO / "data_connectors" / "arcgis_zonal_statistics_adapter" / "template.py")
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "zonal_plan.json"
            result = module.build_zonal_statistics_plan(
                raster_variable="ndvi",
                zone_id_field="region_id",
                statistics=["mean", "std"],
                output_json=output,
            )
            text = output.read_text(encoding="utf-8")
        self.assertEqual(result["execution_backend"], "arcgis_or_project_bound_gis_runtime")
        self.assertIn("region_id", text)

    def test_monthly_remote_sensing_summary_groups_values(self) -> None:
        module = load_template(GEO / "method_templates" / "monthly_remote_sensing_index_summary" / "template.py")
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "monthly.csv"
            result = module.summarize_monthly_indices(
                input_csv=GEO / "method_templates" / "monthly_remote_sensing_index_summary" / "fixture_monthly_indices.csv",
                output_csv=output,
                month_column="month",
                value_columns=["ndvi", "lai"],
            )
            text = output.read_text(encoding="utf-8")
        self.assertEqual(result["month_count"], 3)
        self.assertIn("ndvi_mean", text)

    def test_phenology_smoothing_detects_peak_month(self) -> None:
        module = load_template(GEO / "method_templates" / "phenology_curve_smoothing" / "template.py")
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "phenology.csv"
            result = module.smooth_phenology_curve(
                input_csv=GEO / "method_templates" / "phenology_curve_smoothing" / "fixture_curve.csv",
                output_csv=output,
                time_column="month",
                value_column="ndvi",
                window=3,
            )
            text = output.read_text(encoding="utf-8")
        self.assertEqual(result["peak_time"], "5")
        self.assertIn("smoothed_value", text)

    def test_ndvi_temporal_kmeans_zoning_assigns_clusters(self) -> None:
        module = load_template(GEO / "method_templates" / "ndvi_temporal_kmeans_zoning" / "template.py")
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "clusters.csv"
            result = module.cluster_temporal_profiles(
                input_csv=GEO / "method_templates" / "ndvi_temporal_kmeans_zoning" / "fixture_profiles.csv",
                output_csv=output,
                id_column="sample_id",
                feature_columns=["m1", "m2", "m3"],
                cluster_count=2,
            )
            text = output.read_text(encoding="utf-8")
        self.assertEqual(result["cluster_count"], 2)
        self.assertIn("cluster_id", text)

    def test_ndvi_cluster_diagnostics_writes_reviewable_statistics(self) -> None:
        module = load_template(GEO / "method_templates" / "ndvi_cluster_statistical_diagnostics" / "template.py")
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "diagnostics.json"
            result = module.write_cluster_diagnostics(
                input_csv=GEO / "method_templates" / "ndvi_cluster_statistical_diagnostics" / "fixture_cluster_values.csv",
                output_json=output,
                cluster_column="cluster_id",
                value_column="yield",
            )
            payload = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(result["cluster_count"], 2)
        self.assertIn("formal_tests_require", payload)


if __name__ == "__main__":
    unittest.main()
