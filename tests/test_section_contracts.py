# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import unittest

from draftpaper_cli.section_contracts import validate_section_writing


REGISTRY = {
    "records": [
        {"entity_role": "result_metric_f1_macro", "value": 0.8667, "unit": "score"},
        {"entity_role": "source_count", "value": 60, "unit": "count"},
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


if __name__ == "__main__":
    unittest.main()
