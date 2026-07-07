# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from draftpaper_cli.project_scaffold import create_project
from draftpaper_cli.data_feasibility import assess_data_feasibility, assess_data_quality, inventory_data
from draftpaper_cli.method_plan import collect_method_plan


def prepare_passing_data_gate(project_path: Path) -> None:
    (project_path / "research_plan" / "research_plan.md").write_text("# Plan\n\nExploratory pilot analysis.\n", encoding="utf-8")
    rows = "\n".join(f"{i},{i % 2}" for i in range(1, 41))
    (project_path / "data" / "raw" / "sample.csv").write_text("id,target\n" + rows + "\n", encoding="utf-8")
    inventory_data(project_path)
    assess_data_quality(project_path, required_columns=["id", "target"])
    assess_data_feasibility(project_path, min_rows=30)
    collect_method_plan(project_path, user_method="Use supervised classification with light-curve features.", primary_metric="f1", minimum_primary_metric=0.7)


class MethodsHardGateTests(unittest.TestCase):
    def test_write_methods_requires_successful_run_manifest(self) -> None:
        from draftpaper_cli.methods import MethodsGateError, write_methods

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Method gate test", field="workflow engineering")

            with self.assertRaises(MethodsGateError):
                write_methods(project.path)

            self.assertTrue((project.path / "methods" / "method_plan.md").exists())
            self.assertFalse((project.path / "methods" / "methods.tex").exists())

    def test_write_methods_rejects_missing_declared_outputs(self) -> None:
        from draftpaper_cli.methods import MethodsGateError, write_methods

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Missing output test", field="workflow engineering")
            prepare_passing_data_gate(project.path)
            (project.path / "methods" / "run_manifest.yaml").write_text(
                json.dumps({
                    "status": "success",
                    "command": "manual",
                    "input_data": [],
                    "output_files": ["results/tables/missing_metrics.csv"],
                    "metrics": {"accuracy": 0.91},
                    "figures_generated": [],
                    "tables_generated": ["results/tables/missing_metrics.csv"],
                    "started_at": "2026-05-29T00:00:00Z",
                    "finished_at": "2026-05-29T00:00:01Z",
                }),
                encoding="utf-8",
            )

            with self.assertRaises(MethodsGateError):
                write_methods(project.path)

    def test_verify_methods_and_write_methods_success(self) -> None:
        from draftpaper_cli.methods import verify_methods, write_methods

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Transformer AGN prediction", field="machine learning astronomy")
            prepare_passing_data_gate(project.path)
            output = project.path / "results" / "tables" / "metrics.csv"
            command = f"{sys.executable} -c \"from pathlib import Path; Path(r'{output}').write_text('metric,value\\naccuracy,0.91\\n', encoding='utf-8')\""

            verify_result = verify_methods(project.path, command=command, output_files=["results/tables/metrics.csv"])
            self.assertEqual(verify_result["status"], "success")
            self.assertTrue((project.path / "methods" / "run_manifest.yaml").exists())
            run_manifest = json.loads((project.path / "methods" / "run_manifest.yaml").read_text(encoding="utf-8"))
            self.assertFalse(run_manifest["shell_used"])
            self.assertEqual(run_manifest["command_source"], "cli_override")
            self.assertIsInstance(run_manifest["command_argv"], list)
            self.assertTrue(run_manifest["stdout_log"]["path"].replace("\\", "/").startswith("methods/run_logs/"))
            self.assertTrue(run_manifest["stderr_log"]["path"].replace("\\", "/").startswith("methods/run_logs/"))
            self.assertIn("excerpt", run_manifest["stdout_log"])

            write_result = write_methods(project.path)
            self.assertEqual(write_result["status"], "written")
            self.assertTrue((project.path / "methods" / "method_writing_brief.json").exists())
            self.assertTrue((project.path / "methods" / "method_writing_brief.html").exists())
            methods_tex = (project.path / "methods" / "methods.tex").read_text(encoding="utf-8")
            self.assertIn("\\section{Methods}", methods_tex)
            self.assertNotIn("results/tables/metrics.csv", methods_tex)
            self.assertNotIn("code/scripts", methods_tex)
            self.assertNotIn("\\texttt", methods_tex)
            self.assertIn("accuracy", methods_tex)

            manifest = json.loads((project.path / "methods_writing" / "stage_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "draft")
            self.assertIn("methods/method_requirements.json", manifest["input_files"])
            self.assertIn("methods/run_manifest.yaml", manifest["input_files"])
            self.assertIn("methods/method_writing_brief.json", manifest["input_files"])
            self.assertIn("methods/methods.tex", manifest["output_files"])
            self.assertIn("methods/method_writing_brief.json", manifest["output_files"])

    def test_verify_methods_prefers_manifest_argv_over_legacy_string(self) -> None:
        from draftpaper_cli.methods import verify_methods

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Manifest argv method verification", field="workflow engineering")
            prepare_passing_data_gate(project.path)
            output = project.path / "results" / "tables" / "metrics.csv"
            code = (
                "from pathlib import Path; "
                f"Path(r'{output}').parent.mkdir(parents=True, exist_ok=True); "
                f"Path(r'{output}').write_text('metric,value\\naccuracy,0.93\\n', encoding='utf-8')"
            )
            (project.path / "methods" / "method_code_manifest.json").write_text(
                json.dumps({
                    "verify_command_argv": ["{python}", "-c", code],
                    "verify_command": "cmd.exe /c exit 99",
                    "declared_outputs": ["results/tables/metrics.csv"],
                }),
                encoding="utf-8",
            )

            result = verify_methods(project.path)

            self.assertEqual(result["status"], "success")
            manifest = json.loads((project.path / "methods" / "run_manifest.yaml").read_text(encoding="utf-8"))
            self.assertEqual(manifest["command_source"], "method_code_manifest")
            self.assertEqual(Path(manifest["command_argv"][0]).resolve(), Path(sys.executable).resolve())
            self.assertFalse(manifest["shell_used"])
            self.assertEqual(manifest["returncode"], 0)

    def test_verify_methods_rejects_shell_operators_and_shell_runners(self) -> None:
        from draftpaper_cli.methods import MethodsGateError, verify_methods

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Unsafe shell method verification", field="workflow engineering")
            prepare_passing_data_gate(project.path)

            with self.assertRaises(MethodsGateError):
                verify_methods(project.path, command=f"{sys.executable} -c \"print('ok')\" && echo unsafe")

            (project.path / "methods" / "method_code_manifest.json").write_text(
                json.dumps({"verify_command_argv": ["cmd.exe", "/c", "echo", "unsafe"]}),
                encoding="utf-8",
            )
            with self.assertRaises(MethodsGateError):
                verify_methods(project.path)

    def test_cli_verify_and_write_methods(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="CLI method gate", field="workflow engineering")
            prepare_passing_data_gate(project.path)
            output = project.path / "results" / "tables" / "metrics.csv"
            command = f"{sys.executable} -c \"from pathlib import Path; Path(r'{output}').write_text('metric,value\\nf1,0.88\\n', encoding='utf-8')\""

            verify_completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "draftpaper_cli.cli",
                    "verify-methods",
                    "--project",
                    str(project.path),
                    "--command",
                    command,
                    "--output",
                    "results/tables/metrics.csv",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(json.loads(verify_completed.stdout)["status"], "success")

            write_completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "draftpaper_cli.cli",
                    "write-methods",
                    "--project",
                    str(project.path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            payload = json.loads(write_completed.stdout)
            self.assertEqual(payload["status"], "written")
            self.assertTrue(Path(payload["methods"]).exists())

    def test_cli_verify_methods_returns_nonzero_when_gate_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="CLI failed method gate", field="workflow engineering")
            prepare_passing_data_gate(project.path)
            (project.path / "results" / "figure_plan.json").write_text(
                json.dumps({
                    "figures": [
                        {
                            "id": "fig1",
                            "path": "results/figures/generated.png",
                            "generation_mode": "generated_code",
                            "figure_type": "scatter_regression",
                        }
                    ]
                }),
                encoding="utf-8",
            )
            output = project.path / "results" / "tables" / "metrics.csv"
            figure = project.path / "results" / "figures" / "generated.png"
            command = (
                f"{sys.executable} -c \"from pathlib import Path; "
                f"Path(r'{output}').parent.mkdir(parents=True, exist_ok=True); "
                f"Path(r'{output}').write_text('metric,value\\nf1,0.88\\n', encoding='utf-8'); "
                f"Path(r'{figure}').parent.mkdir(parents=True, exist_ok=True); "
                f"Path(r'{figure}').write_bytes(b'fake image')\""
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "draftpaper_cli.cli",
                    "verify-methods",
                    "--project",
                    str(project.path),
                    "--command",
                    command,
                    "--output",
                    "results/tables/metrics.csv",
                    "--output",
                    "results/figures/generated.png",
                ],
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(completed.returncode, 0)
            self.assertEqual(json.loads(completed.stdout)["status"], "failed")

    def test_cli_verify_methods_uses_method_code_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Manifest driven method gate", field="workflow engineering")
            prepare_passing_data_gate(project.path)
            output = project.path / "results" / "tables" / "metrics.csv"
            command = f"{sys.executable} -c \"from pathlib import Path; Path(r'{output}').parent.mkdir(parents=True, exist_ok=True); Path(r'{output}').write_text('metric,value\\nf1,0.88\\n', encoding='utf-8')\""
            (project.path / "methods" / "method_code_manifest.json").write_text(
                json.dumps({
                    "status": "written",
                    "verify_command": command,
                    "declared_outputs": ["results/tables/metrics.csv"],
                    "selected_input_data": "data/raw/sample.csv",
                }),
                encoding="utf-8",
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "draftpaper_cli.cli",
                    "verify-methods",
                    "--project",
                    str(project.path),
                ],
                capture_output=True,
                text=True,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(json.loads(completed.stdout)["status"], "success")

    def test_verify_methods_fails_unsatisfied_main_figure_contract(self) -> None:
        from draftpaper_cli.methods import verify_methods

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Main figure contract gate", field="workflow engineering")
            prepare_passing_data_gate(project.path)
            output = project.path / "results" / "tables" / "metrics.csv"
            command = f"{sys.executable} -c \"from pathlib import Path; Path(r'{output}').parent.mkdir(parents=True, exist_ok=True); Path(r'{output}').write_text('metric,value\\nf1,0.88\\n', encoding='utf-8')\""
            (project.path / "results" / "figure_contracts.json").write_text(
                json.dumps({
                    "contracts": [
                        {
                            "storyboard_id": "fig_expected_main",
                            "figure_id": "fig_expected_main",
                            "path": "results/figures/expected_main.png",
                            "figure_role": "main_result",
                            "allowed_substitute": False,
                        }
                    ]
                }),
                encoding="utf-8",
            )

            result = verify_methods(project.path, command=command, output_files=["results/tables/metrics.csv"])

            self.assertEqual(result["status"], "failed")
            self.assertTrue(result["figure_contract_issues"])
            manifest = json.loads((project.path / "methods" / "run_manifest.yaml").read_text(encoding="utf-8"))
            self.assertEqual(manifest["figure_contract_checks"]["status"], "failed")

    def test_write_methods_excludes_windows_command_text_from_latex(self) -> None:
        from draftpaper_cli.methods import write_methods

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Windows command escaping", field="workflow engineering")
            prepare_passing_data_gate(project.path)
            (project.path / "results" / "tables" / "metrics.csv").write_text("metric,value\nf1,0.88\n", encoding="utf-8")
            (project.path / "methods" / "run_manifest.yaml").write_text(
                json.dumps({
                    "status": "success",
                    "command": r"C:\download\Anaconda\python.exe code\scripts\run_method.py --rate 50%",
                    "input_data": [],
                    "output_files": ["results/tables/metrics.csv"],
                    "metrics": {"f1_score": "0.88"},
                    "figures_generated": [],
                    "tables_generated": ["results/tables/metrics.csv"],
                    "started_at": "2026-05-29T00:00:00Z",
                    "finished_at": "2026-05-29T00:00:01Z",
                }),
                encoding="utf-8",
            )

            write_methods(project.path)

            tex = (project.path / "methods" / "methods.tex").read_text(encoding="utf-8")
            self.assertNotIn("`", tex)
            self.assertNotIn(r"C:\download", tex)
            self.assertNotIn(r"\textbackslash{}", tex)
            self.assertNotIn(r"50\%", tex)
            self.assertNotIn("run_method.py", tex)
            self.assertIn("f1\\_score", tex)

    def test_write_methods_expands_time_aware_classification_formulas_and_sanitizes_internal_terms(self) -> None:
        from draftpaper_cli.methods import verify_methods, write_methods

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Time-aware Transformer classification", field="astronomy machine learning")
            prepare_passing_data_gate(project.path)
            (project.path / "methods" / "method_blueprint.json").write_text(
                json.dumps({
                    "method_code_plan": {
                        "method_families": ["time_aware_transformer", "multimodal_classification"],
                        "validation_checks": ["source_holdout_validation", "ablation_study", "roc_auc"],
                    }
                }),
                encoding="utf-8",
            )
            (project.path / "methods" / "method_code_manifest.json").write_text(
                json.dumps({
                    "files": [
                        {"code_role": "time_aware_transformer_training", "canonical_path": "methods/code_templates/train.py"},
                        {"code_role": "figure_generation", "canonical_path": "methods/code_templates/plot.py"},
                    ],
                    "selected_input_profile": {"columns": ["pha_file", "bkg_pha_file", "arf_file", "rmf_file", "light_curve"]},
                }),
                encoding="utf-8",
            )
            output = project.path / "results" / "tables" / "metrics.csv"
            command = f"{sys.executable} -c \"from pathlib import Path; Path(r'{output}').parent.mkdir(parents=True, exist_ok=True); Path(r'{output}').write_text('metric,value\\nf1_macro,0.82\\nroc_auc,0.91\\n', encoding='utf-8')\""

            verify_methods(project.path, command=command, output_files=["results/tables/metrics.csv"])
            write_methods(project.path)

            formulas = (project.path / "methods" / "method_formulas.tex").read_text(encoding="utf-8")
            tex = (project.path / "methods" / "methods.tex").read_text(encoding="utf-8")
            self.assertIn("Time2Vec", formulas)
            self.assertIn("Cross-entropy", formulas)
            self.assertIn("Macro averaging", formulas)
            self.assertIn("Area under the ROC curve", formulas)
            self.assertIn("\\subsection{Study Design and Input Representation}", tex)
            self.assertIn("\\subsection{Model Formulation}", tex)
            self.assertIn("\\subsection{Validation and Metrics}", tex)
            self.assertIn("source and background spectral products", tex)
            self.assertIn("Here $t$ denotes", tex)
            for token in ["stage-owned", "formula extraction layer", "figure-code trace", "manifest internals", "pha_file", "bkg_pha_file", "arf_file", "rmf_file", "documented method component", "figure generation", "software operations"]:
                self.assertNotIn(token, tex)
            self.assertIn("scientific figure synthesis", tex)
            self.assertNotIn("Auto-generated", tex)
            self.assertNotIn("retained method-oriented references", tex)

    def test_build_method_context_refreshes_stale_formula_manifest_from_project_context(self) -> None:
        from draftpaper_cli.methods import build_method_writing_context, write_methods

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Time-aware Transformer classification of X-ray flaring sources", field="astronomy machine learning")
            prepare_passing_data_gate(project.path)
            output = project.path / "results" / "tables" / "metrics.csv"
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text("metric,value\nf1_macro,0.82\nroc_auc,0.91\n", encoding="utf-8")
            (project.path / "methods" / "run_manifest.yaml").write_text(
                json.dumps({
                    "status": "success",
                    "command": "manual",
                    "input_data": ["data/raw/sample.csv"],
                    "output_files": ["results/tables/metrics.csv"],
                    "metrics": {"f1_macro": "0.82", "roc_auc": "0.91"},
                    "figures_generated": [],
                    "tables_generated": ["results/tables/metrics.csv"],
                }),
                encoding="utf-8",
            )
            (project.path / "methods" / "method_formula_manifest.json").write_text(
                json.dumps({
                    "status": "written",
                    "formula_count": 1,
                    "formulas": [{"id": "old_softmax", "name": "Softmax", "latex": "s=\\mathrm{softmax}(z)"}],
                }),
                encoding="utf-8",
            )
            requirements = json.loads((project.path / "methods" / "method_requirements.json").read_text(encoding="utf-8"))
            requirements["user_method"] = "Build from event_level_samples, current_observation_tokens, history_lc_tokens, and event_spectral_quick_features. Restrict claims to feasible binary classification."
            (project.path / "methods" / "method_requirements.json").write_text(json.dumps(requirements), encoding="utf-8")

            context = build_method_writing_context(project.path)
            write_methods(project.path)

            self.assertGreaterEqual(context["formula_manifest"]["formula_count"], 5)
            formulas = (project.path / "methods" / "method_formulas.tex").read_text(encoding="utf-8")
            tex = (project.path / "methods" / "methods.tex").read_text(encoding="utf-8")
            self.assertIn("Time2Vec", formulas)
            self.assertIn("Cross-entropy", formulas)
            self.assertIn("Area under the ROC curve", formulas)
            self.assertIn("Here $t$ denotes", tex)
            self.assertIn("event-level sample table", tex)
            self.assertIn("current-observation tokens", tex)
            self.assertIn("The model is built from", tex)
            self.assertIn("Claims are restricted to", tex)
            self.assertNotIn("event_level_samples", tex)
            self.assertNotIn("current_observation_tokens", tex)
            self.assertNotIn("Build from", tex)
            self.assertNotIn("Restrict claims to", tex)
            self.assertNotIn("expression(s)", tex)
            self.assertNotIn("verification run", tex.lower())
            self.assertNotIn("data feasibility gate", tex.lower())
            self.assertNotIn("declared metrics", tex.lower())

    def test_verify_methods_fails_generated_png_without_metadata(self) -> None:
        from draftpaper_cli.methods import verify_methods

        with tempfile.TemporaryDirectory() as tmp:
            project = create_project(root=tmp, idea="Generated figure metadata gate", field="workflow engineering")
            prepare_passing_data_gate(project.path)
            (project.path / "results" / "figure_plan.json").write_text(
                json.dumps({
                    "figures": [
                        {
                            "id": "fig1",
                            "path": "results/figures/generated.png",
                            "generation_mode": "generated_code",
                            "figure_type": "scatter_regression",
                        }
                    ]
                }),
                encoding="utf-8",
            )
            output = project.path / "results" / "tables" / "metrics.csv"
            figure = project.path / "results" / "figures" / "generated.png"
            command = (
                f"{sys.executable} -c \"from pathlib import Path; "
                f"Path(r'{output}').parent.mkdir(parents=True, exist_ok=True); "
                f"Path(r'{output}').write_text('metric,value\\nf1,0.88\\n', encoding='utf-8'); "
                f"Path(r'{figure}').parent.mkdir(parents=True, exist_ok=True); "
                f"Path(r'{figure}').write_bytes(b'fake image')\""
            )

            result = verify_methods(
                project.path,
                command=command,
                output_files=["results/tables/metrics.csv", "results/figures/generated.png"],
            )

            self.assertEqual(result["status"], "failed")
            manifest = json.loads((project.path / "methods" / "run_manifest.yaml").read_text(encoding="utf-8"))
            self.assertTrue(manifest["figure_quality_issues"])


if __name__ == "__main__":
    unittest.main()
