# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import unittest

from draftpaper_cli.data_contracts import assess_role_coverage, available_data_roles


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


if __name__ == "__main__":
    unittest.main()
