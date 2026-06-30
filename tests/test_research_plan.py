# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from draftpaper_cli.project_scaffold import create_project
from draftpaper_cli.journal_profile import resolve_journal_template
from draftpaper_cli.references import write_reference_outputs


SAMPLE_ITEMS = [
    {
        "title": "Transformer models for active galactic nuclei outburst prediction",
        "authors": ["Jane Smith", "Alan Chen"],
        "year": "2024",
        "doi": "10.1000/agn.2024.1",
        "url": "https://example.org/agn-transformer",
        "abstract": "Existing models lack external validation for long-term outburst prediction in active galactic nuclei.",
        "publication": "Journal of Astroinformatics",
        "citation_count": 42,
        "source": "semantic_scholar",
    },
    {
        "title": "Multimodal survey data for time-domain astronomy",
        "authors": ["Maria Lee"],
        "year": "2023",
        "doi": "",
        "url": "https://arxiv.org/abs/2301.00001",
        "abstract": "Multimodal photometric and spectroscopic survey data improve time-domain event characterization.",
        "publication": "arXiv",
        "citation_count": 7,
        "source": "arxiv",
    },
]


def write_generic_profile(project_path: Path, tmp: str) -> None:
    html = Path(tmp) / "journal.html"
    html.write_text("<html><body><pre>\\documentclass{article}\\n\\begin{document}\\n%%DRAFTPAPER_SECTIONS%%\\n%%DRAFTPAPER_BIBLIOGRAPHY%%\\n\\end{document}</pre></body></html>", encoding="utf-8")
    resolve_journal_template(project_path, target_journal="General Academic Journal", from_html=html)


