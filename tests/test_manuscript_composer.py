# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import tempfile
import unittest

from draftpaper_cli.manuscript_composer import (
    SectionCompositionError,
    accept_section_draft,
    build_section_evidence_packet,
    select_validated_section_draft,
    submit_section_draft,
)
from draftpaper_cli.project_scaffold import create_project


class ManuscriptComposerTests(unittest.TestCase):
    EVIDENCE_REGISTRY = (
        '{"records":[{"evidence_id":"metric-main","entity_role":"result_metric_f1_macro",'
        '"value":0.8667,"unit":"score","metric_dimension":"score","run_id":"run-1",'
        '"cohort_id":"main","sample_unit":"model_evaluation","split":"held_out","model_id":"classifier"}]}'
    )

    def test_free_candidate_is_selected_after_contract_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Free Results", field="machine learning")
            (project.path / "writing" / "scientific_evidence_registry.json").write_text(
                self.EVIDENCE_REGISTRY,
                encoding="utf-8",
            )
            candidate = project.path / "writing" / "candidates" / "results.tex"
            candidate.parent.mkdir(parents=True, exist_ok=True)
            candidate.write_text(
                "Across the held-out evaluation, the strongest model reached macro-F1=0.8667.",
                encoding="utf-8",
            )

            packet = build_section_evidence_packet(project.path, "results")
            selected = select_validated_section_draft(project.path, "results", "Fallback prose.")

            self.assertEqual(selected["composition_mode"], "codex_free_candidate")
            self.assertIn("0.8667", selected["text"])
            self.assertEqual(packet["section"], "results")

    def test_invalid_candidate_is_rejected_instead_of_silently_using_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Grounded Results", field="machine learning")
            (project.path / "writing" / "scientific_evidence_registry.json").write_text(
                self.EVIDENCE_REGISTRY,
                encoding="utf-8",
            )
            candidate = project.path / "writing" / "candidates" / "results.tex"
            candidate.parent.mkdir(parents=True, exist_ok=True)
            candidate.write_text("The model reached F1=0.5.", encoding="utf-8")

            with self.assertRaises(SectionCompositionError):
                select_validated_section_draft(project.path, "results", "Fallback prose.")

    def test_submit_section_draft_validates_before_installing_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Submit free draft", field="machine learning")
            (project.path / "writing" / "scientific_evidence_registry.json").write_text(
                self.EVIDENCE_REGISTRY,
                encoding="utf-8",
            )
            source = project.path / "free_results.tex"
            source.write_text("The held-out macro-F1 was 0.8667.", encoding="utf-8")

            report = submit_section_draft(project.path, "results", source)

            self.assertEqual(report["status"], "accepted")
            self.assertTrue((project.path / "writing" / "candidates" / "results.tex").exists())

    def test_section_acceptance_requires_current_scientific_editor_pass(self) -> None:
        import hashlib
        import json

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Accept free draft", field="machine learning")
            (project.path / "writing" / "scientific_evidence_registry.json").write_text(
                self.EVIDENCE_REGISTRY,
                encoding="utf-8",
            )
            source = project.path / "free_results.tex"
            text = "The held-out comparison showed a macro-F1 of 0.8667; Figure 1 reports the pattern, while the uncertainty boundary limits interpretation."
            source.write_text(text, encoding="utf-8")
            report = submit_section_draft(project.path, "results", source)
            report["quality_parity_eligible"] = True
            validation_path = project.path / "writing" / "section_validation" / "results.json"
            validation_path.write_text(json.dumps(report), encoding="utf-8")

            with self.assertRaises(SectionCompositionError):
                accept_section_draft(project.path, "results")

            digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
            editor = project.path / "writing" / "scientific_editor" / "results.json"
            editor.parent.mkdir(parents=True, exist_ok=True)
            editor.write_text(json.dumps({"decision": "pass", "source_hash": digest, "tasks": []}), encoding="utf-8")
            accepted = accept_section_draft(project.path, "results")
            self.assertEqual(accepted["status"], "accepted")
            self.assertTrue(accepted["formal_release_eligible"])


if __name__ == "__main__":
    unittest.main()
