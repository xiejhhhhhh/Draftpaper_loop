# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json
import tempfile
import unittest
import hashlib

from draftpaper_cli.project_scaffold import create_project
from draftpaper_cli.result_evidence import resolve_result_evidence


class ResultEvidenceResolverTests(unittest.TestCase):
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
            self.assertEqual(report["primary_metric"]["value"], 0.8667)
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


if __name__ == "__main__":
    unittest.main()
