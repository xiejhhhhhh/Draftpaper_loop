# Copyright (c) 2026 Jinray Xie

from __future__ import annotations

import json
import tempfile
import unittest

from draftpaper_cli.paper_narrative import build_paper_narrative, build_results_synthesis_plan
from draftpaper_cli.project_scaffold import create_project
from draftpaper_cli.writing_architecture import (
    assess_functional_quality_release,
    build_argument_matrices,
    build_panel_writing_contracts,
    build_section_lifecycles,
    prepare_panel_repair,
    prepare_scientific_editor,
    record_scientific_editor_revision,
    resolve_venue_style_adapter,
)


class PaperNarrativeArchitectureTests(unittest.TestCase):
    def _project(self, root: str):
        project = create_project(root=root, idea="Cross-disciplinary evidence study", field="geography machine learning")
        (project.path / "results" / "figures").mkdir(parents=True, exist_ok=True)
        (project.path / "results" / "result_manifest.yaml").write_text(
            """main_figures:
  - id: main-performance
    path: results/figures/main.png
    figure_group_id: performance-story
    scientific_question: Does the proposed analysis improve the held-out comparison?
    result_claim: The approved comparison supports a bounded improvement.
    evidence_ids: [metric-main]
    run_id: run-main
appendix_figures:
  - id: robustness-panel
    path: results/figures/robustness.png
    parent_figure_group: performance-story
    manuscript_role: appendix
    result_claim: The diagnostic constrains the stability boundary.
tables: []
""",
            encoding="utf-8",
        )
        (project.path / "results" / "figure_plan.json").write_text(
            json.dumps({
                "figure_groups": [{
                    "id": "performance-story",
                    "scientific_question": "Does the proposed analysis improve the held-out comparison?",
                    "claim_boundary": "Interpret only within the held-out cohort.",
                    "panels": [{
                        "id": "main-performance",
                        "data_roles": ["held_out_predictions"],
                        "method_outputs": ["validated_scores"],
                        "visual_grammar": "comparison plot",
                    }],
                    "supporting_figures": [{"id": "robustness-panel", "manuscript_role": "appendix"}],
                }]
            }),
            encoding="utf-8",
        )
        (project.path / "results" / "resolved_result_evidence.json").write_text(
            json.dumps({"metrics": [{"evidence_id": "metric-main", "run_id": "run-main", "metric_name": "score", "value": 0.81}]}),
            encoding="utf-8",
        )
        (project.path / "writing" / "scientific_evidence_registry.json").write_text(
            json.dumps({"records": [{"evidence_id": "metric-main", "entity_role": "result_metric", "value": 0.81, "run_id": "run-main", "target_sections": ["results", "discussion"]}]}),
            encoding="utf-8",
        )
        ref_dir = project.path / "references" / "literature_summaries"
        ref_dir.mkdir(parents=True, exist_ok=True)
        (ref_dir / "prior.json").write_text(json.dumps({"citation_key": "Prior2025", "title": "Prior study", "summary": "Prior work established a related baseline under a different cohort."}), encoding="utf-8")
        return project

    def test_true_yaml_and_main_appendix_story_group_are_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = self._project(tmp)
            narrative = build_paper_narrative(project.path)
            groups = narrative["figure_story_arc"]["figure_groups"]
            self.assertEqual(len(groups), 1)
            self.assertEqual(groups[0]["main_artifact_ids"], ["main-performance"])
            self.assertEqual(groups[0]["supporting_artifact_ids"], ["robustness-panel"])
            self.assertIn("metric-main", groups[0]["evidence_ids"])

    def test_results_metrics_require_explicit_binding(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = self._project(tmp)
            plan = build_results_synthesis_plan(project.path)
            block = plan["finding_blocks"][0]
            self.assertEqual(block["metric_evidence"][0]["value"], 0.81)
            self.assertIn("robustness-panel", block["supporting_evidence"])

    def test_reasoning_lifecycle_panel_style_and_editor_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = self._project(tmp)
            matrices = build_argument_matrices(project.path)
            lifecycles = build_section_lifecycles(project.path)
            panels = build_panel_writing_contracts(project.path)
            style = resolve_venue_style_adapter(project.path)
            candidate = project.path / "candidate.tex"
            candidate.write_text("\\section{Results}\n\nA short result paragraph.", encoding="utf-8")
            editor = prepare_scientific_editor(project.path, "results", candidate)
            repair = prepare_panel_repair(project.path)
            revised = project.path / "candidate_revised.tex"
            revised.write_text("\\section{Results}\n\nA short result paragraph with an observed pattern.", encoding="utf-8")
            revision = record_scientific_editor_revision(project.path, "results", candidate, revised, 1)
            self.assertTrue(matrices["discussion_finding_comparison_matrix"])
            self.assertEqual(lifecycles["schema_version"], "v0.21.6")
            self.assertEqual(panels["figure_groups"][0]["panels"][0]["repair_scope"], "this_panel_only")
            self.assertIn("panel_question", panels["figure_groups"][0]["panels"][0]["contract"])
            self.assertTrue((project.path / "writing" / "venue_writing_contract.json").exists())
            self.assertTrue((project.path / "writing" / "style_function_profile.json").exists())
            self.assertIn("forbidden_learning", style)
            self.assertEqual(editor["max_iterations"], 3)
            self.assertEqual(revision["iteration"], 1)
            self.assertTrue(repair["tasks"])

    def test_release_rejects_missing_free_prose_sections(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = self._project(tmp)
            build_paper_narrative(project.path)
            build_argument_matrices(project.path)
            build_section_lifecycles(project.path)
            build_panel_writing_contracts(project.path)
            resolve_venue_style_adapter(project.path)
            report = assess_functional_quality_release(project.path)
            self.assertEqual(report["decision"], "blocked")
            self.assertLess(report["functional_quality_score"], 0.95)


if __name__ == "__main__":
    unittest.main()