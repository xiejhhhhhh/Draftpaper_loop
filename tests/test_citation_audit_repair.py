# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from draftpaper_cli.project_scaffold import create_project


def _write_minimal_citation_project(root: str) -> Path:
    project = create_project(
        root=root,
        idea="Citation audit repair loop",
        field="research workflow engineering",
        target_journal="General Academic Journal",
    )
    project_path = project.path
    (project_path / "references" / "library.bib").write_text(
        """@article{Smith2024Model,
  title={External validation of compact models},
  author={Smith, Jane},
  year={2024},
  journal={Journal of Reproducible Models},
  doi={10.1000/model.2024}
}
@article{Lee2023Data,
  title={Curated benchmark data for model evaluation},
  author={Lee, Maria},
  year={2023},
  journal={Data Science Journal},
  doi={10.1000/data.2023}
}
""",
        encoding="utf-8",
    )
    (project_path / "references" / "citation_evidence.csv").write_text(
        "citation_key,section,claim,evidence_summary,source,doi,url\n"
        'Smith2024Model,introduction,"external validation","The paper reports external validation of compact models.",semantic_scholar,10.1000/model.2024,https://example.org/model\n'
        'Lee2023Data,introduction,"benchmark data","The paper describes curated benchmark data for model evaluation.",semantic_scholar,10.1000/data.2023,https://example.org/data\n',
        encoding="utf-8",
    )
    (project_path / "introduction" / "introduction.tex").write_text(
        "\\section{Introduction}\n"
        "Existing models need external validation in independent data \\citep{Smith2024Model}. "
        "Satellite governance policy proves clinical treatment superiority \\citep{Lee2023Data}.\n",
        encoding="utf-8",
    )
    (project_path / "discussion" / "discussion.tex").write_text(
        "\\section{Discussion}\n"
        "The interpretation remains limited by the validation setting \\citep{Smith2024Model}.\n",
        encoding="utf-8",
    )
    (project_path / "latex" / "main.tex").write_text(
        "\\documentclass{article}\n\\begin{document}\n"
        "\\input{sections/introduction}\n\\input{sections/discussion}\n"
        "\\bibliography{library}\n\\end{document}\n",
        encoding="utf-8",
    )
    return project_path


def _write_citation_preservation_project(root: str) -> Path:
    project = create_project(
        root=root,
        idea="High-energy source classification with method citations",
        field="astronomy machine learning",
        target_journal="APJS",
    )
    project_path = project.path
    (project_path / "references" / "library.bib").write_text(
        """@article{Freeman2001Sherpa14,
  title={Sherpa: a mission-independent data analysis application},
  author={Freeman, Peter},
  year={2001},
  journal={SPIE},
  doi={10.0000/sherpa}
}
@article{Yuan2022The13,
  title={The Einstein Probe Mission},
  author={Yuan, Weimin},
  year={2022},
  journal={Chinese Journal of Space Science},
  doi={10.0000/ep}
}
@article{Unused2025Relevant,
  title={Transformer baselines for X-ray transient classification},
  author={Chen, Ada},
  year={2025},
  journal={Astrophysical Journal},
  doi={10.0000/unused}
}
@article{OffTopic2024Policy,
  title={Municipal transport finance policy},
  author={Policy, Pat},
  year={2024},
  journal={Urban Policy Review},
  doi={10.0000/policy}
}
""",
        encoding="utf-8",
    )
    (project_path / "references" / "citation_evidence.csv").write_text(
        "citation_key,section,claim,evidence_summary,source,doi,url\n"
        'Freeman2001Sherpa14,methods,"Sherpa fitting software","Sherpa is the CIAO modeling and fitting application used for model fitting in high-energy astrophysics.",semantic_scholar,10.0000/sherpa,https://example.org/sherpa\n'
        'Freeman2001Sherpa14,discussion,"Sherpa fitting software","Sherpa is the CIAO modeling and fitting application used for model fitting in high-energy astrophysics.",semantic_scholar,10.0000/sherpa,https://example.org/sherpa\n'
        'Yuan2022The13,introduction,"Einstein Probe WXT mission","The Einstein Probe mission paper describes the Wide-field X-ray Telescope and lobster-eye focusing design for high-energy transients.",semantic_scholar,10.0000/ep,https://example.org/ep\n'
        'Unused2025Relevant,methods,"X-ray transient transformer baselines","The study compares transformer baselines for X-ray transient classification.",semantic_scholar,10.0000/unused,https://example.org/unused\n'
        'OffTopic2024Policy,introduction,"municipal policy","The article studies municipal transport finance policy.",semantic_scholar,10.0000/policy,https://example.org/policy\n',
        encoding="utf-8",
    )
    (project_path / "references" / "literature_items.json").write_text(
        json.dumps([
            {"bibtex_key": "Freeman2001Sherpa14", "title": "Sherpa: a mission-independent data analysis application"},
            {"bibtex_key": "Yuan2022The13", "title": "The Einstein Probe Mission"},
            {"bibtex_key": "Unused2025Relevant", "title": "Transformer baselines for X-ray transient classification"},
            {"bibtex_key": "OffTopic2024Policy", "title": "Municipal transport finance policy"},
        ]),
        encoding="utf-8",
    )
    summary_dir = project_path / "references" / "literature_summaries"
    summary_dir.mkdir(parents=True, exist_ok=True)
    for key in ["Freeman2001Sherpa14", "Yuan2022The13", "Unused2025Relevant", "OffTopic2024Policy"]:
        (summary_dir / f"{key.lower()}.html").write_text(f"<html><body>{key}</body></html>", encoding="utf-8")
    (summary_dir / "index.html").write_text(
        "<html><body>"
        "<a>Freeman2001Sherpa14</a><a>Yuan2022The13</a><a>Unused2025Relevant</a><a>OffTopic2024Policy</a>"
        "</body></html>",
        encoding="utf-8",
    )
    (project_path / "introduction" / "introduction.tex").write_text(
        "\\section{Introduction}\n"
        "The Einstein Probe Wide-field X-ray Telescope supports high-energy transient discovery \\citep{Yuan2022The13}. "
        "This astronomy paper is not about municipal transport pricing \\citep{OffTopic2024Policy}.\n",
        encoding="utf-8",
    )
    (project_path / "methods" / "methods.tex").write_text(
        "\\section{Methods}\n"
        "Sherpa-based absorbed power-law fits can add hydrogen column density, photon index, and goodness-of-fit diagnostics; "
        "however, those quantities should enter the current-observation encoder only after fit failures and low-count cases "
        "are recorded explicitly \\citep{Freeman2001Sherpa14}.\n",
        encoding="utf-8",
    )
    (project_path / "discussion" / "discussion.tex").write_text(
        "\\section{Discussion}\n"
        "Sherpa provides the fitting environment, but this manuscript must separately document fit failures before using fitted parameters \\citep{Freeman2001Sherpa14}.\n",
        encoding="utf-8",
    )
    return project_path


