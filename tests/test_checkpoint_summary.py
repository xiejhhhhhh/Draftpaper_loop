from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

from draftpaper_cli.checkpoint_summary import validate_checkpoint_summary
from draftpaper_cli.orchestrator import (
    _is_confirmed_research_plan_packet_compatibility_case,
    checkpoint_project,
    resume_project,
)
from draftpaper_cli.project_scaffold import create_project


class CheckpointSummaryTests(unittest.TestCase):
    def test_checkpoint_writes_chinese_summary_and_agent_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Summary contract", field="astronomy")
            result = checkpoint_project(project.path, stage="idea", note="Review summary.")
            summary_dir = project.path / result["checkpoint_summary"]["project_relative_dir"]
            summary = json.loads((summary_dir / "stage_summary.json").read_text(encoding="utf-8"))

            self.assertTrue((summary_dir / "stage_summary.zh-CN.html").is_file())
            self.assertTrue((summary_dir / "artifact_manifest.json").is_file())
            self.assertTrue((summary_dir / "confirmation_request.json").is_file())
            self.assertIn("本阶段", (summary_dir / "stage_summary.zh-CN.html").read_text(encoding="utf-8"))
            for field in ("generated", "modified", "deployed", "validated", "failed", "unresolved"):
                self.assertIn(field, summary)
            self.assertTrue(result["stage_summary_zh_html"]["absolute_path"].endswith("stage_summary.zh-CN.html"))
            self.assertEqual(validate_checkpoint_summary(project.path, json.loads((project.path / "checkpoint_ledger.jsonl").read_text(encoding="utf-8").splitlines()[-1]))["valid"], True)

    def test_resume_rejects_changed_bound_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Summary invalidation", field="astronomy")
            checkpoint = checkpoint_project(project.path, stage="idea")
            (project.path / "idea" / "idea.md").write_text("# changed\n", encoding="utf-8")

            with self.assertRaises(Exception) as context:
                resume_project(project.path, checkpoint_hash=checkpoint["checkpoint_hash"])
            self.assertIn("Checkpoint summary is stale", str(context.exception))

    def test_status_and_read_only_command_expose_exact_summary_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Summary CLI", field="workflow engineering")
            checkpoint = checkpoint_project(project.path, stage="idea")
            status = subprocess.run(
                [sys.executable, "-m", "draftpaper_cli.cli", "status", "--project", str(project.path)],
                check=True,
                capture_output=True,
                text=True,
            )
            status_payload = json.loads(status.stdout)
            next_action = status_payload["next_action"]
            self.assertEqual(next_action["stage_summary_zh_html"]["project_relative_path"], checkpoint["stage_summary_zh_html"]["project_relative_path"])
            self.assertTrue(Path(next_action["stage_summary_zh_html"]["absolute_path"]).is_file())

            shown = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "draftpaper_cli.cli",
                    "show-checkpoint-summary",
                    "--project",
                    str(project.path),
                    "--checkpoint-hash",
                    checkpoint["checkpoint_hash"],
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(json.loads(shown.stdout)["status"], "ready_for_human_review")

    def test_missing_companion_or_tampered_summary_is_not_consumable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=Path(tmp) / "missing", idea="Summary companion", field="workflow engineering")
            checkpoint = checkpoint_project(project.path, stage="idea")
            summary_dir = project.path / checkpoint["checkpoint_summary"]["project_relative_dir"]
            (summary_dir / "stage_summary.zh-CN.html").unlink()
            shown = subprocess.run(
                [sys.executable, "-m", "draftpaper_cli.cli", "show-checkpoint-summary", "--project", str(project.path)],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(json.loads(shown.stdout)["status"], "not_found")

            tampered = create_project(root=Path(tmp) / "tampered", idea="Summary tampered", field="workflow engineering")
            checkpoint = checkpoint_project(tampered.path, stage="idea")
            summary_path = tampered.path / checkpoint["checkpoint_summary"]["stage_summary_json"]
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            summary["scientific_summary_zh"].append("未经 hash 更新的篡改")
            summary_path.write_text(json.dumps(summary, ensure_ascii=False), encoding="utf-8")
            with self.assertRaises(Exception) as context:
                from draftpaper_cli.orchestrator import resume_project

                resume_project(tampered.path, checkpoint_hash=checkpoint["checkpoint_hash"])
            self.assertIn("semantic hash", str(context.exception))

    def test_html_presentation_change_does_not_invalidate_scientific_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Summary presentation", field="workflow engineering")
            checkpoint = checkpoint_project(project.path, stage="idea")
            html_path = project.path / checkpoint["stage_summary_zh_html"]["project_relative_path"]
            html = html_path.read_text(encoding="utf-8")
            html_path.write_text(html.replace("<style>", "<style>body{background:#fff;}"), encoding="utf-8")
            from draftpaper_cli.orchestrator import resume_project

            result = resume_project(project.path, checkpoint_hash=checkpoint["checkpoint_hash"])
            self.assertEqual(result["status"], "resumed")

    def test_research_plan_packet_compatibility_requires_current_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Research plan compatibility", field="astronomy")
            packet = project.path / "research_plan" / "research_plan_review_packet.html"
            packet.parent.mkdir(parents=True, exist_ok=True)
            packet.write_text("<html>review packet</html>\n", encoding="utf-8")
            checkpoint = {
                "stage": "research_plan",
                "next_action": {"plan_hash": "confirmed-plan"},
            }
            reasons = ["Bound artifact is missing: research_plan/research_plan_review_packet.html"]
            with mock.patch(
                "draftpaper_cli.research_plan_confirmation.confirmation_state",
                return_value={"status": "confirmed", "current": True, "confirmed_plan_hash": "confirmed-plan"},
            ), mock.patch(
                "draftpaper_cli.research_plan_confirmation.current_plan_hash",
                return_value="confirmed-plan",
            ):
                self.assertTrue(_is_confirmed_research_plan_packet_compatibility_case(project.path, checkpoint, reasons))

            self.assertFalse(
                _is_confirmed_research_plan_packet_compatibility_case(
                    project.path,
                    checkpoint,
                    [*reasons, "Checkpoint summary hash changed."],
                )
            )

    def test_checkpoint_index_is_published_only_after_ledger_commit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Atomic checkpoint", field="workflow engineering")
            with mock.patch("draftpaper_cli.orchestrator.append_checkpoint_event", side_effect=RuntimeError("ledger unavailable")):
                with self.assertRaisesRegex(RuntimeError, "ledger unavailable"):
                    checkpoint_project(project.path, stage="idea")
            self.assertFalse((project.path / "review" / "checkpoints" / "index.json").exists())
            ledger = project.path / "checkpoint_ledger.jsonl"
            self.assertFalse(ledger.exists() and ledger.read_text(encoding="utf-8").strip())


if __name__ == "__main__":
    unittest.main()
