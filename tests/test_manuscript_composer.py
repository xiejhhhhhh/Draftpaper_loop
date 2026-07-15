# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from draftpaper_cli.manuscript_composer import (
    SectionCompositionError,
    _compact_reference_items,
    _compact_result_manifest,
    _functional_job_coverage,
    accept_section_draft,
    build_section_evidence_packet,
    select_validated_section_draft,
    submit_section_draft,
)
from draftpaper_cli.project_scaffold import create_project


class ManuscriptComposerTests(unittest.TestCase):
    def test_reference_packet_compacts_long_summaries_without_losing_identity(self) -> None:
        compact = _compact_reference_items([{
            "citation_key": "Example2026",
            "title": "A bounded comparison",
            "summary": "evidence " * 200,
            "search_contexts": ["discussion"],
            "authors": ["Internal metadata omitted"],
        }])
        self.assertEqual(compact[0]["citation_key"], "Example2026")
        self.assertLessEqual(len(compact[0]["summary"]), 423)
        self.assertNotIn("authors", compact[0])

    def test_non_results_manifest_omits_repeated_paths_and_caption_text(self) -> None:
        manifest = {
            "figures": [{
                "id": "fig-1", "path": "results/figures/fig_01.png",
                "caption_draft": "A repeated caption.", "result_claim": "A bounded claim.",
            }],
            "tables": [{
                "id": "table-1", "path": "results/tables/table.csv",
                "caption_draft": "A repeated table caption.", "result_claim": "Supporting values.",
            }],
        }

        compact = _compact_result_manifest(manifest, section="discussion")

        self.assertNotIn("path", compact["figures"][0])
        self.assertNotIn("caption_draft", compact["figures"][0])
        self.assertEqual(compact["figures"][0]["result_claim"], "A bounded claim.")
        self.assertEqual(compact["tables"], [{"id": "table-1"}])

    def test_data_packet_exposes_source_provenance_and_required_topics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=Path(tmp), idea="Source provenance", field="astronomy")
            provenance = {
                "source_products": [{"logical_id": "survey-r1", "release": "R1"}],
                "selection_contract": {"duplicate_rule": "one-to-one"},
            }
            (project.path / "data" / "source_provenance.json").write_text(
                json.dumps(provenance), encoding="utf-8"
            )
            packet = build_section_evidence_packet(project.path, "data")
            contract = packet["section_evidence_pack"]["data_writing_contract"]
            self.assertEqual(contract["source_provenance"], provenance)
            self.assertIn("selection, matching, duplicate-resolution, and join rules", contract["required_writer_topics"])
            self.assertTrue(packet["hard_constraints"]["available_data_or_model_provenance_must_be_reported_or_explicitly_bounded"])

    def test_results_packet_carries_non_nested_pipeline_semantics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=Path(tmp), idea="Pipeline comparison", field="machine learning")
            context = {
                "reproducibility_contract": {
                    "preprocessing_components": [{"component": "PCA", "parameters": {"n_components": 64}}],
                    "comparison_semantics_policy": "Non-nested variants require pipeline-performance contrast wording.",
                }
            }
            (project.path / "methods" / "method_writing_context.json").write_text(
                json.dumps(context), encoding="utf-8"
            )

            packet = build_section_evidence_packet(project.path, "results")

            contract = packet["section_evidence_pack"]["model_comparison_contract"]
            self.assertIn("Non-nested", contract["comparison_semantics_policy"])
            self.assertTrue(packet["hard_constraints"]["incremental_or_conditional_model_claim_requires_verified_nested_preprocessing"])

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
            self.assertEqual(packet["schema_version"], "v0.23.1")
            self.assertIn("audit_sources", packet)
            self.assertNotIn("resolved_result_evidence", packet["result_manifest"])
            self.assertEqual(packet["section_lifecycles"], {})

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

    def test_numeric_claim_bindings_are_json_serializable(self) -> None:
        from draftpaper_cli.section_contracts import validate_section_writing

        registry = json.loads(self.EVIDENCE_REGISTRY)
        report = validate_section_writing(
            "results",
            "Across held-out events, the classifier reached macro-F1=0.8667.",
            registry,
        )
        json.dumps(report["numeric_claim_bindings"])

    def test_section_contract_rejects_control_characters_and_unescaped_math_subscripts(self) -> None:
        from draftpaper_cli.section_contracts import validate_section_writing

        control = validate_section_writing("methods", "Where " + chr(8) + "ar{h} denotes the pooled state.", {})
        underscore = validate_section_writing("methods", "Where omega_j denotes a frequency.", {})
        self.assertEqual(control["decision"], "blocked")
        self.assertEqual(underscore["decision"], "blocked")
        self.assertIn("latex_control_character", {item["kind"] for item in control["issues"]})
        self.assertIn("unescaped_underscore_outside_math", {item["kind"] for item in underscore["issues"]})

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
            self.assertEqual(
                (project.path / "writing" / "drafts" / "results.tex").read_text(encoding="utf-8"),
                source.read_text(encoding="utf-8"),
            )

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

    def test_outline_jobs_outrank_unconsolidated_reasoning_rows(self) -> None:
        packet = {
            "section_outline": {"paragraphs": [{"paragraph_id": f"intro-{index}"} for index in range(3)]},
            "section_reasoning_inputs": [{"gap_id": f"gap-{index}"} for index in range(6)],
        }
        text = (
            "Previous studies have shown that image representations preserve useful survey information.\n\n"
            "Yet it remains unclear whether that structure survives independent validation.\n\n"
            "We ask whether the proposed comparison resolves this research question within a bounded cohort."
        )

        report = _functional_job_coverage("introduction", text, packet)

        self.assertEqual(report["expected_paragraph_jobs"], 3)
        self.assertEqual(report["paragraph_coverage"], 1.0)
        self.assertEqual(report["role_coverage"], 1.0)
        self.assertEqual(report["decision"], "pass")


if __name__ == "__main__":
    unittest.main()
