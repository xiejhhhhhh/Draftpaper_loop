from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from draftpaper_cli.project_scaffold import create_project
from draftpaper_cli.revision_cycle import begin_revision_cycle


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def prepare_formal_blueprint(project_path: Path) -> None:
    """Create the smallest complete, cross-domain plan contract for v0.42 tests."""

    figure = {
        "figure_id": "fig_primary",
        "proposed_title": "Group held out classification performance",
        "research_question": "Does the model generalize across held out groups?",
        "expected_finding": "Held out performance should be compared with a transparent baseline.",
        "scientific_claim_boundary": "Interpret only for the held-out cohort.",
        "required_data": ["feature_matrix", "class_label", "group_id"],
        "required_method": ["group_aware_classification", "baseline_comparison"],
        "validation_metric": "macro_f1_with_interval",
        "claim_id": "claim_primary",
        "panels": [{"panel_id": "fig_primary_panel_1", "label": "a"}],
    }
    storyboard = {"status": "written", "figures": [figure], "tables": []}
    blueprint = {
        "status": "written",
        "project_id": json.loads((project_path / "project.json").read_text(encoding="utf-8"))["project_id"],
        "research_objective": {
            "working_title": "Grouped classifier",
            "scientific_objective": "Evaluate generalization on held-out groups.",
        },
        "research_claims": [
            {
                "claim_id": "claim_primary",
                "research_question": figure["research_question"],
                "expected_finding": figure["expected_finding"],
                "scientific_claim_boundary": figure["scientific_claim_boundary"],
            }
        ],
        "figure_storyboard": storyboard,
        "method_plan": {
            "status": "written",
            "method_tasks": [
                {
                    "task_id": "method_1",
                    "figure_id": "fig_primary",
                    "method_family": "group_aware_classification",
                    "required_data": figure["required_data"],
                    "validation_metric": figure["validation_metric"],
                    "claim_id": "claim_primary",
                }
            ],
        },
    }
    for name, value in {
        "research_blueprint.json": blueprint,
        "claim_contract.json": {"status": "written", "claims": blueprint["research_claims"]},
        "figure_storyboard.json": storyboard,
        "method_plan.json": blueprint["method_plan"],
        "discipline_contract.json": {"status": "written", "primary_discipline": "machine_learning"},
        "research_capability_contract.json": {"status": "written", "requirements": []},
    }.items():
        _write_json(project_path / "research_plan" / name, value)
    (project_path / "research_plan" / "research_plan.md").write_text("# Research plan\n", encoding="utf-8")
    (project_path / "research_plan" / "research_plan.zh-CN.md").write_text("# 研究方案\n", encoding="utf-8")
    from draftpaper_cli.research_plan_confirmation import mark_research_plan_confirmation_required
    from draftpaper_cli.statistical_validation import build_statistical_validation_contract

    build_statistical_validation_contract(project_path, blueprint=blueprint)
    mark_research_plan_confirmation_required(project_path)


