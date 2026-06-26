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
        self.assertIn("finance", module_ids)
        self.assertIn("medicine", module_ids)
        self.assertIn("biology", module_ids)
        self.assertIn("engineering", module_ids)

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

    def test_new_foundation_modules_have_minimum_data_method_and_review_specs(self) -> None:
        from draftpaper_cli.discipline_modules import get_discipline_module

        expected = {
            "finance": {"data": "market_price_api", "method": "event_study", "review": "lookahead_bias_gate"},
            "medicine": {"data": "clinical_trials_registry", "method": "cohort_construction", "review": "ethics_and_privacy_gate"},
            "biology": {"data": "public_sequence_repository", "method": "differential_expression", "review": "multiple_testing_fdr_gate"},
            "engineering": {"data": "sensor_log_manifest", "method": "signal_processing_pipeline", "review": "unit_boundary_condition_gate"},
        }
        for discipline, ids in expected.items():
            module = get_discipline_module({"discipline": discipline})
            hints = module.method_blueprint_hints({})
            connector_ids = {item["connector_id"] for item in hints["data_acquisition_hints"]}
            method_ids = {item["template_id"] for item in hints["method_template_hints"]}
            review_ids = {item["rule_group_id"] for item in hints["review_rule_hints"]}
            self.assertGreaterEqual(len(connector_ids), 3, discipline)
            self.assertGreaterEqual(len(method_ids), 3, discipline)
            self.assertGreaterEqual(len(review_ids), 3, discipline)
            self.assertIn(ids["data"], connector_ids)
            self.assertIn(ids["method"], method_ids)
            self.assertIn(ids["review"], review_ids)

    def test_discipline_inference_supports_ecology_and_bioinformatics(self) -> None:
        from draftpaper_cli.discipline import infer_discipline_from_text

        ecology = infer_discipline_from_text("ecology environmental monitoring habitat GeoTIFF NetCDF")
        self.assertEqual(ecology["discipline"], "ecology")

        bioinformatics = infer_discipline_from_text("bioinformatics RNA-seq GEO SRA ENA gene expression")
        self.assertEqual(bioinformatics["discipline"], "bioinformatics")

        finance = infer_discipline_from_text("finance event study portfolio return volatility factor model")
        self.assertEqual(finance["discipline"], "finance")

        medicine = infer_discipline_from_text("clinical medicine cohort survival analysis EHR patient trial")
        self.assertEqual(medicine["discipline"], "medicine")

        biology = infer_discipline_from_text("biology gene expression protein assay differential expression")
        self.assertEqual(biology["discipline"], "biology")

        engineering = infer_discipline_from_text("engineering sensor signal finite element boundary condition")
        self.assertEqual(engineering["discipline"], "engineering")


if __name__ == "__main__":
    unittest.main()
