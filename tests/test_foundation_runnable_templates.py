# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1] / "draftpaper_cli" / "discipline_modules"


def load_template(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FoundationRunnableTemplateTests(unittest.TestCase):
    def test_finance_event_study_template_runs_on_fixture(self) -> None:
        module = load_template(ROOT / "finance" / "method_templates" / "event_study" / "template.py")
        with tempfile.TemporaryDirectory() as tmp:
            result = module.run_template(
                input_csv=ROOT / "finance" / "method_templates" / "event_study" / "fixture_returns.csv",
                output_dir=Path(tmp),
            )
            self.assertEqual(result["status"], "written")
            self.assertTrue(Path(result["event_window_table"]).exists())

    def test_medicine_cohort_template_runs_on_fixture(self) -> None:
        module = load_template(ROOT / "medicine" / "method_templates" / "cohort_construction" / "template.py")
        with tempfile.TemporaryDirectory() as tmp:
            result = module.run_template(
                input_csv=ROOT / "medicine" / "method_templates" / "cohort_construction" / "fixture_patients.csv",
                output_dir=Path(tmp),
            )
            self.assertEqual(result["status"], "written")
            self.assertGreater(result["included_count"], 0)

    def test_biology_differential_expression_template_runs_on_fixture(self) -> None:
        module = load_template(ROOT / "biology" / "method_templates" / "differential_expression" / "template.py")
        with tempfile.TemporaryDirectory() as tmp:
            result = module.run_template(
                input_csv=ROOT / "biology" / "method_templates" / "differential_expression" / "fixture_expression.csv",
                output_dir=Path(tmp),
            )
            self.assertEqual(result["status"], "written")
            self.assertTrue(Path(result["differential_table"]).exists())

    def test_engineering_signal_template_runs_on_fixture(self) -> None:
        module = load_template(ROOT / "engineering" / "method_templates" / "signal_processing_pipeline" / "template.py")
        with tempfile.TemporaryDirectory() as tmp:
            result = module.run_template(
                input_csv=ROOT / "engineering" / "method_templates" / "signal_processing_pipeline" / "fixture_signal.csv",
                output_dir=Path(tmp),
            )
            self.assertEqual(result["status"], "written")
            self.assertTrue(Path(result["signal_feature_table"]).exists())


if __name__ == "__main__":
    unittest.main()
