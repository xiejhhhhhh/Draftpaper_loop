# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import unittest

from draftpaper_cli.writing_quality import evaluate_section_quality


class WritingQualityTests(unittest.TestCase):
    def test_introduction_requires_natural_prose_length_and_citations(self) -> None:
        tex = "\\section{Introduction}\n\\textbf{Background}\n\\begin{itemize}\\item Too short.\\end{itemize}\n"

        issues = evaluate_section_quality("introduction", tex)

        codes = {issue.code for issue in issues}
        self.assertIn("section_too_short", codes)
        self.assertIn("section_too_few_paragraphs", codes)
        self.assertIn("section_uses_bullets", codes)
        self.assertIn("section_uses_bold", codes)
        self.assertIn("introduction_missing_citations", codes)

    def test_results_requires_enough_figures_no_citations_and_figures_inside_subsections(self) -> None:
        tex = (
            "\\section{Results}\n"
            "\\subsection{First empirical pattern}\n"
            "The pattern is discussed but then a citation appears \\citep{Bad2024}.\n\n"
            "\\subsection{Second empirical pattern}\n"
            "This subsection has prose but no figure artifact at its end.\n"
        )

        issues = evaluate_section_quality("results", tex, figure_count=2)

        codes = {issue.code for issue in issues}
        self.assertIn("results_contains_citation", codes)
        self.assertIn("results_too_few_figures", codes)
        self.assertIn("result_subsection_missing_figure", codes)

    def test_methods_requires_formula_block(self) -> None:
        tex = "\\section{Methods}\nThe model workflow is described in prose without a mathematical statement.\n\n"

        codes = {issue.code for issue in evaluate_section_quality("methods", tex)}

        self.assertIn("methods_missing_formula", codes)

    def test_results_accepts_a_starred_figure_at_the_end_of_a_subsection(self) -> None:
        tex = (
            "\\section{Results}\n"
            "\\subsection{Full-width result}\n"
            "The empirical pattern and its scientific boundary are explained here.\n\n"
            "\\begin{figure*}[htbp]\n"
            "\\includegraphics{result.png}\n"
            "\\caption{A full-width result figure.}\n"
            "\\end{figure*}\n"
        )

        codes = {issue.code for issue in evaluate_section_quality("results", tex, figure_count=5)}

        self.assertNotIn("result_subsection_missing_figure", codes)


if __name__ == "__main__":
    unittest.main()
