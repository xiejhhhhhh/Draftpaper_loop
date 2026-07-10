# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json
import tempfile
import unittest

from draftpaper_cli.evidence_registry import (
    EvidenceConflictError,
    build_scientific_evidence_registry,
    ensure_registry_consistent,
)
from draftpaper_cli.project_scaffold import create_project


class EvidenceRegistryTests(unittest.TestCase):
    def test_metrics_for_distinct_models_do_not_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Model comparison", field="machine learning")
            (project.path / "results" / "resolved_result_evidence.json").write_text(
                json.dumps(
                    {
                        "evidence_records": [
                            {
                                "entity_role": "result_metric_f1_macro",
                                "value": 0.8667,
                                "unit": "score",
                                "cohort": "main",
                                "sample_unit": "model_evaluation",
                                "split": "source_held_out",
                                "run_id": "run-1",
                                "model": "logistic",
                            },
                            {
                                "entity_role": "result_metric_f1_macro",
                                "value": 0.8053,
                                "unit": "score",
                                "cohort": "main",
                                "sample_unit": "model_evaluation",
                                "split": "source_held_out",
                                "run_id": "run-1",
                                "model": "transformer",
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )

            registry = build_scientific_evidence_registry(project.path)

            self.assertEqual(registry["status"], "ready")
            self.assertEqual({item["model"] for item in registry["records"]}, {"logistic", "transformer"})

    def test_conflicting_source_counts_in_same_cohort_block_writing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="AGN XRB classification", field="astronomy")
            (project.path / "data" / "data_key_facts.json").write_text(
                json.dumps(
                    {
                        "evidence_records": [
                            {
                                "entity_role": "source_count",
                                "value": 1,
                                "unit": "sources",
                                "cohort": "main",
                                "sample_unit": "source",
                            },
                            {
                                "entity_role": "class_balance",
                                "value": {"AGN": 5, "XRB": 5},
                                "unit": "sources",
                                "cohort": "main",
                                "sample_unit": "source",
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )

            registry = build_scientific_evidence_registry(project.path)

            self.assertEqual(registry["status"], "blocked")
            self.assertEqual(registry["blocking_conflict_count"], 1)
            with self.assertRaises(EvidenceConflictError):
                ensure_registry_consistent(project.path)

    def test_main_and_smoke_test_cohorts_can_have_different_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="AGN XRB classification", field="astronomy")
            (project.path / "data" / "data_key_facts.json").write_text(
                json.dumps(
                    {
                        "evidence_records": [
                            {
                                "entity_role": "source_count",
                                "value": 60,
                                "unit": "sources",
                                "cohort": "main",
                                "sample_unit": "source",
                            },
                            {
                                "entity_role": "class_balance",
                                "value": {"AGN": 5, "XRB": 5},
                                "unit": "sources",
                                "cohort": "smoke_test",
                                "sample_unit": "source",
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )

            registry = build_scientific_evidence_registry(project.path)

            self.assertEqual(registry["status"], "ready")
            self.assertEqual(registry["blocking_conflict_count"], 0)

    def test_registry_accepts_domain_neutral_geography_roles(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Spatial yield validation", field="geography")
            (project.path / "data" / "data_key_facts.json").write_text(
                json.dumps(
                    {
                        "evidence_records": [
                            {
                                "entity_role": "spatial_block_count",
                                "value": 12,
                                "unit": "regions",
                                "cohort": "main",
                                "sample_unit": "region",
                                "split": "spatial_holdout",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            registry = build_scientific_evidence_registry(project.path)

            self.assertEqual(registry["status"], "ready")
            self.assertEqual(registry["records"][0]["entity_role"], "spatial_block_count")
            self.assertEqual(registry["records"][0]["split"], "spatial_holdout")

    def test_free_text_observations_are_not_promoted_to_authoritative_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="AGN XRB classification", field="astronomy")
            (project.path / "observations" / "observations.jsonl").write_text(
                json.dumps({"stage": "data", "text": "A smoke test used 1 source, while another note mentioned 60 sources."}) + "\n",
                encoding="utf-8",
            )

            registry = build_scientific_evidence_registry(project.path)

            self.assertEqual(registry["records"], [])
            self.assertEqual(registry["status"], "ready")


if __name__ == "__main__":
    unittest.main()
