# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json
import tempfile
import unittest

from draftpaper_cli.figure_semantic_annotations import submit_figure_semantic_annotations
from draftpaper_cli.project_scaffold import create_project


class FigureSemanticAnnotationTests(unittest.TestCase):
    def test_submit_annotations_requires_evidence_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Legacy figures", field="medicine")
            source = project.path / "annotations.json"
            source.write_text(json.dumps({"annotations": [{
                "figure_id": "fig_1",
                "plot_grammar": "relationship",
                "variable_roles": ["features", "label_or_response"],
                "evidence_source_ids": ["run:1", "table:metrics"],
            }]}), encoding="utf-8")

            report = submit_figure_semantic_annotations(project.path, source)

            self.assertEqual(report["status"], "accepted")
            self.assertTrue((project.path / "results" / "figure_semantic_annotations.json").exists())


if __name__ == "__main__":
    unittest.main()
