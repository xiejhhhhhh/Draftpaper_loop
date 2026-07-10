# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import tempfile
import unittest

from draftpaper_cli.evidence_snapshot import (
    EvidenceSnapshotMismatch,
    create_evidence_snapshot,
    manuscript_snapshot,
    reopen_evidence_snapshot,
    validate_citation_audit_snapshot,
    validate_evidence_snapshot,
)
from draftpaper_cli.project_scaffold import create_project


class EvidenceSnapshotTests(unittest.TestCase):
    def test_scientific_figure_change_invalidates_promoted_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Snapshot test", field="astronomy")
            figure = project.path / "results" / "figures" / "main.png"
            figure.write_bytes(b"approved-png")
            (project.path / "results" / "resolved_result_evidence.json").write_text(
                '{"run_id":"run-1","primary_metric":{"value":0.8667}}',
                encoding="utf-8",
            )

            snapshot = create_evidence_snapshot(project.path)
            figure.write_bytes(b"changed-png")

            with self.assertRaises(EvidenceSnapshotMismatch):
                validate_evidence_snapshot(project.path, snapshot["snapshot_id"])

    def test_unchanged_snapshot_validates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Stable snapshot", field="geography")
            figure = project.path / "results" / "figures" / "main.png"
            figure.write_bytes(b"stable")

            snapshot = create_evidence_snapshot(project.path)
            validated = validate_evidence_snapshot(project.path, snapshot["snapshot_id"])

            self.assertEqual(validated["snapshot_id"], snapshot["snapshot_id"])

    def test_section_change_after_citation_audit_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Citation order", field="machine learning")
            section = project.path / "discussion" / "discussion.tex"
            section.write_text("Original discussion.", encoding="utf-8")
            audit_binding = manuscript_snapshot(project.path)
            section.write_text("Changed after citation audit.", encoding="utf-8")

            with self.assertRaises(EvidenceSnapshotMismatch):
                validate_citation_audit_snapshot(project.path, audit_binding)

    def test_reopen_archives_snapshot_and_unlocks_scientific_revision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Reopen evidence", field="geography")
            (project.path / "results" / "figures" / "main.png").write_bytes(b"approved")
            snapshot = create_evidence_snapshot(project.path)

            report = reopen_evidence_snapshot(project.path, reason="Replace a scientifically incorrect figure.")

            self.assertEqual(report["status"], "reopened")
            self.assertEqual(report["archived_snapshot_id"], snapshot["snapshot_id"])
            self.assertFalse((project.path / "results" / "promoted_evidence_snapshot.json").exists())
            self.assertTrue((project.path / "results" / "evidence_snapshots" / f"{snapshot['snapshot_id']}.json").exists())


if __name__ == "__main__":
    unittest.main()
