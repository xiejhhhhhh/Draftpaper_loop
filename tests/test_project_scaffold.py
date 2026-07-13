# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class ProjectScaffoldTests(unittest.TestCase):
    def test_create_project_writes_expected_directory_model(self) -> None:
        from draftpaper_cli.project_scaffold import create_project

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = create_project(
                root=root,
                idea="Long-term AGN outburst prediction using multimodal survey data",
                field="machine learning astronomy",
                target_journal="General Academic Journal",
            )

            self.assertRegex(project.project_slug, r"^long-term-agn-outburst-prediction-using_[0-9a-f]{8}$")
            self.assertLessEqual(len(project.project_slug), 48)
            self.assertTrue(project.path.exists())
            expected_dirs = [
                "idea",
                "research_plan",
                "research_feasibility",
                "research_plan_feasibility",
                "references",
                "journal_profile",
                "introduction",
                "data/acquisition",
                "data/raw",
                "data/processed",
                "data/scripts",
                "method_plan",
                "method_feasibility",
                "figure_plan",
                "figure_contracts",
                "methods",
                "methods/scripts",
                "methods/src",
                "code/shared",
                "code/src",
                "code/scripts",
                "code/tests",
                "result_validity",
                "result_support",
                "core_evidence",
                "results/figures",
                "results/tables",
                "data_writing",
                "methods_writing",
                "discussion",
                "latex/sections",
                "latex/template",
                "integrity",
                "review",
                "quality_checks",
            ]
            for relative in expected_dirs:
                self.assertTrue((project.path / relative).is_dir(), relative)

            metadata = json.loads((project.path / "project.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["idea"], "Long-term AGN outburst prediction using multimodal survey data")
            self.assertEqual(metadata["field"], "machine learning astronomy")
            self.assertEqual(metadata["target_journal"], "General Academic Journal")
            self.assertEqual(metadata["current_stage"], "idea")
            self.assertEqual(metadata["stages"]["research_plan"]["status"], "pending")
            self.assertEqual(metadata["stages"]["references"]["status"], "pending")
            self.assertEqual(metadata["stages"]["journal_profile"]["depends_on"], ["idea"])
            self.assertEqual(metadata["stages"]["research_feasibility"]["depends_on"], ["references", "journal_profile"])
            self.assertEqual(metadata["stages"]["research_plan"]["depends_on"], ["research_feasibility"])
            self.assertEqual(metadata["stages"]["research_plan_feasibility"]["depends_on"], ["research_plan"])
            self.assertEqual(metadata["stages"]["method_plan"]["depends_on"], ["research_plan_feasibility", "references", "data"])
            self.assertEqual(metadata["stages"]["method_feasibility"]["depends_on"], ["method_plan", "data"])
            self.assertEqual(metadata["stages"]["figure_plan"]["depends_on"], ["method_feasibility", "data", "references", "journal_profile"])
            self.assertEqual(metadata["stages"]["figure_contracts"]["depends_on"], ["figure_plan", "method_feasibility", "data"])
            self.assertEqual(metadata["stages"]["code"]["depends_on"], ["figure_contracts", "method_plan", "data", "references"])
            self.assertEqual(
                metadata["stages"]["result_support"]["depends_on"],
                ["result_validity", "research_plan", "figure_plan", "methods", "data"],
            )
            self.assertEqual(metadata["stages"]["core_evidence"]["depends_on"], ["result_support", "figure_plan", "methods", "data"])
            self.assertEqual(metadata["stages"]["results"]["depends_on"], ["core_evidence"])
            self.assertEqual(metadata["stages"]["introduction"]["depends_on"], ["research_plan", "references", "journal_profile", "core_evidence"])
            self.assertEqual(metadata["stages"]["data_writing"]["depends_on"], ["data", "results", "core_evidence"])
            self.assertEqual(metadata["stages"]["methods_writing"]["depends_on"], ["method_plan", "methods", "results", "core_evidence"])
            self.assertEqual(metadata["dpl"]["schema_family"], "dpl")
            self.assertEqual(metadata["dpl"]["project_schema"], "dpl.project.v1")
            self.assertEqual(metadata["dpl"]["stage_manifest_schema"], "dpl.stage_manifest.v1")
            self.assertEqual(metadata["generated_by"]["name"], "Draftpaper-loop")
            self.assertEqual(metadata["generated_by"]["schema_family"], "dpl")
            self.assertIn("does not grant commercial use rights", metadata["generated_by"]["sponsorship_note"])
            serialized_metadata = json.dumps(metadata, ensure_ascii=False)
            self.assertNotIn("D:\\DraftAI_agent", serialized_metadata)
            self.assertNotIn("source_mvp", metadata)
            self.assertEqual(metadata["legacy_mvp_reference"], "legacy MVP design notes")

            references_manifest = json.loads((project.path / "references" / "stage_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(references_manifest["dpl"]["schema_family"], "dpl")
            self.assertEqual(references_manifest["dpl"]["stage_manifest_schema"], "dpl.stage_manifest.v1")
            self.assertEqual(references_manifest["generated_by"]["name"], "Draftpaper-loop")

            idea_note = (project.path / "idea" / "idea.md").read_text(encoding="utf-8")
            self.assertIn("Long-term AGN outburst prediction", idea_note)
            self.assertIn("machine learning astronomy", idea_note)

    def test_existing_project_is_not_overwritten_without_flag(self) -> None:
        from draftpaper_cli.project_scaffold import ProjectAlreadyExistsError, create_project

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_project(root=root, idea="Reusable project", field="test field")

            with self.assertRaises(ProjectAlreadyExistsError):
                create_project(root=root, idea="Reusable project", field="test field")

    def test_cli_create_project_outputs_project_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            command = [
                sys.executable,
                "-m",
                "draftpaper_cli.cli",
                "create-project",
                "--root",
                tmp,
                "--allow-external-project-root",
                "--idea",
                "Multimodal crop disease early warning",
                "--field",
                "precision agriculture",
            ]
            completed = subprocess.run(command, check=True, capture_output=True, text=True)

            payload = json.loads(completed.stdout)
            self.assertEqual(payload["status"], "created")
            self.assertTrue(Path(payload["project_path"]).exists())
            self.assertTrue((Path(payload["project_path"]) / "project.json").exists())


if __name__ == "__main__":
    unittest.main()
