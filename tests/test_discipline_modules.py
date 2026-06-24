# Copyright (c) 2026 xiejhhhhhh
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import unittest


class DisciplineModuleTests(unittest.TestCase):
    def test_registry_exposes_core_modules(self) -> None:
        from draftpaper_cli.discipline_modules import get_discipline_module, list_discipline_modules

        module_ids = {item["module_id"] for item in list_discipline_modules()}
        self.assertIn("default", module_ids)
        self.assertIn("geography", module_ids)
        self.assertIn("astronomy", module_ids)
        self.assertIn("machine_learning", module_ids)
        self.assertIn("ecology", module_ids)
        self.assertIn("bioinformatics", module_ids)

        geography = get_discipline_module({"discipline": "geography"})
        hints = geography.method_blueprint_hints({})
        self.assertIn("spatial_block_validation", hints["method_code_hints"])
        self.assertIn("spatial_group_or_coordinates", hints["data_contract_hints"])
        self.assertGreaterEqual(hints["figure_policy"]["minimum_main_figures"], 5)
        self.assertTrue(hints["data_acquisition_hints"])
        self.assertIn("data_formats", hints["data_acquisition_hints"][0])
        template_ids = {item["template_id"] for item in hints["method_template_hints"]}
        self.assertIn("remote_sensing_feature_reconstruction", template_ids)
        self.assertIn("spatial_block_validation", template_ids)

        ml = get_discipline_module({"discipline": "machine_learning"})
        ml_template_ids = {item["template_id"] for item in ml.method_blueprint_hints({})["method_template_hints"]}
        self.assertIn("baseline_model", ml_template_ids)
        self.assertIn("ablation_study", ml_template_ids)
        self.assertIn("train_validation_test_split_check", ml_template_ids)

    def test_discipline_inference_supports_ecology_and_bioinformatics(self) -> None:
        from draftpaper_cli.discipline import infer_discipline_from_text

        ecology = infer_discipline_from_text("ecology environmental monitoring habitat GeoTIFF NetCDF")
        self.assertEqual(ecology["discipline"], "ecology")

        bioinformatics = infer_discipline_from_text("bioinformatics RNA-seq GEO SRA ENA gene expression")
        self.assertEqual(bioinformatics["discipline"], "bioinformatics")


if __name__ == "__main__":
    unittest.main()
