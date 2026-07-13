from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

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
                "citation_audit/final_citation_audit_report.json": json.dumps({"status": "passed"}).encode(),
                "quality_checks/blind_reviews/aggregate.json": json.dumps({"status": "passed"}).encode(),
                "quality_checks/blind_reviews/reviewer_01/report.md": b"# Reviewer 1\n",
                "quality_checks/blind_reviews/reviewer_02/report.md": b"# Reviewer 2\n",
                "quality_checks/quality_report.json": json.dumps({"status": "passed"}).encode(),
            }
            for relative, content in artifacts.items():
                path = project.path / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
            review = review_final_manuscript(project.path)
            confirmed = confirm_final_manuscript(project.path, release_hash=review["release_hash"])
            self.assertEqual(confirmed["status"], "approved")
            self.assertTrue(final_confirmation_state(project.path)["current"])
            (project.path / "latex" / "main.pdf").write_bytes(b"%PDF-1.5\nchanged")
            self.assertEqual(final_confirmation_state(project.path)["status"], "release_drift")


if __name__ == "__main__":
    unittest.main()