class CitationAuditRepairTests(unittest.TestCase):
    def test_audit_repair_loop_writes_iteration_and_final_html_reports(self) -> None:
        from draftpaper_cli.citation_audit import audit_citations
        from draftpaper_cli.citation_repair import apply_citation_repair, generate_citation_repair_plan

        with tempfile.TemporaryDirectory() as tmp:
            project_path = _write_minimal_citation_project(tmp)

            audit = audit_citations(project_path)

            self.assertEqual(audit["status"], "failed")
            self.assertEqual(audit["summary"]["unsupported"], 1)
            self.assertTrue((project_path / "citation_audit" / "citation_audit_report.html").exists())
            self.assertTrue(list((project_path / "citation_audit" / "iterations").glob("citation_audit_iteration_*.html")))

            plan = generate_citation_repair_plan(project_path)
            self.assertEqual(plan["status"], "repair_plan_written")
            self.assertEqual(plan["issue_count"], 1)
            self.assertTrue((project_path / "citation_audit" / "citation_repair_plan.html").exists())

            applied = apply_citation_repair(project_path)
            self.assertEqual(applied["status"], "applied")
            self.assertEqual(applied["applied_action_count"], 1)

            final_audit = audit_citations(project_path, final=True)
            self.assertEqual(final_audit["status"], "passed")
            self.assertEqual(final_audit["summary"]["unsupported"], 0)
            self.assertTrue((project_path / "citation_audit" / "final_citation_audit_report.html").exists())

    def test_cli_commands_run_citation_repair_loop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_path = _write_minimal_citation_project(tmp)

            audit = subprocess.run(
                [sys.executable, "-m", "draftpaper_cli.cli", "audit-citations", "--project", str(project_path)],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(audit.returncode, 1)
            self.assertEqual(json.loads(audit.stdout)["status"], "failed")

            repair = subprocess.run(
                [sys.executable, "-m", "draftpaper_cli.cli", "run-citation-repair-loop", "--project", str(project_path)],
                check=True,
                capture_output=True,
                text=True,
            )
            payload = json.loads(repair.stdout)
            self.assertEqual(payload["status"], "passed")
            self.assertTrue((project_path / "citation_audit" / "final_citation_audit_report.html").exists())

    def test_contextual_method_citations_are_preserved_and_repair_prefers_rewrite(self) -> None:
        from draftpaper_cli.citation_audit import audit_citations
        from draftpaper_cli.citation_repair import generate_citation_repair_plan

        with tempfile.TemporaryDirectory() as tmp:
            project_path = _write_citation_preservation_project(tmp)

            audit = audit_citations(project_path)
            sherpa_usage = next(
                usage for usage in audit["usages"]
                if usage["citation_key"] == "Freeman2001Sherpa14" and usage["section"] == "methods"
            )

            self.assertEqual(sherpa_usage["citation_intent"], "method_tool_background")
            self.assertEqual(sherpa_usage["support_status"], "contextually_relevant")
            self.assertGreaterEqual(sherpa_usage["topic_relevance_score"], 0.45)
            self.assertFalse(sherpa_usage["blocking"])

            plan = generate_citation_repair_plan(project_path)
            sherpa_issue = next(
                issue for issue in plan["issues"]
                if issue["citation_key"] == "Freeman2001Sherpa14" and issue["section"] == "methods"
            )
            self.assertEqual(sherpa_issue["action"], "rewrite_to_supported_claim")
            self.assertNotEqual(sherpa_issue["action"], "remove_unsupported_claim")
            self.assertIn("Sherpa is the CIAO modeling and fitting application", sherpa_issue["suggested_claim"])

    def test_reference_coverage_report_tracks_uncited_and_topic_suspect_summaries(self) -> None:
        from draftpaper_cli.citation_audit import audit_citations

        with tempfile.TemporaryDirectory() as tmp:
            project_path = _write_citation_preservation_project(tmp)

            report = audit_citations(project_path)
            coverage = report["reference_coverage"]

            self.assertEqual(coverage["total_summarized_references"], 4)
            self.assertIn("Unused2025Relevant", coverage["summarized_but_uncited"])
            self.assertIn("OffTopic2024Policy", coverage["topic_suspect_references"])
            self.assertTrue((project_path / "citation_audit" / "reference_coverage_report.json").exists())
            self.assertTrue((project_path / "citation_audit" / "reference_coverage_report.html").exists())


if __name__ == "__main__":
    unittest.main()
