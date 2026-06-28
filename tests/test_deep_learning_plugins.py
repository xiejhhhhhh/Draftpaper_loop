# Copyright (c) 2026 Jinray Xie
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
ML = ROOT / "draftpaper_cli" / "discipline_modules" / "machine_learning"


def load_template(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem + "_ml_test_module", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot import template: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class DeepLearningPluginTemplateTests(unittest.TestCase):
    def test_machine_learning_module_exposes_deep_learning_plugins(self) -> None:
        from draftpaper_cli.discipline_modules import get_discipline_module

        hints = get_discipline_module({"discipline": "machine_learning"}).method_blueprint_hints({})
        connector_ids = {item["connector_id"] for item in hints["data_acquisition_hints"]}
        template_ids = {item["template_id"] for item in hints["method_template_hints"]}
        self.assertIn("vision_catalog_image", connector_ids)
        self.assertIn("pretrained_backbone", connector_ids)
        self.assertIn("self_supervised_dino_training", template_ids)
        self.assertIn("checkpoint_shape_adapter", template_ids)
        self.assertIn("embedding_extraction_health_diagnostics", template_ids)
        self.assertIn("few_label_probe_benchmark", template_ids)
        self.assertIn("embedding_similarity_retrieval", template_ids)

    def test_vision_catalog_connector_aligns_files_to_catalog(self) -> None:
        module = load_template(ML / "data_connectors" / "vision_catalog_image" / "template.py")
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "manifest.csv"
            result = module.build_catalog_image_manifest(
                catalog_csv=ML / "data_connectors" / "vision_catalog_image" / "fixture_catalog.csv",
                image_files=["1001_cutout.fits", "1002_cutout.fits", "9999_cutout.fits"],
                output_csv=output,
                ignore_labels={"uncertain"},
            )
            text = output.read_text(encoding="utf-8")
        self.assertEqual(result["matched_count"], 2)
        self.assertEqual(result["missing_catalog"], 1)
        self.assertIn("spiral", text)

    def test_pretrained_backbone_connector_writes_sanitized_metadata(self) -> None:
        module = load_template(ML / "data_connectors" / "pretrained_backbone" / "template.py")
        fixture = json.loads((ML / "data_connectors" / "pretrained_backbone" / "fixture_backbone_metadata.json").read_text(encoding="utf-8"))
        metadata = module.normalize_backbone_metadata(**fixture, checkpoint_path="C:/private/model.pth")
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "metadata.json"
            result = module.write_backbone_metadata(metadata, output)
            text = output.read_text(encoding="utf-8")
        self.assertEqual(result["model_name"], "dinov2_vits14")
        self.assertIn("{{checkpoint_path}}", text)
        self.assertNotIn("C:/private", text)

    def test_checkpoint_shape_adapter_reports_resizable_position_embedding(self) -> None:
        module = load_template(ML / "method_templates" / "checkpoint_shape_adapter" / "template.py")
        fixture = json.loads((ML / "method_templates" / "checkpoint_shape_adapter" / "fixture_checkpoint_shapes.json").read_text(encoding="utf-8"))
        report = module.compare_checkpoint_shapes(fixture["checkpoint"], fixture["model"])
        self.assertEqual(len(report["resizable_position_embeddings"]), 1)
        self.assertEqual(module.expected_token_count(224, 16), 197)

    def test_embedding_health_template_writes_diagnostics(self) -> None:
        module = load_template(ML / "method_templates" / "embedding_extraction_health_diagnostics" / "template.py")
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "health.csv"
            result = module.compute_embedding_health(
                embedding_csv=ML / "method_templates" / "embedding_extraction_health_diagnostics" / "fixture_embeddings.csv",
                output_csv=output,
            )
            text = output.read_text(encoding="utf-8")
        self.assertEqual(result["sample_count"], 4.0)
        self.assertIn("active_dimensions", text)

    def test_few_label_probe_benchmark_aggregates_metrics(self) -> None:
        module = load_template(ML / "method_templates" / "few_label_probe_benchmark" / "template.py")
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "probe_summary.csv"
            result = module.aggregate_probe_results(
                raw_results_csv=ML / "method_templates" / "few_label_probe_benchmark" / "fixture_probe_results.csv",
                output_csv=output,
            )
            text = output.read_text(encoding="utf-8")
        self.assertEqual(result["group_count"], 4)
        self.assertIn("macro_f1_mean", text)

    def test_embedding_similarity_retrieval_writes_topk(self) -> None:
        module = load_template(ML / "method_templates" / "embedding_similarity_retrieval" / "template.py")
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "retrieval.csv"
            result = module.retrieve_similar_embeddings(
                embedding_csv=ML / "method_templates" / "embedding_similarity_retrieval" / "fixture_embeddings.csv",
                query_sample_id="a",
                output_csv=output,
                top_k=2,
            )
            text = output.read_text(encoding="utf-8")
        self.assertEqual(result["written_count"], 2)
        self.assertIn("cosine_similarity", text)

    def test_self_supervised_dino_training_template_writes_plan(self) -> None:
        module = load_template(ML / "method_templates" / "self_supervised_dino_training" / "template.py")
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "images.csv"
            manifest.write_text("sample_id,file_path\n1,a.fits\n", encoding="utf-8")
            output = Path(tmp) / "plan.json"
            result = module.build_dino_training_plan(dataset_manifest=manifest, output_json=output)
            text = output.read_text(encoding="utf-8")
        self.assertTrue(result["dataset_manifest_provided"])
        self.assertIn("embedding_health.csv", text)


if __name__ == "__main__":
    unittest.main()
