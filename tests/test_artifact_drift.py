# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from draftpaper_cli.project_scaffold import create_project
from draftpaper_cli.project_state import load_project

from tests.test_orchestrator_passport import read_jsonl


class ArtifactDriftTests(unittest.TestCase):
    def test_status_reports_drift_before_refreshing_passport(self) -> None:
        from draftpaper_cli.orchestrator import status_project

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Artifact drift", field="workflow engineering")
            (project.path / "idea" / "idea.md").write_text("# Research Idea\n\nChanged by user.\n", encoding="utf-8")

            status = status_project(project.path)

            self.assertEqual(status["pipeline_state"], "drift_detected")
            self.assertEqual(status["next_action"]["command"], "sync-artifact-stale")
            self.assertIn("idea/idea.md", {item["path"] for item in status["drift"]["changed_artifacts"]})

    def test_sync_artifact_stale_requires_reconciliation_before_refreshing_passport(self) -> None:
        from draftpaper_cli.orchestrator import status_project
        from draftpaper_cli.stale_sync import reconcile_project_drift, sync_artifact_stale

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Artifact sync", field="workflow engineering")
            (project.path / "idea" / "idea.md").write_text("# Research Idea\n\nChanged by user.\n", encoding="utf-8")

            result = sync_artifact_stale(project.path)

            self.assertEqual(result["status"], "reconciliation_required")
            self.assertFalse(result["passport_refreshed"])
            self.assertIn("references", result["stale_stages"])
            self.assertIn("research_plan", result["stale_stages"])
            state = load_project(project.path)
            self.assertTrue(state.metadata["stages"]["references"]["stale"])
            self.assertTrue(state.metadata["stages"]["research_plan"]["stale"])

            events = read_jsonl(project.path / "integrity_ledger.jsonl")
            self.assertTrue(any(event["kind"] == "artifact_drift" for event in events))

            status = status_project(project.path)
            self.assertEqual(status["pipeline_state"], "drift_detected")

            resolution = reconcile_project_drift(
                project.path,
                route="reopen_scientific_stage",
                reconciliation_id=result["reconciliation_id"],
            )
            self.assertEqual(resolution["status"], "reopen_required")
            status = status_project(project.path)
            self.assertEqual(status["pipeline_state"], "ready")
            self.assertEqual(status["next_action"]["stage"], "references")

    def test_cli_detect_and_sync_artifact_stale(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="CLI drift", field="workflow engineering")
            (project.path / "idea" / "idea.md").write_text("# Research Idea\n\nChanged by user.\n", encoding="utf-8")

            detect_completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "draftpaper_cli.cli",
                    "detect-artifact-drift",
                    "--project",
                    str(project.path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            detect_payload = json.loads(detect_completed.stdout)
            self.assertEqual(detect_payload["status"], "drift_detected")

            sync_completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "draftpaper_cli.cli",
                    "sync-artifact-stale",
                    "--project",
                    str(project.path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            sync_payload = json.loads(sync_completed.stdout)
            self.assertEqual(sync_payload["status"], "reconciliation_required")
            self.assertFalse(sync_payload["passport_refreshed"])
            self.assertIn("references", sync_payload["stale_stages"])

            status_completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "draftpaper_cli.cli",
                    "status",
                    "--project",
                    str(project.path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            status_payload = json.loads(status_completed.stdout)
            self.assertEqual(status_payload["pipeline_state"], "drift_detected")

    def test_semantic_drift_cannot_be_adopted_or_rebuilt_without_a_scoped_revision(self) -> None:
        from draftpaper_cli.revision_cycle import begin_revision_cycle
        from draftpaper_cli.stale_sync import ArtifactDriftError, reconcile_project_drift, sync_artifact_stale

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Reconciliation routes", field="workflow engineering")
            (project.path / "idea" / "idea.md").write_text("# Research Idea\n\nChanged by user.\n", encoding="utf-8")
            result = sync_artifact_stale(project.path)

            with self.assertRaisesRegex(ArtifactDriftError, "Derived-artifact rebuild"):
                reconcile_project_drift(
                    project.path,
                    route="rebuild_derived_artifacts",
                    reconciliation_id=result["reconciliation_id"],
                )
            with self.assertRaisesRegex(ArtifactDriftError, "open revision cycle"):
                reconcile_project_drift(
                    project.path,
                    route="adopt_as_expected_change",
                    reconciliation_id=result["reconciliation_id"],
                )

            begin_revision_cycle(
                project.path,
                reason="review_round",
                allowed_change_classes=["prose_only"],
            )
            with self.assertRaisesRegex(ArtifactDriftError, "outside the active revision-cycle"):
                reconcile_project_drift(
                    project.path,
                    route="adopt_as_expected_change",
                    reconciliation_id=result["reconciliation_id"],
                )

    def test_successful_mutating_cli_command_refreshes_its_own_passport(self) -> None:
        from draftpaper_cli.orchestrator import status_project

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="CLI transaction", field="workflow engineering")

            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "draftpaper_cli.cli",
                    "update-stage-status",
                    "--project",
                    str(project.path),
                    "--stage",
                    "references",
                    "--status",
                    "draft",
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(status_project(project.path)["pipeline_state"], "drift_detected")

    def test_unknown_changed_artifact_is_isolated_without_reopening_research_plan(self) -> None:
        from draftpaper_cli.stale_sync import detect_artifact_drift

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Unknown drift", field="workflow engineering")
            previous = {"byte_sha256": "old", "semantic_sha256": "old-semantic"}
            current = {"byte_sha256": "new", "semantic_sha256": "new-semantic"}
            with mock.patch("draftpaper_cli.stale_sync._artifact_maps", return_value=({"review/unregistered.bin": previous}, {"review/unregistered.bin": current})):
                drift = detect_artifact_drift(project.path)
            assert drift["changed_artifacts"][0]["drift_kind"] == "unresolved_artifact"
            assert drift["source_stages"] == []


if __name__ == "__main__":
    unittest.main()
