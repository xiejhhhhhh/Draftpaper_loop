# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json
import tempfile
import unittest

from draftpaper_cli.observations import record_observation
from draftpaper_cli.project_scaffold import create_project


class ScientificFactLedgerTests(unittest.TestCase):
    def test_fact_summary_is_not_rendered_as_manuscript_instruction(self) -> None:
        from draftpaper_cli.scientific_fact_ledger import fact_summary_for_sections

        summary = fact_summary_for_sections(
            {
                "facts": [
                    {
                        "must_preserve": True,
                        "target_sections": ["methods"],
                        "text": "60 sources",
                    }
                ]
            },
            {"methods"},
        )

        self.assertEqual(summary, "")

    def test_ledger_extracts_must_preserve_sample_facts_from_observations(self) -> None:
        from draftpaper_cli.scientific_fact_ledger import build_scientific_fact_ledger

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Time-aware X-ray source classification", field="astronomy machine learning")
            record_observation(
                project.path,
                stage="data",
                kind="data_summary",
                text=(
                    "The curated supervised subset contains 6010 events from 60 sources, "
                    "with 30 AGN and 30 XRB sources. The long-term light-curve table contains "
                    "1.996M token bins. TDE cases are used only for stress testing."
                ),
            )

            ledger = build_scientific_fact_ledger(project.path)

            facts = {item["role"]: item for item in ledger["facts"]}
            self.assertEqual(facts["event_count"]["value"], "6010")
            self.assertEqual(facts["source_count"]["value"], "60")
            self.assertEqual(facts["class_balance"]["text"], "30 AGN and 30 XRB sources")
            self.assertEqual(facts["token_bin_count"]["text"], "1.996M token bins")
            self.assertIn("data", facts["event_count"]["target_sections"])
            self.assertTrue(facts["event_count"]["must_preserve"])
            self.assertTrue((project.path / "writing" / "scientific_fact_ledger.json").exists())

    def test_legacy_ledger_is_not_an_authoritative_quality_gate(self) -> None:
        from draftpaper_cli.quality_gate import check_scientific_evidence_registry
        from draftpaper_cli.scientific_fact_ledger import build_scientific_fact_ledger

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Time-aware X-ray source classification", field="astronomy machine learning")
            record_observation(
                project.path,
                stage="data",
                kind="data_summary",
                text="The curated supervised subset contains 6010 events from 60 sources with 30 AGN and 30 XRB sources.",
            )
            build_scientific_fact_ledger(project.path)
            (project.path / "data" / "data.tex").write_text(
                "\\section{Data}\nThe curated subset contains 6010 events from 60 sources.\n",
                encoding="utf-8",
            )
            (project.path / "methods" / "methods.tex").write_text(
                "\\section{Methods}\nThe model uses a supervised astronomy classification design.\n",
                encoding="utf-8",
            )

            report = check_scientific_evidence_registry(project.path)

            self.assertEqual(report["status"], "passed")
            self.assertEqual(report["record_count"], 0)
            self.assertEqual(report["blocking_conflict_count"], 0)

    def test_results_writer_creates_interpretation_blueprint_from_main_and_appendix_figures(self) -> None:
        from draftpaper_cli.results import write_results
        from tests.test_results import prepare_passing_result_validity

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Time-aware X-ray source classification", field="astronomy machine learning")
            (project.path / "results" / "figures" / "main.png").write_bytes(b"fake image")
            (project.path / "results" / "figures" / "appendix.png").write_bytes(b"fake image")
            (project.path / "results" / "tables" / "metrics.csv").write_text("metric,value\nf1,0.81\n", encoding="utf-8")
            prepare_passing_result_validity(project.path)
            (project.path / "results" / "result_manifest.yaml").write_text(
                json.dumps({
                    "figures": [
                        {
                            "id": "main-performance",
                            "path": "results/figures/main.png",
                            "manuscript_role": "main",
                            "caption_draft": "Source-held-out classification performance.",
                            "scientific_question": "Does the time-aware classifier separate AGN and XRB sources under source-held-out validation?",
                            "result_claim": "The model shows useful source-held-out discrimination.",
                            "metrics": {"f1": 0.81, "auc": 0.87, "class_count": 2},
                        },
                        {
                            "id": "appendix-ablation",
                            "path": "results/figures/appendix.png",
                            "manuscript_role": "appendix",
                            "linked_main_figure": "main-performance",
                            "supporting_reason": "diagnostic evidence supports ablation stability",
                            "caption_draft": "Ablation diagnostic.",
                            "result_claim": "The ablation diagnostic constrains the reliability of the classifier interpretation.",
                        },
                    ],
                    "main_figures": [
                        {
                            "id": "main-performance",
                            "path": "results/figures/main.png",
                            "manuscript_role": "main",
                            "caption_draft": "Source-held-out classification performance.",
                            "scientific_question": "Does the time-aware classifier separate AGN and XRB sources under source-held-out validation?",
                            "result_claim": "The model shows useful source-held-out discrimination.",
                            "metrics": {"f1": 0.81, "auc": 0.87, "class_count": 2},
                        }
                    ],
                    "appendix_figures": [
                        {
                            "id": "appendix-ablation",
                            "path": "results/figures/appendix.png",
                            "manuscript_role": "appendix",
                            "linked_main_figure": "main-performance",
                            "supporting_reason": "diagnostic evidence supports ablation stability",
                            "caption_draft": "Ablation diagnostic.",
                            "result_claim": "The ablation diagnostic constrains the reliability of the classifier interpretation.",
                        }
                    ],
                    "tables": [],
                }),
                encoding="utf-8",
            )

            write_results(project.path)

            blueprint = json.loads((project.path / "results" / "figure_interpretation_blueprint.json").read_text(encoding="utf-8"))
            tex = (project.path / "results" / "results.tex").read_text(encoding="utf-8")
            self.assertEqual(blueprint["main_group_count"], 1)
            self.assertEqual(blueprint["groups"][0]["primary_metrics"], {"F1": "0.81", "AUC": "0.87"})
            self.assertIn("Appendix Figure~\\ref{fig:appendix-ablation}", tex)
            self.assertIn("source-held-out", tex)

