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


if __name__ == "__main__":
    unittest.main()
