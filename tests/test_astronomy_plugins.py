# Copyright (c) 2026 xiejhhhhhh
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
ASTRO = ROOT / "draftpaper_cli" / "discipline_modules" / "astronomy"


def load_template(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem + "_test_module", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot import template: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class AstronomyPluginTemplateTests(unittest.TestCase):
    def test_astronomy_module_exposes_specific_connectors_and_methods(self) -> None:
        from draftpaper_cli.discipline_modules import get_discipline_module

        hints = get_discipline_module({"discipline": "astronomy"}).method_blueprint_hints({})
        connector_ids = {item["connector_id"] for item in hints["data_acquisition_hints"]}
        method_ids = {item["template_id"] for item in hints["method_template_hints"]}
        self.assertIn("einstein_probe_photon_api", connector_ids)
        self.assertIn("wxt_manifest_product", connector_ids)
        self.assertIn("long_term_light_curve_feature_extraction", method_ids)
        self.assertIn("event_level_transformer_input_builder", method_ids)

    def test_photon_payload_connector_normalizes_fixture(self) -> None:
        module = load_template(ASTRO / "data_connectors" / "einstein_probe_photon_api" / "template.py")
        payload = json.loads((ASTRO / "data_connectors" / "einstein_probe_photon_api" / "fixture_photon_payload.json").read_text(encoding="utf-8"))
        rows = module.parse_photon_payload(payload)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["flux"], 1.2)
        query = module.build_photon_query(ra=12.3, dec=-4.5, start_time="2024-01-01T00:00", end_time="2024-01-02T00:00", bin_size=100)
        self.assertEqual(query["bin_size"], "100")

    def test_wxt_manifest_connector_builds_generic_product_paths(self) -> None:
        module = load_template(ASTRO / "data_connectors" / "wxt_manifest_product" / "template.py")
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "manifest.csv"
            result = module.build_manifest_rows(
                ASTRO / "data_connectors" / "wxt_manifest_product" / "fixture_wxt_manifest.csv",
                output,
                server_root="/archive/wxt",
            )
            text = output.read_text(encoding="utf-8")
        self.assertEqual(result["row_count"], 2)
        self.assertIn("/archive/wxt/lv2/", text)
        self.assertIn("event_id", text)

    def test_long_term_light_curve_feature_template_writes_features(self) -> None:
        module = load_template(ASTRO / "method_templates" / "long_term_light_curve_feature_extraction" / "template.py")
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "features.csv"
            result = module.extract_light_curve_features(
                light_curve_csv=ASTRO / "method_templates" / "long_term_light_curve_feature_extraction" / "fixture_light_curve.csv",
                output_features_csv=output,
                source_id="fixture_source",
            )
            text = output.read_text(encoding="utf-8")
        self.assertEqual(result["n_bins"], 3.0)
        self.assertIn("active_fraction", text)

    def test_event_transformer_input_builder_reports_completeness(self) -> None:
        module = load_template(ASTRO / "method_templates" / "event_level_transformer_input_builder" / "template.py")
        with tempfile.TemporaryDirectory() as tmp:
            source_features = Path(tmp) / "source_features.csv"
            source_features.write_text("source_id,n_bins,mean_flux\nAGN_1,3,1.4\n", encoding="utf-8")
            output_events = Path(tmp) / "events.csv"
            completeness = Path(tmp) / "completeness.csv"
            result = module.build_event_level_transformer_inputs(
                event_manifest_csv=ASTRO / "method_templates" / "event_level_transformer_input_builder" / "fixture_event_manifest.csv",
                source_feature_csv=source_features,
                output_event_table=output_events,
                output_completeness_csv=completeness,
            )
            report = completeness.read_text(encoding="utf-8")
        self.assertEqual(result["event_count"], 3)
        self.assertEqual(result["events_missing_source_features"], 1)
        self.assertIn("class_count_AGN", report)


if __name__ == "__main__":
    unittest.main()