class ResearchPlanReviewPacketV042Tests(unittest.TestCase):
    def _project(self, root: Path):
        project = create_project(root=root, idea="Grouped classifier", field="machine learning")
        prepare_formal_blueprint(project.path)
        return project

    def test_complete_bilingual_packet_is_versioned_and_readable(self) -> None:
        from draftpaper_cli.research_plan_confirmation import review_research_plan

        with tempfile.TemporaryDirectory() as tmp:
            project = self._project(Path(tmp))
            result = review_research_plan(project.path)

            self.assertEqual(result["status"], "ready_for_human_review")
            zh = Path(result["primary_human_review_html"]["absolute_path"])
            en = Path(result["secondary_human_review_html"]["absolute_path"])
            packet_dir = zh.parent
            self.assertTrue(zh.is_file())
            self.assertTrue(en.is_file())
            self.assertIn("研究目标与问题", zh.read_text(encoding="utf-8"))
            self.assertIn("Claims and boundaries", en.read_text(encoding="utf-8"))
            self.assertIn('href="stage_audit.json"', zh.read_text(encoding="utf-8"))
            self.assertTrue((packet_dir / "human_decision_brief_v1.json").is_file())
            self.assertTrue((packet_dir / "scientific_plan_fingerprint_v1.json").is_file())
            self.assertTrue((packet_dir / "stage_audit.json").is_file())
            self.assertFalse((packet_dir / "stage_audit.zh-CN.html").exists())

            active = json.loads((project.path / "research_plan" / "active_review_packet.json").read_text(encoding="utf-8"))
            self.assertEqual(active["packet_id"], result["packet_id"])
            payload = json.loads((packet_dir / "agent_payload.json").read_text(encoding="utf-8"))
            self.assertLessEqual(len(json.dumps(payload, ensure_ascii=False).encode("utf-8")), 12 * 1024)

    def test_pending_revision_tasks_never_create_a_confirmation_packet(self) -> None:
        from draftpaper_cli.research_plan_confirmation import review_research_plan

        with tempfile.TemporaryDirectory() as tmp:
            project = self._project(Path(tmp))
            begin_revision_cycle(
                project.path,
                reason="complete methods before review",
                scope="research_plan",
                pending_tasks=[{"task": "Complete the method contract", "status": "pending"}],
            )

            result = review_research_plan(project.path)

            self.assertEqual(result["status"], "refinement_required")
            self.assertEqual(result["unresolved_items"][0]["code"], "revision_cycle_pending_tasks")
            self.assertFalse((project.path / "research_plan" / "active_review_packet.json").exists())

    def test_repeated_review_reuses_immutable_packet_and_scientific_change_creates_another(self) -> None:
        from draftpaper_cli.project_state import load_project
        from draftpaper_cli.research_plan_confirmation import (
            confirm_research_plan,
            reopen_research_plan,
            review_research_plan,
        )

        with tempfile.TemporaryDirectory() as tmp:
            project = self._project(Path(tmp))
            first = review_research_plan(project.path)
            packet = Path(first["primary_human_review_html"]["absolute_path"]).parent
            original_html = (packet / "stage_summary.zh-CN.html").read_bytes()

            repeated = review_research_plan(project.path)
            self.assertEqual(repeated["packet_id"], first["packet_id"])
            self.assertEqual((packet / "stage_summary.zh-CN.html").read_bytes(), original_html)

            confirmed = confirm_research_plan(project.path, decision_hash=first["decision_hash"], accept_limitations=True)
            self.assertEqual(confirmed["status"], "approved")
            research_stage = load_project(project.path).metadata["stages"]["research_plan"]
            self.assertEqual(research_stage["status"], "approved")
            self.assertFalse(research_stage["stale"])
            continuity = review_research_plan(project.path)
            self.assertEqual(continuity["status"], "continuity_preserved")
            self.assertEqual(continuity["packet_id"], first["packet_id"])
            self.assertFalse((packet / "confirmation_continuity_receipt.json").exists())

            reopen_research_plan(project.path, reason="The author corrected the primary claim boundary.")
            claim_path = project.path / "research_plan" / "claim_contract.json"
            claims = json.loads(claim_path.read_text(encoding="utf-8"))
            claims["claims"][0]["expected_finding"] = "A narrower, changed scientific claim."
            _write_json(claim_path, claims)

            changed = review_research_plan(project.path)
            self.assertEqual(changed["status"], "ready_for_human_review")
            self.assertNotEqual(changed["packet_id"], first["packet_id"])
            self.assertTrue(packet.is_dir())
            delta = json.loads(
                (Path(changed["primary_human_review_html"]["absolute_path"]).parent / "semantic_diff.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(delta["classification"], "scientific_change")

    def test_reopen_records_user_intent_without_deleting_the_reviewed_packet(self) -> None:
        from draftpaper_cli.research_plan_confirmation import (
            confirm_research_plan,
            reopen_research_plan,
            review_research_plan,
        )

        with tempfile.TemporaryDirectory() as tmp:
            project = self._project(Path(tmp))
            reviewed = review_research_plan(project.path)
            confirm_research_plan(project.path, decision_hash=reviewed["decision_hash"], accept_limitations=True)
            packet = Path(reviewed["primary_human_review_html"]["absolute_path"])

            reopened = reopen_research_plan(project.path, reason="The author requested one scoped scientific revision.")

            receipt = json.loads((project.path / reopened["user_intent_receipt"]).read_text(encoding="utf-8"))
            self.assertEqual(receipt["schema_version"], "dpl.user_intent_receipt.v1")
            self.assertEqual(receipt["intent"], "reopen_research_plan")
            self.assertTrue(packet.is_file())

    def test_migration_audit_never_promotes_or_rewrites_a_snapshot(self) -> None:
        from draftpaper_cli.research_plan_confirmation import (
            audit_research_plan_migration,
            confirm_research_plan,
            review_research_plan,
        )

        with tempfile.TemporaryDirectory() as tmp:
            project = self._project(Path(tmp))
            reviewed = review_research_plan(project.path)
            confirm_research_plan(project.path, decision_hash=reviewed["decision_hash"], accept_limitations=True)
            snapshot_path = project.path / "research_plan" / "confirmed_research_blueprint_snapshot.json"
            before = snapshot_path.read_bytes()

            current = audit_research_plan_migration(project.path)
            self.assertEqual(current["status"], "continuity_eligible")
            self.assertFalse(current["source_files_mutated"])
            self.assertTrue(current["source_snapshot_unchanged"])
            self.assertEqual(snapshot_path.read_bytes(), before)

            legacy = json.loads(snapshot_path.read_text(encoding="utf-8"))
            legacy["schema_version"] = "dpl.confirmed_research_blueprint_snapshot.v1"
            legacy.pop("scientific_plan_fingerprint", None)
            _write_json(snapshot_path, legacy)
            legacy_before = snapshot_path.read_bytes()
            audited_legacy = audit_research_plan_migration(project.path)
            self.assertEqual(audited_legacy["status"], "legacy_read_only")
            self.assertEqual(snapshot_path.read_bytes(), legacy_before)


if __name__ == "__main__":
    unittest.main()
