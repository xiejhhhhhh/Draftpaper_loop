from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from draftpaper_cli.evidence_snapshot import manuscript_snapshot
from draftpaper_cli.project_scaffold import create_project


class FinalConfirmationV026Tests(unittest.TestCase):
    def test_final_release_binds_pdf_citations_two_reviews_and_quality(self) -> None:
        from draftpaper_cli.final_manuscript_confirmation import (
            confirm_final_manuscript,
            final_confirmation_state,
            review_final_manuscript,
        )

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Final paper", field="astronomy")
            artifacts = {
                "latex/main.pdf": b"%PDF-1.4\n",
                "writing/manuscript_completion/active_completion_manifest.json": json.dumps({"status": "applied", "packet_id": "packet:test", "packet_hash": "a" * 64, "applied_at": "2026-07-18T08:00:00+00:00"}).encode(),
                "writing/manuscript_metadata.yaml": b"title: Final paper\n",
                "introduction/introduction.tex": b"\\section{Introduction}\nFinal.\n",
                "data/data.tex": b"\\section{Data}\nFinal.\n",
                "methods/methods.tex": b"\\section{Methods}\nFinal.\n",
                "results/results.tex": b"\\section{Results}\nFinal.\n",
                "discussion/discussion.tex": b"\\section{Discussion}\nFinal.\n",
                "references/library.bib": b"@article{Test2026,title={Test},year={2026}}\n",
                "latex/library.bib": b"@article{Test2026,title={Test},year={2026}}\n",
                "references/reference_registry.json": json.dumps({"status": "passed"}).encode(),
                "results/promoted_evidence_snapshot.json": json.dumps({"snapshot_id": "evidence:test", "artifacts": {}}).encode(),
                "results/result_manifest.yaml": b"schema_version: dpl.result_manifest.v2\nstatus: passed\n",
                "results/figure_metadata.json": json.dumps({"status": "passed"}).encode(),
                "core_evidence/core_evidence_report.json": json.dumps({"decision": "pass"}).encode(),
                "integrity/integrity_report.json": json.dumps({"status": "passed"}).encode(),
                "quality_checks/blind_reviews/aggregate.json": json.dumps({"status": "passed", "reviewer_count": 2}).encode(),
                "quality_checks/blind_reviews/reviewer_01/report.md": b"# Reviewer 1\n",
                "quality_checks/blind_reviews/reviewer_02/report.md": b"# Reviewer 2\n",
                "quality_checks/quality_report.json": json.dumps({"status": "passed"}).encode(),
            }
            for relative, content in artifacts.items():
                path = project.path / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
            citation_snapshot = manuscript_snapshot(project.path)
            citation = project.path / "citation_audit" / "final_citation_audit_report.json"
            citation.parent.mkdir(parents=True, exist_ok=True)
            citation.write_text(
                json.dumps({"status": "passed", "generated_at": "2026-07-18T09:00:00+00:00", "manuscript_snapshot": citation_snapshot}),
                encoding="utf-8",
            )
            review = review_final_manuscript(project.path)
            confirmed = confirm_final_manuscript(project.path, release_hash=review["release_hash"])
            self.assertEqual(confirmed["status"], "approved")
            self.assertTrue(final_confirmation_state(project.path)["current"])
            (project.path / "latex" / "main.pdf").write_bytes(b"%PDF-1.5\nchanged")
            self.assertEqual(final_confirmation_state(project.path)["status"], "release_drift")


if __name__ == "__main__":
    unittest.main()
