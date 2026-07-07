# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from draftpaper_cli.project_scaffold import create_project


def write_traceable_project(tmp: str) -> Path:
    project = create_project(
        root=tmp,
        idea="Traceable multimodal astronomy classification",
        field="machine learning astronomy",
        target_journal="APJS",
    )
    project_path = project.path
    (project_path / "references" / "library.bib").write_text(
        "@article{Smith2024Model,\n"
        "  title={Traceable multimodal classification},\n"
        "  author={Smith, Jane},\n"
        "  year={2024},\n"
        "  journal={Astrophysical Journal Supplement Series}\n"
        "}\n",
        encoding="utf-8",
    )
    with (project_path / "references" / "citation_evidence.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["citation_key", "section", "claim", "evidence_summary", "source", "doi", "url"])
        writer.writeheader()
        for section in ["introduction", "data", "methods", "discussion"]:
            writer.writerow({
                "citation_key": "Smith2024Model",
                "section": section,
                "claim": f"{section} claim",
                "evidence_summary": f"Supports the {section} statement.",
                "source": "semantic_scholar",
                "doi": "",
                "url": "https://example.org/smith2024",
            })
    for section in ["introduction", "data", "methods", "discussion"]:
        (project_path / section / f"{section}.tex").write_text(
            f"\\section{{{section.title()}}}\nA traceable statement \\citep{{Smith2024Model}}.\n",
            encoding="utf-8",
        )
    (project_path / "results" / "figures" / "roc_curve.svg").write_text("<svg></svg>\n", encoding="utf-8")
    (project_path / "results" / "tables" / "metrics.csv").write_text("metric,value\nf1,0.91\n", encoding="utf-8")
    (project_path / "results" / "result_manifest.yaml").write_text(
        json.dumps({
            "figures": [{
                "id": "fig_1_roc_curve",
                "path": "results/figures/roc_curve.svg",
                "caption_draft": "Classification performance curve.",
                "result_claim": "The classifier reaches the planned performance threshold.",
            }],
            "tables": [{
                "id": "table_1_metrics",
                "path": "results/tables/metrics.csv",
                "caption_draft": "Primary metric table.",
                "result_claim": "The primary metric table records the validation score.",
            }],
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (project_path / "results" / "results.tex").write_text(
        "\\section{Results}\nThe local artifacts support the reported results.\n",
        encoding="utf-8",
    )
    return project_path


class IntegrityGateTests(unittest.TestCase):
    def test_integrity_gate_passes_traceable_citations_and_result_artifacts(self) -> None:
        from draftpaper_cli.integrity_gate import run_integrity_gate

        with tempfile.TemporaryDirectory() as tmp:
            project_path = write_traceable_project(tmp)

            report = run_integrity_gate(project_path)

            self.assertEqual(report["status"], "passed")
            self.assertEqual(report["error_count"], 0)
            self.assertTrue((project_path / "integrity" / "integrity_report.json").exists())
            self.assertTrue((project_path / "integrity" / "integrity_report.md").exists())
            self.assertEqual(report["citations"]["missing_bib_keys"], [])
            self.assertEqual(report["citations"]["citations_without_evidence"], [])
            self.assertEqual(report["results"]["missing_artifacts"], [])
            ledger = (project_path / "integrity_ledger.jsonl").read_text(encoding="utf-8")
            self.assertIn('"kind": "integrity_gate"', ledger)

    def test_integrity_gate_fails_missing_bib_evidence_and_unbound_result_claim(self) -> None:
        from draftpaper_cli.integrity_gate import run_integrity_gate

        with tempfile.TemporaryDirectory() as tmp:
            project_path = write_traceable_project(tmp)
            (project_path / "introduction" / "introduction.tex").write_text(
                "\\section{Introduction}\nUnsupported citation \\citep{Unknown2026}.\n",
                encoding="utf-8",
            )
            manifest = json.loads((project_path / "results" / "result_manifest.yaml").read_text(encoding="utf-8"))
            manifest["figures"][0]["path"] = "results/figures/missing.svg"
            manifest["tables"][0]["result_claim"] = ""
            (project_path / "results" / "result_manifest.yaml").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
            (project_path / "results" / "results.tex").write_text(
                "\\section{Results}\nResults must not cite \\citep{Smith2024Model}.\n",
                encoding="utf-8",
            )

            report = run_integrity_gate(project_path)

            self.assertEqual(report["status"], "failed")
            codes = {issue["code"] for issue in report["issues"]}
            self.assertIn("missing_bib_key", codes)
            self.assertIn("missing_citation_evidence", codes)
            self.assertIn("results_contains_citation", codes)
            self.assertIn("result_artifact_missing", codes)
            self.assertIn("result_claim_missing", codes)

    def test_integrity_gate_fails_internal_manuscript_language(self) -> None:
        from draftpaper_cli.integrity_gate import run_integrity_gate

        with tempfile.TemporaryDirectory() as tmp:
            project_path = write_traceable_project(tmp)
            (project_path / "methods" / "methods.tex").write_text(
                "\\section{Methods}\nThe stage-owned workflow.html manifest internals and formula extraction layer describe the current draft should be revised.\n",
                encoding="utf-8",
            )

            report = run_integrity_gate(project_path)

            self.assertEqual(report["status"], "failed")
            self.assertGreater(report["manuscript_language"]["finding_count"], 0)
            self.assertIn("manuscript_internal_language", {issue["code"] for issue in report["issues"]})

    def test_integrity_gate_fails_data_result_sample_count_mismatch(self) -> None:
        from draftpaper_cli.integrity_gate import run_integrity_gate

        with tempfile.TemporaryDirectory() as tmp:
            project_path = write_traceable_project(tmp)
            (project_path / "results" / "tables" / "sample_composition.csv").write_text(
                "category,event_count,source_count\nAGN,500,5\nTDE,26,1\nXRB,499,5\n",
                encoding="utf-8",
            )
            (project_path / "data" / "data.tex").write_text(
                "\\section{Data}\nThe study uses 1025 events from 11 sources.\n",
                encoding="utf-8",
            )
            (project_path / "results" / "results.tex").write_text(
                "\\section{Results}\nThe final evidence base contains 6010 events from 60 sources.\n",
                encoding="utf-8",
            )

            report = run_integrity_gate(project_path)

            self.assertEqual(report["status"], "failed")
            self.assertEqual(report["evidence_numbers"]["sample_composition"], {"event_count": 1025, "source_count": 11})
            self.assertIn("evidence_number_mismatch", {issue["code"] for issue in report["issues"]})

    def test_integrity_gate_does_not_compare_context_specific_counts_to_main_sample(self) -> None:
        from draftpaper_cli.integrity_gate import run_integrity_gate

        with tempfile.TemporaryDirectory() as tmp:
            project_path = write_traceable_project(tmp)
            (project_path / "results" / "tables" / "sample_composition.csv").write_text(
                "category,event_count,source_count\nAGN,500,5\nTDE,26,1\nXRB,499,5\n",
                encoding="utf-8",
            )
            (project_path / "data" / "data.tex").write_text(
                "\\section{Data}\nThe study uses 1025 events from 11 sources. "
                "A parser validation subset contains 26 parsed events.\n",
                encoding="utf-8",
            )
            (project_path / "results" / "results.tex").write_text(
                "\\section{Results}\nThe validation split contains 6010 events from 60 sources, "
                "and the temporal encoder receives 49825 source-history tokens.\n",
                encoding="utf-8",
            )

            report = run_integrity_gate(project_path)

            self.assertEqual(report["status"], "passed")
            self.assertEqual(report["evidence_numbers"]["mismatches"], [])
            roles = {count["role"] for count in report["evidence_numbers"]["observed_counts"]}
            self.assertIn("main_modeling_sample", roles)
            self.assertIn("parser_validation_subset", roles)
            self.assertIn("model_validation_subset", roles)
            self.assertIn("history_token_count", roles)

    def test_cli_run_integrity_gate_uses_exit_code_for_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_path = write_traceable_project(tmp)
            passed = subprocess.run(
                [sys.executable, "-m", "draftpaper_cli.cli", "run-integrity-gate", "--project", str(project_path)],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(json.loads(passed.stdout)["status"], "passed")

            (project_path / "references" / "library.bib").write_text("", encoding="utf-8")
            failed = subprocess.run(
                [sys.executable, "-m", "draftpaper_cli.cli", "run-integrity-gate", "--project", str(project_path)],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(failed.returncode, 1)
            self.assertEqual(json.loads(failed.stdout)["status"], "failed")


if __name__ == "__main__":
    unittest.main()
