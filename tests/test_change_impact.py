# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import unittest

from draftpaper_cli.change_impact import affected_stages, artifact_role_for_path, classify_change


class ChangeImpactTests(unittest.TestCase):
    def test_code_and_result_control_manifests_have_narrow_scientific_roles(self) -> None:
        from draftpaper_cli.change_impact import artifact_role_for_path

        self.assertEqual(
            artifact_role_for_path("methods/method_code_manifest.json"),
            ("method_config", "methods"),
        )
        self.assertEqual(
            artifact_role_for_path("data/external_data_locators.json"),
            ("data_schema", "data"),
        )
        self.assertEqual(
            artifact_role_for_path("data/scripts/audit_image_quality.py"),
            ("data_code", "data"),
        )
        self.assertEqual(
            artifact_role_for_path("results/figure_quality_report.json"),
            ("result_manifest", "results"),
        )
        self.assertEqual(
            artifact_role_for_path("core_evidence/core_evidence_report.json"),
            ("evidence_assessment", "core_evidence"),
        )

    def test_derived_core_evidence_report_does_not_invalidate_scientific_sources(self) -> None:
        change = classify_change(
            artifact_role="evidence_assessment",
            before="old-report",
            after="new-report",
            source_stage="core_evidence",
        )

        self.assertEqual(change.change_class, "derived_assessment")
        self.assertEqual(affected_stages(change), ["core_evidence"])

    def test_local_citation_repair_does_not_invalidate_empirical_pipeline(self) -> None:
        change = classify_change(
            artifact_role="citation_repair",
            before="The method is established \\citep{Old}.",
            after="The method provides contextual precedent \\citep{New}.",
            source_stage="discussion",
            declaration={"claim_semantics_changed": False},
        )

        self.assertEqual(change.change_class, "citation_local")
        self.assertEqual(
            affected_stages(change),
            ["discussion", "citation_audit", "latex", "quality_checks"],
        )

    def test_cosmetic_figure_change_only_invalidates_presentation_consumers(self) -> None:
        change = classify_change(
            artifact_role="figure",
            before=b"old-png",
            after=b"new-png",
            source_stage="results",
            declaration={
                "cosmetic_only": True,
                "before_evidence_fingerprint": "same",
                "after_evidence_fingerprint": "same",
            },
        )

        self.assertEqual(change.change_class, "presentation_only")
        self.assertEqual(
            affected_stages(change),
            ["results", "latex", "quality_checks"],
        )

    def test_reference_metadata_only_change_does_not_invalidate_research_evidence(self) -> None:
        fingerprint = {
            "citation_key_count": 2,
            "work_count": 2,
            "citation_keys_sha256": "same-keys",
            "work_ids_sha256": "same-works",
        }
        change = classify_change(
            artifact_role="reference_library",
            before="old-bib-hash",
            after="new-bib-hash",
            source_stage="references",
            declaration={
                "before_semantic_fingerprint": fingerprint,
                "after_semantic_fingerprint": dict(fingerprint),
            },
        )

        self.assertEqual(change.change_class, "reference_metadata_only")
        self.assertEqual(affected_stages(change), ["references", "citation_audit", "latex", "quality_checks"])

    def test_scientific_figure_change_invalidates_all_manuscript_consumers(self) -> None:
        change = classify_change(
            artifact_role="figure",
            before=b"old-png",
            after=b"new-png",
            source_stage="results",
        )

        self.assertEqual(change.change_class, "scientific_result")
        self.assertEqual(
            affected_stages(change),
            [
                "result_validity",
                "core_evidence",
                "results",
                "introduction",
                "data_writing",
                "methods_writing",
                "discussion",
                "citation_audit",
                "latex",
                "quality_checks",
            ],
        )

    def test_method_change_invalidates_verification_and_downstream_evidence(self) -> None:
        change = classify_change(
            artifact_role="method_code",
            before="old model",
            after="new model",
            source_stage="methods",
        )

        self.assertEqual(change.change_class, "method_semantic")
        self.assertIn("methods", affected_stages(change))
        self.assertIn("core_evidence", affected_stages(change))
        self.assertIn("citation_audit", affected_stages(change))

    def test_research_design_change_invalidates_every_downstream_stage(self) -> None:
        change = classify_change(
            artifact_role="research_plan",
            before="old question",
            after="new question",
            source_stage="research_plan",
        )

        impacted = affected_stages(change)
        self.assertEqual(change.change_class, "research_design")
        self.assertEqual(impacted[0], "research_plan")
        self.assertIn("data", impacted)
        self.assertIn("methods", impacted)
        self.assertIn("quality_checks", impacted)

    def test_artifact_paths_distinguish_manuscript_prose_from_scientific_data(self) -> None:
        self.assertEqual(artifact_role_for_path("data/data.tex"), ("section_prose", "data_writing"))
        self.assertEqual(artifact_role_for_path("data/processed/sample.csv"), ("processed_data", "data"))
        self.assertEqual(artifact_role_for_path("results/figures/main.png"), ("figure", "results"))
        self.assertEqual(artifact_role_for_path("latex/sections/results.tex"), ("latex_style", "latex"))


if __name__ == "__main__":
    unittest.main()
