from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from draftpaper_cli.project_scaffold import create_project


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def prepare_formal_blueprint(project_path: Path) -> None:
    figure = {
        "figure_id": "fig_primary",
        "proposed_title": "Group held out classification performance",
        "research_question": "Does the model generalize across held out groups?",
        "expected_finding": "Held out performance should be compared with a transparent baseline.",
        "required_data": ["feature_matrix", "class_label", "group_id"],
        "required_method": ["group_aware_classification", "baseline_comparison"],
        "supporting_literature_keys": ["Ref2026"],
        "validation_metric": "macro_f1_with_interval",
        "claim_id": "claim_primary",
        "unique_evidence_contribution": "This is the only figure that tests cross-group generalization.",
        "why_not_table": "The group and model uncertainty pattern requires visual comparison.",
        "panels": [{"panel_id": "fig_primary_panel_1", "label": "a", "description": "Held-out model comparison", "expected_content": "Held-out model comparison", "required_method": "group_aware_classification", "required_data_roles": ["feature_matrix", "class_label", "group_id"]}],
        "panel_contract": [{"panel_id": "fig_primary_panel_1", "label": "a", "description": "Held-out model comparison", "expected_content": "Held-out model comparison", "required_method": "group_aware_classification", "required_data_roles": ["feature_matrix", "class_label", "group_id"]}],
        "statistical_validation_ids": ["stat_01_sampling_and_independence"],
        "caption_contract": {
            "headline": "This figure establishes group held out classification performance.",
            "panels": [{"label": "a", "description": "Held-out model comparison", "panel_id": "fig_primary_panel_1"}],
            "statistics": "Report sample unit and uncertainty interval.",
            "claim_boundary": "Interpret only for the held-out cohort.",
        },
    }
    storyboard = {"status": "written", "figures": [figure], "tables": []}
    blueprint = {
        "status": "written",
        "project_id": json.loads((project_path / "project.json").read_text(encoding="utf-8"))["project_id"],
        "research_claims": [{"claim_id": "claim_primary", "research_question": figure["research_question"], "expected_finding": figure["expected_finding"]}],
        "figure_storyboard": storyboard,
        "method_plan": {"status": "written", "method_tasks": [{"task_id": "method_1", "figure_id": "fig_primary", "method_family": "group_aware_classification", "required_data": figure["required_data"], "validation_metric": figure["validation_metric"], "claim_id": "claim_primary"}]},
    }
    for name, value in {
        "research_blueprint.json": blueprint,
        "claim_contract.json": {"status": "written", "claims": blueprint["research_claims"]},
        "figure_storyboard.json": storyboard,
        "method_plan.json": blueprint["method_plan"],
        "discipline_contract.json": {"status": "written", "primary_discipline": "machine_learning", "secondary_disciplines": []},
        "research_capability_contract.json": {"status": "written", "requirements": []},
    }.items():
        _write_json(project_path / "research_plan" / name, value)
    (project_path / "research_plan" / "research_plan.md").write_text("# Research plan\n\nConfirmed group-aware design.\n", encoding="utf-8")
    (project_path / "research_plan" / "research_plan.zh-CN.md").write_text("# 研究方案\n\n采用分组留出验证并比较透明基线。\n", encoding="utf-8")
    from draftpaper_cli.statistical_validation import build_statistical_validation_contract
    from draftpaper_cli.research_plan_confirmation import mark_research_plan_confirmation_required

    build_statistical_validation_contract(project_path, blueprint=blueprint)
    mark_research_plan_confirmation_required(project_path)


