# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from draftpaper_cli.data_feasibility import assess_data_feasibility, assess_data_quality, inventory_data, write_data
from draftpaper_cli.evidence_snapshot import create_evidence_snapshot
from draftpaper_cli.discussion import write_discussion
from draftpaper_cli.introduction import write_introduction
from draftpaper_cli.journal_profile import resolve_journal_template
from draftpaper_cli.method_plan import collect_method_plan
from draftpaper_cli.methods import verify_methods, write_methods
from draftpaper_cli.project_scaffold import create_project
from draftpaper_cli.passport import refresh_project_passport
from draftpaper_cli.project_state import update_stage_status
from draftpaper_cli.references import write_reference_outputs
from draftpaper_cli.research_plan import generate_research_plan
from draftpaper_cli.result_validity import assess_result_validity
from draftpaper_cli.results import inventory_results, write_results
from tests.helpers import write_core_evidence_pass


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


def prepared_project(tmp: str) -> Path:
    project = create_project(
        root=tmp,
        idea="Long-term AGN outburst prediction using multimodal survey data",
        field="machine learning astronomy",
        target_journal="General Academic Journal",
    )
    write_reference_outputs(project.path, SAMPLE_ITEMS, query="AGN outburst prediction")
    resolve_journal_template(project.path, target_journal="APJS", from_html=_write_aas_html(Path(tmp)))
    generate_research_plan(project.path)
    (project.path / "data" / "data_acquisition_plan.json").write_text(json.dumps({"tasks": [{"status": "ready"}]}), encoding="utf-8")
    rows = "\n".join(f"{i},{i % 2},0.{i % 10}" for i in range(1, 41))
    (project.path / "data" / "raw" / "sample.csv").write_text("id,target,value\n" + rows + "\n", encoding="utf-8")
    inventory_data(project.path)
    assess_data_quality(project.path, required_columns=["id", "target"])
    assess_data_feasibility(project.path, min_rows=30)
    update_stage_status(project.path, "data", "draft")
    collect_method_plan(project.path, user_method="Use supervised multimodal classification.", primary_metric="f1", minimum_primary_metric=0.7)
    update_stage_status(project.path, "figure_plan", "draft")
    update_stage_status(project.path, "code", "draft")
    runner = project.path / "methods" / "scripts" / "run_analysis.py"
    runner.parent.mkdir(parents=True, exist_ok=True)
    runner.write_text(
        "from pathlib import Path\n"
        "root = Path(__file__).resolve().parents[2]\n"
        "output = root / 'results/tables/metrics.csv'\n"
        "figure = root / 'results/figures/risk_curve.png'\n"
        "output.parent.mkdir(parents=True, exist_ok=True)\n"
        "figure.parent.mkdir(parents=True, exist_ok=True)\n"
        "output.write_text('metric,value\\nf1,0.88\\n', encoding='utf-8')\n"
        "figure.write_bytes(b'fake image')\n",
        encoding="utf-8",
    )
    verify_methods(
        project.path,
        command=f'"{sys.executable}" methods/scripts/run_analysis.py',
        output_files=["results/tables/metrics.csv", "results/figures/risk_curve.png"],
    )
    assess_result_validity(project.path)
    write_core_evidence_pass(project.path, figure_count=1)
    create_evidence_snapshot(project.path)
    inventory_results(project.path)
    write_results(project.path)
    write_introduction(project.path)
    write_data(project.path)
    write_methods(project.path)
    write_discussion(project.path)
    refresh_project_passport(project.path, event="test_prepared_project")
    return project.path


def _write_aas_html(base: Path) -> Path:
    path = base / "aas_template.html"
    path.write_text(
        "<html><body><pre>\\documentclass[linenumbers,trackchanges]{aastex701}\n\\submitjournal{ApJS}\n\\begin{document}\n\\title{%%DRAFTPAPER_TITLE%%}\n%%DRAFTPAPER_SECTIONS%%\n\\bibliography{library}{ }\n\\bibliographystyle{aasjournal}\n\\end{document}</pre></body></html>",
        encoding="utf-8",
    )
    return path


def _write_fake_tool(tool_dir: Path, name: str, *, writes_pdf: bool = False) -> Path:
    suffix = ".cmd" if os.name == "nt" else ""
    tool = tool_dir / f"{name}{suffix}"
    if os.name == "nt":
        lines = ["@echo off", f"echo fake {name} %* >> compile-tools.log"]
        if writes_pdf:
            lines.append("echo PDF > main.pdf")
        lines.append("exit /b 0")
        tool.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8")
    else:
        lines = ["#!/usr/bin/env sh", f"echo fake {name} \"$@\" >> compile-tools.log"]
        if writes_pdf:
            lines.append("printf 'PDF\\n' > main.pdf")
        lines.append("exit 0")
        tool.write_text("\n".join(lines) + "\n", encoding="utf-8")
        tool.chmod(0o755)
    return tool


