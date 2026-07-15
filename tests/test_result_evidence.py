# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json
import tempfile
import unittest
import hashlib

from draftpaper_cli.project_scaffold import create_project
from draftpaper_cli.evidence_registry import build_scientific_evidence_registry
from draftpaper_cli.result_evidence import resolve_result_evidence


class ResultEvidenceResolverTests(unittest.TestCase):
    def test_distinct_validation_table_families_keep_distinct_analysis_variants(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Multi-seed and grouped validation", field="machine learning")
            tables = project.path / "results" / "tables"
            (tables / "multi_seed_metrics.csv").write_text(
                "seed,macro_f1\n1,0.90\n2,0.88\n", encoding="utf-8"
            )
            (tables / "tile_grouped_validation.csv").write_text(
                "seed,macro_f1\n1,0.87\n2,0.86\n", encoding="utf-8"
            )
            (project.path / "methods" / "run_manifest.yaml").write_text(
                json.dumps({
                    "status": "success",
                    "run_id": "run-1",
                    "output_files": [
                        "results/tables/multi_seed_metrics.csv",
                        "results/tables/tile_grouped_validation.csv",
                    ],
                }),
                encoding="utf-8",
            )

            report = resolve_result_evidence(project.path)
            registry = build_scientific_evidence_registry(project.path)

            variants = {
                item["analysis_variant"]
                for item in report["evidence_records"]
                if item["entity_role"] == "result_metric_macro_f1"
            }
            self.assertEqual(variants, {"multi_seed_summary", "tile_grouped_validation"})
            self.assertEqual(registry["blocking_conflict_count"], 0)

    def test_quality_filtered_metrics_remain_distinct_sensitivity_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Primary and sensitivity metrics", field="machine learning")
            tables = project.path / "results" / "tables"
            (tables / "model_metrics_by_fold.csv").write_text(
                "run_id,model_variant,fold,macro_f1\n"
                "run-1,combined,0,0.48\n"
                "run-1,combined,1,0.52\n",
                encoding="utf-8",
            )
            (tables / "quality_filtered_model_metrics_by_fold.csv").write_text(
                "run_id,model_variant,fold,macro_f1\n"
                "run-1,combined,0,0.49\n"
                "run-1,combined,1,0.53\n",
                encoding="utf-8",
            )
            (project.path / "methods" / "method_requirements.json").write_text(
                json.dumps({"primary_metric": "macro_f1", "primary_model_id": "combined"}),
                encoding="utf-8",
            )
            (project.path / "methods" / "run_manifest.yaml").write_text(
                json.dumps(
                    {
                        "status": "success",
                        "run_id": "run-1",
                        "output_files": [
                            "results/tables/model_metrics_by_fold.csv",
                            "results/tables/quality_filtered_model_metrics_by_fold.csv",
                        ],
                    }
                ),
                encoding="utf-8",
            )

            report = resolve_result_evidence(project.path)

            records = [item for item in report["evidence_records"] if item["entity_role"] == "result_metric_macro_f1"]
            self.assertEqual(
                {item["analysis_variant"] for item in records},
                {"primary_fixed_partition", "quality_filtered_sensitivity"},
            )
            self.assertEqual(len({item["evidence_id"] for item in records}), 2)
            self.assertEqual(report["primary_metric"]["analysis_variant"], "primary_fixed_partition")
            self.assertEqual(report["primary_metric"]["value"], 0.5)

    def test_fixed_pooled_and_repeated_partition_estimands_do_not_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Partition-aware evaluation", field="machine learning")
            tables = project.path / "results" / "tables"
            (tables / "model_metrics_by_fold.csv").write_text(
                "run_id,model_variant,fold,macro_f1\n"
                "run-1,combined,0,0.48\n"
                "run-1,combined,1,0.50\n",
                encoding="utf-8",
            )
            (tables / "pooled_out_of_fold_metrics.csv").write_text(
                "run_id,model_variant,macro_f1\nrun-1,combined,0.496\n",
                encoding="utf-8",
            )
            (tables / "repeated_group_partition_metrics.csv").write_text(
                "run_id,model_variant,fold,macro_f1\n"
                "run-1,combined,0,0.49\n"
                "run-1,combined,1,0.51\n",
                encoding="utf-8",
            )
            (project.path / "methods" / "method_requirements.json").write_text(
                json.dumps({"primary_metric": "macro_f1", "primary_model_id": "combined"}),
                encoding="utf-8",
            )
            (project.path / "methods" / "run_manifest.yaml").write_text(
                json.dumps(
                    {
                        "status": "success",
                        "run_id": "run-1",
                        "output_files": [
                            "results/tables/model_metrics_by_fold.csv",
                            "results/tables/pooled_out_of_fold_metrics.csv",
                            "results/tables/repeated_group_partition_metrics.csv",
                        ],
                    }
                ),
                encoding="utf-8",
            )

            report = resolve_result_evidence(project.path)
            scopes = {
                (item["aggregation"], item["analysis_variant"])
                for item in report["evidence_records"]
                if item["entity_role"] == "result_metric_macro_f1"
            }
            self.assertEqual(
                scopes,
                {
                    ("mean_across_primary_folds", "primary_fixed_partition"),
                    ("pooled_out_of_fold", "primary_fixed_partition"),
                    ("mean_across_repeated_group_partitions", "repeated_partition_sensitivity"),
                },
            )
            registry = build_scientific_evidence_registry(project.path)
            self.assertEqual(registry["blocking_conflict_count"], 0)
            self.assertEqual(registry["conflicts"], [])

    def test_configured_primary_metric_uses_run_summary_without_hiding_stronger_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Primary model comparison", field="machine learning")
            tables = project.path / "results" / "tables"
            (tables / "metrics.csv").write_text(
                "metric,value\nf1_macro,0.8053\nbest_baseline_f1_macro,0.8667\n",
                encoding="utf-8",
            )
            detail = tables / "details"
            detail.mkdir()
            (detail / "model_metrics.csv").write_text(
                "model,split,f1_macro\ntransformer,test,0.8053\nlogistic,test,0.8667\n",
                encoding="utf-8",
            )
            (project.path / "methods" / "method_requirements.json").write_text(
                json.dumps({"primary_metric": "f1_macro"}), encoding="utf-8"
            )
            (project.path / "methods" / "run_manifest.yaml").write_text(
                json.dumps({
                    "status": "success",
                    "run_id": "primary-run",
                    "output_files": ["results/tables/metrics.csv"],
                    "metrics": {"f1_macro": 0.8053, "best_baseline_f1_macro": 0.8667},
                }),
                encoding="utf-8",
            )

            report = resolve_result_evidence(project.path)

            self.assertEqual(report["primary_metric"]["value"], 0.8053)
            self.assertTrue(any(item.get("model") == "logistic" and item["value"] == 0.8667 for item in report["metrics"]))

    def test_unconfigured_primary_metric_does_not_promote_ablation_variant(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Fine-tuning sensitivity", field="machine learning")
            table = project.path / "results" / "tables" / "metrics.csv"
            table.write_text(
                "variant,macro_f1\n"
                "fine_tune_last_three_blocks,0.7211\n"
                "ablation_no_augmentation,0.7305\n",
                encoding="utf-8",
            )
            (project.path / "methods" / "method_requirements.json").write_text(
                json.dumps({"primary_metric": "f1"}), encoding="utf-8"
            )
            (project.path / "methods" / "run_manifest.yaml").write_text(
                json.dumps({"status": "success", "run_id": "run-1", "output_files": ["results/tables/metrics.csv"]}),
                encoding="utf-8",
            )

            report = resolve_result_evidence(project.path)

            self.assertEqual(report["primary_metric"]["model"], "fine_tune_last_three_blocks")
            self.assertEqual(report["primary_metric_selection"], "highest_ranked_non_ablation_run_bound_model")

    def test_resolver_is_byte_stable_when_run_evidence_is_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Stable evidence", field="engineering")
            table = project.path / "results" / "tables" / "verified.csv"
            table.write_text("model,split,f1_macro\nbaseline,test,0.8\n", encoding="utf-8")
            (project.path / "methods" / "run_manifest.yaml").write_text(
                json.dumps({"status": "success", "run_id": "stable", "output_files": ["results/tables/verified.csv"]}),
                encoding="utf-8",
            )

            resolve_result_evidence(project.path)
            output = project.path / "results" / "resolved_result_evidence.json"
            first_hash = hashlib.sha256(output.read_bytes()).hexdigest()
            resolve_result_evidence(project.path)
            second_hash = hashlib.sha256(output.read_bytes()).hexdigest()

            self.assertEqual(first_hash, second_hash)

    def test_summary_metric_anchors_bind_matching_detailed_tables(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Legacy run evidence", field="astronomy machine learning")
            tables = project.path / "results" / "tables"
            detail = tables / "model_outputs"
            detail.mkdir(parents=True, exist_ok=True)
            (tables / "metrics.csv").write_text(
                "metric,value\n"
                "f1_macro,0.8053\n"
                "best_baseline_f1_macro,0.8667\n"
                "token_transformer_best_f1_macro,0.8205\n",
                encoding="utf-8",
            )
            (detail / "baseline_metrics.csv").write_text(
                "model,fold_id,f1_macro\n"
                "logistic_event_static,0,0.8667\n"
                "random_forest_event_static,0,0.8486\n",
                encoding="utf-8",
            )
            (detail / "transformer_metrics.csv").write_text(
                "model,fold_id,f1_macro\n"
                "token_transformer_time2vec_full,0,0.8053\n"
                "token_transformer_no_history,0,0.8205\n",
                encoding="utf-8",
            )
            (detail / "unrelated_metrics.csv").write_text(
                "model,fold_id,f1_macro\nunrelated,0,0.9999\n",
                encoding="utf-8",
            )
            (project.path / "methods" / "run_manifest.yaml").write_text(
                json.dumps(
                    {
                        "status": "success",
                        "run_id": "legacy-anchored-run",
                        "output_files": ["results/tables/metrics.csv"],
                    }
                ),
                encoding="utf-8",
            )

            report = resolve_result_evidence(project.path)

            model_values = {
                item["model"]: item["value"]
                for item in report["metrics"]
                if item.get("model") and item["metric_name"] == "f1_macro"
            }
            self.assertEqual(model_values["logistic_event_static"], 0.8667)
            self.assertEqual(model_values["random_forest_event_static"], 0.8486)
            self.assertEqual(model_values["token_transformer_time2vec_full"], 0.8053)
            self.assertEqual(model_values["token_transformer_no_history"], 0.8205)
            self.assertNotIn("unrelated", model_values)
            self.assertIn(
                "results/tables/model_outputs/baseline_metrics.csv",
                report["anchor_verified_sources"],
            )

    def test_verified_model_tables_override_generic_metrics_csv(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="AGN XRB classification", field="astronomy machine learning")
            tables = project.path / "results" / "tables"
            (tables / "metrics.csv").write_text("metric,value\nf1,0.5\n", encoding="utf-8")
            (tables / "baseline_source_holdout_metrics.csv").write_text(
                "model,split,fold,f1_macro\n"
                "logistic_event_static,source_held_out,0,0.8667\n"
                "random_forest_event_static,source_held_out,0,0.8486\n",
                encoding="utf-8",
            )
            (tables / "ablation_metrics.csv").write_text(
                "model,split,fold,f1_macro\n"
                "token_transformer_time2vec_full,source_held_out,0,0.8053\n"
                "token_transformer_no_history,source_held_out,0,0.8205\n",
                encoding="utf-8",
            )
            (project.path / "methods" / "run_manifest.yaml").write_text(
                json.dumps(
                    {
                        "status": "success",
                        "run_id": "astro-run-1",
                        "output_files": [
                            "results/tables/metrics.csv",
                            "results/tables/baseline_source_holdout_metrics.csv",
                            "results/tables/ablation_metrics.csv",
                        ],
                        "metrics": {"f1": 0.5},
                    }
                ),
                encoding="utf-8",
            )

            report = resolve_result_evidence(project.path)

            by_model = {
                item["model"]: item["value"]
                for item in report["metrics"]
                if item["metric_name"] == "f1_macro" and item.get("model")
            }
            self.assertEqual(by_model["logistic_event_static"], 0.8667)
            self.assertEqual(by_model["random_forest_event_static"], 0.8486)
            self.assertEqual(by_model["token_transformer_time2vec_full"], 0.8053)
            self.assertEqual(by_model["token_transformer_no_history"], 0.8205)
            self.assertEqual(report["primary_metric"]["value"], 0.8053)
            self.assertEqual(report["primary_metric"]["model"], "token_transformer_time2vec_full")
            self.assertNotEqual(report["primary_metric"]["value"], 0.5)
            self.assertEqual(report["run_id"], "astro-run-1")

    def test_unbound_metric_file_is_not_promoted_when_run_outputs_exist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Model comparison", field="machine learning")
            tables = project.path / "results" / "tables"
            (tables / "metrics.csv").write_text("metric,value\nf1,0.99\n", encoding="utf-8")
            (tables / "verified.csv").write_text(
                "model,split,f1_macro\nbaseline,test,0.73\n",
                encoding="utf-8",
            )
            (project.path / "methods" / "run_manifest.yaml").write_text(
                json.dumps(
                    {
                        "status": "success",
                        "run_id": "verified-run",
                        "output_files": ["results/tables/verified.csv"],
                    }
                ),
                encoding="utf-8",
            )

            report = resolve_result_evidence(project.path)

            self.assertEqual(report["primary_metric"]["value"], 0.73)
            self.assertNotIn("results/tables/metrics.csv", report["bound_sources"])

    def test_long_form_model_metrics_preserve_identity_and_select_full_model(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Time-aware classifier", field="astronomy machine learning")
            table = project.path / "results" / "tables" / "verified_model_metrics.csv"
            table.write_text(
                "run_id,cohort_id,sample_unit,split,model_id,metric,metric_dimension,sample_count,value\n"
                "run-1,baseline,event,source_held_out,logistic_event_static,f1_macro,dimensionless_score,6290,0.8667\n"
                "run-1,baseline,event,source_held_out,random_forest_event_static,f1_macro,dimensionless_score,6290,0.8486\n"
                "run-1,token,event,source_held_out,token_transformer_time2vec_full,f1_macro,dimensionless_score,5980,0.8053\n"
                "run-1,token,event,source_held_out,token_transformer_no_history,f1_macro,dimensionless_score,5980,0.8205\n",
                encoding="utf-8",
            )
            (project.path / "methods" / "method_requirements.json").write_text(
                json.dumps({"primary_metric": "f1"}), encoding="utf-8"
            )
            (project.path / "methods" / "run_manifest.yaml").write_text(
                json.dumps({"status": "success", "run_id": "run-1", "output_files": ["results/tables/verified_model_metrics.csv"]}),
                encoding="utf-8",
            )

            report = resolve_result_evidence(project.path)

            by_model = {item["model"]: item["value"] for item in report["metrics"] if item.get("model")}
            self.assertEqual(by_model, {
                "logistic_event_static": 0.8667,
                "random_forest_event_static": 0.8486,
                "token_transformer_time2vec_full": 0.8053,
                "token_transformer_no_history": 0.8205,
            })
            self.assertEqual(report["primary_metric"]["model"], "token_transformer_time2vec_full")
            self.assertEqual(report["primary_metric"]["value"], 0.8053)
            self.assertEqual(report["primary_metric_selection"], "inferred_full_or_proposed_model")

    def test_resolver_rejects_identifiers_ranks_and_per_sample_scores_as_global_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Group-aware image model", field="astronomy machine learning")
            tables = project.path / "results" / "tables"
            (tables / "metrics.csv").write_text(
                "metric,value\nmacro_f1,0.49\nbalanced_accuracy,0.60\n",
                encoding="utf-8",
            )
            (tables / "out_of_fold_predictions.csv").write_text(
                "TARGETID,group_id,true_label,predicted_label,prediction_score\n"
                "39633477292786966,tile_1,SER,DEV,0.64\n",
                encoding="utf-8",
            )
            (tables / "anomaly_candidates.csv").write_text(
                "TARGETID,group_id,candidate_rank,candidate_score,is_candidate\n"
                "39633477292786966,tile_1,1,0.55,true\n",
                encoding="utf-8",
            )
            (tables / "model_comparison.csv").write_text(
                "model_variant,metric,mean,std\n"
                "catalog_only,macro_f1,0.42,0.02\n"
                "combined,macro_f1,0.49,0.02\n",
                encoding="utf-8",
            )
            (project.path / "methods" / "method_requirements.json").write_text(
                json.dumps({"primary_metric": "f1"}), encoding="utf-8"
            )
            (project.path / "methods" / "run_manifest.yaml").write_text(
                json.dumps(
                    {
                        "status": "success",
                        "run_id": "image-run",
                        "output_files": [
                            "results/tables/metrics.csv",
                            "results/tables/out_of_fold_predictions.csv",
                            "results/tables/anomaly_candidates.csv",
                            "results/tables/model_comparison.csv",
                        ],
                    }
                ),
                encoding="utf-8",
            )

            report = resolve_result_evidence(project.path)

            metric_names = {item["metric_name"] for item in report["metrics"]}
            self.assertIn("macro_f1", metric_names)
            self.assertIn("balanced_accuracy", metric_names)
            self.assertNotIn("targetid", metric_names)
            self.assertNotIn("group_id", metric_names)
            self.assertNotIn("candidate_rank", metric_names)
            self.assertNotIn("prediction_score", metric_names)
            self.assertNotIn("candidate_score", metric_names)
            by_model = {
                item["model"]: item["value"]
                for item in report["metrics"]
                if item.get("model") and item["metric_name"] == "macro_f1"
            }
            self.assertEqual(by_model, {"catalog_only": 0.42, "combined": 0.49})


if __name__ == "__main__":
    unittest.main()