class ResearchPlanTests(unittest.TestCase):
    def test_generate_research_plan_requires_references_outputs(self) -> None:
        from draftpaper_cli.research_plan import MissingReferencesError, generate_research_plan

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="AGN outburst prediction", field="machine learning astronomy")

            with self.assertRaises(MissingReferencesError):
                generate_research_plan(project.path)

    def test_generate_research_plan_uses_literature_evidence_and_writes_outputs(self) -> None:
        from draftpaper_cli.research_plan import generate_research_plan

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(
                root=tmp,
                idea="Long-term AGN outburst prediction using multimodal survey data",
                field="machine learning astronomy",
                target_journal="General Academic Journal",
            )
            write_reference_outputs(project.path, SAMPLE_ITEMS, query="AGN outburst prediction")
            write_generic_profile(project.path, tmp)

            result = generate_research_plan(project.path)

            self.assertEqual(result["status"], "written")
            self.assertEqual(result["citation_count"], 2)
            self.assertTrue((project.path / "research_plan" / "research_plan.md").exists())
            self.assertTrue((project.path / "research_plan" / "research_plan.zh-CN.md").exists())
            self.assertFalse((project.path / "research_plan" / "research_plan.html").exists())
            self.assertFalse((project.path / "research_plan" / "research_questions.md").exists())
            self.assertFalse((project.path / "research_plan" / "research_questions.html").exists())
            self.assertTrue((project.path / "research_plan" / "target_journal_anchor_papers.json").exists())
            self.assertTrue((project.path / "research_plan" / "novelty_overlap_report.md").exists())
            self.assertTrue((project.path / "research_plan" / "novelty_overlap_report.html").exists())

            plan = (project.path / "research_plan" / "research_plan.md").read_text(encoding="utf-8")
            self.assertIn("Long-term AGN outburst prediction", plan)
            self.assertIn("Smith2024Transformer1", plan)
            self.assertIn("external validation", plan)
            self.assertIn("Research Questions", plan)
            self.assertIn("Data Requirements", plan)
            self.assertIn("Method Route", plan)
            self.assertIn("Method Plan Contract", plan)
            self.assertIn("Figure Storyboard", plan)
            self.assertIn("Target-Journal Anchor Literature", plan)
            self.assertIn("Risks and User Confirmation", plan)

            manifest = json.loads((project.path / "research_plan" / "stage_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "draft")
            self.assertFalse(manifest["stale"])
            self.assertIn("references/citation_evidence.csv", manifest["input_files"])
            self.assertIn("research_plan/target_journal_anchor_papers.json", manifest["output_files"])
            self.assertIn("research_plan/research_plan.md", manifest["output_files"])
            self.assertIn("research_plan/research_plan.zh-CN.md", manifest["output_files"])
            self.assertNotIn("research_plan/research_plan.html", manifest["output_files"])

            project_json = json.loads((project.path / "project.json").read_text(encoding="utf-8"))
            self.assertEqual(project_json["stages"]["research_plan"]["status"], "draft")
            self.assertEqual(project_json["stages"]["introduction"]["status"], "stale")

    def test_research_plan_declares_minimum_main_figures_and_literature_index_link(self) -> None:
        from draftpaper_cli.research_plan import generate_research_plan

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(
                root=tmp,
                idea="Time-aware Transformer classification of EP WXT flaring sources using long-term light curves",
                field="high-energy time-domain astronomy; machine learning",
                target_journal="APJS",
            )
            write_reference_outputs(project.path, SAMPLE_ITEMS, query="EP WXT flaring source classification")
            write_generic_profile(project.path, tmp)
            literature_index = project.path / "references" / "literature_summaries" / "index.html"
            literature_index.parent.mkdir(parents=True, exist_ok=True)
            literature_index.write_text("<html><body>literature summaries</body></html>", encoding="utf-8")

            generate_research_plan(project.path)

            plan = (project.path / "research_plan" / "research_plan.md").read_text(encoding="utf-8")
            figure_count = len(re.findall(r"^- Fig\.\s+\d+:", plan, flags=re.MULTILINE))
            table_count = len(re.findall(r"^- Table\s+\d+:", plan, flags=re.MULTILINE))
            self.assertGreaterEqual(figure_count, 5)
            self.assertGreaterEqual(table_count, 1)
            self.assertIn("[Open the full literature summaries](../references/literature_summaries/index.html)", plan)
            snapshot = plan.split("## Literature Notes Snapshot", 1)[1]
            self.assertNotIn("# Literature Review Notes", snapshot)

    def test_generate_research_plan_writes_structured_blueprint_storyboard_and_bilingual_outputs(self) -> None:
        from draftpaper_cli.research_plan import generate_research_plan

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(
                root=tmp,
                idea="Time-aware Transformer classification of EP WXT flaring sources using long-term light curves, current observation tokens, and spectral features",
                field="high-energy time-domain astronomy; X-ray transient classification; machine learning for irregular light curves",
                target_journal="APJS",
            )
            write_reference_outputs(project.path, [
                {
                    "title": "Astronomical Transformer for time series and tabular data",
                    "authors": ["A. Author"],
                    "year": "2024",
                    "publication": "Astronomy and Computing",
                    "abstract": "Transformer models combine irregular light curves and tabular features for transient classification.",
                    "citation_count": 20,
                    "source": "semantic_scholar",
                },
                {
                    "title": "Representation learning for high-energy time-domain astrophysics",
                    "authors": ["B. Author"],
                    "year": "2025",
                    "publication": "Astrophysical Journal Supplement Series",
                    "abstract": "High-energy transient studies need temporal, spectral, and uncertainty-aware event representations.",
                    "citation_count": 12,
                    "source": "semantic_scholar",
                },
            ], query="EP WXT flaring source transformer classification")
            write_generic_profile(project.path, tmp)

            result = generate_research_plan(project.path, allow_high_similarity=True)

            self.assertEqual(result["status"], "written")
            for relative in [
                "research_plan/research_blueprint.json",
                "research_plan/figure_storyboard.json",
                "research_plan/method_plan.json",
                "research_plan/research_plan.zh-CN.md",
            ]:
                self.assertTrue((project.path / relative).exists(), relative)

            blueprint = json.loads((project.path / "research_plan" / "research_blueprint.json").read_text(encoding="utf-8"))
            storyboard = json.loads((project.path / "research_plan" / "figure_storyboard.json").read_text(encoding="utf-8"))
            method_plan = json.loads((project.path / "research_plan" / "method_plan.json").read_text(encoding="utf-8"))
            self.assertGreaterEqual(len(blueprint["research_claims"]), 4)
            self.assertGreaterEqual(len(storyboard["figures"]), 5)
            self.assertGreaterEqual(len(storyboard["tables"]), 1)
            self.assertLessEqual(storyboard["quality_gate"]["incomplete_figure_count"], 2)
            self.assertEqual(method_plan["source"], "research_blueprint")
            self.assertGreaterEqual(len(method_plan["method_tasks"]), 4)
            for figure in storyboard["figures"]:
                self.assertTrue(figure["research_question"])
                self.assertTrue(figure["expected_finding"])
                self.assertTrue(figure["required_data"])
                self.assertTrue(figure["required_method"])
                self.assertTrue(figure["supporting_literature_keys"])
                self.assertNotIn("Additional discipline-specific", figure["proposed_title"])
            plan = (project.path / "research_plan" / "research_plan.md").read_text(encoding="utf-8")
            plan_cn = (project.path / "research_plan" / "research_plan.zh-CN.md").read_text(encoding="utf-8")
            self.assertIn("Figure Storyboard", plan)
            self.assertIn("Time-aware Transformer", plan)
            self.assertIn("图表故事板", plan_cn)
            self.assertIn("时间感知", plan_cn)
            self.assertIn("预期发现", plan_cn)
            self.assertNotIn("Research question:", plan_cn)
            self.assertNotIn("Expected finding:", plan_cn)
            chinese_chars = len(re.findall(r"[\u4e00-\u9fff]", plan_cn))
            ascii_letters = len(re.findall(r"[A-Za-z]", plan_cn))
            self.assertGreater(chinese_chars, ascii_letters * 0.35)

    def test_cli_generate_plan_writes_research_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="AGN outburst prediction", field="machine learning astronomy")
            write_reference_outputs(project.path, SAMPLE_ITEMS, query="AGN outburst prediction")
            write_generic_profile(project.path, tmp)

            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "draftpaper_cli.cli",
                    "generate-plan",
                    "--project",
                    str(project.path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            payload = json.loads(completed.stdout)
            self.assertEqual(payload["status"], "written")
            self.assertTrue(payload["research_plan"].endswith(".md"))
            self.assertTrue(Path(payload["research_plan"]).exists())
            self.assertTrue(Path(payload["research_plan_zh_cn"]).exists())
            self.assertNotIn("research_questions", payload)

    def test_cli_generate_plan_returns_blocked_high_similarity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(
                root=tmp,
                idea="Deep multimodal classification of Einstein Probe WXT FXT X-ray transient sources using light curves spectral hardness AGN XRB TDE QPE ULX",
                field="machine learning astronomy",
                target_journal="APJS",
            )
            write_generic_profile(project.path, tmp)
            write_reference_outputs(project.path, [{
                "title": "Deep multimodal classification of Einstein Probe WXT FXT X-ray transient sources using light curves spectral hardness AGN XRB TDE QPE ULX",
                "authors": ["A. Similar"],
                "year": "2026",
                "abstract": "Deep multimodal classification of Einstein Probe WXT FXT X-ray transient sources using light curves spectral hardness AGN XRB TDE QPE ULX.",
                "publication": "Astrophysical Journal Supplement Series",
                "citation_count": 5,
                "source": "semantic_scholar",
            }], query="Einstein Probe X-ray transient classification")

            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "draftpaper_cli.cli",
                    "generate-plan",
                    "--project",
                    str(project.path),
                ],
                capture_output=True,
                text=True,
            )

            self.assertEqual(completed.returncode, 3)
            payload = json.loads(completed.stderr)
            self.assertEqual(payload["status"], "blocked_high_similarity")
            self.assertTrue(Path(payload["novelty_overlap_report"]).exists())

    def test_generate_research_plan_blocks_when_prior_paper_is_too_similar(self) -> None:
        from draftpaper_cli.research_plan import NoveltyOverlapError, generate_research_plan

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(
                root=tmp,
                idea="Deep multimodal classification of Einstein Probe WXT FXT X-ray transient sources using light curves spectral hardness AGN XRB TDE QPE ULX",
                field="machine learning astronomy",
                target_journal="APJS",
            )
            write_generic_profile(project.path, tmp)
            very_similar = [{
                "title": "Deep multimodal classification of Einstein Probe WXT FXT X-ray transient sources using light curves spectral hardness AGN XRB TDE QPE ULX",
                "authors": ["A. Similar"],
                "year": "2026",
                "abstract": "Deep multimodal classification of Einstein Probe WXT FXT X-ray transient sources using light curves spectral hardness AGN XRB TDE QPE ULX.",
                "publication": "Astrophysical Journal Supplement Series",
                "citation_count": 5,
                "source": "semantic_scholar",
            }]
            write_reference_outputs(project.path, very_similar, query="Einstein Probe X-ray transient classification")

            with self.assertRaises(NoveltyOverlapError):
                generate_research_plan(project.path)

            report = json.loads((project.path / "research_plan" / "novelty_overlap_report.json").read_text(encoding="utf-8"))
            self.assertTrue(report["high_similarity_found"])

            result = generate_research_plan(project.path, allow_high_similarity=True)
            self.assertEqual(result["status"], "written")


if __name__ == "__main__":
    unittest.main()
