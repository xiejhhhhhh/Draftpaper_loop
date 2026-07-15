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

    def test_registry_preserves_figure_formula_and_interpretation_bindings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Bound evidence", field="machine learning")
            (project.path / "results" / "resolved_result_evidence.json").write_text(
                json.dumps({
                    "evidence_records": [{
                        "evidence_id": "metric-bound",
                        "entity_role": "result_metric_macro_f1",
                        "value": 0.81,
                        "unit": "score",
                        "cohort_id": "held-out",
                        "sample_unit": "source",
                        "split": "group-held-out",
                        "run_id": "run-1",
                        "model_id": "model-1",
                        "metric_dimension": "dimensionless_score",
                        "figure_ids": ["figure-performance"],
                        "formula_ids": ["formula-f1"],
                        "allowed_interpretation": "A bounded held-out comparison.",
                    }]
                }),
                encoding="utf-8",
            )

            registry = build_scientific_evidence_registry(project.path)
            record = registry["records"][0]

            self.assertEqual(record["figure_ids"], ["figure-performance"])
            self.assertEqual(record["formula_ids"], ["formula-f1"])
            self.assertEqual(record["allowed_interpretation"], "A bounded held-out comparison.")

    def test_cohort_figure_counts_are_available_to_data_writing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Cohort study", field="astronomy")
            (project.path / "results" / "result_manifest.yaml").write_text(json.dumps({
                "figures": [{
                    "id": "cohort-figure",
                    "storyboard_id": "cohort-figure",
                    "scientific_question": "What sample coverage and missingness define the cohort?",
                    "metrics": {"source_catalog": 5544, "image_available": 5275, "embedding_valid": 4800},
                }]
            }), encoding="utf-8")
            (project.path / "methods" / "run_manifest.yaml").write_text(
                json.dumps({"status": "success", "run_id": "run-1"}), encoding="utf-8"
            )

            registry = build_scientific_evidence_registry(project.path)

            cohort_records = [item for item in registry["records"] if item["figure_ids"] == ["cohort-figure"]]
            self.assertEqual(len(cohort_records), 3)
            self.assertTrue(all("data" in item["target_sections"] for item in cohort_records))
            self.assertTrue(all(item["metric_dimension"] == "count" for item in cohort_records))

    def test_nested_figure_lists_are_registered_as_numeric_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Nested figure evidence", field="machine learning")
            (project.path / "results" / "result_manifest.yaml").write_text(json.dumps({
                "figures": [{
                    "id": "figure-audit",
                    "storyboard_id": "figure-audit",
                    "scientific_question": "How does the cohort flow into the held-out confusion matrix?",
                    "metrics": {
                        "sample_flow": [5544, 5275, 4800, 1225],
                        "confusion_matrix": [[105, 11], [4, 64]],
                        "tile_grouped": [{"macro_f1": 0.8662, "test_group_count": 15}],
                        "shared_tiles_remain": True,
                    },
                }]
            }), encoding="utf-8")
            (project.path / "methods" / "run_manifest.yaml").write_text(
                json.dumps({"status": "success", "run_id": "run-1"}), encoding="utf-8"
            )

            registry = build_scientific_evidence_registry(project.path)

            values = {item["value"] for item in registry["records"]}
            self.assertTrue({5544.0, 5275.0, 4800.0, 1225.0, 105.0, 11.0, 4.0, 64.0}.issubset(values))
            self.assertNotIn(1.0, values)
            confusion = [item for item in registry["records"] if "confusion_matrix" in item["entity_role"]]
            self.assertTrue(confusion)
            self.assertTrue(all(item["metric_dimension"] == "count" for item in confusion))
            grouped_f1 = next(item for item in registry["records"] if "tile_grouped_0_macro_f1" in item["entity_role"])
            grouped_count = next(item for item in registry["records"] if "test_group_count" in item["entity_role"])
            self.assertEqual(grouped_f1["metric_dimension"], "score")
            self.assertEqual(grouped_count["metric_dimension"], "count")


if __name__ == "__main__":
    unittest.main()