class LatexAssemblyTests(unittest.TestCase):
    def test_aastex_metadata_without_authors_receives_review_placeholder_affiliation(self) -> None:
        from draftpaper_cli.latex_assembly import _apply_manuscript_metadata, _ensure_aastex_author_block

        rendered = _apply_manuscript_metadata(
            "\\documentclass{aastex701}\n\\begin{document}\n\\title{Draft}\n\\author{}\n\\end{document}\n",
            {"title": "Evidence-bound title", "abstract": "A complete abstract for review."},
            aastex=True,
        )
        rendered = _ensure_aastex_author_block(rendered)

        self.assertIn(r"\author{Manuscript author to be supplied}", rendered)
        self.assertIn(r"\affiliation{Affiliation to be supplied by the authors}", rendered)

    def test_assemble_latex_requires_all_sections_and_bibtex(self) -> None:
        from draftpaper_cli.latex_assembly import LatexAssemblyError, assemble_latex

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="No sections yet", field="workflow engineering")

            with self.assertRaises(LatexAssemblyError):
                assemble_latex(project.path)

    def test_assemble_latex_rejects_stale_input_stage(self) -> None:
        from draftpaper_cli.latex_assembly import LatexAssemblyError, assemble_latex

        with tempfile.TemporaryDirectory() as tmp:
            project_path = prepared_project(tmp)
            update_stage_status(project_path, "results", "stale")

            with self.assertRaises(LatexAssemblyError):
                assemble_latex(project_path)

    def test_assemble_latex_writes_main_sections_and_bibtex(self) -> None:
        from draftpaper_cli.latex_assembly import assemble_latex

        with tempfile.TemporaryDirectory() as tmp:
            project_path = prepared_project(tmp)

            result = assemble_latex(project_path)

            self.assertEqual(result["status"], "written")
            self.assertEqual(result["section_count"], 5)
            main_tex = project_path / "latex" / "main.tex"
            library = project_path / "latex" / "library.bib"
            self.assertTrue(main_tex.exists())
            self.assertTrue(library.exists())
            for name in ["introduction", "data", "methods", "results", "discussion"]:
                self.assertTrue((project_path / "latex" / "sections" / f"{name}.tex").exists())
            result_artifacts = project_path / "latex" / "sections" / "result_artifacts.tex"
            self.assertTrue(result_artifacts.exists())
            artifact_content = result_artifacts.read_text(encoding="utf-8")
            self.assertIn("\\includegraphics", artifact_content)
            self.assertIn("\\caption{", artifact_content)
            self.assertIn("\\label{fig:", artifact_content)
            self.assertNotIn("Analysis context (", artifact_content)
            self.assertNotIn("Reported quantities:", artifact_content)

            content = main_tex.read_text(encoding="utf-8")
            self.assertIn("Generated with Draftpaper-loop", content)
            self.assertIn("\\documentclass", content)
            self.assertIn("\\usepackage{amsmath,amssymb}", content)
            self.assertIn("\\graphicspath{{../}}", content)
            self.assertIn("\\input{sections/introduction}", content)
            introduction_section = (project_path / "latex" / "sections" / "introduction.tex").read_text(encoding="utf-8")
            self.assertTrue(
                "\\section{Introduction}\n\\input{sections/introduction}" in content
                or introduction_section.lstrip().startswith("\\section{"),
            )
            self.assertIn("\\input{sections/result_artifacts}", content)
            self.assertIn("\\input{sections/result_artifacts}\n\\clearpage\n\\input{sections/discussion}", content)
            self.assertIn("Draftpaper-loop", content)
            self.assertNotIn("Draft Author", content)
            self.assertNotIn("Draft affiliation", content)
            self.assertNotIn("author@example.com", content)
            self.assertIn("\\author{Manuscript author to be supplied}", content)
            self.assertIn("\\affiliation{Affiliation to be supplied by the authors}", content)
            self.assertIn("\\email{corresponding.author@placeholder.invalid}", content)
            self.assertIn("https://github.com/xiejhhhhhh/Draftpaper\\_loop", content)
            self.assertIn("\\bibliography{library}", content)
            self.assertIn("\\bibliographystyle{aasjournal}", content)
            self.assertIn("\\begin{acknowledgments}", content)
            self.assertIn("\\end{acknowledgments}", content)
            self.assertNotIn("\\acknowledgments\n", content)
            self.assertNotIn("\\bibliography{library}{ }", content)
            self.assertLess(content.index("Draftpaper-loop"), content.index("\\bibliography{library}"))
            self.assertIn("Long-term AGN outburst prediction", content)

            manifest = json.loads((project_path / "latex" / "stage_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "draft")
            self.assertFalse(manifest["stale"])
            self.assertIn("discussion/discussion.tex", manifest["input_files"])
            self.assertIn("latex/main.tex", manifest["output_files"])

            project_json = json.loads((project_path / "project.json").read_text(encoding="utf-8"))
            self.assertEqual(project_json["stages"]["latex"]["status"], "draft")
            self.assertEqual(project_json["stages"]["quality_checks"]["status"], "stale")

    def test_assemble_latex_materializes_cited_supplemental_bibliography(self) -> None:
        from draftpaper_cli.latex_assembly import assemble_latex

        with tempfile.TemporaryDirectory() as tmp:
            project_path = prepared_project(tmp)
            (project_path / "references" / "supplemental_library.bib").write_text(
                "@article{Comparison2020,author={Doe, Jane},title={Independent comparison},year={2020},"
                "journal={Test Journal},doi={10.1234/comparison},url={https://doi.org/10.1234/comparison}}\n",
                encoding="utf-8",
            )
            discussion = project_path / "discussion" / "discussion.tex"
            discussion.write_text(
                discussion.read_text(encoding="utf-8") + "\nIndependent comparison \\citep{Comparison2020}.\n",
                encoding="utf-8",
            )

            assemble_latex(project_path)

            materialized = (project_path / "latex" / "library.bib").read_text(encoding="utf-8")
            self.assertIn("@article{Comparison2020", materialized)
            merge = json.loads(
                (project_path / "references" / "supplemental_bibliography_merge_report.json").read_text(encoding="utf-8")
            )
            self.assertEqual(merge["status"], "passed")

    def test_section_input_wraps_prose_only_artifact(self) -> None:
        from draftpaper_cli.latex_assembly import _section_input

        with tempfile.TemporaryDirectory() as tmp:
            project_path = Path(tmp)
            section = project_path / "introduction" / "introduction.tex"
            section.parent.mkdir(parents=True)
            section.write_text("Opening scientific argument.\n", encoding="utf-8")

            rendered = _section_input(project_path, "introduction")

            self.assertEqual(rendered, "\\section{Introduction}\n\\input{sections/introduction}")

    def test_result_labels_use_the_same_hyphenated_form_as_section_references(self) -> None:
        from draftpaper_cli.latex_assembly import _safe_result_label

        self.assertEqual(_safe_result_label("fig_1_fig_01"), "fig-1-fig-01")

    def test_assemble_latex_applies_manuscript_caption_override_without_changing_figure_metadata(self) -> None:
        from draftpaper_cli.latex_assembly import assemble_latex

        with tempfile.TemporaryDirectory() as tmp:
            project_path = prepared_project(tmp)
            metadata = project_path / "writing" / "manuscript_metadata.yaml"
            metadata.write_text(
                "figure_captions:\n  risk_curve: Conditional fixed-fold result; no pipeline refitting is claimed.\n",
                encoding="utf-8",
            )

            assemble_latex(project_path)

            artifacts = (project_path / "latex" / "sections" / "result_artifacts.tex").read_text(encoding="utf-8")
            self.assertIn("Conditional fixed-fold result; no pipeline refitting is claimed.", artifacts)

    def test_assemble_latex_rejects_citation_missing_from_bibtex(self) -> None:
        from draftpaper_cli.latex_assembly import LatexCitationError, assemble_latex

        with tempfile.TemporaryDirectory() as tmp:
            project_path = prepared_project(tmp)
            discussion = project_path / "discussion" / "discussion.tex"
            discussion.write_text(discussion.read_text(encoding="utf-8") + "\nMissing citation \\citep{Unknown2026}.\n", encoding="utf-8")

            with self.assertRaises(LatexCitationError):
                assemble_latex(project_path)

    def test_assemble_latex_rejects_abstract_with_stale_numeric_evidence(self) -> None:
        from draftpaper_cli.latex_assembly import LatexAssemblyError, assemble_latex

        with tempfile.TemporaryDirectory() as tmp:
            project_path = prepared_project(tmp)
            metadata = project_path / "writing" / "manuscript_metadata.yaml"
            metadata.write_text(
                "title: Current title\nabstract: The held-out model reached macro-F1=0.5.\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(LatexAssemblyError, "abstract is stale"):
                assemble_latex(project_path)

    def test_assemble_latex_replaces_empty_aastex_author_without_control_character(self) -> None:
        from draftpaper_cli.latex_assembly import assemble_latex

        with tempfile.TemporaryDirectory() as tmp:
            project_path = prepared_project(tmp)
            template = project_path / "latex" / "template" / "main.tex"
            template.write_text(
                template.read_text(encoding="utf-8").replace(
                    "\\title{%%DRAFTPAPER_TITLE%%}",
                    "\\title{%%DRAFTPAPER_TITLE%%}\n\\author{}",
                ),
                encoding="utf-8",
            )

            assemble_latex(project_path)

            content = (project_path / "latex" / "main.tex").read_text(encoding="utf-8")
            self.assertNotIn("\a", content)
            self.assertIn("\\author{Manuscript author to be supplied}", content)
            self.assertIn("\\affiliation{Affiliation to be supplied by the authors}", content)
            self.assertIn("\\email{corresponding.author@placeholder.invalid}", content)

    def test_cli_assemble_latex_outputs_main_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_path = prepared_project(tmp)

            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "draftpaper_cli.cli",
                    "assemble-latex",
                    "--project",
                    str(project_path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            payload = json.loads(completed.stdout)
            self.assertEqual(payload["status"], "written")
            self.assertTrue(Path(payload["main_tex"]).exists())
            self.assertTrue(Path(payload["library_bib"]).exists())

    def test_compile_latex_pdf_skips_cleanly_without_engine(self) -> None:
        from draftpaper_cli.latex_assembly import assemble_latex, compile_latex_pdf

        with tempfile.TemporaryDirectory() as tmp:
            project_path = prepared_project(tmp)
            assemble_latex(project_path)

            with patch.dict(os.environ, {"PATH": "", "LOCALAPPDATA": str(Path(tmp) / "no-localappdata")}):
                result = compile_latex_pdf(project_path)

            self.assertEqual(result["status"], "skipped")
            self.assertIsNone(result["pdf"])
            manifest = json.loads((project_path / "latex" / "pdf_compile_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "skipped")
            self.assertIn("no local LaTeX engine", manifest["message"])

    def test_compile_latex_pdf_uses_local_engine_and_writes_manifest(self) -> None:
        from draftpaper_cli.latex_assembly import assemble_latex, compile_latex_pdf

        with tempfile.TemporaryDirectory() as tmp:
            project_path = prepared_project(tmp)
            assemble_latex(project_path)
            tool_dir = Path(tmp) / "tools"
            tool_dir.mkdir()
            _write_fake_tool(tool_dir, "xelatex", writes_pdf=True)
            _write_fake_tool(tool_dir, "bibtex")

            old_path = os.environ.get("PATH", "")
            with patch.dict(os.environ, {"PATH": str(tool_dir) + os.pathsep + old_path, "LOCALAPPDATA": str(Path(tmp) / "no-localappdata")}):
                result = compile_latex_pdf(project_path)

            self.assertEqual(result["status"], "success")
            self.assertTrue(Path(result["pdf"]).exists())
            self.assertTrue((project_path / "latex" / "main.compile.log").exists())
            manifest = json.loads((project_path / "latex" / "pdf_compile_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "success")
            self.assertIn("xelatex", manifest["engine"])
            skipped = [item for item in manifest["commands"] if item.get("status") == "skipped"]
            self.assertEqual(skipped[0]["reason"], "aux file does not request BibTeX")

    def test_local_bibstyle_fallback_copies_available_natbib_style(self) -> None:
        from draftpaper_cli.latex_assembly import _ensure_local_bibstyle_fallback

        with tempfile.TemporaryDirectory() as tmp:
            latex_dir = Path(tmp)
            tex = latex_dir / "main.tex"
            tex.write_text("\\bibliographystyle{missingjournal}\n\\bibliography{library}\n", encoding="utf-8")
            (latex_dir / "plainnat.bst").write_text("ENTRY{}{}{}\n", encoding="utf-8")

            fallback = _ensure_local_bibstyle_fallback(latex_dir, tex)

            self.assertIsNotNone(fallback)
            assert fallback is not None
            self.assertEqual(fallback["status"], "used")
            self.assertEqual(fallback["requested_style"], "missingjournal")
            self.assertEqual(fallback["fallback_style"], "plainnat")
            self.assertTrue((latex_dir / "missingjournal.bst").exists())
            self.assertIn("\\bibliographystyle{missingjournal}", tex.read_text(encoding="utf-8"))

    def test_cli_assemble_latex_can_compile_pdf_for_review(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_path = prepared_project(tmp)
            tool_dir = Path(tmp) / "tools"
            tool_dir.mkdir()
            _write_fake_tool(tool_dir, "xelatex", writes_pdf=True)
            old_path = os.environ.get("PATH", "")
            env = os.environ.copy()
            env["PATH"] = str(tool_dir) + os.pathsep + old_path
            env["LOCALAPPDATA"] = str(Path(tmp) / "no-localappdata")

            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "draftpaper_cli.cli",
                    "assemble-latex",
                    "--project",
                    str(project_path),
                    "--compile-pdf",
                ],
                check=True,
                capture_output=True,
                text=True,
                env=env,
            )

            payload = json.loads(completed.stdout)
            self.assertEqual(payload["status"], "written")
            self.assertEqual(payload["pdf_status"], "success")
            self.assertTrue(Path(payload["pdf"]).exists())


if __name__ == "__main__":
    unittest.main()
