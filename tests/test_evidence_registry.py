# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import hashlib
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

    def test_performance_scope_words_do_not_turn_scores_into_data_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Event-level classification", field="astronomy")
            (project.path / "results" / "result_manifest.yaml").write_text(json.dumps({
                "figures": [
                    {
                        "storyboard_id": "performance-figure",
                        "scientific_question": "How well does event-level classification generalize?",
                        "metrics": {
                            "source_balanced_event_macro_f1": 0.8257,
                            "independent_event_count": 3283,
                            "event_confusion_matrix": [[2218, 189], [123, 753]],
                        },
                    },
                    {
                        "storyboard_id": "coverage-figure",
                        "scientific_question": "What sample coverage and missingness define the cohort?",
                        "metrics": {"current_token_available_fraction": 0.8337},
                    },
                ]
            }), encoding="utf-8")
            (project.path / "methods" / "run_manifest.yaml").write_text(
                json.dumps({"status": "success", "run_id": "run-1"}), encoding="utf-8"
            )

            registry = build_scientific_evidence_registry(project.path)
            by_role = {item["entity_role"]: item for item in registry["records"]}

            performance = by_role["result_metric_source_balanced_event_macro_f1"]
            self.assertEqual(performance["metric_dimension"], "score")
            self.assertNotIn("data", performance["target_sections"])
            denominator = by_role["result_metric_independent_event_count"]
            self.assertEqual(denominator["metric_dimension"], "count")
            self.assertIn("data", denominator["target_sections"])
            confusion = [item for role, item in by_role.items() if "event_confusion_matrix" in role]
            self.assertTrue(confusion)
            self.assertTrue(all(item["metric_dimension"] == "count" for item in confusion))
            self.assertTrue(all("data" not in item["target_sections"] for item in confusion))
            coverage = by_role["result_metric_current_token_available_fraction"]
            self.assertEqual(coverage["metric_dimension"], "fraction")
            self.assertIn("data", coverage["target_sections"])

    def test_figure_contract_bindings_distinguish_same_named_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Bound figure metrics", field="geography")
            (project.path / "results" / "result_manifest.yaml").write_text(json.dumps({
                "figures": [
                    {"storyboard_id": "figure-a", "metrics": {"sample_count": 3000}},
                    {"storyboard_id": "figure-b", "metrics": {"sample_count": 2153}},
                ]
            }), encoding="utf-8")
            (project.path / "results" / "figure_contracts.json").write_text(json.dumps({
                "contracts": [
                    {
                        "storyboard_id": "figure-a",
                        "analysis_spec_id": "analysis-a",
                        "estimand_id": "estimand-a",
                        "cohort_view_id": "cohort-a",
                    },
                    {
                        "storyboard_id": "figure-b",
                        "analysis_spec_id": "analysis-b",
                        "estimand_id": "estimand-b",
                        "cohort_view_id": "cohort-b",
                    },
                ]
            }), encoding="utf-8")
            (project.path / "methods" / "run_manifest.yaml").write_text(
                json.dumps({"status": "success", "run_id": "run-1"}), encoding="utf-8"
            )

            registry = build_scientific_evidence_registry(project.path)

            self.assertEqual(registry["status"], "ready")
            self.assertEqual(registry["blocking_conflict_count"], 0)
            self.assertEqual(
                {item["analysis_spec_id"] for item in registry["records"]},
                {"analysis-a", "analysis-b"},
            )
            self.assertTrue(all(item["binding_complete"] for item in registry["records"]))

    def test_same_metric_in_distinct_cohorts_does_not_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Cohort-specific external validation", field="astronomy")
            (project.path / "results" / "resolved_result_evidence.json").write_text(
                json.dumps({
                    "evidence_records": [
                        {
                            "entity_role": "result_metric_macro_f1",
                            "value": 0.82,
                            "unit": "score",
                            "cohort_id": "main",
                            "cohort_view_id": "held_out",
                            "estimand_id": "classification",
                            "analysis_spec_id": "source_held_out",
                            "sample_unit": "source",
                            "split_id": "source_held_out",
                            "run_id": "run-1",
                            "model_id": "model-a",
                            "metric_dimension": "score",
                            "aggregation": "mean",
                        },
                        {
                            "entity_role": "result_metric_macro_f1",
                            "value": 0.76,
                            "unit": "score",
                            "cohort_id": "external",
                            "cohort_view_id": "held_out",
                            "estimand_id": "classification",
                            "analysis_spec_id": "source_held_out",
                            "sample_unit": "source",
                            "split_id": "source_held_out",
                            "run_id": "run-1",
                            "model_id": "model-a",
                            "metric_dimension": "score",
                            "aggregation": "mean",
                        },
                    ]
                }),
                encoding="utf-8",
            )

            registry = build_scientific_evidence_registry(project.path)

            self.assertEqual(registry["status"], "ready")
            self.assertEqual(registry["blocking_conflict_count"], 0)

    def test_content_addressed_figure_tables_are_registered(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Figure table evidence", field="astronomy")
            table = project.path / "results" / "tables" / "external.csv"
            table.parent.mkdir(parents=True, exist_ok=True)
            table.write_text(
                "cohort,time_encoding,source_count,macro_f1,balanced_accuracy\n"
                "external,time2vec,40,0.7953964194,0.8\n",
                encoding="utf-8",
            )
            digest = hashlib.sha256(table.read_bytes()).hexdigest()
            (project.path / "results" / "figure_metadata.json").write_text(
                json.dumps({
                    "figures": [{
                        "figure_id": "external-validation",
                        "cohort_id": "external",
                        "cohort_view_id": "external-cohort",
                        "estimand_id": "external-transfer",
                        "analysis_spec_id": "external-source-validation",
                        "sample_unit": "source",
                        "split": "source_held_out",
                        "split_id": "source_held_out",
                        "model_id": "time2vec",
                        "evidence_ids": [f"table:external.csv:{digest[:16]}"],
                    }]
                }),
                encoding="utf-8",
            )
            (project.path / "methods" / "run_manifest.yaml").write_text(
                json.dumps({"status": "success", "run_id": "run-1"}), encoding="utf-8"
            )

            registry = build_scientific_evidence_registry(project.path)

            table_records = [
                item for item in registry["records"]
                if item["source_artifact"] == "results/tables/external.csv"
            ]
            self.assertEqual(registry["figure_table_binding_count"], 3)
            self.assertEqual(
                {item["entity_role"] for item in table_records},
                {
                    "result_metric_source_count",
                    "result_metric_macro_f1",
                    "result_metric_balanced_accuracy",
                },
            )
            self.assertTrue(all(item["binding_complete"] for item in table_records))

    def test_figure_declared_source_tables_are_registered(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Figure source-table evidence", field="astronomy")
            table = project.path / "results" / "tables" / "summary.tsv"
            table.parent.mkdir(parents=True, exist_ok=True)
            table.write_text(
                "cohort\tsource_count\tmacro_f1\n"
                "external\t25\t0.72\n",
                encoding="utf-8",
            )
            (project.path / "results" / "figure_metadata.json").write_text(
                json.dumps({
                    "figures": [{
                        "figure_id": "external-summary",
                        "cohort_id": "external",
                        "cohort_view_id": "external-cohort",
                        "estimand_id": "external-transfer",
                        "analysis_spec_id": "external-source-validation",
                        "sample_unit": "source",
                        "split": "source_held_out",
                        "split_id": "source_held_out",
                        "model_id": "time2vec",
                        "source_tables": ["results/tables/summary.tsv"],
                    }]
                }),
                encoding="utf-8",
            )
            (project.path / "methods" / "run_manifest.yaml").write_text(
                json.dumps({"status": "success", "run_id": "run-1"}), encoding="utf-8"
            )

            registry = build_scientific_evidence_registry(project.path)

            table_records = [
                item for item in registry["records"]
                if item["source_artifact"] == "results/tables/summary.tsv"
            ]
            self.assertEqual(len(table_records), 2)
            self.assertTrue(all(item["binding_complete"] for item in table_records))

    def test_unbound_figure_tables_are_not_promoted_to_canonical_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Unbound figure table", field="astronomy")
            table = project.path / "results" / "tables" / "draft.csv"
            table.parent.mkdir(parents=True, exist_ok=True)
            table.write_text("source_count,macro_f1\n25,0.72\n", encoding="utf-8")
            (project.path / "results" / "figure_metadata.json").write_text(
                json.dumps({
                    "figures": [{
                        "figure_id": "draft-figure",
                        "source_tables": ["results/tables/draft.csv"],
                    }]
                }),
                encoding="utf-8",
            )
            (project.path / "methods" / "run_manifest.yaml").write_text(
                json.dumps({"status": "success", "run_id": "run-1"}), encoding="utf-8"
            )

            registry = build_scientific_evidence_registry(project.path)

            self.assertEqual(registry["incomplete_binding_count"], 0)
            self.assertFalse(
                any(item["source_artifact"] == "results/tables/draft.csv" for item in registry["records"])
            )


if __name__ == "__main__":
    unittest.main()
