# Copyright (c) 2026 xiejhhhhhh
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest

from draftpaper_cli.data_feasibility import assess_data_feasibility, assess_data_quality, inventory_data
from draftpaper_cli.method_plan import collect_method_plan
from draftpaper_cli.methods import write_methods
from draftpaper_cli.project_scaffold import create_project


class ObservationDrivenWriterTests(unittest.TestCase):
    def prepare_project(self, tmp: str):
        project = create_project(
            root=tmp,
            idea="Exploratory wheat NDVI yield nitrogen proxy analysis",
            field="remote sensing agronomy",
        )
        (project.path / "research_plan" / "research_plan.md").write_text(
            "# Plan\n\nThis is an exploratory proxy-variable analysis of wheat NDVI, yield response, and nitrogen-related environmental variables.\n",
            encoding="utf-8",
        )
        rows = "\n".join(f"{index},wheat,{0.2 + index / 1000:.3f},{index % 9},{index % 5}" for index in range(1, 45))
        (project.path / "data" / "processed" / "wheat_ndvi_yield_proxy.csv").write_text(
            "sample_id,crop,ndvi,yield,tnc\n" + rows + "\n",
            encoding="utf-8",
        )
        inventory_data(project.path)
        assess_data_quality(project.path, required_columns=["ndvi", "yield", "tnc"])
        assess_data_feasibility(project.path, min_rows=30)
        collect_method_plan(
            project.path,
            user_method="Use descriptive statistics, correlation analysis, and univariate yield baselines from the processed wheat analysis table.",
            primary_metric="r2",
            minimum_primary_metric=0.05,
        )
        (project.path / "results" / "tables" / "metrics.csv").write_text("metric,value\nr2,0.12\n", encoding="utf-8")
        (project.path / "methods" / "run_manifest.yaml").write_text(
            json.dumps({
                "status": "success",
                "command": "python code/scripts/run_analysis.py",
                "input_data": ["data/processed/wheat_ndvi_yield_proxy.csv"],
                "output_files": ["results/tables/metrics.csv"],
                "metrics": {"r2": "0.12"},
                "figures_generated": [],
                "tables_generated": ["results/tables/metrics.csv"],
            }),
            encoding="utf-8",
        )
        return project

    def test_data_writer_uses_observation_context_without_file_paths(self) -> None:
        from draftpaper_cli.data_feasibility import build_data_writing_context, write_data
        from draftpaper_cli.observations import record_observation

        with tempfile.TemporaryDirectory() as tmp:
            project = self.prepare_project(tmp)
            record_observation(
                project.path,
                stage="data",
                kind="agent_analysis",
                text=(
                    "The available evidence represents a processed wheat analysis table with NDVI as the canopy "
                    "remote-sensing indicator, yield as the agronomic response, and TNC as a nitrogen-related proxy variable."
                ),
            )

            context = build_data_writing_context(project.path)
            result = write_data(project.path)

            self.assertEqual(result["status"], "written")
            self.assertIn("processed wheat analysis table", context["narrative_summary"])
            data_tex = (project.path / "data" / "data.tex").read_text(encoding="utf-8")
            self.assertIn("NDVI", data_tex)
            self.assertIn("nitrogen-related proxy", data_tex)
            self.assertNotIn("wheat_ndvi_yield_proxy.csv", data_tex)
            self.assertNotIn("data/processed", data_tex)
            self.assertTrue((project.path / "data" / "data_writing_context.html").exists())

    def test_methods_writer_uses_method_context_without_commands_or_paths(self) -> None:
        from draftpaper_cli.methods import build_method_writing_context
        from draftpaper_cli.observations import record_observation

        with tempfile.TemporaryDirectory() as tmp:
            project = self.prepare_project(tmp)
            record_observation(
                project.path,
                stage="methods",
                kind="method_rationale",
                text=(
                    "The method should be framed as an exploratory association workflow: summarize variable distributions, "
                    "estimate pairwise relationships, and report a conservative univariate yield baseline."
                ),
            )

            context = build_method_writing_context(project.path)
            result = write_methods(project.path)

            self.assertEqual(result["status"], "written")
            self.assertIn("exploratory association workflow", context["narrative_summary"])
            methods_tex = (project.path / "methods" / "methods.tex").read_text(encoding="utf-8")
            self.assertIn("correlation", methods_tex.lower())
            self.assertIn("univariate", methods_tex.lower())
            self.assertNotIn("code/scripts/run_analysis.py", methods_tex)
            self.assertNotIn("data/processed", methods_tex)
            self.assertNotIn("\\texttt", methods_tex)
            self.assertTrue((project.path / "methods" / "method_writing_context.html").exists())

    def test_cli_records_observation_and_writes_data_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = self.prepare_project(tmp)
            recorded = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "draftpaper_cli.cli",
                    "record-observation",
                    "--project",
                    str(project.path),
                    "--stage",
                    "data",
                    "--kind",
                    "agent_analysis",
                    "--text",
                    "The dataset contains wheat canopy indicators and yield response variables.",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(json.loads(recorded.stdout)["status"], "recorded")

            context = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "draftpaper_cli.cli",
                    "build-data-context",
                    "--project",
                    str(project.path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(json.loads(context.stdout)["status"], "written")


if __name__ == "__main__":
    unittest.main()
