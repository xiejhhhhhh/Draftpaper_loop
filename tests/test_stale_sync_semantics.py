# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import tempfile
import unittest
import json

from draftpaper_cli.passport import refresh_project_passport
from draftpaper_cli.project_scaffold import create_project
from draftpaper_cli.stale_sync import sync_artifact_stale


class SemanticStaleSyncTests(unittest.TestCase):
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