class WorkspaceAndBlueprintV026Tests(unittest.TestCase):
    def test_default_projects_root_short_slug_and_path_budget(self) -> None:
        from draftpaper_cli.workspace_policy import require_path_budget

        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"DRAFTPAPER_PROJECTS_ROOT": tmp}):
            project = create_project(
                idea="An intentionally very long research title that would otherwise exceed practical Windows path limits for generated paper artifacts",
                field="astronomy machine learning",
            )
            self.assertEqual(project.path.parent, Path(tmp).resolve())
            self.assertLessEqual(len(project.project_slug), 48)
            self.assertRegex(project.project_slug, r"_[0-9a-f]{8}$")
            workspace = json.loads((project.path / "project_workspace.json").read_text(encoding="utf-8"))
            self.assertEqual(workspace["artifact_policy"], "all_managed_outputs_remain_inside_project_except_explicit_export")
            self.assertEqual(require_path_budget(project.path)["status"], "passed")

    def test_artifact_ownership_guard_rejects_escape(self) -> None:
        from draftpaper_cli.workspace_policy import ArtifactOwnershipGuard, WorkspacePolicyError

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Boundary", field="statistics")
            guard = ArtifactOwnershipGuard(project.path)
            self.assertEqual(guard.output("results/report.json"), project.path / "results" / "report.json")
            with self.assertRaises(WorkspacePolicyError):
                guard.output(project.path.parent / "orphan.json")

    def test_large_external_data_is_inventoried_in_place(self) -> None:
        from draftpaper_cli.data_acquisition import prepare_data_acquisition

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "large_dataset"
            source.mkdir()
            (source / "catalog.csv").write_text("id,label\n1,a\n", encoding="utf-8")
            (source / "large.bin").write_bytes(b"0" * 1024)
            project = create_project(root=root / "projects", idea="External data", field="astronomy")
            prepare_data_acquisition(project.path, source_root=source)
            contract = json.loads((project.path / "data" / "data_source_contract.json").read_text(encoding="utf-8"))
            public = json.loads((project.path / "data" / "external_data_locators.json").read_text(encoding="utf-8"))
            private = json.loads((project.path / "data" / "external_data_locators.private.json").read_text(encoding="utf-8"))
            self.assertEqual(contract["sources"][0]["copy_policy"], "manifest_only")
            self.assertNotIn(str(source), json.dumps(public))
            self.assertEqual(private["source_root"], str(source.resolve()))
            self.assertFalse((project.path / "data" / "raw" / "catalog.csv").exists())

    def test_confirmation_snapshot_detects_drift_and_requires_reopen(self) -> None:
        from draftpaper_cli.research_plan_confirmation import (
            ResearchPlanConfirmationError,
            confirm_research_plan,
            confirmation_state,
            reopen_research_plan,
            require_confirmed_research_blueprint,
            review_research_plan,
        )

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Grouped classifier", field="machine learning")
            prepare_formal_blueprint(project.path)
            review = review_research_plan(project.path)
            confirmed = confirm_research_plan(project.path, plan_hash=review["plan_hash"], accept_limitations=True)
            self.assertEqual(confirmed["status"], "approved")
            self.assertTrue(confirmation_state(project.path)["current"])
            claim_path = project.path / "research_plan" / "claim_contract.json"
            payload = json.loads(claim_path.read_text(encoding="utf-8"))
            payload["claims"][0]["expected_finding"] = "A changed scientific claim."
            _write_json(claim_path, payload)
            self.assertEqual(confirmation_state(project.path)["status"], "scientific_contract_drift")
            with self.assertRaises(ResearchPlanConfirmationError):
                require_confirmed_research_blueprint(project.path)
            reopened = reopen_research_plan(project.path, reason="User corrected the claim boundary.")
            self.assertEqual(reopened["status"], "reopened")
            self.assertTrue((project.path / reopened["history_snapshot"]).exists())

    def test_key_figure_codegen_is_rejected_before_human_confirmation(self) -> None:
        from draftpaper_cli.analysis_code import AnalysisCodeGenerationError, generate_analysis_code

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Strict blueprint", field="machine learning")
            prepare_formal_blueprint(project.path)
            with self.assertRaisesRegex(AnalysisCodeGenerationError, "human-confirmed research blueprint"):
                generate_analysis_code(project.path)


if __name__ == "__main__":
    unittest.main()
