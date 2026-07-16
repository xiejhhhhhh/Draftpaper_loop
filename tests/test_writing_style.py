# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest

from draftpaper_cli.project_scaffold import create_project
from draftpaper_cli.writing_style import learn_writing_style_from_draft


class WritingStyleLearningTests(unittest.TestCase):
    def test_learn_writing_style_writes_non_verbatim_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Style profile", field="astronomy machine learning")
            draft = project.path / "latex" / "main.tex"
            draft.write_text(
                "\\section{Results}\nThe model reached F1=0.81, which suggests useful but limited discrimination. Figure~\\ref{fig:a} supports this interpretation.\n\n"
                "\\section{Methods}\nThe model optimizes a cross-entropy objective and reports AUC.\n\n"
                "\\section{Discussion}\nCompared with prior work \\citep{Smith2024}, the result is consistent with the expected limitation rather than a complete solution.\n",
                encoding="utf-8",
            )

            result = learn_writing_style_from_draft(project.path, draft)

            self.assertEqual(result["status"], "written")
            profile = json.loads((project.path / "writing" / "style_profile.json").read_text(encoding="utf-8"))
            self.assertEqual(profile["schema_version"], "dpl.writing_style_profile.v2")
            self.assertTrue(profile["results_style"]["uses_scientific_judgment"])
            self.assertIn("first establishes the main empirical pattern", profile["avoid_phrases"])
            self.assertNotIn("The model reached F1=0.81", json.dumps(profile))

    def test_cli_learn_writing_style(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="CLI style profile", field="workflow engineering")
            draft = project.path / "latex" / "main.tex"
            draft.write_text("\\section{Results}\nAUC=0.90 indicates strong discrimination.\n", encoding="utf-8")

            completed = subprocess.run(
                [sys.executable, "-m", "draftpaper_cli.cli", "learn-writing-style-from-draft", "--project", str(project.path), "--draft", str(draft)],
                check=True,
                capture_output=True,
                text=True,
            )

            payload = json.loads(completed.stdout)
            self.assertEqual(payload["status"], "written")

    def test_learn_writing_style_expands_latex_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Input style profile", field="astronomy")
            sections = project.path / "latex" / "sections"
            sections.mkdir(parents=True, exist_ok=True)
            (project.path / "latex" / "main.tex").write_text(
                "\\input{sections/results}\n\\input{sections/methods}\n\\input{sections/discussion}\n",
                encoding="utf-8",
            )
            (sections / "results.tex").write_text(
                "\\section{Results}\nThe reported F1=0.64 indicates a limited but interpretable result.\n",
                encoding="utf-8",
            )
            (sections / "methods.tex").write_text(
                "\\section{Methods}\nThe method uses a masked pooling equation and source-held-out validation.\n",
                encoding="utf-8",
            )
            (sections / "discussion.tex").write_text(
                "\\section{Discussion}\nCompared with prior work \\citep{Smith2024}, the evidence is consistent with a bounded claim.\n",
                encoding="utf-8",
            )

            learn_writing_style_from_draft(project.path, project.path / "latex" / "main.tex")

            profile = json.loads((project.path / "writing" / "style_profile.json").read_text(encoding="utf-8"))
            self.assertGreater(profile["results_style"]["paragraph_count"], 0)
            self.assertTrue(profile["results_style"]["uses_scientific_judgment"])
            self.assertTrue(profile["discussion_style"]["compares_against_literature"])


if __name__ == "__main__":
    unittest.main()
