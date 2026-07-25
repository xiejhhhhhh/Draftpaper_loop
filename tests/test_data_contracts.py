# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import unittest

from draftpaper_cli.data_contracts import (
    assess_role_coverage,
    available_data_roles,
    normalize_roles,
    required_roles_from_storyboard,
)


class DataContractRoleAliasTests(unittest.TestCase):
    def test_astronomy_token_modality_and_feature_aliases_are_scientific_roles(self) -> None:
        inventory = {
            "total_rows": 100,
            "files": [
                {
                    "path": "data/processed/model_inputs.csv",
                    "suffix": ".csv",
                    "columns": [
                        "current_n_tokens",
                        "history_n_tokens",
                        "has_pha",
                        "has_arf",
                        "has_rmf",
                        "feature",
                        "importance",
                        "fold",
                        "n_train",
                        "n_test",
                    ],
                }
            ]
        }

        roles = set(available_data_roles(inventory, {}))

        self.assertIn("current_observation_tokens", roles)
        self.assertIn("history_sequence_tokens", roles)
        self.assertIn("modality_availability", roles)
        self.assertIn("spectral_or_remote_sensing_features", roles)
        self.assertIn("features", roles)
        self.assertIn("event_level_samples", roles)
        self.assertIn("sample_group", roles)

        coverage = assess_role_coverage(["event_level_samples", "sample_group"], list(roles))
        self.assertEqual(coverage["decision"], "pass")

    def test_scientific_image_embeddings_expose_feature_confounder_missingness_and_quality_roles(self) -> None:
        inventory = {
            "total_rows": 4800,
            "files": [{
                "path": "external://survey/catalog.csv",
                "kind": "external_read_only",
                "suffix": ".csv",
                "columns": [
                    "OBJECT_ID", "emb_0", "emb_1", "redshift", "mag_r", "color_gr",
                    "image_available", "quality_flag", "is_anomaly", "PROFILE_LABEL", "group_id",
                ],
            }],
        }
        roles = set(available_data_roles(inventory, {}))
        self.assertIn("features", roles)
        self.assertIn("confounder_variables", roles)
        self.assertIn("missingness_reason", roles)
        self.assertIn("quality_flags", roles)
        self.assertIn("label_or_response", roles)
        self.assertIn("sample_group", roles)
        self.assertNotIn("emb_0", roles)

    def test_astronomy_columns_expose_storyboard_scientific_roles(self) -> None:
        inventory = {
            "files": [{
                "path": "catalog.csv",
                "suffix": ".csv",
                "columns": [
                    "TARGETID", "Z", "MORPHTYPE", "mag_g", "mag_r", "mag_z",
                    "color_gr", "abs_mag_r", "adaptive_label", "BGS_TARGET",
                    "neighbour_contamination_score", "background_quality_score",
                ],
            }],
        }
        roles = set(available_data_roles(inventory, {}))
        expected = {
            "selection_covariates",
            "continuous_colour_magnitude_observables",
            "physical_state_proxy",
            "catalog_profile_morphology",
            "continuous_physical_observables",
            "redshift",
            "absolute_magnitude",
            "apparent_magnitude",
            "selection_function",
            "neighbour_contamination",
            "background_quality",
        }
        self.assertTrue(expected.issubset(roles))
        self.assertEqual(assess_role_coverage(sorted(expected), sorted(roles))["decision"], "pass")

    def test_dual_view_galaxy_columns_cover_physical_roles_without_treating_targetid_as_label(self) -> None:
        inventory = {
            "files": [{
                "path": "catalog.csv",
                "suffix": ".csv",
                "columns": [
                    "TARGETID", "Z", "ZERR", "SPECTYPE", "abs_mag_r",
                    "color_gr", "color_rz", "color_w1w2", "quality_flag",
                ],
            }],
        }

        roles = set(available_data_roles(inventory, {}))

        self.assertIn("identifier_or_metadata", roles)
        self.assertIn("physical_observables", roles)
        self.assertIn("redshift_uncertainty", roles)
        self.assertIn("spectral_type", roles)
        self.assertIn("photometric_colours", roles)
        self.assertIn("image_quality_flags", roles)
        self.assertNotIn("label_or_response", roles)

    def test_storyboard_data_contract_excludes_post_method_assignments(self) -> None:
        storyboard = {
            "figures": [{
                "required_data": [
                    "image_embedding",
                    "physical_observables",
                    "image_class_assignment",
                    "physical_class_assignment",
                    "assignment_stability",
                    "sample_support",
                ]
            }]
        }

        roles = required_roles_from_storyboard(storyboard)

        self.assertIn("features", roles)
        self.assertIn("physical_observables", roles)
        self.assertNotIn("image_class_assignment", roles)
        self.assertNotIn("physical_class_assignment", roles)
        self.assertNotIn("assignment_stability", roles)
        self.assertNotIn("sample_support", roles)

    def test_structured_literature_tables_expose_interval_and_citation_evidence_roles(self) -> None:
        inventory = {
            "files": [
                {
                    "path": "literature_observational_intervals.csv",
                    "suffix": ".csv",
                    "columns": [
                        "citation_key", "physical_parameter", "interval_kind",
                        "lower", "upper", "central", "evidence_locator",
                    ],
                },
                {
                    "path": "literature_citation_evidence.csv",
                    "suffix": ".csv",
                    "columns": ["citation_key", "doi", "evidence_status", "local_source"],
                },
            ]
        }

        roles = set(available_data_roles(inventory, {}))

        self.assertIn("literature_observational_interval", roles)
        self.assertIn("citation_evidence", roles)

    def test_role_alias_matching_does_not_infer_light_curve_from_curated(self) -> None:
        roles = normalize_roles(["curated_literature_evidence", "apparent_r_magnitude"])

        self.assertNotIn("light_curve", roles)

    def test_storyboard_excludes_contextual_prediction_outputs(self) -> None:
        roles = required_roles_from_storyboard({
            "figures": [{
                "required_data": [
                    "source_catalog",
                    "held_out_dev_exp_predictions",
                    "multi_seed_predictions",
                    "tile_grouped_predictions",
                    "calibration_bins",
                ]
            }]
        })

        self.assertEqual(roles, ["source_catalog"])

    def test_specific_image_catalog_roles_use_composite_inventory_evidence(self) -> None:
        inventory = {
            "files": [{
                "path": "external://catalog/vis_cutout_catalog.csv",
                "suffix": ".csv",
                "columns": [
                    "source_id",
                    "split",
                    "euclid_primary_tile_id",
                    "cutout_exists",
                    "cutout_file_path",
                    "color_gr",
                    "mag_r",
                    "z",
                    "prediction_score",
                ],
            }],
        }
        roles = available_data_roles(inventory, {})
        coverage = assess_role_coverage(
            [
                "vis_cutout_manifest",
                "held_out_vis_cutouts",
                "euclid_tile",
                "observed_colours",
                "apparent_r_magnitude",
                "spectroscopic_redshift",
                "calibration_bins",
            ],
            roles,
        )

        self.assertEqual(coverage["decision"], "pass")
        self.assertEqual(coverage["missing_roles"], [])


if __name__ == "__main__":
    unittest.main()
