# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import unittest

from draftpaper_cli.section_contracts import validate_section_writing


REGISTRY = {
    "records": [
        {"evidence_id": "metric-main", "entity_role": "result_metric_f1_macro", "value": 0.8667, "unit": "score", "metric_dimension": "score", "run_id": "run-1", "cohort_id": "main", "sample_unit": "source", "split": "source_held_out", "model_id": "classifier"},
        {"evidence_id": "sources-main", "entity_role": "source_count", "value": 60, "unit": "count", "metric_dimension": "count", "run_id": "not_applicable", "cohort_id": "main", "sample_unit": "source", "split": "not_applicable", "model_id": "not_applicable"},
    ]
}


class SectionWritingContractTests(unittest.TestCase):
    def test_repeated_template_sentence_is_rejected(self) -> None:
        sentence = "This evidence establishes the main empirical pattern for the current analysis."
        report = validate_section_writing("discussion", f"{sentence} {sentence}", REGISTRY)

        self.assertIn("repeated_template_sentence", {item["kind"] for item in report["issues"]})

    def test_result_metric_leakage_before_results_is_rejected(self) -> None:
        report = validate_section_writing(
            "introduction",
            "The proposed classifier achieved macro-F1=0.8667 in the present study.",
            REGISTRY,
        )

        self.assertIn("result_metric_leakage", {item["kind"] for item in report["issues"]})

    def test_placeholder_abstract_is_rejected(self) -> None:
        report = validate_section_writing("abstract", "Abstract to be supplied after analysis.", REGISTRY)

        self.assertIn("placeholder_abstract", {item["kind"] for item in report["issues"]})

    def test_results_reject_citations_and_unsupported_numbers(self) -> None:
        report = validate_section_writing(
            "results",
            r"The model reached F1=0.5000 across 60 sources \cite{Example2024}.",
            REGISTRY,
        )

        self.assertEqual(report["decision"], "blocked")
        self.assertIn("results_citation", {item["kind"] for item in report["issues"]})
        self.assertIn("unsupported_numeric_claim", {item["kind"] for item in report["issues"]})

    def test_methods_rejects_unexplained_formula_variables(self) -> None:
        report = validate_section_writing(
            "methods",
            r"We minimized \begin{equation}L=-\sum_i y_i\log p_i\end{equation}.",
            REGISTRY,
        )

        self.assertEqual(report["decision"], "blocked")
        self.assertIn("unexplained_formula_variables", {item["kind"] for item in report["issues"]})

    def test_free_results_prose_passes_when_grounded(self) -> None:
        report = validate_section_writing(
            "results",
            "Across 60 sources, the strongest verified model reached a macro-F1 of 0.8667.",
            REGISTRY,
        )

        self.assertEqual(report["decision"], "pass")

    def test_wrong_cohort_unit_split_and_model_block_even_when_value_exists(self) -> None:
        registry = {"records": [
            {"evidence_id": "main-source-count", "entity_role": "source_count", "value": 60, "unit": "count", "metric_dimension": "count", "run_id": "not_applicable", "cohort_id": "main", "sample_unit": "source", "split": "not_applicable", "model_id": "not_applicable"},
            {"evidence_id": "smoke-source-count", "entity_role": "source_count", "value": 10, "unit": "count", "metric_dimension": "count", "run_id": "not_applicable", "cohort_id": "smoke_test", "sample_unit": "source", "split": "not_applicable", "model_id": "not_applicable"},
            {"evidence_id": "model-a", "entity_role": "result_metric_f1_macro", "value": 0.8, "unit": "score", "metric_dimension": "score", "run_id": "run-a", "cohort_id": "main", "sample_unit": "source", "split": "source_held_out", "model_id": "baseline"},
            {"evidence_id": "model-b", "entity_role": "result_metric_f1_macro", "value": 0.7, "unit": "score", "metric_dimension": "score", "run_id": "run-b", "cohort_id": "main", "sample_unit": "observation", "split": "random_split", "model_id": "transformer"},
        ]}

        wrong_cohort = validate_section_writing("results", "The smoke-test cohort contained 60 sources.", registry)
        wrong_scope = validate_section_writing("results", "The transformer reached macro-F1=0.8 on the random split at observation level.", registry)
        wrong_run = validate_section_writing("results", "Under run-b, the baseline reached macro-F1=0.8 for source-level evidence.", registry)

        self.assertIn("numeric_claim_scope_mismatch", {item["kind"] for item in wrong_cohort["issues"]})
        self.assertIn("numeric_claim_scope_mismatch", {item["kind"] for item in wrong_scope["issues"]})
        self.assertIn("numeric_claim_scope_mismatch", {item["kind"] for item in wrong_run["issues"]})

    def test_zero_one_and_one_hundred_are_not_magic_exemptions(self) -> None:
        registry = {"records": [REGISTRY["records"][0]]}
        report = validate_section_writing("results", "The classifier reached macro-F1=1.0 with 100 sources and zero errors (0).", registry)
        unsupported = [item for item in report["issues"] if item["kind"] == "unsupported_numeric_claim"]
        self.assertGreaterEqual(len(unsupported), 3)

    def test_same_numeric_value_cannot_be_relabelled_as_another_metric(self) -> None:
        report = validate_section_writing(
            "results",
            "The held-out model reached ROC-AUC=0.8667.",
            REGISTRY,
        )

        self.assertIn("numeric_claim_metric_mismatch", {item["kind"] for item in report["issues"]})

    def test_metric_cannot_bind_to_a_record_with_the_wrong_dimension(self) -> None:
        registry = {"records": [{
            **REGISTRY["records"][0],
            "metric_dimension": "count",
            "unit": "count",
        }]}
        report = validate_section_writing(
            "results",
            "The held-out model reached macro-F1=0.8667.",
            registry,
        )

        self.assertIn("numeric_claim_metric_dimension_mismatch", {item["kind"] for item in report["issues"]})


if __name__ == "__main__":
    unittest.main()
