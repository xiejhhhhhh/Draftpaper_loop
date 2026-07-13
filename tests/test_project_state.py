# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from draftpaper_cli.project_scaffold import create_project


class ProjectStateTests(unittest.TestCase):
    def test_load_project_reads_metadata_and_path(self) -> None:
        from draftpaper_cli.project_state import load_project

        with tempfile.TemporaryDirectory() as tmp:
            created = create_project(root=tmp, idea="Reusable stage model", field="workflow engineering")
            state = load_project(created.path)

            self.assertEqual(state.path, created.path)
            self.assertEqual(state.metadata["project_id"], created.project_id)
            self.assertRegex(state.metadata["project_id"], r"^[0-9a-f]{8}$")
            self.assertEqual(state.stage_names[0], "idea")
            self.assertIn("results", state.stage_names)

    def test_validate_project_reports_missing_manifest(self) -> None:
        from draftpaper_cli.project_state import validate_project

        with tempfile.TemporaryDirectory() as tmp:
            created = create_project(root=tmp, idea="Validation test", field="workflow engineering")
            (created.path / "results" / "stage_manifest.json").unlink()

            report = validate_project(created.path)

            self.assertEqual(report["status"], "failed")
            self.assertIn("missing_stage_manifest", {issue["code"] for issue in report["issues"]})

    def test_update_stage_status_writes_project_and_manifest(self) -> None:
        from draftpaper_cli.project_state import load_project, update_stage_status

        with tempfile.TemporaryDirectory() as tmp:
            created = create_project(root=tmp, idea="Status update test", field="workflow engineering")
            update_stage_status(created.path, "research_plan", "approved")
            state = load_project(created.path)
            manifest = json.loads((created.path / "research_plan" / "stage_manifest.json").read_text(encoding="utf-8"))

            self.assertEqual(state.metadata["current_stage"], "research_plan")
            self.assertEqual(state.metadata["stages"]["research_plan"]["status"], "approved")
            self.assertFalse(state.metadata["stages"]["research_plan"]["stale"])
            self.assertEqual(manifest["status"], "approved")
            self.assertFalse(manifest["stale"])
            self.assertTrue(manifest["last_updated"])

    def test_mark_stage_stale_propagates_to_transitive_dependents(self) -> None:
        from draftpaper_cli.project_state import load_project, mark_stage_stale, update_stage_status

        with tempfile.TemporaryDirectory() as tmp:
            created = create_project(root=tmp, idea="Dependency stale test", field="workflow engineering")
            for stage in ["research_plan", "references", "introduction", "methods", "results", "discussion", "latex"]:
                update_stage_status(created.path, stage, "approved")

            changed = mark_stage_stale(created.path, "research_plan")
            state = load_project(created.path)

            self.assertNotIn("research_plan", changed)
            self.assertNotIn("references", changed)
            self.assertIn("introduction", changed)
            self.assertIn("methods", changed)
            self.assertIn("results", changed)
            self.assertIn("discussion", changed)
            self.assertIn("latex", changed)
            self.assertTrue(state.metadata["stages"]["results"]["stale"])
            self.assertEqual(state.metadata["stages"]["results"]["status"], "stale")

    def test_references_change_marks_research_plan_and_downstream_stale(self) -> None:
        from draftpaper_cli.project_state import load_project, mark_stage_stale, update_stage_status

        with tempfile.TemporaryDirectory() as tmp:
            created = create_project(root=tmp, idea="Literature first test", field="workflow engineering")
            for stage in ["references", "research_plan", "introduction", "methods", "results", "discussion", "latex"]:
                update_stage_status(created.path, stage, "approved")

            changed = mark_stage_stale(created.path, "references")
            state = load_project(created.path)

            self.assertIn("research_plan", changed)
            self.assertIn("introduction", changed)
            self.assertIn("discussion", changed)
            self.assertIn("latex", changed)
            self.assertEqual(state.metadata["stages"]["research_plan"]["status"], "stale")

    def test_cli_update_and_validate_project(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            created = create_project(root=tmp, idea="CLI state test", field="workflow engineering")
            update_command = [
                sys.executable,
                "-m",
                "draftpaper_cli.cli",
                "update-stage-status",
                "--project",
                str(created.path),
                "--stage",
                "research_plan",
                "--status",
                "approved",
            ]
            update_completed = subprocess.run(update_command, check=True, capture_output=True, text=True)
            update_payload = json.loads(update_completed.stdout)
            self.assertEqual(update_payload["status"], "updated")
            self.assertEqual(update_payload["stage"], "research_plan")

            validate_command = [
                sys.executable,
                "-m",
                "draftpaper_cli.cli",
                "validate-project",
                "--project",
                str(created.path),
            ]
            validate_completed = subprocess.run(validate_command, check=True, capture_output=True, text=True)
            validate_payload = json.loads(validate_completed.stdout)
            self.assertEqual(validate_payload["status"], "passed")

    def test_cli_update_stage_status_draft_returns_project_state_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            created = create_project(root=tmp, idea="CLI draft state test", field="workflow engineering")
            update_completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "draftpaper_cli.cli",
                    "update-stage-status",
                    "--project",
                    str(created.path),
                    "--stage",
                    "data",
                    "--status",
                    "draft",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            payload = json.loads(update_completed.stdout)
            self.assertEqual(payload["status"], "updated")
            self.assertEqual(payload["stage"], "data")
            self.assertEqual(payload["stage_status"], "draft")

    def test_old_project_load_is_read_only_and_migration_is_explicit(self) -> None:
        from draftpaper_cli.project_state import inspect_project_migration, load_project, migrate_project

        with tempfile.TemporaryDirectory() as tmp:
            created = create_project(root=tmp, idea="Explicit migration", field="workflow engineering")
            project_json = created.path / "project.json"
            metadata = json.loads(project_json.read_text(encoding="utf-8"))
            metadata["stages"].pop("result_support")
            project_json.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
            shutil.rmtree(created.path / "result_support")
            before = hashlib.sha256(project_json.read_bytes()).hexdigest()

            state = load_project(created.path)
            plan = inspect_project_migration(created.path)

            self.assertNotIn("result_support", state.metadata["stages"])
            self.assertEqual(hashlib.sha256(project_json.read_bytes()).hexdigest(), before)
            self.assertFalse((created.path / "result_support").exists())
            self.assertEqual(plan["status"], "migration_required")
            self.assertIn("result_support", plan["missing_stages"])

            migrated = migrate_project(created.path)
            self.assertEqual(migrated["status"], "migrated")
            self.assertIn("result_support", load_project(created.path).metadata["stages"])
            self.assertTrue((created.path / "result_support").is_dir())


if __name__ == "__main__":
    unittest.main()
