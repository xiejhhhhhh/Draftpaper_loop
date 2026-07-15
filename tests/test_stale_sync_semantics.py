# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import tempfile
import unittest
import json

from draftpaper_cli.passport import refresh_project_passport
from draftpaper_cli.project_scaffold import create_project
from draftpaper_cli.stale_sync import detect_artifact_drift, sync_artifact_stale


class SemanticStaleSyncTests(unittest.TestCase):
    def test_stage_manifest_updates_are_managed_state_not_artifact_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Managed stage state", field="workflow engineering")
            refresh_project_passport(project.path, event="test_stage_manifest_baseline")
            manifest_path = project.path / "results" / "stage_manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["status"] = "approved"
            manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

            report = detect_artifact_drift(project.path)

            self.assertEqual(report["status"], "clean")

    def test_managed_project_state_updates_are_not_scientific_artifact_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Managed state", field="workflow engineering")
            refresh_project_passport(project.path, event="test_managed_state_baseline")
            json_path = project.path / "project.json"
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            payload["current_stage"] = "references"
            json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            yaml_path = project.path / "project.yaml"
            yaml_path.write_text(yaml_path.read_text(encoding="utf-8") + "# managed state refresh\n", encoding="utf-8")

            report = detect_artifact_drift(project.path)

            self.assertEqual(report["status"], "clean")

    def test_bibliography_metadata_change_preserves_empirical_and_writing_stages(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Bibliography metadata", field="astronomy")
            bib = project.path / "references" / "library.bib"
            bib.write_text("@article{Key2026,\n title={Stable Work},\n doi={10.1234/stable},\n year={2026}\n}\n", encoding="utf-8")
            manifest_path = project.path / "references" / "stage_manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["output_files"] = ["references/library.bib"]
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            refresh_project_passport(project.path, event="test_bibliography_baseline")

            bib.write_text("@article{Key2026,\n title={Stable Work},\n doi={10.1234/stable},\n year={2026},\n volume={12},\n pages={44}\n}\n", encoding="utf-8")
            report = sync_artifact_stale(project.path)

            self.assertEqual(report["classified_changes"][0]["change_class"], "reference_metadata_only")
            self.assertNotIn("research_plan", report["stale_stages"])
            self.assertNotIn("data", report["stale_stages"])
            self.assertNotIn("methods", report["stale_stages"])
            self.assertNotIn("results", report["stale_stages"])

    def test_discussion_edit_does_not_stale_data_methods_or_results(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Stale propagation", field="astronomy")
            discussion = project.path / "discussion" / "discussion.tex"
            discussion.write_text("\\section{Discussion}\nOriginal.", encoding="utf-8")
            manifest_path = project.path / "discussion" / "stage_manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["output_files"] = ["discussion/discussion.tex"]
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            refresh_project_passport(project.path, event="test_baseline")

            discussion.write_text("\\section{Discussion}\nCitation wording repaired.", encoding="utf-8")
            report = sync_artifact_stale(project.path)

            self.assertEqual(
                report["stale_stages"],
                ["discussion", "latex", "quality_checks"],
            )

    def test_figure_change_stales_evidence_and_writing_but_not_data_or_method_code(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Figure replacement", field="astronomy")
            figure = project.path / "results" / "figures" / "main.png"
            figure.write_bytes(b"old")
            manifest_path = project.path / "results" / "stage_manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["output_files"] = ["results/figures/main.png"]
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            refresh_project_passport(project.path, event="test_baseline")

            figure.write_bytes(b"new")
            report = sync_artifact_stale(project.path)

            self.assertIn("result_validity", report["stale_stages"])
            self.assertIn("core_evidence", report["stale_stages"])
            self.assertIn("discussion", report["stale_stages"])
            self.assertNotIn("data", report["stale_stages"])
            self.assertNotIn("methods", report["stale_stages"])


if __name__ == "__main__":
    unittest.main()
