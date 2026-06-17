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


if __name__ == "__main__":
    unittest.main()
