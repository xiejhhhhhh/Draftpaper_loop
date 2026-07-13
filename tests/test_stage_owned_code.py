# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import csv
import json
import subprocess
import sys
import tempfile
import unittest

from draftpaper_cli.data_feasibility import assess_data_feasibility, assess_data_quality, build_data_writing_context, inventory_data
from draftpaper_cli.discussion import prepare_discussion_comparison
from draftpaper_cli.method_plan import collect_method_plan
from draftpaper_cli.methods import build_method_writing_context
from draftpaper_cli.project_scaffold import create_project


class StageOwnedCodeTests(unittest.TestCase):
    def _project_with_legacy_code(self, tmp: str):
        project = create_project(
            root=tmp,
            idea="Time-aware transformer classification of X-ray flaring sources",
            field="astronomy machine learning",
        )
        (project.path / "research_plan" / "research_plan.md").write_text(
            "# Research Plan\n\nUse long-term light curves and spectral features to classify X-ray flaring sources.\n",
            encoding="utf-8",
        )
        (project.path / "data" / "processed" / "event_samples.csv").write_text(
            "source_id,label,rate,hardness\ns1,AGN,1.2,0.4\ns2,XRB,2.1,0.8\ns3,AGN,1.5,0.5\n",
            encoding="utf-8",
        )
        inventory_data(project.path)
        assess_data_quality(project.path, required_columns=["source_id", "label", "rate"])
        assess_data_feasibility(project.path, min_rows=2)
        collect_method_plan(
            project.path,
            user_method="Use time-aware sequence modeling, class-support checks, and source-level validation.",
            primary_metric="f1",
            minimum_primary_metric=0.6,
        )
        (project.path / "code" / "build_event_inputs.py").write_text(
            "import csv\n# build event-level transformer data from remote or processed source tables\n",
            encoding="utf-8",
        )
        (project.path / "code" / "train_timeaware_transformer.py").write_text(
            "import math\n# draftpaper:formula id=cross_entropy latex=L=-\\sum_i y_i\\log p_i variables=y_i,p_i\n"
            "def cross_entropy(probabilities):\n    return -sum(math.log(max(p, 1e-6)) for p in probabilities)\n",
            encoding="utf-8",
        )
        (project.path / "code" / "make_final_figures.py").write_text(
            "from pathlib import Path\n"
            "# figure fig_1_light_curve_feature_distribution uses rate and hardness\n"
            "Path('results/figures/fig_1_light_curve_feature_distribution.png').parent.mkdir(parents=True, exist_ok=True)\n",
            encoding="utf-8",
        )
        (project.path / "results" / "figure_metadata.json").write_text(
            json.dumps(
                {
                    "figures": [
                        {
                            "figure_id": "fig_1_light_curve_feature_distribution",
                            "path": "results/figures/fig_1_light_curve_feature_distribution.png",
                            "interpretation_summary": "Rate and hardness define the first feature-space diagnostic.",
                            "statistics": {"class_count": 2},
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        (project.path / "results" / "tables" / "metrics.csv").write_text("metric,value\nf1,0.71\n", encoding="utf-8")
        (project.path / "methods" / "run_manifest.yaml").write_text(
            json.dumps(
                {
                    "status": "success",
                    "command": "python methods/scripts/train_timeaware_transformer.py",
                    "input_data": ["data/processed/event_samples.csv"],
                    "output_files": ["results/tables/metrics.csv"],
                    "metrics": {"f1": "0.71"},
                }
            ),
            encoding="utf-8",
        )
        return project

    def test_classifies_routes_and_traces_legacy_code(self) -> None:
        from draftpaper_cli.code_ownership import (
            build_code_provenance,
            classify_code_ownership,
            extract_method_formulas,
            route_stage_code,
            trace_figures_to_code,
        )

        with tempfile.TemporaryDirectory() as tmp:
            project = self._project_with_legacy_code(tmp)

            classification = classify_code_ownership(project.path)
            self.assertEqual(classification["status"], "written")
            roles = {item["source_path"]: item["owner_stage"] for item in classification["files"]}
            self.assertEqual(roles["code/build_event_inputs.py"], "data")
            self.assertEqual(roles["code/train_timeaware_transformer.py"], "methods")
            self.assertEqual(roles["code/make_final_figures.py"], "methods")

            routed = route_stage_code(project.path, mode="copy", keep_compat_launchers=True)
            self.assertEqual(routed["status"], "written")
            self.assertTrue((project.path / "data" / "scripts" / "build_event_inputs.py").exists())
            self.assertTrue((project.path / "methods" / "scripts" / "train_timeaware_transformer.py").exists())
            self.assertTrue((project.path / "methods" / "plotting" / "make_final_figures.py").exists())
            self.assertTrue((project.path / "data" / "data_code_manifest.json").exists())
            self.assertTrue((project.path / "methods" / "method_code_manifest.json").exists())

            provenance = build_code_provenance(project.path)
            self.assertEqual(provenance["status"], "written")
            self.assertTrue((project.path / "code" / "code_ownership_manifest.json").exists())
            self.assertGreaterEqual(provenance["file_count"], 3)

            formulas = extract_method_formulas(project.path)
            self.assertEqual(formulas["status"], "written")
            formula_tex = (project.path / "methods" / "method_formulas.tex").read_text(encoding="utf-8")
            self.assertIn("cross_entropy", formula_tex)
            self.assertIn("\\sum_{i=1}", formula_tex)

            trace = trace_figures_to_code(project.path)
            self.assertEqual(trace["status"], "written")
            self.assertTrue((project.path / "results" / "figure_code_trace.json").exists())
            self.assertEqual(trace["traces"][0]["code_files"][0], "methods/plotting/make_final_figures.py")

    def test_cli_stage_code_commands(self) -> None:
        from draftpaper_cli.passport import refresh_project_passport

        with tempfile.TemporaryDirectory() as tmp:
            project = self._project_with_legacy_code(tmp)
            refresh_project_passport(project.path)
            for command in [
                "classify-code-ownership",
                "route-stage-code",
                "build-code-provenance",
                "extract-method-formulas",
                "trace-figures-to-code",
            ]:
                completed = subprocess.run(
                    [sys.executable, "-m", "draftpaper_cli.cli", command, "--project", str(project.path)],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(json.loads(completed.stdout)["status"], "written")

    def test_writing_contexts_require_stage_owned_code_manifests(self) -> None:
        from draftpaper_cli.code_ownership import extract_method_formulas, route_stage_code, trace_figures_to_code

        with tempfile.TemporaryDirectory() as tmp:
            project = self._project_with_legacy_code(tmp)
            route_stage_code(project.path)
            extract_method_formulas(project.path)
            trace_figures_to_code(project.path)

            data_context = build_data_writing_context(project.path)
            method_context = build_method_writing_context(project.path)

            self.assertIn("data_code_manifest", data_context)
            self.assertIn("data acquisition or preprocessing code record", data_context["narrative_summary"])
            self.assertIn("method_code_manifest", method_context)
            self.assertIn("formula_manifest", method_context)
            self.assertIn("figure_code_trace", method_context)
            self.assertIn("cross_entropy", json.dumps(method_context["formula_manifest"]))

    def test_discussion_comparison_matrix_is_prepared_before_discussion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = self._project_with_legacy_code(tmp)
            (project.path / "introduction" / "introduction.tex").write_text(
                "\\section{Introduction}\nPrior source classification studies motivate this work \\citep{Smith2024}.\n",
                encoding="utf-8",
            )
            (project.path / "results" / "results.tex").write_text(
                "\\section{Results}\nThe verified model reached F1=0.71 in Figure~\\ref{fig:1}.\n",
                encoding="utf-8",
            )
            (project.path / "references" / "citation_evidence.csv").write_text(
                "citation_key,section,claim,evidence_summary,source,doi,url\n"
                "Smith2024,discussion,method comparison,Prior work reports transformer classification for variable X-ray sources,semantic_scholar,10.1/example,https://example.org\n",
                encoding="utf-8",
            )
            (project.path / "references" / "library.bib").write_text(
                "@article{Smith2024,title={Transformer classification},year={2024}}\n",
                encoding="utf-8",
            )
            (project.path / "references" / "literature_items.json").write_text(
                json.dumps(
                    [
                        {
                            "bibtex_key": "Smith2024",
                            "title": "Transformer classification",
                            "year": 2024,
                            "abstract": "Prior work reports transformer classification for variable X-ray sources.",
                            "deep_summary": {"results": "Transformer validation metrics provide comparison context."},
                        }
                    ]
                ),
                encoding="utf-8",
            )

            report = prepare_discussion_comparison(project.path)

            self.assertEqual(report["status"], "written")
            self.assertTrue((project.path / "discussion" / "comparison_literature_matrix.csv").exists())
            self.assertTrue((project.path / "discussion" / "comparison_evidence_notes.html").exists())
            with (project.path / "discussion" / "comparison_literature_matrix.csv").open(encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[0]["citation_key"], "Smith2024")
            self.assertIn("F1", rows[0]["result_anchor"])


if __name__ == "__main__":
    unittest.main()
