from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from draftpaper_cli.artifact_identity import compute_artifact_identity


class ArtifactIdentityTests(unittest.TestCase):
    def test_report_json_ignores_schema_declared_regeneration_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "report.json"
            path.write_text('{"generated_at":"2026-01-01","value":1,"items":[2,3]}\n', encoding="utf-8")
            first = compute_artifact_identity(path, "review/report.json")
            path.write_text('{"items":[2,3],"value":1,"generated_at":"2026-01-02"}\n', encoding="utf-8")
            second = compute_artifact_identity(path, "review/report.json")

            self.assertNotEqual(first["byte_sha256"], second["byte_sha256"])
            self.assertEqual(first["semantic_sha256"], second["semantic_sha256"])
            self.assertEqual(first["evidence_sha256"], second["evidence_sha256"])

    def test_bibliography_evidence_identity_ignores_metadata_only_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "library.bib"
            path.write_text("@article{Work,\n title={A Work},\n doi={10.1000/example},\n year={2026}\n}\n", encoding="utf-8")
            first = compute_artifact_identity(path, "references/library.bib")
            path.write_text(
                "@article{Work,\n title={A Work},\n doi={10.1000/example},\n year={2026},\n volume={4}\n}\n",
                encoding="utf-8",
            )
            second = compute_artifact_identity(path, "references/library.bib")

            self.assertNotEqual(first["byte_sha256"], second["byte_sha256"])
            self.assertNotEqual(first["semantic_sha256"], second["semantic_sha256"])
            self.assertEqual(first["evidence_sha256"], second["evidence_sha256"])
            self.assertEqual(first["semantic_fingerprint"], second["semantic_fingerprint"])

    def test_binary_artifact_identity_does_not_decode_image_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "figure.png"
            path.write_bytes(b"\x89PNG\r\n\x1a\n\xff\x00")
            identity = compute_artifact_identity(path, "results/figures/figure.png")

            self.assertNotEqual(identity["byte_sha256"], identity["semantic_sha256"])
            self.assertEqual(identity["schema_family"], "dpl.binary.v1")
            self.assertTrue(identity["evidence_sha256"])


if __name__ == "__main__":
    unittest.main()
