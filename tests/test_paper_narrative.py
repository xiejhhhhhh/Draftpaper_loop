# Copyright (c) 2026 Jinray Xie

from __future__ import annotations

import json
import tempfile
import unittest

from draftpaper_cli.paper_narrative import _paragraph_blueprint, build_paper_narrative, build_results_synthesis_plan, build_section_outline
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
            introduction_claim = narrative["section_claim_allocation"]["sections"]["introduction"][0]
            self.assertEqual(introduction_claim["claim"], groups[0]["scientific_question"])
            self.assertIn("do not reveal observed results", introduction_claim["claim_boundary"].lower())

    def test_results_metrics_require_explicit_binding(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = self._project(tmp)
            plan = build_results_synthesis_plan(project.path)
            block = plan["finding_blocks"][0]
            self.assertEqual(block["metric_evidence"][0]["value"], 0.81)
            self.assertIn("robustness-panel", block["supporting_evidence"])

    def test_unlinked_result_tables_do_not_become_synthetic_findings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = self._project(tmp)
            manifest_path = project.path / "results" / "result_manifest.yaml"
            manifest = manifest_path.read_text(encoding="utf-8")
            manifest = manifest.replace(
                "tables: []",
                """tables:
  - id: fold-metrics
    path: results/tables/fold_metrics.csv
    table_role: result_table
    result_claim: Quantitative support for the main comparison.
  - id: internal-metrics
    path: results/tables/metrics.csv
    table_role: internal
""",
            )
            manifest_path.write_text(manifest, encoding="utf-8")

            narrative = build_paper_narrative(project.path)
            groups = narrative["figure_story_arc"]["figure_groups"]

            self.assertEqual(len(groups), 1)
            self.assertEqual(groups[0]["story_id"], "performance-story")


    def test_reference_items_support_consolidated_literature_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = self._project(tmp)
            (project.path / "references" / "literature_items.json").write_text(
                json.dumps([{
                    "bibtex_key": "Current2026",
                    "title": "Current evidence",
                    "abstract": "A structured abstract supports the introduction.",
                    "search_contexts": ["introduction"],
                }]),
                encoding="utf-8",
            )
            narrative = build_paper_narrative(project.path)
            self.assertEqual(narrative["paper_brief"]["reference_count"], 2)

    def test_discussion_outline_distributes_allocated_evidence_instead_of_repeating_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = self._project(tmp)
            records = [
                {
                    "evidence_id": f"metric-{index}",
                    "entity_role": "result_metric",
                    "value": index / 10,
                    "run_id": "run-main",
                    "target_sections": ["discussion"],
                }
                for index in range(1, 10)
            ]
            (project.path / "writing" / "scientific_evidence_registry.json").write_text(
                json.dumps({"records": records}),
                encoding="utf-8",
            )

            outline = build_section_outline(project.path, "discussion")
            paragraphs = outline["paragraphs"]
            distributed = [set(item["required_evidence_ids"]) for item in paragraphs]

            self.assertEqual(set().union(*distributed), {item["evidence_id"] for item in records})
            self.assertEqual(len({tuple(sorted(item)) for item in distributed}), len(paragraphs))

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

    def test_scientific_editor_ignores_latex_figure_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = self._project(tmp)
            text = (
                "\\section{Results}\n\n"
                "The held-out comparison establishes the study boundary and explains the observed evidence, "
                "while uncertainty limits interpretation to the current cohort and validation design. "
                "This paragraph contains enough scientific reasoning to stand on its own.\n\n"
                "\\begin{figure}[htbp]\n\\includegraphics{results/figures/main.png}\n"
                "\\caption{A scientific result figure.}\n\\end{figure}\n"
            )
            candidate = project.path / "candidate_with_figure.tex"
            candidate.write_text(text, encoding="utf-8")
            editor = prepare_scientific_editor(project.path, "results", candidate)
            self.assertFalse(any("internal_artifact_language" in task["issues"] for task in editor["tasks"]))

    def test_scientific_editor_ignores_all_latex_sectioning_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = self._project(tmp)
            text = (
                "\\section{Methods}\n\n"
                "\\subsection{Image representation}\n\n"
                "\\subsubsection{Optimization}\n\n"
                "This paragraph explains the scientific method, why the selected representation is suitable, "
                "how validation constrains model choice, and which interpretation remains outside the evidence "
                "boundary. It contains enough scientific reasoning for editor review and connects the design "
                "choice to a reproducible comparison across the declared analysis cohort.\n\n"
                "\\paragraph{Uncertainty}\n\n"
                "This paragraph defines the uncertainty calculation, connects it to the scientific estimand, "
                "and explains why the resulting interval limits rather than enlarges the supported conclusion. "
                "It also contains enough scientific reasoning for editor review and identifies how resampling "
                "preserves the source-level unit used by the inferential design.\n"
            )
            candidate = project.path / "candidate_with_sectioning.tex"
            candidate.write_text(text, encoding="utf-8")
            editor = prepare_scientific_editor(project.path, "methods", candidate)
            self.assertEqual(editor["decision"], "pass")
            self.assertEqual(editor["tasks"], [])

    def test_discussion_blueprint_binds_evidence_by_figure_story(self) -> None:
        stories = [{"story_id": f"story-{index}", "claim": f"Finding {index}"} for index in range(1, 7)]
        evidence = [
            {
                "evidence_id": f"evidence-{story_index}-{item_index}",
                "figure_links": [f"story-{story_index}"],
                "claim_role": "uncertainty evidence" if item_index == 0 else "result metric",
            }
            for story_index in range(1, 7)
            for item_index in range(10)
        ]
        paragraphs = _paragraph_blueprint(
            "discussion",
            {"allocated_claims": [], "figure_story_links": stories, "evidence_items": evidence},
        )
        finding_paragraphs = [item for item in paragraphs if str(item["paragraph_id"]).startswith("discussion_finding_")]
        self.assertEqual(len(finding_paragraphs), 6)
        for index, paragraph in enumerate(finding_paragraphs, start=1):
            self.assertEqual(len(paragraph["required_evidence_ids"]), 10)
            self.assertTrue(all(value.startswith(f"evidence-{index}-") for value in paragraph["required_evidence_ids"]))
        self.assertEqual(paragraphs[-1]["paragraph_id"], "discussion_synthesis")
        self.assertLessEqual(len(paragraphs[-1]["required_evidence_ids"]), 8)

    def test_results_blueprint_caps_prompt_evidence_without_dropping_registry_items(self) -> None:
        stories = [{"story_id": "story-model", "claim": "Compare verified models"}]
        evidence = [
            {
                "evidence_id": f"metric-{index:03d}",
                "figure_links": ["story-model"],
                "claim_role": "result_metric_macro_f1" if index % 2 == 0 else "result_metric_threshold",
                "model_id": f"model-{index % 6}",
                "analysis_variant": "primary" if index < 60 else "sensitivity",
                "value": index / 100,
            }
            for index in range(120)
        ]

        paragraphs = _paragraph_blueprint(
            "results",
            {"allocated_claims": [], "figure_story_links": stories, "evidence_items": evidence},
        )

        self.assertEqual(len(paragraphs[0]["required_evidence_ids"]), 28)
        self.assertEqual(len(evidence), 120)
        selected = set(paragraphs[0]["required_evidence_ids"])
        self.assertTrue(selected.issubset({item["evidence_id"] for item in evidence}))

    def test_methods_blueprint_selects_role_diverse_evidence_with_a_bounded_prompt(self) -> None:
        evidence = []
        for variant in range(20):
            for metric in ("macro_f1", "roc_auc", "balanced_accuracy", "ece"):
                evidence.append({
                    "evidence_id": f"metric-{variant}-{metric}",
                    "entity_role": f"result_metric_variant_{variant}_{metric}",
                    "analysis_variant": f"variant_{variant}",
                    "metric_dimension": metric,
                })
        evidence.extend([
            {"evidence_id": "cohort", "entity_role": "cohort_audit_primary_eligible_count"},
            {"evidence_id": "split", "entity_role": "cohort_audit_split_counts_train"},
            {"evidence_id": "loss", "entity_role": "training_loss", "formula_ids": ["weighted_cross_entropy"]},
            {"evidence_id": "model", "entity_role": "model_architecture_trainable_blocks"},
            {"evidence_id": "citation", "entity_role": "method_reference", "citation_key": "Method2026"},
        ])

        paragraphs = _paragraph_blueprint(
            "methods",
            {"allocated_claims": [], "figure_story_links": [], "evidence_items": evidence},
        )

        self.assertEqual(len(paragraphs), 3)
        self.assertTrue(all(len(item["required_evidence_ids"]) <= 18 for item in paragraphs))
        self.assertIn("cohort", paragraphs[0]["required_evidence_ids"])
        self.assertIn("loss", paragraphs[1]["required_evidence_ids"])
        self.assertTrue(any(value.startswith("metric-") for value in paragraphs[2]["required_evidence_ids"]))
        self.assertEqual(len(evidence), 85)

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
